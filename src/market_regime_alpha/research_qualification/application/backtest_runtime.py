"""Runtime-backed execution of dependency-ready generic Backtest actions."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid5

from market_regime_alpha.research_qualification.application.backtests import (
    BacktestApplication,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    FrozenBacktestRun,
    FrozenBacktestSource,
    freeze_backtest_specification,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestExpectedAction,
    BacktestNextOperation,
    BacktestRuntimeBinding,
)
from market_regime_alpha.research_qualification.errors import (
    BacktestExecutionIntegrityError,
)
from market_regime_alpha.research_qualification.ports.backtest_runtime import (
    BacktestCanonicalStepHandler,
    BacktestSpecificationReadPort,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    CommandContext,
    RuntimeApplication,
)
from market_regime_alpha.runtime.domain import (
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepDependency,
    StepSpec,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


_IMPLEMENTATION = (
    "market_regime_alpha.research_qualification.application."
    "backtest_runtime:BacktestRuntimeActionExecutor"
)


class BacktestRuntimeActionExecutor:
    """Map one frozen action to one canonical Runtime DAG and fenced attempts."""

    def __init__(
        self,
        *,
        runtime: RuntimeApplication,
        backtests: BacktestApplication,
        specifications: BacktestSpecificationReadPort,
        handler: BacktestCanonicalStepHandler,
        worker_id: str,
        lease_duration: timedelta = timedelta(minutes=10),
    ) -> None:
        if not worker_id:
            raise ValueError("Backtest worker_id is required")
        if lease_duration <= timedelta(0):
            raise ValueError("Backtest lease_duration must be positive")
        self._runtime = runtime
        self._backtests = backtests
        self._specifications = specifications
        self._handler = handler
        self._worker_id = worker_id
        self._lease_duration = lease_duration

    def execute(
        self,
        run: FrozenBacktestRun,
        action: BacktestExpectedAction,
        operation: BacktestNextOperation,
    ) -> None:
        if run.source is not FrozenBacktestSource.CURRENT_RELATIONAL:
            raise ValueError("Backtest execution requires a current relational specification")
        if action.exploratory_backtest_run_id != run.exploratory_backtest_run_id:
            raise BacktestExecutionIntegrityError("Backtest action belongs to another run")
        specification = self._specifications.load_specification(
            run.exploratory_backtest_run_id
        )
        reloaded = freeze_backtest_specification(specification)
        if (
            reloaded.projection_sha256 != run.projection_sha256
            or reloaded.specification_sha256 != run.specification_sha256
        ):
            raise BacktestExecutionIntegrityError(
                "Backtest runtime projection differs from relational Authority"
            )
        runtime_run_id = uuid5(action.action_id, "runtime-run")
        if operation is BacktestNextOperation.EXECUTE:
            self._predeclare_runtime(specification, run, action, runtime_run_id)
        elif operation is BacktestNextOperation.RECOVER:
            self._runtime.recover_expired(
                actor_id=self._worker_id,
                reason_code="BACKTEST_EXECUTION_RECOVERY",
            )
        elif operation is not BacktestNextOperation.RETRY:
            raise AssertionError(f"unsupported Backtest operation {operation}")
        self._drive_runtime(specification, action, runtime_run_id)

    def _predeclare_runtime(
        self,
        specification,
        run: FrozenBacktestRun,
        action: BacktestExpectedAction,
        runtime_run_id: UUID,
    ) -> None:
        planned = self._handler.steps(specification, action)
        if not planned or len({item.step_key for item in planned}) != len(planned):
            raise BacktestExecutionIntegrityError(
                "Backtest action Runtime step roster must be non-empty and unique"
            )
        schedule_id = uuid5(action.action_id, "runtime-schedule")
        step_specs = tuple(
            StepSpec(
                step_key=item.step_key,
                step_kind=item.step_kind,
                implementation=_IMPLEMENTATION,
                implementation_version="1",
                ordinal=ordinal,
                required=True,
                request_hash=str(item.request_sha256),
                input_evidence_hash=str(run.specification_sha256),
                retry_policy=RetryPolicy(
                    3,
                    (timedelta(0), timedelta(0)),
                    frozenset({"BACKTEST_ACTION_RETRYABLE"}),
                ),
                external_effect_class=item.external_effect_class,
            )
            for ordinal, item in enumerate(planned, start=1)
        )
        dependencies = tuple(
            StepDependency(previous.step_key, current.step_key)
            for previous, current in zip(step_specs, step_specs[1:])
        )
        catalog_hash = canonical_json_sha256(
            tuple(
                (item.step_key, item.step_kind, item.request_hash)
                for item in step_specs
            )
        )
        self._runtime.create_schedule(
            ScheduleSpec(
                schedule_id=schedule_id,
                schedule_code=f"backtest-{action.action_id}",
                revision=1,
                runtime_mode=RuntimeMode.HISTORICAL,
                schedule_expression=None,
                timezone_name="Asia/Shanghai",
                step_catalog_hash=catalog_hash,
                enabled=True,
            ),
            self._context(action, "schedule"),
        )
        self._runtime.schedule_run(
            RunSpec(
                run_id=runtime_run_id,
                schedule_id=schedule_id,
                fire_key=str(action.action_id),
                runtime_mode=RuntimeMode.HISTORICAL,
                requested_at=self._handler.requested_at(specification, action),
                decision_time=self._handler.decision_time(specification, action),
                code_sha=str(specification.code_artifact.content_sha256),
                config_artifact_id=specification.config_artifact.artifact_id,
                config_hash=str(specification.config_artifact.content_sha256),
            ),
            step_specs,
            dependencies,
            self._context(action, "run"),
        )
        binding = BacktestRuntimeBinding(
            backtest_runtime_binding_id=uuid5(action.action_id, "runtime-binding"),
            exploratory_backtest_run_id=run.exploratory_backtest_run_id,
            specification_sha256=run.specification_sha256,
            action=action,
            runtime_run_id=runtime_run_id,
        )
        self._backtests.bind_runtime(
            binding,
            self._context(action, "binding"),
        )

    def _drive_runtime(
        self,
        specification,
        action: BacktestExpectedAction,
        runtime_run_id: UUID,
    ) -> None:
        trace = self._runtime.inspect_run(runtime_run_id)
        if trace.run_state == "QUEUED":
            self._runtime.start_run(
                runtime_run_id,
                self._context(action, "start"),
            )
        maximum_claims = sum(
            max(1, 3 - len(step.attempt_states)) for step in trace.steps
        )
        for _ in range(maximum_claims + 1):
            trace = self._runtime.inspect_run(runtime_run_id)
            if trace.run_state in {
                "SUCCEEDED",
                "FAILED",
                "BLOCKED",
                "CANCELLED",
            }:
                return
            ready = next((step for step in trace.steps if step.state == "READY"), None)
            if ready is None:
                return
            next_attempt = len(ready.attempt_states) + 1
            claim = self._runtime.claim_next(
                run_id=runtime_run_id,
                worker_id=self._worker_id,
                lease_duration=self._lease_duration,
                context=self._context(
                    action,
                    f"claim-{ready.step_key}-{next_attempt}",
                ),
            )
            if claim is None:
                return
            if claim.run_id != runtime_run_id or claim.step_key != ready.step_key:
                raise BacktestExecutionIntegrityError(
                    "Runtime returned a different Backtest action Step"
                )
            self._runtime.start_attempt(
                claim,
                self._context(action, f"attempt-{claim.attempt_id}"),
            )
            try:
                self._handler.execute_step(specification, action, claim)
            except Exception:
                current = self._runtime.inspect_run(runtime_run_id)
                current_step = next(
                    step for step in current.steps if step.step_id == claim.step_id
                )
                if current_step.state == "RUNNING":
                    self._runtime.fail_attempt(
                        claim,
                        error_class="BACKTEST",
                        error_code="BACKTEST_ACTION_FAILED",
                        context=self._context(
                            action,
                            f"failed-{claim.attempt_id}",
                        ),
                    )
                raise
            current = self._runtime.inspect_run(runtime_run_id)
            current_step = next(
                step for step in current.steps if step.step_id == claim.step_id
            )
            if current_step.state in {"READY", "WAITING", "FAILED"}:
                return
            if current_step.state != "SUCCEEDED":
                raise BacktestExecutionIntegrityError(
                    "Backtest canonical Step returned without finalizing its Runtime Attempt"
                )
        raise BacktestExecutionIntegrityError(
            "Backtest action exceeded its frozen Runtime attempt budget"
        )

    def _context(
        self,
        action: BacktestExpectedAction,
        suffix: str,
    ) -> CommandContext:
        return CommandContext(
            idempotency_key=f"backtest:{action.action_id}:{suffix}",
            actor_type=ActorType.WORKER,
            actor_id=self._worker_id,
            reason_code="BACKTEST_EXECUTION",
        )


__all__ = ["BacktestRuntimeActionExecutor"]
