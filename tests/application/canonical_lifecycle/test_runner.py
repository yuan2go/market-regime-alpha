from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pytest

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationKind,
    LifecycleConfigurationReference,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    CanonicalDecisionLifecycleRunner,
    LifecycleHandlerRegistrationError,
    LifecycleStageExecutionError,
)
from tests.postgres_path_repositories import (
    PostgresLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.core.identity import ArtifactId


UTC = timezone.utc
AS_OF = datetime(2026, 8, 4, 6, 55, tzinfo=UTC)


def _hash(number: int) -> str:
    return f"sha256:{number:064x}"


class TickClock:
    def __init__(self) -> None:
        self.value = AS_OF

    def __call__(self) -> datetime:
        self.value += timedelta(seconds=1)
        return self.value


def _reference(
    object_type: LifecycleObjectType,
    reader_kind: LifecycleReaderKind,
    number: int,
    *,
    locator: str | None,
) -> LifecycleObjectReference:
    return LifecycleObjectReference(
        object_type=object_type,
        object_id=LifecycleObjectId(f"object-{number}"),
        content_hash=_hash(number),
        reader_kind=reader_kind,
        locator=locator,
        available_at=AS_OF,
    )


def _canonical_inputs() -> tuple[LifecycleObjectReference, ...]:
    return tuple(
        sorted(
            (
                _reference(
                    LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
                    LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER,
                    1,
                    locator="artifacts/composite",
                ),
                _reference(
                    LifecycleObjectType.SOURCE_MANIFEST,
                    LifecycleReaderKind.SOURCE_MANIFEST_READER,
                    2,
                    locator="artifacts/source",
                ),
            ),
            key=lambda item: item.sort_key,
        )
    )


def _command(
    *,
    stop_after_stage: LifecycleStageName | None = None,
    idempotency_key: str = "runner-command",
) -> CanonicalLifecycleCommand:
    return CanonicalLifecycleCommand(
        run_type=LifecycleRunType.CANONICAL_DECISION_LIFECYCLE,
        decision_date=date(2026, 8, 4),
        as_of_time=AS_OF,
        idempotency_key=idempotency_key,
        input_manifest_id=ArtifactId("lifecycle-input-1"),
        input_content_hash=_hash(3),
        input_manifest_locator=Path("artifacts/lifecycle-input-1.json"),
        input_references=_canonical_inputs(),
        configuration_references=(
            LifecycleConfigurationReference(
                configuration_kind=LifecycleConfigurationKind.GENERIC,
                configuration_id=ArtifactId("runner-config"),
                configuration_version="1",
                content_hash=_hash(4),
                locator="configurations/runner-config.json",
            ),
        ),
        model_references=(),
        stop_after_stage=stop_after_stage,
        output_directory=Path("artifacts/lifecycle-tests"),
    )


def _risk_inputs() -> tuple[LifecycleObjectReference, ...]:
    specifications = (
        (
            LifecycleObjectType.RISK_REDUCING_DECISION,
            LifecycleReaderKind.RISK_REDUCTION_REPOSITORY,
            None,
        ),
        (
            LifecycleObjectType.POSITION_BOOK,
            LifecycleReaderKind.POSITION_BOOK_REPOSITORY,
            None,
        ),
        (
            LifecycleObjectType.OPERATIONAL_EXIT_DIRECTIVE,
            LifecycleReaderKind.OPERATIONAL_EXIT_DIRECTIVE_REPOSITORY,
            None,
        ),
        (
            LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
            LifecycleReaderKind.TRADING_CALENDAR_ARTIFACT_READER,
            "artifacts/calendar",
        ),
        (
            LifecycleObjectType.THESIS_HEALTH_OBSERVATION,
            LifecycleReaderKind.THESIS_HEALTH_REPOSITORY,
            None,
        ),
        (
            LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
            LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER,
            "artifacts/composite-risk",
        ),
        (
            LifecycleObjectType.REDUCING_EXECUTION_OBSERVATION,
            LifecycleReaderKind.REDUCING_EXECUTION_OBSERVATION_READER,
            "artifacts/reducing-observation.json",
        ),
        (
            LifecycleObjectType.SYMBOL_TRADING_SESSION_STATUS_SET,
            LifecycleReaderKind.SYMBOL_TRADING_SESSION_STATUS_READER,
            "artifacts/session-status.json",
        ),
        (
            LifecycleObjectType.RISK_REDUCTION_CONFIRMATION_POLICY,
            LifecycleReaderKind.RISK_REDUCTION_CONFIRMATION_POLICY_READER,
            "artifacts/confirmation-policy.json",
        ),
    )
    return tuple(
        sorted(
            (
                _reference(object_type, reader_kind, 20 + index, locator=locator)
                for index, (object_type, reader_kind, locator) in enumerate(
                    specifications
                )
            ),
            key=lambda item: item.sort_key,
        )
    )


def _risk_command() -> CanonicalLifecycleCommand:
    return CanonicalLifecycleCommand(
        run_type=LifecycleRunType.RISK_REDUCTION_CONTINUATION,
        decision_date=date(2026, 8, 4),
        as_of_time=AS_OF,
        idempotency_key="runner-risk-command",
        input_manifest_id=None,
        input_content_hash=None,
        input_manifest_locator=None,
        input_references=_risk_inputs(),
        configuration_references=(),
        model_references=(),
        stop_after_stage=LifecycleStageName.RISK_REDUCTION,
        output_directory=Path("artifacts/lifecycle-tests"),
    )


ResultFactory = Callable[[LifecycleStageContext], StageExecutionResult]


@dataclass
class RecordingHandler:
    stage_name: LifecycleStageName
    calls: list[tuple[str, LifecycleStageName]]
    result_factory: ResultFactory | None = None
    mutation_kind: StageMutationKind = StageMutationKind.PURE
    recover_calls: int = 0
    execute_calls: int = 0

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        assert context.stage_name is self.stage_name
        self.recover_calls += 1
        self.calls.append(("recover", self.stage_name))
        return None

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        self.execute_calls += 1
        self.calls.append(("execute", self.stage_name))
        if self.result_factory is not None:
            return self.result_factory(context)
        return _completed_result(context)


def _completed_result(context: LifecycleStageContext) -> StageExecutionResult:
    index = LIFECYCLE_STAGE_ORDER.index(context.stage_name)
    output = _reference(
        LifecycleObjectType.FEATURE_ARTIFACT,
        LifecycleReaderKind.FEATURE_ARTIFACT_READER,
        100 + index,
        locator=f"artifacts/stage-{index}",
    )
    return StageExecutionResult(
        stage_status=LifecycleStageStatus.COMPLETED,
        run_status=(
            LifecycleRunStatus.COMPLETED
            if context.stage_name is LIFECYCLE_STAGE_ORDER[-1]
            else LifecycleRunStatus.RUNNING
        ),
        input_references=(
            context.initial_references
            if context.stage_name is LIFECYCLE_STAGE_ORDER[0]
            else context.upstream_references
        ),
        output_references=(output,),
        model_versions=(),
        configuration_hashes=tuple(
            sorted(item.content_hash for item in context.run.configuration_references)
        ),
        reason_codes=("STAGE_COMPLETED",),
        blocker_reason=None,
    )


def _handlers(
    calls: list[tuple[str, LifecycleStageName]],
    *,
    overrides: dict[LifecycleStageName, ResultFactory] | None = None,
) -> tuple[RecordingHandler, ...]:
    configured = overrides or {}
    return tuple(
        RecordingHandler(
            stage_name=stage,
            calls=calls,
            result_factory=configured.get(stage),
        )
        for stage in LIFECYCLE_STAGE_ORDER
    )


def _runner(
    tmp_path: Path,
    handlers: tuple[RecordingHandler, ...],
    *,
    clock: TickClock | None = None,
) -> CanonicalDecisionLifecycleRunner:
    return CanonicalDecisionLifecycleRunner(
        repository=PostgresLifecycleRunRepository(tmp_path / "journal.postgres-scope"),
        handlers=handlers,
        clock=clock or TickClock(),
    )


def test_runner_requires_exact_complete_handler_order(tmp_path: Path) -> None:
    calls: list[tuple[str, LifecycleStageName]] = []
    handlers = _handlers(calls)
    with pytest.raises(LifecycleHandlerRegistrationError, match="exact"):
        _runner(tmp_path, handlers[:-1])
    with pytest.raises(LifecycleHandlerRegistrationError, match="exact"):
        _runner(tmp_path, (handlers[1], handlers[0], *handlers[2:]))
    with pytest.raises(LifecycleHandlerRegistrationError, match="exact"):
        _runner(tmp_path, (*handlers[:-1], handlers[0]))


def test_runner_executes_exact_stage_order_and_completes(tmp_path: Path) -> None:
    calls: list[tuple[str, LifecycleStageName]] = []
    handlers = _handlers(calls)

    result = _runner(tmp_path, handlers).run(_command())

    assert result.run.status is LifecycleRunStatus.COMPLETED
    assert result.attempted_stages == LIFECYCLE_STAGE_ORDER
    assert result.recovered_stages == ()
    assert tuple(stage.stage_name for stage in result.stages) == LIFECYCLE_STAGE_ORDER
    assert all(
        stage.stage_status is LifecycleStageStatus.COMPLETED
        for stage in result.stages
    )
    assert tuple(stage for operation, stage in calls if operation == "execute") == (
        LIFECYCLE_STAGE_ORDER
    )
    assert len(result.receipts) == len(LIFECYCLE_STAGE_ORDER)


def test_runner_stops_after_settled_control_stage(tmp_path: Path) -> None:
    calls: list[tuple[str, LifecycleStageName]] = []
    handlers = _handlers(calls)
    stop = LifecycleStageName.PATH_FORECAST

    result = _runner(tmp_path, handlers).run(_command(stop_after_stage=stop))

    expected = LIFECYCLE_STAGE_ORDER[: LIFECYCLE_STAGE_ORDER.index(stop) + 1]
    assert result.run.status is LifecycleRunStatus.RUNNING
    assert result.attempted_stages == expected
    assert result.stopped_after_stage is stop
    assert tuple(stage for operation, stage in calls if operation == "execute") == expected
    assert all(
        result.stages[index].stage_status is LifecycleStageStatus.PENDING
        for index in range(len(expected), len(result.stages))
    )
    execute_count = sum(operation == "execute" for operation, _stage in calls)
    replay = _runner(tmp_path, handlers).run(_command(stop_after_stage=stop))
    assert replay.run == result.run
    assert replay.attempted_stages == ()
    assert replay.stopped_after_stage is stop
    assert sum(operation == "execute" for operation, _stage in calls) == execute_count


def test_waiting_and_blocked_results_stop_without_later_handler(tmp_path: Path) -> None:
    def waiting(context: LifecycleStageContext) -> StageExecutionResult:
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.WAITING,
            run_status=LifecycleRunStatus.WAITING_FOR_ENTRY_CONFIRMATION,
            input_references=context.upstream_references,
            output_references=(),
            model_versions=(),
            configuration_hashes=(),
            reason_codes=("ENTRY_CONFIRMATION_MISSING",),
            blocker_reason="entry confirmation has not been observed",
        )

    calls: list[tuple[str, LifecycleStageName]] = []
    handlers = _handlers(
        calls,
        overrides={LifecycleStageName.SIGNAL: waiting},
    )
    result = _runner(tmp_path, handlers).run(_command())
    executed = tuple(stage for operation, stage in calls if operation == "execute")
    assert result.run.status is LifecycleRunStatus.WAITING_FOR_ENTRY_CONFIRMATION
    assert executed == LIFECYCLE_STAGE_ORDER[:3]
    assert LifecycleStageName.PATH_FORECAST not in executed

    def blocked(context: LifecycleStageContext) -> StageExecutionResult:
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.BLOCKED,
            run_status=LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
            input_references=context.upstream_references,
            output_references=(),
            model_versions=(),
            configuration_hashes=(),
            reason_codes=("MODEL_NOT_VALIDATED",),
            blocker_reason="entry model validation is unavailable",
        )

    blocked_calls: list[tuple[str, LifecycleStageName]] = []
    blocked_handlers = _handlers(
        blocked_calls,
        overrides={LifecycleStageName.SIGNAL: blocked},
    )
    blocked_result = _runner(
        tmp_path / "blocked", blocked_handlers
    ).run(_command(idempotency_key="blocked-command"))
    assert blocked_result.run.status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    assert tuple(
        stage for operation, stage in blocked_calls if operation == "execute"
    ) == LIFECYCLE_STAGE_ORDER[:3]


