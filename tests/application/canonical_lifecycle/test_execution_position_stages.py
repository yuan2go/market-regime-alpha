from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tests.postgres_path_repositories import postgres_connection
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleAttemptId,
    LifecycleAttemptResult,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
    LifecycleRetryState,
    LifecycleRun,
    LifecycleRunId,
    LifecycleStage,
    configuration_manifest_hash,
    model_version_manifest_hash,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
)
from market_regime_alpha.application.canonical_lifecycle.stages.assessment import (
    ThesisHealthStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.risk_reduction import (
    build_symbol_trading_session_status_set,
)
from market_regime_alpha.application.canonical_lifecycle.stages.execution_position import (
    FillPositionStageHandler,
    ManualConfirmationStageHandler,
    ManualTradeStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    ordered_references,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.application.trading_lifecycle.manual_execution import (
    ManualExecutionApplicationService,
)
from market_regime_alpha.core.identity import ArtifactId, PositionSnapshotId
from market_regime_alpha.evidence.canonical import canonical_hash
from tests.postgres_path_repositories import (
    PostgresRiskRouteRepository,
)
from tests.postgres_path_repositories import (
    PostgresThesisHealthRepository,
)
from tests.execution.risk_reduction_confirmation_support import (
    ConfirmationFixture,
    build_confirmation_fixture,
)


pytest_plugins = ("tests.daily_decision.conftest",)

UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class ExecutionStageFixture:
    authority: ConfirmationFixture
    initial_references: tuple[LifecycleObjectReference, ...]
    as_of_time: datetime


def test_manual_confirmation_and_trade_stages_only_observe_external_authority(
    tmp_path: Path,
    daily_decision_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, daily_decision_fixture)
    confirmation_handler = ManualConfirmationStageHandler(
        repository=fixture.authority.repository
    )
    before = _authority_counts(fixture.authority.repository.path)

    waiting = confirmation_handler.execute(
        _context(fixture, LifecycleStageName.MANUAL_CONFIRMATION, {})
    )

    assert waiting.stage_status is LifecycleStageStatus.WAITING
    assert waiting.run_status is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
    assert waiting.output_references == ()
    assert _authority_counts(fixture.authority.repository.path) == before

    confirmed = fixture.authority.repository.confirm_risk_reduction(
        fixture.authority.command
    )
    assert confirmed.manual_trade is not None

    def forbidden_confirmation(*args, **kwargs):
        raise AssertionError("lifecycle handler must not confirm H4.5")

    def forbidden_fill(*args, **kwargs):
        raise AssertionError("lifecycle handler must not append Fill")

    monkeypatch.setattr(
        fixture.authority.repository,
        "confirm_risk_reduction",
        forbidden_confirmation,
    )
    monkeypatch.setattr(
        fixture.authority.repository,
        "append_fill",
        forbidden_fill,
    )
    counts_after_external_confirmation = _authority_counts(
        fixture.authority.repository.path
    )
    confirmation = confirmation_handler.execute(
        _context(fixture, LifecycleStageName.MANUAL_CONFIRMATION, {})
    )
    assert confirmation_handler.recover(
        _context(fixture, LifecycleStageName.MANUAL_CONFIRMATION, {})
    ) == confirmation
    assert confirmation.reason_codes == (
        "BROKER_NOT_INVOKED",
        "EXTERNAL_MANUAL_CONFIRMATION_VERIFIED",
        "NO_FILL_CREATED",
        "NO_ORDER_CREATED",
    )
    assert confirmation.output_references[0].object_type is (
        LifecycleObjectType.RISK_REDUCTION_CONFIRMATION
    )

    trade_handler = ManualTradeStageHandler(repository=fixture.authority.repository)
    trade = trade_handler.execute(
        _context(
            fixture,
            LifecycleStageName.MANUAL_TRADE,
            {LifecycleStageName.MANUAL_CONFIRMATION: confirmation},
        )
    )

    assert trade.run_status is LifecycleRunStatus.WAITING_FOR_FILL
    assert trade.output_references[0].object_type is LifecycleObjectType.MANUAL_TRADE
    assert _authority_counts(fixture.authority.repository.path) == (
        counts_after_external_confirmation
    )


def test_fill_position_waits_without_fill_and_replays_existing_external_fill(
    tmp_path: Path,
    daily_decision_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, daily_decision_fixture)
    external_confirmation = fixture.authority.repository.confirm_risk_reduction(
        fixture.authority.command
    )
    assert external_confirmation.manual_trade is not None
    confirmation = ManualConfirmationStageHandler(
        repository=fixture.authority.repository
    ).execute(_context(fixture, LifecycleStageName.MANUAL_CONFIRMATION, {}))
    trade = ManualTradeStageHandler(repository=fixture.authority.repository).execute(
        _context(
            fixture,
            LifecycleStageName.MANUAL_TRADE,
            {LifecycleStageName.MANUAL_CONFIRMATION: confirmation},
        )
    )
    handler = FillPositionStageHandler(repository=fixture.authority.repository)
    prior = {
        LifecycleStageName.MANUAL_CONFIRMATION: confirmation,
        LifecycleStageName.MANUAL_TRADE: trade,
    }

    no_fill = handler.execute(
        _context(fixture, LifecycleStageName.FILL_POSITION, prior)
    )

    assert no_fill.stage_status is LifecycleStageStatus.WAITING
    assert no_fill.run_status is LifecycleRunStatus.WAITING_FOR_FILL
    assert no_fill.output_references == ()
    assert "NO_EXTERNAL_FILL_OBSERVED" in no_fill.reason_codes

    fill_time = fixture.authority.command.confirmed_at + timedelta(seconds=2)
    ManualExecutionApplicationService(fixture.authority.repository).record_fill(
        external_confirmation.manual_trade.manual_trade_id,
        external_fill_id="external-human-risk-reduction-fill",
        quantity=fixture.authority.quantity,
        price=10.0,
        fees=0.0,
        occurred_at=fill_time - timedelta(seconds=1),
        recorded_at=fill_time,
        actor="manual-operator",
        reason="observed external manual execution",
        idempotency_key="external-human-risk-reduction-fill",
    )
    after_external_fill = _authority_counts(fixture.authority.repository.path)

    def forbidden_append(*args, **kwargs):
        raise AssertionError("FillPosition stage must not append Fill")

    monkeypatch.setattr(
        fixture.authority.repository,
        "append_fill",
        forbidden_append,
    )
    completed = handler.execute(
        _context(fixture, LifecycleStageName.FILL_POSITION, prior)
    )
    replayed = handler.recover(
        _context(fixture, LifecycleStageName.FILL_POSITION, prior)
    )

    assert completed == replayed
    assert completed.stage_status is LifecycleStageStatus.COMPLETED
    assert completed.run_status is LifecycleRunStatus.READY_FOR_EXIT_REVIEW
    assert _authority_counts(fixture.authority.repository.path) == after_external_fill
    assert sum(
        item.object_type is LifecycleObjectType.FILL
        for item in completed.output_references
    ) == 2
    position_reference = next(
        item
        for item in completed.output_references
        if item.object_type is LifecycleObjectType.POSITION_SNAPSHOT
    )
    assert position_reference.reader_kind is (
        LifecycleReaderKind.POSITION_SNAPSHOT_REPOSITORY
    )
    restored_position = (
        fixture.authority.repository.get_fill_derived_position(
            fixture.authority.decision_id,
            position_snapshot_id=PositionSnapshotId(
                str(position_reference.object_id)
            ),
        )
    )
    assert restored_position is not None
    assert str(position_reference.object_id) == str(restored_position.snapshot_id)
    assert position_reference.content_hash == canonical_hash(
        restored_position.to_canonical_dict()
    )
    book = fixture.authority.repository.get_position_book(
        fixture.authority.book.position_book_id
    )
    fills = fixture.authority.repository.fills_for_book(book.position_book_id)
    assert len(fills) == 2
    assert "POSITION_STATE_CLOSED" in completed.reason_codes


def test_repeated_resume_does_not_duplicate_manual_trade_or_fill(
    tmp_path: Path, daily_decision_fixture
) -> None:
    fixture = _fixture(tmp_path, daily_decision_fixture)
    fixture.authority.repository.confirm_risk_reduction(fixture.authority.command)
    handler = ManualConfirmationStageHandler(repository=fixture.authority.repository)
    context = _context(fixture, LifecycleStageName.MANUAL_CONFIRMATION, {})
    before = _authority_counts(fixture.authority.repository.path)

    outputs = tuple(handler.recover(context) for _ in range(3))

    assert outputs[0] == outputs[1] == outputs[2]
    assert _authority_counts(fixture.authority.repository.path) == before


def test_thesis_health_stage_uses_command_bound_as_of_authority(
    tmp_path: Path, daily_decision_fixture
) -> None:
    fixture = _fixture(tmp_path, daily_decision_fixture)
    confirmed = fixture.authority.repository.confirm_risk_reduction(
        fixture.authority.command
    )
    assert confirmed.manual_trade is not None
    confirmation = ManualConfirmationStageHandler(
        repository=fixture.authority.repository
    ).execute(_context(fixture, LifecycleStageName.MANUAL_CONFIRMATION, {}))
    trade = ManualTradeStageHandler(repository=fixture.authority.repository).execute(
        _context(
            fixture,
            LifecycleStageName.MANUAL_TRADE,
            {LifecycleStageName.MANUAL_CONFIRMATION: confirmation},
        )
    )
    fill_time = fixture.authority.command.confirmed_at + timedelta(seconds=2)
    ManualExecutionApplicationService(fixture.authority.repository).record_fill(
        confirmed.manual_trade.manual_trade_id,
        external_fill_id="external-health-stage-fill",
        quantity=fixture.authority.quantity,
        price=10.0,
        fees=0.0,
        occurred_at=fill_time - timedelta(seconds=1),
        recorded_at=fill_time,
        actor="manual-operator",
        reason="observed external manual execution",
        idempotency_key="external-health-stage-fill",
    )
    preceding = {
        LifecycleStageName.MANUAL_CONFIRMATION: confirmation,
        LifecycleStageName.MANUAL_TRADE: trade,
    }
    position = FillPositionStageHandler(
        repository=fixture.authority.repository
    ).execute(_context(fixture, LifecycleStageName.FILL_POSITION, preceding))
    preceding[LifecycleStageName.FILL_POSITION] = position
    handler = ThesisHealthStageHandler(
        repository=PostgresThesisHealthRepository(
            fixture.authority.repository.path
        )
    )

    result = handler.execute(
        _context(fixture, LifecycleStageName.THESIS_HEALTH, preceding)
    )

    assert result.stage_status is LifecycleStageStatus.COMPLETED
    assert result.run_status is LifecycleRunStatus.READY_FOR_HOLDING_ASSESSMENT
    assert result.output_references[0].object_type is (
        LifecycleObjectType.THESIS_HEALTH_OBSERVATION
    )
    assert "LATEST_DURABLE_THESIS_HEALTH_VERIFIED" in result.reason_codes


def _fixture(tmp_path: Path, daily_decision_fixture) -> ExecutionStageFixture:
    authority = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    risk_bundle = PostgresRiskRouteRepository(
        authority.repository.path
    ).get_verified_reducing_decision_bundle(authority.decision_id)
    health = PostgresThesisHealthRepository(
        authority.repository.path
    ).get_verified_thesis_health_bundle(
        authority.command.thesis_health_observation_id
    )
    calendar_path = tmp_path / "lifecycle-calendar.json"
    calendar_path.write_text(
        _json(authority.command.trading_calendar.to_canonical_dict()),
        encoding="utf-8",
    )
    status_payload = build_symbol_trading_session_status_set(
        authority.command.symbol_trading_statuses
    )
    status_path = tmp_path / "lifecycle-symbol-statuses.json"
    status_path.write_text(_json(status_payload), encoding="utf-8")
    policy_path = tmp_path / "lifecycle-confirmation-policy.json"
    policy_path.write_text(
        _json(authority.command.confirmation_policy.to_canonical_dict()),
        encoding="utf-8",
    )
    available = authority.command.confirmed_at.astimezone(UTC)
    references = ordered_references(
        (
            _reference(
                object_type=LifecycleObjectType.RISK_REDUCING_DECISION,
                object_id=risk_bundle.decision.decision_id,
                content_hash=risk_bundle.decision.content_hash,
                reader_kind=LifecycleReaderKind.RISK_REDUCTION_REPOSITORY,
                available_at=risk_bundle.decision.assessed_at,
            ),
            _reference(
                object_type=LifecycleObjectType.POSITION_BOOK,
                object_id=ArtifactId(str(authority.book.position_book_id)),
                content_hash=canonical_hash(authority.book.to_canonical_dict()),
                reader_kind=LifecycleReaderKind.POSITION_BOOK_REPOSITORY,
                available_at=authority.book.opened_at,
            ),
            _reference(
                object_type=LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
                object_id=authority.command.trading_calendar.artifact_id,
                content_hash=authority.command.trading_calendar.content_hash,
                reader_kind=LifecycleReaderKind.TRADING_CALENDAR_ARTIFACT_READER,
                available_at=available,
                locator=calendar_path,
            ),
            _reference(
                object_type=LifecycleObjectType.SYMBOL_TRADING_SESSION_STATUS_SET,
                object_id=ArtifactId(str(status_payload["status_set_id"])),
                content_hash=str(status_payload["content_hash"]),
                reader_kind=(
                    LifecycleReaderKind.SYMBOL_TRADING_SESSION_STATUS_READER
                ),
                available_at=available,
                locator=status_path,
            ),
            _reference(
                object_type=LifecycleObjectType.THESIS_HEALTH_OBSERVATION,
                object_id=health.observation.observation_id,
                content_hash=canonical_hash(
                    health.observation.to_canonical_dict()
                ),
                reader_kind=LifecycleReaderKind.THESIS_HEALTH_REPOSITORY,
                available_at=health.observation.assessed_at,
            ),
            _reference(
                object_type=(
                    LifecycleObjectType.RISK_REDUCTION_CONFIRMATION_POLICY
                ),
                object_id=authority.command.confirmation_policy.policy_id,
                content_hash=authority.command.confirmation_policy.policy_hash,
                reader_kind=(
                    LifecycleReaderKind.RISK_REDUCTION_CONFIRMATION_POLICY_READER
                ),
                available_at=available,
                locator=policy_path,
            ),
        )
    )
    return ExecutionStageFixture(
        authority=authority,
        initial_references=references,
        as_of_time=available,
    )


def _reference(
    *,
    object_type: LifecycleObjectType,
    object_id: ArtifactId,
    content_hash: str,
    reader_kind: LifecycleReaderKind,
    available_at: datetime,
    locator: Path | None = None,
) -> LifecycleObjectReference:
    return LifecycleObjectReference(
        object_type=object_type,
        object_id=LifecycleObjectId(str(object_id)),
        content_hash=content_hash,
        reader_kind=reader_kind,
        locator=str(locator.resolve()) if locator is not None else None,
        available_at=available_at.astimezone(UTC),
    )


def _context(
    fixture: ExecutionStageFixture,
    stage_name: LifecycleStageName,
    overrides: dict[LifecycleStageName, StageExecutionResult],
) -> LifecycleStageContext:
    index = LIFECYCLE_STAGE_ORDER.index(stage_name)
    run_id = LifecycleRunId("lifecycle-run-execution-position-test")
    prior_results = tuple(
        overrides.get(name, _default_prior_result(fixture, name))
        for name in LIFECYCLE_STAGE_ORDER[:index]
    )
    run = LifecycleRun(
        run_id=run_id,
        idempotency_key="execution-position-stage-test",
        command_hash=canonical_hash({"command": "execution-position-stage-test"}),
        run_type=LifecycleRunType.RISK_REDUCTION_CONTINUATION,
        decision_date=fixture.as_of_time.astimezone(SHANGHAI).date(),
        as_of_time=fixture.as_of_time,
        status=LifecycleRunStatus.RUNNING,
        current_stage=stage_name,
        input_manifest_id=None,
        input_content_hash=None,
        completed_stages=tuple(LIFECYCLE_STAGE_ORDER[:index]),
        configuration_references=(),
        configuration_manifest_hash=configuration_manifest_hash(()),
        model_references=(),
        model_version_manifest_hash=model_version_manifest_hash(()),
        retry_state=LifecycleRetryState.NOT_REQUIRED,
        failure_reason=None,
        blocker_reason=None,
        created_at=fixture.as_of_time,
        updated_at=fixture.as_of_time + timedelta(seconds=index + 1),
        completed_at=None,
        version=index + 1,
        claim_token=1,
    )
    prior_stages = tuple(
        LifecycleStage(
            run_id=run_id,
            stage_name=name,
            stage_status=result.stage_status,
            attempt_count=1,
            input_references=result.input_references,
            output_references=result.output_references,
            started_at=fixture.as_of_time + timedelta(seconds=prior_index + 1),
            completed_at=fixture.as_of_time + timedelta(seconds=prior_index + 2),
            failure_reason=None,
            blocker_reason=(
                result.blocker_reason
                if result.stage_status
                in {
                    LifecycleStageStatus.WAITING,
                    LifecycleStageStatus.BLOCKED,
                    LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
                }
                else None
            ),
            version=2,
        )
        for prior_index, (name, result) in enumerate(
            zip(LIFECYCLE_STAGE_ORDER[:index], prior_results, strict=True)
        )
    )
    stage = LifecycleStage(
        run_id=run_id,
        stage_name=stage_name,
        stage_status=LifecycleStageStatus.RUNNING,
        attempt_count=1,
        input_references=(),
        output_references=(),
        started_at=run.updated_at,
        completed_at=None,
        failure_reason=None,
        blocker_reason=None,
        version=2,
    )
    return LifecycleStageContext(
        run=run,
        stage=stage,
        attempt=LifecycleAttempt(
            attempt_id=LifecycleAttemptId(f"attempt-{stage_name.value.lower()}"),
            run_id=run_id,
            stage_name=stage_name,
            attempt_number=1,
            started_at=run.updated_at,
            completed_at=None,
            result=LifecycleAttemptResult.RUNNING,
            exception_type=None,
            exception_message=None,
            claim_token=1,
        ),
        prior_stages=prior_stages,
        initial_references=fixture.initial_references,
    )


def _default_prior_result(
    fixture: ExecutionStageFixture, stage_name: LifecycleStageName
) -> StageExecutionResult:
    risk_reference = next(
        item
        for item in fixture.initial_references
        if item.object_type is LifecycleObjectType.RISK_REDUCING_DECISION
    )
    if stage_name is LifecycleStageName.RISK_REDUCTION:
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION,
            input_references=fixture.initial_references,
            output_references=(risk_reference,),
            model_versions=(),
            configuration_hashes=(),
            reason_codes=("MANUAL_CONFIRMATION_REQUIRED",),
            blocker_reason="external manual confirmation is required",
        )
    return StageExecutionResult(
        stage_status=LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
        run_status=LifecycleRunStatus.RUNNING,
        input_references=fixture.initial_references,
        output_references=(),
        model_versions=(),
        configuration_hashes=(),
        reason_codes=("RUN_TYPE_NOT_APPLICABLE",),
        blocker_reason="risk-reduction continuation starts at H4",
    )


def _authority_counts(path: Path) -> tuple[int, int, int]:
    with postgres_connection(path) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "risk_reduction_confirmation_attempts",
                "manual_trade_records",
                "manual_fills",
            )
        )


def _json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
