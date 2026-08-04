"""Recoverable, domain-neutral canonical decision lifecycle orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, NoReturn

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectReference,
    LifecycleRun,
    LifecycleRunId,
    LifecycleStage,
    StageReceipt,
    require_utc_second,
    validate_lifecycle_object_references,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleHistory,
    LifecycleRunRepository,
    StageFailure,
    StageTransition,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    LifecycleStageHandler,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    TERMINAL_LIFECYCLE_RUN_STATUSES,
    TERMINAL_LIFECYCLE_STAGE_STATUSES,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)


Clock = Callable[[], datetime]
AfterStageHook = Callable[[LifecycleStageName, LifecycleRun], None]


class LifecycleRunnerError(RuntimeError):
    """Base class for lifecycle orchestration errors."""


class LifecycleHandlerRegistrationError(LifecycleRunnerError, ValueError):
    """The registered handler set cannot execute the canonical stage graph."""


class LifecycleRunnerInvariantError(LifecycleRunnerError):
    """The journal or a stage result violates runner invariants."""


class LifecycleStageExecutionError(LifecycleRunnerError):
    """An unexpected stage error, recorded as failure when still mutable."""

    def __init__(
        self,
        *,
        run_id: LifecycleRunId,
        stage_name: LifecycleStageName,
        exception_type: str,
        exception_message: str,
        journal_settled: bool,
    ) -> None:
        self.run_id = run_id
        self.stage_name = stage_name
        self.exception_type = exception_type
        self.exception_message = exception_message
        self.journal_settled = journal_settled
        state = "after durable settlement" if journal_settled else "and was failed"
        super().__init__(
            f"{stage_name.value} {state}: {exception_type}: {exception_message}"
        )


@dataclass(frozen=True, slots=True)
class LifecycleRunResult:
    """Durable journal view returned by one runner invocation."""

    run: LifecycleRun
    stages: tuple[LifecycleStage, ...]
    receipts: tuple[StageReceipt, ...]
    attempted_stages: tuple[LifecycleStageName, ...]
    recovered_stages: tuple[LifecycleStageName, ...]
    stopped_after_stage: LifecycleStageName | None

    def __post_init__(self) -> None:
        run_id = self.run.run_id
        if any(item.run_id != run_id for item in self.stages):
            raise ValueError("result stages must bind the result run")
        if any(item.run_id != run_id for item in self.receipts):
            raise ValueError("result receipts must bind the result run")
        for label, values in (
            ("attempted_stages", self.attempted_stages),
            ("recovered_stages", self.recovered_stages),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(item, LifecycleStageName) for item in values
            ):
                raise TypeError(f"{label} must contain LifecycleStageName values")
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must be unique within one invocation")
        if not set(self.recovered_stages).issubset(self.attempted_stages):
            raise ValueError("recovered stages must have been attempted")
        if self.stopped_after_stage is not None and not isinstance(
            self.stopped_after_stage, LifecycleStageName
        ):
            raise TypeError("stopped_after_stage must be a LifecycleStageName or None")


_RISK_CONTINUATION_START = LifecycleStageName.RISK_REDUCTION
_RISK_CONTINUATION_SKIPPED = LIFECYCLE_STAGE_ORDER[
    : LIFECYCLE_STAGE_ORDER.index(_RISK_CONTINUATION_START)
]
_RUN_TYPE_NOT_APPLICABLE = "RUN_TYPE_NOT_APPLICABLE"
_RISK_CONTINUATION_SKIP_REASON = (
    "RISK_REDUCTION_CONTINUATION starts from existing traced risk authorities"
)


class CanonicalDecisionLifecycleRunner:
    """Sequence stage adapters and atomically journal their verified outcomes."""

    def __init__(
        self,
        *,
        repository: LifecycleRunRepository,
        handlers: tuple[LifecycleStageHandler, ...],
        clock: Clock,
        after_stage_hook: AfterStageHook | None = None,
    ) -> None:
        if not isinstance(handlers, tuple):
            raise TypeError("handlers must be a tuple")
        names = tuple(self._handler_name(handler) for handler in handlers)
        if names != LIFECYCLE_STAGE_ORDER:
            raise LifecycleHandlerRegistrationError(
                "handlers must match the exact canonical lifecycle stage order"
            )
        for handler in handlers:
            # Accessing both attributes up front rejects partially shaped adapters.
            if not isinstance(handler.mutation_kind, StageMutationKind):
                raise LifecycleHandlerRegistrationError(
                    f"{handler.stage_name.value} has an invalid mutation kind"
                )
            if not callable(handler.recover) or not callable(handler.execute):
                raise LifecycleHandlerRegistrationError(
                    f"{handler.stage_name.value} must implement recover and execute"
                )
        if not callable(clock):
            raise TypeError("clock must be callable")
        if after_stage_hook is not None and not callable(after_stage_hook):
            raise TypeError("after_stage_hook must be callable or None")
        self._repository = repository
        self._handlers = dict(zip(names, handlers, strict=True))
        self._clock = clock
        self._after_stage_hook = after_stage_hook

    @staticmethod
    def _handler_name(handler: LifecycleStageHandler) -> LifecycleStageName:
        try:
            name = handler.stage_name
        except AttributeError as exc:
            raise LifecycleHandlerRegistrationError(
                "every handler must declare stage_name"
            ) from exc
        if not isinstance(name, LifecycleStageName):
            raise LifecycleHandlerRegistrationError(
                "handler stage_name must be a LifecycleStageName"
            )
        return name

    def run(self, command: CanonicalLifecycleCommand) -> LifecycleRunResult:
        if not isinstance(command, CanonicalLifecycleCommand):
            raise TypeError("command must be a CanonicalLifecycleCommand")
        if command.is_resume:
            run = self._repository.get_run(command.run_id)
            command.assert_resume_identity(run)
        else:
            run = self._repository.create_or_get(
                command,
                created_at=self._now(),
            )
            if run.status is not LifecycleRunStatus.CREATED:
                history = self._repository.history(run.run_id)
                self._validate_history_shape(history)
                return self._result(
                    history,
                    attempted=(),
                    recovered=(),
                    stopped_after_stage=(
                        command.stop_after_stage
                        if self._is_stop_already_satisfied(
                            history, command.stop_after_stage
                        )
                        else None
                    ),
                )
        return self._continue(
            run,
            initial_references=command.input_references,
            stop_after_stage=command.stop_after_stage,
            allow_failed_resume=command.is_resume,
        )

    def resume(
        self,
        run_id: LifecycleRunId,
        *,
        stop_after_stage: LifecycleStageName | None = None,
    ) -> LifecycleRunResult:
        if not isinstance(run_id, LifecycleRunId):
            raise TypeError("run_id must be a LifecycleRunId")
        if stop_after_stage is not None and not isinstance(
            stop_after_stage, LifecycleStageName
        ):
            raise TypeError("stop_after_stage must be a LifecycleStageName or None")
        command = self._repository.get_command(run_id)
        run = self._repository.get_run(run_id)
        if command.run_id != run.run_id or command.command_hash != run.command_hash:
            raise LifecycleRunnerInvariantError(
                "stored command identity does not match the lifecycle run"
            )
        return self._continue(
            run,
            initial_references=command.input_references,
            stop_after_stage=stop_after_stage,
            allow_failed_resume=True,
        )

    def _continue(
        self,
        run: LifecycleRun,
        *,
        initial_references: tuple[LifecycleObjectReference, ...],
        stop_after_stage: LifecycleStageName | None,
        allow_failed_resume: bool,
    ) -> LifecycleRunResult:
        validate_lifecycle_object_references(
            "initial_references", initial_references
        )
        history = self._repository.history(run.run_id)
        self._validate_history_shape(history)
        run = history.run
        if self._is_stop_already_satisfied(history, stop_after_stage):
            return self._result(
                history,
                attempted=(),
                recovered=(),
                stopped_after_stage=stop_after_stage,
            )
        if run.status in TERMINAL_LIFECYCLE_RUN_STATUSES:
            return self._result(
                history,
                attempted=(),
                recovered=(),
                stopped_after_stage=None,
            )
        if run.status is LifecycleRunStatus.FAILED and not allow_failed_resume:
            return self._result(
                history,
                attempted=(),
                recovered=(),
                stopped_after_stage=None,
            )
        claimed = self._claim(run, allow_failed_resume=allow_failed_resume)
        attempted: list[LifecycleStageName] = []
        recovered: list[LifecycleStageName] = []
        while claimed.status is LifecycleRunStatus.RUNNING:
            history = self._repository.history(claimed.run_id)
            self._validate_history_shape(history)
            stage = self._next_stage(history)
            if stage is None:
                raise LifecycleRunnerInvariantError(
                    "all stages are settled but the run is not terminal"
                )
            stage_name = stage.stage_name
            attempted.append(stage_name)
            if self._should_skip(history.run.run_type, stage_name):
                claimed = self._settle_stage(
                    history,
                    stage,
                    result=StageExecutionResult(
                        stage_status=(
                            LifecycleStageStatus.SKIPPED_NOT_APPLICABLE
                        ),
                        run_status=LifecycleRunStatus.RUNNING,
                        input_references=initial_references,
                        output_references=(),
                        model_versions=(),
                        configuration_hashes=(),
                        reason_codes=(_RUN_TYPE_NOT_APPLICABLE,),
                        blocker_reason=_RISK_CONTINUATION_SKIP_REASON,
                    ),
                    initial_references=initial_references,
                    handler=None,
                    recovered_stages=recovered,
                )
            else:
                claimed = self._settle_stage(
                    history,
                    stage,
                    result=None,
                    initial_references=initial_references,
                    handler=self._handlers[stage_name],
                    recovered_stages=recovered,
                )
            if stop_after_stage is stage_name:
                return self._result(
                    self._repository.history(claimed.run_id),
                    attempted=tuple(attempted),
                    recovered=tuple(recovered),
                    stopped_after_stage=stage_name,
                )
            if claimed.status is not LifecycleRunStatus.RUNNING:
                break
        return self._result(
            self._repository.history(claimed.run_id),
            attempted=tuple(attempted),
            recovered=tuple(recovered),
            stopped_after_stage=None,
        )

    def _claim(
        self,
        run: LifecycleRun,
        *,
        allow_failed_resume: bool,
    ) -> LifecycleRun:
        if run.status is LifecycleRunStatus.FAILED:
            if not allow_failed_resume:
                raise LifecycleRunnerInvariantError(
                    "failed runs require an explicit resume operation"
                )
            return self._repository.resume(run.run_id, resumed_at=self._now())
        if run.status in {
            LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
            LifecycleRunStatus.COMPLETED,
        }:
            return run
        if run.status is LifecycleRunStatus.RETRYING:
            raise LifecycleRunnerInvariantError(
                "RETRYING must be resolved atomically by the repository"
            )
        return self._repository.claim(
            run.run_id,
            expected_version=run.version,
            claimed_at=self._now(),
        )

    def _settle_stage(
        self,
        history: LifecycleHistory,
        stage: LifecycleStage,
        *,
        result: StageExecutionResult | None,
        initial_references: tuple[LifecycleObjectReference, ...],
        handler: LifecycleStageHandler | None,
        recovered_stages: list[LifecycleStageName],
    ) -> LifecycleRun:
        attempt = self._repository.start_stage(
            history.run.run_id,
            stage.stage_name,
            started_at=self._now(),
            claim_token=history.run.claim_token,
        )
        running_history = self._repository.history(history.run.run_id)
        running_stage = self._stage(running_history, stage.stage_name)
        context = LifecycleStageContext(
            run=running_history.run,
            stage=running_stage,
            attempt=attempt,
            prior_stages=running_history.stages[
                : LIFECYCLE_STAGE_ORDER.index(stage.stage_name)
            ],
            initial_references=initial_references,
        )
        if result is None:
            if handler is None:
                raise LifecycleRunnerInvariantError("active stage requires a handler")
            try:
                recovered_result = handler.recover(context)
                if recovered_result is None:
                    result = handler.execute(context)
                else:
                    result = recovered_result
                    recovered_stages.append(stage.stage_name)
                if not isinstance(result, StageExecutionResult):
                    raise TypeError("stage handler must return StageExecutionResult")
            except Exception as exc:
                self._fail_stage(context, exc)
        assert result is not None
        try:
            self._validate_result(result, context)
            completed_at = self._now()
            receipt = StageReceipt.create(
                run_id=running_history.run.run_id,
                stage_name=stage.stage_name,
                attempt_number=attempt.attempt_number,
                input_hashes=tuple(
                    sorted(item.content_hash for item in result.input_references)
                ),
                output_hashes=tuple(
                    sorted(item.content_hash for item in result.output_references)
                ),
                model_versions=result.receipt_model_versions,
                configuration_hashes=result.configuration_hashes,
                reason_codes=result.reason_codes,
                stage_result=result.stage_status,
                created_at=completed_at,
            )
            transition = StageTransition(
                run_id=running_history.run.run_id,
                stage_name=stage.stage_name,
                attempt_id=attempt.attempt_id,
                expected_run_version=running_history.run.version,
                expected_stage_version=running_stage.version,
                claim_token=running_history.run.claim_token,
                target_run_status=result.run_status,
                receipt=receipt,
                input_references=result.input_references,
                output_references=result.output_references,
                blocker_reason=result.blocker_reason,
                completed_at=completed_at,
            )
        except Exception as exc:
            self._fail_stage(context, exc)
        try:
            settled_run = self._repository.finish_stage(transition)
        except Exception as exc:
            if self._receipt_is_durable(transition):
                self._raise_stage_error(context, exc, journal_settled=True)
            self._fail_stage(context, exc)
        if self._after_stage_hook is not None:
            try:
                self._after_stage_hook(stage.stage_name, settled_run)
            except Exception as exc:
                self._raise_stage_error(context, exc, journal_settled=True)
        return settled_run

    def _validate_result(
        self,
        result: StageExecutionResult,
        context: LifecycleStageContext,
    ) -> None:
        final_stage = context.stage_name is LIFECYCLE_STAGE_ORDER[-1]
        if final_stage and result.run_status is not LifecycleRunStatus.COMPLETED:
            raise LifecycleRunnerInvariantError(
                "OUTCOME_REVIEW must complete the lifecycle run"
            )
        if not final_stage and result.run_status is LifecycleRunStatus.COMPLETED:
            raise LifecycleRunnerInvariantError(
                "only OUTCOME_REVIEW may complete the lifecycle run"
            )
        observed_at = self._now()
        for reference in (*result.input_references, *result.output_references):
            if reference.available_at > observed_at:
                raise LifecycleRunnerInvariantError(
                    "stage reference has a future availability time"
                )
        allowed_inputs = {
            reference.sort_key: reference
            for reference in self._default_inputs(context)
        }
        for reference in result.input_references:
            if allowed_inputs.get(reference.sort_key) != reference:
                raise LifecycleRunnerInvariantError(
                    "stage input is not traceable to initial or upstream references"
                )
        allowed_models = {
            (str(reference.model_id), reference.model_version)
            for reference in context.run.model_references
        }
        if not set(result.model_versions).issubset(allowed_models):
            raise LifecycleRunnerInvariantError(
                "stage result uses an undeclared model version"
            )
        allowed_configurations = {
            reference.content_hash
            for reference in context.run.configuration_references
        }
        if not set(result.configuration_hashes).issubset(allowed_configurations):
            raise LifecycleRunnerInvariantError(
                "stage result uses an undeclared configuration hash"
            )

    def _fail_stage(
        self,
        context: LifecycleStageContext,
        exc: Exception,
    ) -> NoReturn:
        current_run = self._repository.get_run(context.run.run_id)
        current_stage = self._repository.get_stage(
            context.run.run_id, context.stage.stage_name
        )
        if current_stage is None:
            raise LifecycleRunnerInvariantError("running stage disappeared") from exc
        failure = StageFailure(
            run_id=current_run.run_id,
            stage_name=current_stage.stage_name,
            attempt_id=context.attempt.attempt_id,
            expected_run_version=current_run.version,
            expected_stage_version=current_stage.version,
            claim_token=current_run.claim_token,
            input_references=self._default_inputs(context),
            exception_type=type(exc).__name__,
            exception_message=str(exc) or repr(exc),
            failed_at=self._now(),
        )
        try:
            self._repository.mark_stage_failed(failure)
        except Exception as journal_exc:
            self._raise_stage_error(context, journal_exc, journal_settled=False)
        self._raise_stage_error(context, exc, journal_settled=False)

    @staticmethod
    def _raise_stage_error(
        context: LifecycleStageContext,
        exc: Exception,
        *,
        journal_settled: bool,
    ) -> NoReturn:
        raise LifecycleStageExecutionError(
            run_id=context.run.run_id,
            stage_name=context.stage.stage_name,
            exception_type=type(exc).__name__,
            exception_message=str(exc) or repr(exc),
            journal_settled=journal_settled,
        ) from exc

    def _receipt_is_durable(self, transition: StageTransition) -> bool:
        try:
            history = self._repository.history(transition.run_id)
        except Exception:
            return False
        stage = self._stage(history, transition.stage_name)
        matching = tuple(
            receipt
            for receipt in history.receipts
            if receipt.stage_name is transition.stage_name
            and receipt.receipt_id == transition.receipt.receipt_id
            and receipt.receipt_hash == transition.receipt.receipt_hash
        )
        return stage.stage_status in TERMINAL_LIFECYCLE_STAGE_STATUSES and len(
            matching
        ) == 1

    @staticmethod
    def _default_inputs(
        context: LifecycleStageContext,
    ) -> tuple[LifecycleObjectReference, ...]:
        references: dict[tuple[str, str, str], LifecycleObjectReference] = {}
        for reference in (
            *context.initial_references,
            *context.upstream_references,
        ):
            existing = references.setdefault(reference.sort_key, reference)
            if existing != reference:
                raise LifecycleRunnerInvariantError(
                    "stage context carries conflicting input references"
                )
        result = tuple(sorted(references.values(), key=lambda item: item.sort_key))
        validate_lifecycle_object_references("failure inputs", result)
        return result

    @staticmethod
    def _should_skip(
        run_type: LifecycleRunType,
        stage_name: LifecycleStageName,
    ) -> bool:
        return (
            run_type is LifecycleRunType.RISK_REDUCTION_CONTINUATION
            and stage_name in _RISK_CONTINUATION_SKIPPED
        )

    @staticmethod
    def _next_stage(history: LifecycleHistory) -> LifecycleStage | None:
        for stage in history.stages:
            if stage.stage_status not in TERMINAL_LIFECYCLE_STAGE_STATUSES:
                return stage
        return None

    @staticmethod
    def _stage(
        history: LifecycleHistory,
        stage_name: LifecycleStageName,
    ) -> LifecycleStage:
        matches = tuple(
            stage for stage in history.stages if stage.stage_name is stage_name
        )
        if len(matches) != 1:
            raise LifecycleRunnerInvariantError(
                f"journal must contain exactly one {stage_name.value} stage"
            )
        return matches[0]

    @staticmethod
    def _validate_history_shape(history: LifecycleHistory) -> None:
        if tuple(stage.stage_name for stage in history.stages) != LIFECYCLE_STAGE_ORDER:
            raise LifecycleRunnerInvariantError(
                "journal stages must match the exact canonical stage order"
            )

    @staticmethod
    def _is_stop_already_satisfied(
        history: LifecycleHistory,
        stop_after_stage: LifecycleStageName | None,
    ) -> bool:
        if stop_after_stage is None:
            return False
        stage = CanonicalDecisionLifecycleRunner._stage(history, stop_after_stage)
        return stage.stage_status in TERMINAL_LIFECYCLE_STAGE_STATUSES or (
            stage.stage_status is LifecycleStageStatus.WAITING
        )

    @staticmethod
    def _result(
        history: LifecycleHistory,
        *,
        attempted: tuple[LifecycleStageName, ...],
        recovered: tuple[LifecycleStageName, ...],
        stopped_after_stage: LifecycleStageName | None,
    ) -> LifecycleRunResult:
        return LifecycleRunResult(
            run=history.run,
            stages=history.stages,
            receipts=history.receipts,
            attempted_stages=attempted,
            recovered_stages=recovered,
            stopped_after_stage=stopped_after_stage,
        )

    def _now(self) -> datetime:
        value = self._clock()
        require_utc_second("clock", value)
        return value