def test_risk_continuation_journals_explicit_not_applicable_prefix(
    tmp_path: Path,
) -> None:
    def risk_result(context: LifecycleStageContext) -> StageExecutionResult:
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=context.initial_references,
            output_references=(),
            model_versions=(),
            configuration_hashes=(),
            reason_codes=("RISK_DECISION_LOADED",),
            blocker_reason=None,
        )

    calls: list[tuple[str, LifecycleStageName]] = []
    handlers = _handlers(
        calls,
        overrides={LifecycleStageName.RISK_REDUCTION: risk_result},
    )
    result = _runner(tmp_path, handlers).run(_risk_command())
    prefix_length = LIFECYCLE_STAGE_ORDER.index(LifecycleStageName.RISK_REDUCTION)

    assert result.stopped_after_stage is LifecycleStageName.RISK_REDUCTION
    assert result.attempted_stages == LIFECYCLE_STAGE_ORDER[: prefix_length + 1]
    assert all(
        stage.stage_status is LifecycleStageStatus.SKIPPED_NOT_APPLICABLE
        for stage in result.stages[:prefix_length]
    )
    assert all(handler.execute_calls == 0 for handler in handlers[:prefix_length])
    assert handlers[prefix_length].execute_calls == 1
    skipped_receipts = tuple(
        receipt
        for receipt in result.receipts
        if receipt.stage_result is LifecycleStageStatus.SKIPPED_NOT_APPLICABLE
    )
    assert len(skipped_receipts) == prefix_length
    expected_hashes = tuple(
        sorted(reference.content_hash for reference in _risk_inputs())
    )
    assert all(receipt.input_hashes == expected_hashes for receipt in skipped_receipts)
    assert all(
        receipt.reason_codes == ("RUN_TYPE_NOT_APPLICABLE",)
        for receipt in skipped_receipts
    )


