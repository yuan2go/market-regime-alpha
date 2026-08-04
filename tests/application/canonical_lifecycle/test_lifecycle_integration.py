from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    CanonicalLifecycleInputManifest,
    LifecycleAuthorityCeiling,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectReference,
    LifecycleObjectType,
)
from market_regime_alpha.application.canonical_lifecycle.replay import (
    LifecycleReplayStatus,
    verify_lifecycle_replay,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    CanonicalDecisionLifecycleRunner,
    LifecycleStageExecutionError,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    LifecycleStageHandler,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    VerifiedCompositeEvidenceStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.execution_position import (
    ManualConfirmationStageHandler,
    ManualTradeStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.research import (
    PlatformResearchStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.signal_forecast import (
    EntryAssessmentStageHandler,
    HistoricalCompatibilitySignalStageHandler,
    HistoricalSignalProductionContext,
    PathForecastStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.application.trading_lifecycle.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.evidence.canonical import canonical_json
from market_regime_alpha.execution.risk_reduction import (
    RiskReductionConfirmationCommand,
    RiskReductionConfirmationPolicy,
)
from tests.application.canonical_lifecycle.test_decision_risk_stages import (
    _NeverCalledHandler,
    _risk_configuration_references,
    _risk_continuation_as_of,
    _risk_handler,
    _risk_references,
)
from tests.application.canonical_lifecycle.test_research_stages import (
    StageFixture,
    _stage_fixture,
)
from tests.execution.risk_reduction_confirmation_support import (
    ConfirmationFixture,
    build_confirmation_fixture,
)


pytest_plugins = ("tests.daily_decision.conftest",)

UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")


class _TickingClock:
    def __init__(self, start: datetime) -> None:
        self._current = start.astimezone(UTC)

    def __call__(self) -> datetime:
        result = self._current
        self._current += timedelta(seconds=1)
        return result


@dataclass
class _CountingHandler:
    delegate: LifecycleStageHandler
    recover_calls: int = 0
    execute_calls: int = 0

    @property
    def stage_name(self) -> LifecycleStageName:
        return self.delegate.stage_name

    @property
    def mutation_kind(self) -> StageMutationKind:
        return self.delegate.mutation_kind

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        self.recover_calls += 1
        return self.delegate.recover(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        self.execute_calls += 1
        return self.delegate.execute(context)


class _CrashAfterResearch:
    def __init__(self) -> None:
        self.raised = False

    def __call__(self, stage_name: LifecycleStageName, _run: object) -> None:
        if stage_name is LifecycleStageName.PLATFORM_RESEARCH and not self.raised:
            self.raised = True
            raise RuntimeError("delivery failed after durable research settlement")


class _ArmableJournalCrash:
    """Fail one journal settlement after an external domain commit."""

    def __init__(self, *, point: str) -> None:
        self._point = point
        self.armed = False
        self.raised = False

    def __call__(self, point: str) -> None:
        if self.armed and point == self._point and not self.raised:
            self.raised = True
            raise RuntimeError("injected crash before lifecycle receipt commit")


def test_verified_h6_chain_is_durable_replayable_and_clock_independent(
    tmp_path: Path,
) -> None:
    fixture, manifest_path = _canonical_fixture(tmp_path)
    first_repository = SQLiteLifecycleRunRepository(tmp_path / "first-journal.sqlite3")
    first = _canonical_runner(
        fixture,
        repository=first_repository,
        output_root=tmp_path / "runtime",
        clock_start=fixture.as_of_time + timedelta(hours=1),
    )
    first_command = _canonical_command(
        fixture,
        manifest_path=manifest_path,
        idempotency_key="canonical-integration-first",
        output_root=tmp_path / "runtime",
    )

    result = first.run(first_command)

    assert result.run.status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    assert result.run.current_stage is LifecycleStageName.ENTRY_ASSESSMENT
    assert result.attempted_stages == LIFECYCLE_STAGE_ORDER[:5]
    history = first_repository.history(result.run.run_id)
    settled = history.stages[:5]
    assert tuple(item.stage_name for item in settled) == LIFECYCLE_STAGE_ORDER[:5]
    assert tuple(item.stage_status for item in settled) == (
        LifecycleStageStatus.COMPLETED,
        LifecycleStageStatus.COMPLETED,
        LifecycleStageStatus.COMPLETED,
        LifecycleStageStatus.COMPLETED,
        LifecycleStageStatus.BLOCKED,
    )
    assert all(item.attempt_count == 1 for item in settled)
    assert len(history.attempts) == 5
    assert len(history.receipts) == 5
    assert len(history.events) == len(history.event_payloads)
    assert all(json.loads(payload)["run_id"] == str(result.run.run_id) for payload in history.event_payloads)
    assert {item.stage_name: item.output_hashes for item in history.receipts[:4]} == _settled_output_hashes(history)
    entry_receipt = history.receipts[-1]
    assert entry_receipt.stage_name is LifecycleStageName.ENTRY_ASSESSMENT
    assert "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE" in entry_receipt.reason_codes

    duplicate = first.run(first_command)
    assert duplicate.run == result.run
    assert duplicate.attempted_stages == ()
    assert first_repository.history(result.run.run_id) == history
    replay = verify_lifecycle_replay(
        repository=first_repository,
        run_id=result.run.run_id,
    )
    assert replay.status is LifecycleReplayStatus.STABLE
    assert (
        verify_lifecycle_replay(
            repository=first_repository,
            run_id=result.run.run_id,
        )
        == replay
    )

    second_repository = SQLiteLifecycleRunRepository(tmp_path / "second-journal.sqlite3")
    second = _canonical_runner(
        fixture,
        repository=second_repository,
        output_root=tmp_path / "runtime",
        clock_start=fixture.as_of_time + timedelta(hours=8),
    )
    second_result = second.run(
        _canonical_command(
            fixture,
            manifest_path=manifest_path,
            idempotency_key="canonical-integration-second",
            output_root=tmp_path / "runtime",
        )
    )

    assert second_result.run.status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    assert _settled_output_hashes(second_repository.history(second_result.run.run_id)) == _settled_output_hashes(history)


def test_risk_continuation_requires_external_h45_then_observes_one_manual_trade(
    tmp_path: Path,
    daily_decision_fixture,
) -> None:
    authority = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    references = _risk_references(authority, tmp_path)
    as_of = _risk_continuation_as_of(authority).astimezone(UTC)
    command = _risk_command(
        authority=authority,
        references=references,
        as_of=as_of,
        idempotency_key="risk-continuation-integration",
        root=tmp_path,
    )
    journal = SQLiteLifecycleRunRepository(tmp_path / "risk-journal.sqlite3")
    runner = _risk_runner(
        authority=authority,
        repository=journal,
        as_of=as_of,
    )
    confirmation_command = _confirmation_command_for_references(authority, references)
    before = _execution_counts(authority.repository)

    waiting = runner.run(command)

    assert waiting.run.status is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
    assert waiting.run.current_stage is LifecycleStageName.RISK_REDUCTION
    assert _execution_counts(authority.repository) == before
    assert "MANUAL_CONFIRMATION_REQUIRED" in waiting.receipts[-1].reason_codes
    assert "NO_ORDER_CREATED" in waiting.receipts[-1].reason_codes
    assert "BROKER_NOT_INVOKED" in waiting.receipts[-1].reason_codes
    same_wait = runner.run(command)
    assert same_wait.run == waiting.run
    assert same_wait.attempted_stages == ()

    confirmed = authority.repository.confirm_risk_reduction(confirmation_command)
    assert confirmed.manual_trade is not None
    after_confirmation = _execution_counts(authority.repository)
    assert after_confirmation == (
        before[0] + 1,
        before[1] + 1,
        before[2],
    )
    assert authority.repository.confirm_risk_reduction(confirmation_command) == confirmed
    assert _execution_counts(authority.repository) == after_confirmation

    resumed = runner.resume(command.run_id)

    assert resumed.run.status is LifecycleRunStatus.WAITING_FOR_FILL
    assert resumed.run.current_stage is LifecycleStageName.MANUAL_TRADE
    assert resumed.attempted_stages == (
        LifecycleStageName.MANUAL_CONFIRMATION,
        LifecycleStageName.MANUAL_TRADE,
    )
    assert _execution_counts(authority.repository) == after_confirmation
    manual_trade = next(
        reference for reference in resumed.stages[10].output_references if reference.object_type is LifecycleObjectType.MANUAL_TRADE
    )
    assert str(manual_trade.object_id) == str(confirmed.manual_trade.manual_trade_id)
    assert "EXISTING_MANUAL_TRADE_VERIFIED" in resumed.receipts[-1].reason_codes
    assert "NO_FILL_CREATED" in resumed.receipts[-1].reason_codes
    assert "NO_ORDER_CREATED" in resumed.receipts[-1].reason_codes
    assert "BROKER_NOT_INVOKED" in resumed.receipts[-1].reason_codes
    assert not any("broker" in table.lower() or "order" in table.lower() for table in _table_names(authority.repository.path))

    replayed_resume = runner.run(command)
    assert replayed_resume.run == resumed.run
    assert replayed_resume.attempted_stages == ()
    assert replayed_resume.run.status is LifecycleRunStatus.WAITING_FOR_FILL
    assert _execution_counts(authority.repository) == after_confirmation


def test_manual_confirmation_rejects_policy_not_bound_by_continuation(
    tmp_path: Path,
    daily_decision_fixture,
) -> None:
    authority = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    references = _risk_references(authority, tmp_path)
    as_of = _risk_continuation_as_of(authority).astimezone(UTC)
    command = _risk_command(
        authority=authority,
        references=references,
        as_of=as_of,
        idempotency_key="risk-continuation-policy-mismatch",
        root=tmp_path,
    )
    journal = SQLiteLifecycleRunRepository(tmp_path / "mismatch-journal.sqlite3")
    runner = _risk_runner(
        authority=authority,
        repository=journal,
        as_of=as_of,
    )
    waiting = runner.run(command)
    assert waiting.run.status is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
    authority.repository.confirm_risk_reduction(authority.command)

    with pytest.raises(LifecycleStageExecutionError) as captured:
        runner.resume(command.run_id)

    assert captured.value.stage_name is LifecycleStageName.MANUAL_CONFIRMATION
    assert captured.value.exception_type == "ValueError"
    assert captured.value.exception_message == ("H4.5 confirmation policy does not match the command-bound policy")
    failed = journal.history(command.run_id)
    assert failed.run.status is LifecycleRunStatus.FAILED
    assert failed.stages[9].stage_status is LifecycleStageStatus.FAILED


def test_manual_trade_commit_survives_crash_before_lifecycle_receipt(
    tmp_path: Path,
    daily_decision_fixture,
) -> None:
    authority = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    references = _risk_references(authority, tmp_path)
    as_of = _risk_continuation_as_of(authority).astimezone(UTC)
    command = _risk_command(
        authority=authority,
        references=references,
        as_of=as_of,
        idempotency_key="risk-cross-repository-crash",
        root=tmp_path,
    )
    crash = _ArmableJournalCrash(point="finish_after_attempt")
    journal_path = tmp_path / "cross-repository-journal.sqlite3"
    crashing_repository = SQLiteLifecycleRunRepository(
        journal_path,
        fault_injector=crash,
    )
    handlers = list(_risk_handlers(authority))
    risk = _CountingHandler(handlers[8])
    confirmation = _CountingHandler(handlers[9])
    manual_trade = _CountingHandler(handlers[10])
    handlers[8] = risk
    handlers[9] = confirmation
    handlers[10] = manual_trade
    clock = _TickingClock(as_of + timedelta(minutes=1))
    crashing_runner = CanonicalDecisionLifecycleRunner(
        repository=crashing_repository,
        handlers=tuple(handlers),
        clock=clock,
    )

    waiting = crashing_runner.run(command)
    assert waiting.run.status is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
    assert risk.recover_calls == 1
    counts_before_confirmation = _execution_counts(authority.repository)
    confirmation_result = authority.repository.confirm_risk_reduction(_confirmation_command_for_references(authority, references))
    assert confirmation_result.manual_trade is not None
    committed_trade_id = confirmation_result.manual_trade.manual_trade_id
    committed_counts = _execution_counts(authority.repository)
    crash.armed = True

    with pytest.raises(LifecycleStageExecutionError) as captured:
        crashing_runner.resume(command.run_id)

    assert not captured.value.journal_settled
    assert captured.value.stage_name is LifecycleStageName.MANUAL_CONFIRMATION
    after_crash = crashing_repository.history(command.run_id)
    assert after_crash.run.status is LifecycleRunStatus.FAILED
    assert after_crash.stages[9].stage_status is LifecycleStageStatus.FAILED
    assert after_crash.stages[9].attempt_count == 1
    assert not any(receipt.stage_name is LifecycleStageName.MANUAL_CONFIRMATION for receipt in after_crash.receipts)
    assert _execution_counts(authority.repository) == committed_counts

    durable_repository = SQLiteLifecycleRunRepository(journal_path)
    resumed = CanonicalDecisionLifecycleRunner(
        repository=durable_repository,
        handlers=tuple(handlers),
        clock=clock,
    ).resume(command.run_id)

    assert resumed.run.run_id == waiting.run.run_id
    assert resumed.run.status is LifecycleRunStatus.WAITING_FOR_FILL
    assert resumed.stages[9].attempt_count == 2
    assert resumed.stages[10].attempt_count == 1
    assert risk.recover_calls == 1
    assert confirmation.recover_calls == 2
    assert manual_trade.recover_calls == 1
    confirmation_receipts = tuple(receipt for receipt in resumed.receipts if receipt.stage_name is LifecycleStageName.MANUAL_CONFIRMATION)
    assert len(confirmation_receipts) == 1
    manual_trade_reference = next(
        reference for reference in resumed.stages[10].output_references if reference.object_type is LifecycleObjectType.MANUAL_TRADE
    )
    assert str(manual_trade_reference.object_id) == str(committed_trade_id)
    assert _execution_counts(authority.repository) == committed_counts
    assert committed_counts[2] == counts_before_confirmation[2]
    assert not any("broker" in table.lower() or "order" in table.lower() for table in _table_names(authority.repository.path))


def test_delivery_failure_after_real_research_receipt_resumes_at_signal(
    tmp_path: Path,
) -> None:
    fixture, manifest_path = _canonical_fixture(tmp_path)
    repository = SQLiteLifecycleRunRepository(tmp_path / "recovery-journal.sqlite3")
    handlers = list(_canonical_handlers(fixture, output_root=tmp_path / "recovery-runtime"))
    evidence = _CountingHandler(handlers[0])
    research = _CountingHandler(handlers[1])
    handlers[0] = evidence
    handlers[1] = research
    clock = _TickingClock(fixture.as_of_time + timedelta(hours=2))
    command = _canonical_command(
        fixture,
        manifest_path=manifest_path,
        idempotency_key="canonical-real-stage-recovery",
        output_root=tmp_path / "recovery-runtime",
    )
    crashing = CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=tuple(handlers),
        clock=clock,
        after_stage_hook=_CrashAfterResearch(),
    )

    with pytest.raises(LifecycleStageExecutionError) as captured:
        crashing.run(command)

    assert captured.value.journal_settled
    committed = repository.history(command.run_id)
    assert committed.stages[0].stage_status is LifecycleStageStatus.COMPLETED
    assert committed.stages[1].stage_status is LifecycleStageStatus.COMPLETED
    assert committed.stages[0].attempt_count == 1
    assert committed.stages[1].attempt_count == 1
    calls_after_crash = (
        evidence.recover_calls,
        evidence.execute_calls,
        research.recover_calls,
        research.execute_calls,
    )

    resumed = CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=tuple(handlers),
        clock=clock,
    ).resume(command.run_id)

    assert resumed.run.status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    assert (
        evidence.recover_calls,
        evidence.execute_calls,
        research.recover_calls,
        research.execute_calls,
    ) == calls_after_crash
    recovered = repository.history(command.run_id)
    assert recovered.stages[0].attempt_count == 1
    assert recovered.stages[1].attempt_count == 1
    assert sum(receipt.stage_name is LifecycleStageName.PLATFORM_RESEARCH for receipt in recovered.receipts) == 1


def _canonical_fixture(tmp_path: Path) -> tuple[StageFixture, Path]:
    fixture = _stage_fixture(tmp_path / "evidence", ranked_percentiles=True)
    config_root = tmp_path / "runtime-configurations"
    config_root.mkdir(parents=True)
    configurations: dict[Any, object] = {
        type(fixture.research_configuration): fixture.research_configuration,
        type(fixture.signal_configuration): fixture.signal_configuration,
        type(fixture.forecast_configuration): fixture.forecast_configuration,
    }
    references = []
    for reference in fixture.configuration_references:
        configuration = next(item for item in configurations.values() if getattr(item, "configuration_id") == reference.configuration_id)
        path = config_root / f"{reference.configuration_id}.json"
        path.write_text(canonical_json(configuration.to_canonical_dict()), encoding="utf-8")
        references.append(replace(reference, locator=str(path.resolve())))
    fixture = replace(fixture, configuration_references=tuple(references))
    manifest = CanonicalLifecycleInputManifest.create(
        decision_date=fixture.decision_date,
        as_of_time=fixture.as_of_time,
        created_at=fixture.as_of_time + timedelta(seconds=1),
        input_references=fixture.initial_references,
        configuration_references=fixture.configuration_references,
        model_references=fixture.model_references,
        authority_ceiling=LifecycleAuthorityCeiling(),
        limitations=("ENTRY_MODEL_NOT_EMPIRICALLY_VALIDATED",),
    )
    manifest_path = tmp_path / "canonical-input-manifest.json"
    manifest_path.write_text(canonical_json(manifest.to_canonical_dict()), encoding="utf-8")
    return fixture, manifest_path


def _canonical_command(
    fixture: StageFixture,
    *,
    manifest_path: Path,
    idempotency_key: str,
    output_root: Path,
) -> CanonicalLifecycleCommand:
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = CanonicalLifecycleInputManifest.from_canonical_dict(manifest_payload)
    return CanonicalLifecycleCommand(
        run_type=LifecycleRunType.CANONICAL_DECISION_LIFECYCLE,
        decision_date=fixture.decision_date,
        as_of_time=fixture.as_of_time,
        idempotency_key=idempotency_key,
        input_manifest_id=manifest.manifest_id,
        input_content_hash=manifest.content_hash,
        input_manifest_locator=manifest_path,
        input_references=fixture.initial_references,
        configuration_references=fixture.configuration_references,
        model_references=fixture.model_references,
        stop_after_stage=None,
        output_directory=output_root,
        authority_database_locator=None,
    )


def _canonical_handlers(fixture: StageFixture, *, output_root: Path) -> tuple[LifecycleStageHandler, ...]:
    configured: dict[LifecycleStageName, LifecycleStageHandler] = {
        LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE: (VerifiedCompositeEvidenceStageHandler()),
        LifecycleStageName.PLATFORM_RESEARCH: PlatformResearchStageHandler(
            configuration=fixture.research_configuration,
            output_root=output_root / "research",
        ),
        LifecycleStageName.SIGNAL: HistoricalCompatibilitySignalStageHandler(
            production_context=HistoricalSignalProductionContext.HISTORICAL_COMPATIBILITY_TEST,
            configuration=fixture.signal_configuration,
            output_root=output_root / "signal",
        ),
        LifecycleStageName.PATH_FORECAST: PathForecastStageHandler(
            configuration=fixture.forecast_configuration,
            output_root=output_root / "forecast",
        ),
        LifecycleStageName.ENTRY_ASSESSMENT: EntryAssessmentStageHandler(authority_ceiling=LifecycleAuthorityCeiling()),
    }
    return tuple(configured.get(stage_name, _NeverCalledHandler(stage_name)) for stage_name in LIFECYCLE_STAGE_ORDER)


def _canonical_runner(
    fixture: StageFixture,
    *,
    repository: SQLiteLifecycleRunRepository,
    output_root: Path,
    clock_start: datetime,
) -> CanonicalDecisionLifecycleRunner:
    return CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=_canonical_handlers(fixture, output_root=output_root),
        clock=_TickingClock(clock_start),
    )


def _confirmation_command_for_references(
    authority: ConfirmationFixture,
    references: tuple[LifecycleObjectReference, ...],
) -> RiskReductionConfirmationCommand:
    policy_reference = next(
        reference for reference in references if reference.object_type is LifecycleObjectType.RISK_REDUCTION_CONFIRMATION_POLICY
    )
    assert policy_reference.locator is not None
    policy = RiskReductionConfirmationPolicy.from_canonical_dict(json.loads(Path(policy_reference.locator).read_text(encoding="utf-8")))
    assert str(policy_reference.object_id) == str(policy.policy_id)
    assert policy_reference.content_hash == policy.policy_hash
    return replace(
        authority.command,
        confirmation_policy=policy,
        idempotency_key="risk-continuation-external-h4-5",
    )


def _risk_command(
    *,
    authority: ConfirmationFixture,
    references: tuple[LifecycleObjectReference, ...],
    as_of: datetime,
    idempotency_key: str,
    root: Path,
) -> CanonicalLifecycleCommand:
    return CanonicalLifecycleCommand(
        run_type=LifecycleRunType.RISK_REDUCTION_CONTINUATION,
        decision_date=as_of.astimezone(SHANGHAI).date(),
        as_of_time=as_of,
        idempotency_key=idempotency_key,
        input_manifest_id=None,
        input_content_hash=None,
        input_manifest_locator=None,
        input_references=references,
        configuration_references=_risk_configuration_references(authority, references, root),
        model_references=(),
        stop_after_stage=None,
        output_directory=root / "risk-output",
        authority_database_locator=authority.repository.path,
    )


def _risk_runner(
    *,
    authority: ConfirmationFixture,
    repository: SQLiteLifecycleRunRepository,
    as_of: datetime,
) -> CanonicalDecisionLifecycleRunner:
    return CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=_risk_handlers(authority),
        clock=_TickingClock(as_of + timedelta(minutes=1)),
    )


def _risk_handlers(
    authority: ConfirmationFixture,
) -> tuple[LifecycleStageHandler, ...]:
    return tuple(
        _risk_handler(authority)
        if stage_name is LifecycleStageName.RISK_REDUCTION
        else ManualConfirmationStageHandler(repository=authority.repository)
        if stage_name is LifecycleStageName.MANUAL_CONFIRMATION
        else ManualTradeStageHandler(repository=authority.repository)
        if stage_name is LifecycleStageName.MANUAL_TRADE
        else _NeverCalledHandler(stage_name)
        for stage_name in LIFECYCLE_STAGE_ORDER
    )


def _settled_output_hashes(history) -> dict[LifecycleStageName, tuple[str, ...]]:
    return {receipt.stage_name: receipt.output_hashes for receipt in history.receipts if receipt.stage_name in LIFECYCLE_STAGE_ORDER[:4]}


def _execution_counts(
    repository: SQLiteRiskReductionManualIntentRepository,
) -> tuple[int, int, int]:
    with sqlite3.connect(repository.path) as connection:
        return tuple(
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "risk_reduction_confirmation_attempts",
                "manual_trade_records",
                "manual_fills",
            )
        )


def _table_names(path: Path) -> tuple[str, ...]:
    with sqlite3.connect(path) as connection:
        return tuple(str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"))