@pytest.mark.parametrize(
    "run_status",
    (
        LifecycleRunStatus.POSITION_OPEN,
        LifecycleRunStatus.READY_FOR_HOLDING_ASSESSMENT,
        LifecycleRunStatus.READY_FOR_EXIT_REVIEW,
    ),
)
def test_non_running_progress_status_is_a_stage_boundary(
    tmp_path: Path,
    run_status: LifecycleRunStatus,
) -> None:
    def boundary(context: LifecycleStageContext) -> StageExecutionResult:
        base = _completed_result(context)
        return StageExecutionResult(
            stage_status=base.stage_status,
            run_status=run_status,
            input_references=base.input_references,
            output_references=base.output_references,
            model_versions=base.model_versions,
            configuration_hashes=base.configuration_hashes,
            reason_codes=base.reason_codes,
            blocker_reason=None,
        )

    calls: list[tuple[str, LifecycleStageName]] = []
    handlers = _handlers(
        calls,
        overrides={LifecycleStageName.SIGNAL: boundary},
    )
    result = _runner(tmp_path, handlers).run(
        _command(idempotency_key=f"boundary-{run_status.value}")
    )

    assert result.run.status is run_status
    assert tuple(stage for operation, stage in calls if operation == "execute") == (
        LIFECYCLE_STAGE_ORDER[:3]
    )


@pytest.mark.parametrize(
    ("stage_name", "run_status", "message"),
    (
        (
            LifecycleStageName.SIGNAL,
            LifecycleRunStatus.COMPLETED,
            "only OUTCOME_REVIEW may complete the lifecycle run",
        ),
        (
            LifecycleStageName.OUTCOME_REVIEW,
            LifecycleRunStatus.RUNNING,
            "OUTCOME_REVIEW must complete the lifecycle run",
        ),
    ),
)
def test_runner_journals_invalid_completion_cursor_as_failure(
    tmp_path: Path,
    stage_name: LifecycleStageName,
    run_status: LifecycleRunStatus,
    message: str,
) -> None:
    def invalid_completion(context: LifecycleStageContext) -> StageExecutionResult:
        base = _completed_result(context)
        return StageExecutionResult(
            stage_status=base.stage_status,
            run_status=run_status,
            input_references=base.input_references,
            output_references=base.output_references,
            model_versions=base.model_versions,
            configuration_hashes=base.configuration_hashes,
            reason_codes=base.reason_codes,
            blocker_reason=None,
        )

    repository = PostgresLifecycleRunRepository(
        tmp_path / f"invalid-{stage_name.value}.postgres-scope"
    )
    calls: list[tuple[str, LifecycleStageName]] = []
    handlers = _handlers(calls, overrides={stage_name: invalid_completion})
    runner = CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=handlers,
        clock=TickClock(),
    )
    command = _command(idempotency_key=f"invalid-{stage_name.value}")

    with pytest.raises(LifecycleStageExecutionError) as captured:
        runner.run(command)

    assert captured.value.exception_type == "LifecycleRunnerInvariantError"
    assert captured.value.exception_message == message
    history = repository.history(command.run_id)
    failed_stage = history.stages[LIFECYCLE_STAGE_ORDER.index(stage_name)]
    assert history.run.status is LifecycleRunStatus.FAILED
    assert failed_stage.stage_status is LifecycleStageStatus.FAILED
    assert failed_stage.failure_reason == (
        f"LifecycleRunnerInvariantError: {message}"
    )


@pytest.mark.parametrize(
    ("stage_status", "run_status", "blocker_reason"),
    (
        (
            LifecycleStageStatus.WAITING,
            LifecycleRunStatus.RUNNING,
            "waiting",
        ),
        (
            LifecycleStageStatus.BLOCKED,
            LifecycleRunStatus.WAITING_FOR_FILL,
            "blocked",
        ),
        (
            LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
            LifecycleRunStatus.COMPLETED,
            "skipped",
        ),
    ),
)
def test_stage_result_rejects_inconsistent_status_pairs(
    stage_status: LifecycleStageStatus,
    run_status: LifecycleRunStatus,
    blocker_reason: str,
) -> None:
    with pytest.raises(ValueError):
        StageExecutionResult(
            stage_status=stage_status,
            run_status=run_status,
            input_references=(),
            output_references=(),
            model_versions=(),
            configuration_hashes=(),
            reason_codes=("EXPECTED",),
            blocker_reason=blocker_reason,
        )
