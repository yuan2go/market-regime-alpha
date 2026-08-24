from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market_regime_alpha.application.continuous_research.composition import (
    FreeDataPreparationInvocation,
)
from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.free_data_runtime import (
    CanonicalFreeDataProvider,
    CanonicalFreeDataResearchComposition,
    ControlledRuntimeModelSelector,
    FREE_DATA_MODEL_SLOTS,
)
from market_regime_alpha.application.continuous_research.journal import (
    ChangeDecisionType,
    ChildReferenceDisposition,
    ContinuousChildKind,
    ContinuousTickStatus,
)
from market_regime_alpha.application.continuous_research.policy import (
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.ports import (
    ProviderAcquisitionRequest,
)
from market_regime_alpha.application.continuous_research.replay import (
    replay_continuous_research,
)
from market_regime_alpha.application.continuous_research.runner import (
    ContinuousResearchTickRunner,
)
from market_regime_alpha.application.continuous_research.postgres_daily_alpha import (
    PostgresDailyAlphaEvidenceGateResolver,
    PostgresDailyAlphaOwnerResolver,
    PostgresDailyAlphaPredictionAuthority,
)
from market_regime_alpha.application.continuous_research.scheduler import (
    TradingDayAssessment,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    publish_controlled_runtime_configuration,
)
from market_regime_alpha.application.controlled_operation.research_config import (
    ControlledCandidateDiscoveryConfig,
    ControlledResearchPipelineConfig,
)
from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)
from market_regime_alpha.application.decision_system.research_summary import (
    ResearchDailySummaryOutcome,
    ResearchStageStatus,
)
from market_regime_alpha.application.free_data_operation import (
    FreeDataInstrument,
    FreeDataOperationScale,
    FreeDataOperationService,
    FreeDataPreparationRequest,
)
from market_regime_alpha.application.governance.access_control import (
    PostgresAccessGovernance,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.state_system.runtime import StateResearchStage
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_contracts import PITSourceEvidenceLevel
from market_regime_alpha.data.providers.public_composite import (
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    TencentFreeOperationalProfile,
)
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.features.technical.catalog import (
    intraday_overlay_feature_set,
    static_technical_feature_set,
)
from market_regime_alpha.market_data import AssetType
from market_regime_alpha.forecasting.sample_provider import (
    HistoricalRegistryPathForecastSampleProvider,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.repository_factory import RepositoryFactory
from market_regime_alpha.persistence.settings import DatabaseSettings
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    ModelDefinition,
    ModelLifecycleStatus,
    ModelRole,
)
from market_regime_alpha.platform.durable_governance import PersistentModelRegistry
from market_regime_alpha.platform.runtime_governance import (
    ArtifactLineageReference,
    AssignmentLane,
    ModelGovernancePolicy,
    ModelQualificationEvidence,
    ModelVersionLineage,
    QualificationEvidenceKind,
    QualificationEvidenceOutcome,
    RuntimeAuthorityMode,
    RuntimePurpose,
)
from market_regime_alpha.signals import (
    canonical_all_factors_required_policy,
    canonical_signal_freshness_policy,
    canonical_signal_input_mapping_v2,
    canonical_signal_model_configuration_v2,
)
from market_regime_alpha.cli import continuous_research as continuous_cli
from tests.application.daily_loop.public_fixture import DECISION
from tests.application.daily_loop.test_runner import _qualified_stage_clients
from tests.persistence.postgres.test_free_data_operation import _path_config
from tests.persistence.postgres.conftest import TEST_DATABASE_URL_ENV
from tests.persistence.postgres.pit_fixture import record_calendar_owner


SHANGHAI = ZoneInfo("Asia/Shanghai")


@pytest.mark.parametrize(
    "authority_mode",
    (
        RuntimeAuthorityMode.RESEARCH,
        RuntimeAuthorityMode.SHADOW,
        RuntimeAuthorityMode.PRODUCTION,
    ),
)
def test_canonical_free_data_runtime_reaches_summary_and_replays(
    tmp_path: Path,
    postgres_factory: PostgresConnectionFactory,
    authority_mode: RuntimeAuthorityMode,
) -> None:
    policy, history, status, quote = _qualified_stage_clients()
    calendar = _calendar()
    calendar_reference = record_calendar_owner(
        postgres_factory,
        calendar=calendar,
        clock=DECISION.value.astimezone(UTC),
        idempotency_key=f"free-data-calendar-{authority_mode.value}",
    )
    target_session = calendar.trading_dates[
        calendar.trading_dates.index(DECISION.value.date()) + 1
    ]
    configuration = _configuration(calendar)
    configuration_path = publish_controlled_runtime_configuration(
        root=tmp_path / "runtime-configurations",
        artifact=configuration,
    )
    repositories = RepositoryFactory(
        DatabaseSettings.from_sources(
            database_url=os.environ[TEST_DATABASE_URL_ENV],
            application_schema=postgres_factory.application_schema,
            environ={},
        ),
        postgres_factory=postgres_factory,
    )
    observed = DECISION.value.astimezone(UTC)
    runtime_clock = [observed]
    service = FreeDataOperationService(
        repositories=repositories,
        output_root=tmp_path / "canonical-runtime",
        code_revision="free-data-continuous-e2e",
        clock=lambda: runtime_clock[0],
        live_profile=TencentFreeOperationalProfile(
            history_client=history,
            security_status_client=status,
            current_client=quote,
        ),
    )
    free_request = FreeDataPreparationRequest(
        scale=FreeDataOperationScale.SMOKE,
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        decision_time=DECISION,
        created_at=observed,
        code_revision="free-data-continuous-e2e",
        instruments=tuple(FreeDataInstrument(symbol=symbol, asset_type=AssetType.A_SHARE) for symbol in policy.symbols),
        membership_source="CANONICAL_FREE_DATA_E2E",
        minimum_history_sessions=21,
        liquidity_lookback_sessions=21,
        minimum_median_daily_amount=Decimal("1"),
        configuration_hash=configuration.configuration_hash,
    )
    continuous_policy = default_continuous_decision_window_policy()
    command = ContinuousResearchCommand.create(
        idempotency_key=f"free-data-e2e-{authority_mode.value}",
        trading_date=DECISION.value.date(),
        requested_symbols=policy.symbols,
        trading_calendar_id=calendar.artifact_id,
        trading_calendar_hash=calendar.content_hash,
        policy_id=continuous_policy.policy_id,
        policy_hash=continuous_policy.content_hash,
        provider_configuration_id=ArtifactId("canonical-free-data-profile-v1"),
        provider_configuration_hash=canonical_hash({"profile": TENCENT_FREE_OPERATIONAL_PROFILE_ID}),
        research_configuration_id=configuration.configuration_id,
        research_configuration_hash=configuration.configuration_hash,
        code_revision="free-data-continuous-e2e",
        authority_mode=authority_mode,
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )
    invocation = FreeDataPreparationInvocation(
        request=free_request,
        runtime_configuration_path=configuration_path,
        idempotency_key=f"{command.run_id}:free-data",
    )
    runtime_clock[0] = observed - timedelta(minutes=25)
    service.prepare_static_sources(
        request=free_request,
        runtime_configuration_path=configuration_path,
    )
    assert (history.calls, status.calls, quote.calls) == (1, 1, 0)
    runtime_clock[0] = observed - timedelta(minutes=1)
    service.prepare(
        request=free_request,
        runtime_configuration_path=configuration_path,
        idempotency_key=invocation.idempotency_key,
    )
    assert (history.calls, status.calls, quote.calls) == (1, 1, 1)
    runtime_clock[0] = observed
    provider = CanonicalFreeDataProvider(
        service=service,
        invocation_builder=lambda _: invocation,
        clock=lambda: observed,
    )
    if authority_mode is not RuntimeAuthorityMode.PRODUCTION:
        _qualify_runtime_models(
            repositories=repositories,
            configuration=configuration,
            purpose=authority_mode.runtime_purpose,
            observed=observed,
            code_revision="free-data-continuous-e2e",
        )
    selected_models = ControlledRuntimeModelSelector(repositories.model_governance())
    daily_alpha_authority = PostgresDailyAlphaPredictionAuthority(
        postgres_factory,
        resolver=PostgresDailyAlphaOwnerResolver(postgres_factory),
    )
    daily_alpha_gate = PostgresDailyAlphaEvidenceGateResolver(
        postgres_factory
    ).assess
    composition = CanonicalFreeDataResearchComposition(
        service=service,
        invocation_builder=lambda _: invocation,
        model_selector=selected_models,
        summary_repository=repositories.decision_system(clock=lambda: observed),
        state_repository=repositories.state_system(clock=lambda: observed),
        strategy_repository=repositories.multi_strategy(),
        daily_alpha_authority=daily_alpha_authority,
        daily_alpha_evidence_gate=daily_alpha_gate,
        target_session_date=target_session,
        target_calendar_reference=calendar_reference,
        clock=lambda: observed,
    )
    journal = repositories.continuous_research(clock=lambda: observed)
    runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=provider,
        children=composition,
        policy=continuous_policy,
        clock=lambda: observed,
    )
    first_tick = _tick(command, "first")
    request = ProviderAcquisitionRequest(
        provider_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        product="BAOSTOCK_TENCENT_CANONICAL_FREE_DATA",
        request_hash=free_request.command_hash,
        provider_revision="canonical-free-data-profile-v1",
    )

    first = runner.execute(
        run_command=command,
        tick_command=first_tick,
        provider_request=request,
    )

    if authority_mode is RuntimeAuthorityMode.PRODUCTION:
        assert first.tick.status is ContinuousTickStatus.FAILED
        assert first.reason_codes == (
            "ENTRY_BLOCKED",
            "FREE_DATA_PRODUCTION_AUTHORITY_DENIED",
        )
        assert first.child_references == ()
        with pytest.raises(KeyError):
            repositories.decision_system().get_research_summary_for_tick(
                run_id=command.run_id,
                tick_id=first_tick.tick_id,
                runtime_mode=authority_mode,
            )
        assert (history.calls, status.calls, quote.calls) == (1, 1, 1)
        return

    assert first.tick.status is ContinuousTickStatus.COMPLETED
    summary = repositories.decision_system().get_research_summary_for_tick(
        run_id=command.run_id,
        tick_id=first_tick.tick_id,
        runtime_mode=authority_mode,
    )
    assert summary.outcome is ResearchDailySummaryOutcome.DATA_INSUFFICIENT
    assert summary.evidence_ceiling is PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY
    assert summary.data_eligibility is DataEligibility.EXPLORATORY
    assert summary.provider_profile_id == TENCENT_FREE_OPERATIONAL_PROFILE_ID
    assert all(contract.product != "ifzq.gtimg.cn:minute" for contract in summary.provider_contracts)
    assert summary.state_system_receipt.reference_kind == "STATE_SYSTEM_RECEIPT"
    assert summary.candidate_set is not None
    strategy_repository = repositories.multi_strategy()
    registry = strategy_repository.load_registry()
    strategy_cycle = strategy_repository.get_cycle_for_tick(
        run_id=command.run_id,
        tick_id=first_tick.tick_id,
    )
    assert {item.strategy_version_reference.artifact_id for item in strategy_cycle.runs} == set(registry.active_version_ids)
    assert {item.child_kind for item in first.child_references} >= {
        ContinuousChildKind.STRATEGY_RUNTIME,
        ContinuousChildKind.DAILY_ALPHA_SNAPSHOT,
    }
    daily_child = next(
        item
        for item in first.child_references
        if item.child_kind is ContinuousChildKind.DAILY_ALPHA_SNAPSHOT
    )
    assert daily_child.child_artifact_id is not None
    daily_snapshot = daily_alpha_authority.get(daily_child.child_artifact_id)
    assert "EVIDENCE_DEPENDENCY_NOT_SATISFIED" in daily_snapshot.reason_codes
    assert all(
        item.validated_alpha_contributions == ()
        and item.conditional_forecast.availability_status == "NOT_AVAILABLE"
        and "CONDITIONAL_FORECAST_OWNER_NOT_AVAILABLE" in item.reason_codes
        for item in daily_snapshot.symbols
    )
    assert all(
        item.path_forecast is None
        or (
            item.path_forecast.forecast_status
            in {"AVAILABLE_FOR_RESEARCH", "DATA_INSUFFICIENT"}
            and item.path_forecast.calibration_status
            in {"NOT_CALIBRATED", "DATA_INSUFFICIENT"}
        )
        for item in daily_snapshot.symbols
    )
    assert summary.no_order and summary.no_fill and summary.no_broker
    assert summary.no_position_mutation_from_shadow
    by_stage = {stage.stage: stage for stage in summary.stages}
    assert by_stage[StateResearchStage.ETF_ROTATION].status is ResearchStageStatus.DATA_INSUFFICIENT
    assert by_stage[StateResearchStage.THEME_ROTATION].status is ResearchStageStatus.DATA_INSUFFICIENT
    assert by_stage[StateResearchStage.CAPITAL_STATE].status is ResearchStageStatus.DATA_INSUFFICIENT
    assert len(summary.model_selection_receipts) == 6
    assert all(
        repositories.model_governance().get_selection_receipt(reference.artifact_id).purpose is authority_mode.runtime_purpose
        for reference in summary.model_selection_receipts
    )
    assert replay_continuous_research(journal, command.run_id).integrity_status == "VERIFIED"

    # A fresh composition recovers the immutable Summary without FreeData calls.
    restarted = ContinuousResearchTickRunner(
        journal=journal,
        provider=CanonicalFreeDataProvider(
            service=service,
            invocation_builder=lambda _: invocation,
            clock=lambda: observed,
        ),
        children=CanonicalFreeDataResearchComposition(
            service=service,
            invocation_builder=lambda _: invocation,
            model_selector=selected_models,
            summary_repository=repositories.decision_system(clock=lambda: observed),
            state_repository=repositories.state_system(clock=lambda: observed),
            strategy_repository=repositories.multi_strategy(),
            daily_alpha_authority=daily_alpha_authority,
            daily_alpha_evidence_gate=daily_alpha_gate,
            target_session_date=target_session,
            target_calendar_reference=calendar_reference,
            clock=lambda: observed,
        ),
        policy=continuous_policy,
        clock=lambda: observed,
    ).execute(
        run_command=command,
        tick_command=first_tick,
        provider_request=request,
    )
    assert restarted.child_references == first.child_references
    assert (history.calls, status.calls, quote.calls) == (1, 1, 1)

    # Same material identity on a new Tick reuses every immutable child Artifact.
    second_tick = _tick(command, "no-material-change")
    second = runner.execute(
        run_command=command,
        tick_command=second_tick,
        provider_request=request,
    )
    assert second.decision is not None
    assert second.decision.decision_type is ChangeDecisionType.NO_MATERIAL_CHANGE
    assert all(item.reference_disposition is ChildReferenceDisposition.REUSED for item in second.child_references)
    assert {item.child_artifact_id for item in second.child_references} == {item.child_artifact_id for item in first.child_references}


@pytest.mark.parametrize(
    "authority_mode",
    (RuntimeAuthorityMode.SHADOW, RuntimeAuthorityMode.PRODUCTION),
)
def test_actual_selector_uses_mode_specific_slots_and_persists_rejections(
    tmp_path: Path,
    postgres_factory: PostgresConnectionFactory,
    authority_mode: RuntimeAuthorityMode,
) -> None:
    policy, history, status, quote = _qualified_stage_clients()
    calendar = _calendar()
    configuration = _configuration(calendar)
    configuration_path = publish_controlled_runtime_configuration(
        root=tmp_path / "runtime-configurations",
        artifact=configuration,
    )
    settings = DatabaseSettings.from_sources(
        database_url=os.environ[TEST_DATABASE_URL_ENV],
        application_schema=postgres_factory.application_schema,
        environ={},
    )
    repositories = RepositoryFactory(settings, postgres_factory=postgres_factory)
    observed = DECISION.value.astimezone(UTC)
    service = FreeDataOperationService(
        repositories=repositories,
        output_root=tmp_path / "selector-runtime",
        code_revision="selector-purpose-e2e",
        clock=lambda: observed,
        live_profile=TencentFreeOperationalProfile(
            history_client=history,
            security_status_client=status,
            current_client=quote,
        ),
    )
    free_request = FreeDataPreparationRequest(
        scale=FreeDataOperationScale.SMOKE,
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        decision_time=DECISION,
        created_at=observed,
        code_revision="selector-purpose-e2e",
        instruments=tuple(FreeDataInstrument(symbol=symbol, asset_type=AssetType.A_SHARE) for symbol in policy.symbols),
        membership_source="SELECTOR_PURPOSE_E2E",
        minimum_history_sessions=21,
        liquidity_lookback_sessions=21,
        minimum_median_daily_amount=Decimal("1"),
        configuration_hash=configuration.configuration_hash,
    )
    preparation = service.prepare(
        request=free_request,
        runtime_configuration_path=configuration_path,
        idempotency_key="selector-purpose-e2e",
    )
    command = _continuous_command(
        policy.symbols,
        calendar,
        configuration,
        authority_mode,
    )
    journal = repositories.continuous_research(clock=lambda: observed)
    journal.create_or_get(command)
    tick = _tick(command, "selector")
    journal.admit_tick(
        tick,
        session_phase=default_continuous_decision_window_policy()
        .assess(
            trading_date=command.trading_date,
            observed_at=observed,
        )
        .session_phase,
    )
    claim = journal.claim_tick(run_id=command.run_id, tick_id=tick.tick_id)
    child_request = _child_request_from_claim(command, claim, observed)

    governed = ControlledRuntimeModelSelector(repositories.model_governance()).select(
        request=child_request,
        preparation=preparation,
        runtime_configuration_path=(preparation.controlled_preparation.input_paths.runtime_configuration),
    )

    assert len(governed.receipts) == 6
    assert not governed.all_selected
    assert {stage for stage, _ in governed.receipts} == set(FREE_DATA_MODEL_SLOTS)
    assert all(
        receipt.purpose is authority_mode.runtime_purpose and "CHAMPION_AUTHORITY_MISSING" in receipt.reason_codes
        for _, receipt in governed.receipts
    )
    assert all(repositories.model_governance().get_selection_receipt(receipt.receipt_id) == receipt for _, receipt in governed.receipts)

    if authority_mode is RuntimeAuthorityMode.PRODUCTION:
        assert all(receipt.production_authorized is False for _, receipt in governed.receipts)
        production_composition = CanonicalFreeDataResearchComposition(
            service=service,
            invocation_builder=lambda _: FreeDataPreparationInvocation(
                request=free_request,
                runtime_configuration_path=configuration_path,
                idempotency_key="selector-purpose-e2e",
            ),
            model_selector=ControlledRuntimeModelSelector(repositories.model_governance()),
            summary_repository=repositories.decision_system(clock=lambda: observed),
            state_repository=repositories.state_system(clock=lambda: observed),
            strategy_repository=repositories.multi_strategy(),
            clock=lambda: observed,
        )
        with pytest.raises(
            PermissionError,
            match="FREE_DATA_PRODUCTION_AUTHORITY_DENIED",
        ):
            production_composition.execute_children(child_request)
        with pytest.raises(KeyError):
            repositories.decision_system().get_research_summary_for_tick(
                run_id=command.run_id,
                tick_id=tick.tick_id,
                runtime_mode=RuntimeAuthorityMode.PRODUCTION,
            )


def test_formal_run_due_entry_executes_staged_research_summary(
    tmp_path: Path,
    postgres_factory: PostgresConnectionFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy, history, status, quote = _qualified_stage_clients()
    calendar = _calendar()
    configuration = _configuration(calendar)
    configuration_path = publish_controlled_runtime_configuration(
        root=tmp_path / "runtime-configurations",
        artifact=configuration,
    )
    command = _continuous_command(
        policy.symbols,
        calendar,
        configuration,
        RuntimeAuthorityMode.RESEARCH,
    )
    trading_day = TradingDayAssessment(
        trading_calendar_id=calendar.artifact_id,
        trading_calendar_hash=calendar.content_hash,
        trading_date=DECISION.value.date(),
        is_trading_day=True,
        reason_codes=("TRADING_DAY",),
    )
    command_path = tmp_path / "run-command.json"
    trading_day_path = tmp_path / "trading-day.json"
    command_path.write_text(json.dumps(command.to_canonical_dict()), encoding="utf-8")
    trading_day_path.write_text(json.dumps(trading_day.to_canonical_dict()), encoding="utf-8")
    monkeypatch.setattr(continuous_cli, "BaoStockHistoryClient", lambda **_: history)
    monkeypatch.setattr(
        continuous_cli,
        "BaoStockSecurityStatusClient",
        lambda **_: status,
    )
    monkeypatch.setattr(
        continuous_cli,
        "TencentCurrentQuoteClient",
        lambda **_: quote,
    )
    historical_minutes = _HistoricalMinuteProvider()
    monkeypatch.setattr(continuous_cli, "BaoStockADataProvider", lambda: historical_minutes)
    authority = [
        "--database-url",
        os.environ[TEST_DATABASE_URL_ENV],
        "--application-schema",
        postgres_factory.application_schema,
    ]
    admin = PostgresAccessGovernance(postgres_factory).bootstrap_admin(
        external_subject="test:free-runtime-cli-admin",
        display_name="Free Runtime CLI Admin",
        reason="CLI authorization fixture",
        occurred_at=datetime(2025, 2, 3, 5, 0, tzinfo=UTC),
        idempotency_key="free-runtime-cli-admin",
    )
    authority.extend(("--principal-id", str(admin.principal_id)))
    common = [
        *authority,
        "run-due",
        "--run-command",
        str(command_path),
        "--trading-day-assessment",
        str(trading_day_path),
        "--runtime-configuration",
        str(configuration_path),
        "--output-root",
        str(tmp_path / "formal-runtime"),
        "--minimum-median-daily-amount",
        "1",
        "--runtime-clock-mode",
        "SIMULATED",
    ]

    assert continuous_cli.main([*common, "--at", "2025-02-03T14:30:00+08:00"]) == 0
    preparing = json.loads(capsys.readouterr().out)
    assert preparing["status"] == "PREPARING"
    assert (history.calls, status.calls, quote.calls) == (1, 1, 0)

    assert continuous_cli.main([*common, "--at", "2025-02-03T14:54:00+08:00"]) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed["status"] == "COMPLETED", json.dumps(completed, sort_keys=True)
    assert completed["daily_decision_window_summary_delivered"] is True
    assert completed["summary_outcome"] == "MODEL_NOT_QUALIFIED_FOR_MODE"
    assert completed["path_forecast_registry_wired"] is True
    assert completed["historical_sample_build"]["qualification"] == "UNQUALIFIED"
    assert completed["historical_sample_build"]["evidence_class"] == "FREE_DATA_EXPLORATORY"
    assert completed["historical_sample_build"]["sample_count"] >= 20 * len(policy.symbols)
    assert completed["entry_authority_granted"] is False
    assert completed["broker_authority_granted"] is False
    assert (history.calls, status.calls, quote.calls) == (1, 1, 1)
    assert historical_minutes.calls == list(policy.symbols)
    with postgres_factory.connection(read_only=True) as connection:
        historical_kinds = dict(
            connection.execute(
                """
                SELECT artifact_kind, count(*)
                FROM research_validation_artifact
                WHERE artifact_kind IN (
                    'FREE_HISTORICAL_DECISION',
                    'FREE_HISTORICAL_MULTI_HORIZON_OUTCOME',
                    'HISTORICAL_SAMPLE_DATASET'
                )
                GROUP BY artifact_kind
                """
            ).fetchall()
        )
    assert historical_kinds == {
        "FREE_HISTORICAL_DECISION": completed["historical_sample_build"]["decision_count"],
        "FREE_HISTORICAL_MULTI_HORIZON_OUTCOME": completed["historical_sample_build"]["outcome_count"],
        "HISTORICAL_SAMPLE_DATASET": 1,
    }

    registry_provider = HistoricalRegistryPathForecastSampleProvider(
        PostgresResearchValidationRepository(postgres_factory, apply_migrations=False)
    )
    sample_batch = registry_provider.load_samples(
        signal_snapshot=SimpleNamespace(symbol=policy.symbols[0]),
        configuration=configuration.path_forecast,
        decision_time=DECISION,
    )
    assert len(sample_batch.samples) >= 20
    assert "HISTORICAL_SAMPLE_DATASET_LOADED" in sample_batch.reason_codes
    assert "HISTORICAL_SAMPLE_QUALIFICATION_UNQUALIFIED" in sample_batch.limitations


def _calendar():
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("free-data-continuous-calendar"),
        market="A_SHARE",
        calendar_version="free-data-continuous-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            *tuple(
                TradingSession(
                    trade_date=(DECISION.value.date() - timedelta(days=offset)),
                    session_close=datetime.combine(
                        DECISION.value.date() - timedelta(days=offset),
                        time(15),
                        tzinfo=SHANGHAI,
                    ),
                )
                for offset in range(30, -1, -1)
            ),
            TradingSession(
                trade_date=DECISION.value.date() + timedelta(days=1),
                session_close=datetime.combine(
                    DECISION.value.date() + timedelta(days=1),
                    time(15),
                    tzinfo=SHANGHAI,
                ),
            ),
        ),
    )


class _HistoricalMinuteProvider:
    name = "baostock-test-history"
    data_source = "baostock-test-history"
    is_realtime = False

    def __init__(self) -> None:
        self.calls: list[str] = []

    def minute_bars(self, symbol: str, **kwargs):
        del kwargs
        self.calls.append(symbol)
        rows = []
        for offset in range(35, 0, -1):
            session_date = DECISION.value.date() - timedelta(days=offset)
            for observed_time in (
                time(9, 35),
                time(9, 45),
                time(10),
                time(10, 30),
                time(11, 30),
                time(14, 55),
                time(15),
            ):
                rows.append(
                    {
                        "symbol": symbol,
                        "timestamp": datetime.combine(session_date, observed_time, tzinfo=SHANGHAI),
                        "open": 10.0,
                        "high": 10.1,
                        "low": 9.9,
                        "close": 10.0,
                    }
                )
        return pd.DataFrame(rows)


def _configuration(calendar) -> ControlledOperationRuntimeConfiguration:
    return ControlledOperationRuntimeConfiguration.create(
        static_feature_set=static_technical_feature_set(effective_from=(DECISION.value - timedelta(days=365)).astimezone(UTC)),
        intraday_feature_set=intraday_overlay_feature_set(effective_from=(DECISION.value - timedelta(days=365)).astimezone(UTC)),
        research=ControlledResearchPipelineConfig.create(
            candidate_discovery=ControlledCandidateDiscoveryConfig.create(
                top_n=5,
                minimum_candidate_population=5,
            )
        ),
        signal_model=canonical_signal_model_configuration_v2(),
        signal_mapping=canonical_signal_input_mapping_v2(effective_from=(DECISION.value - timedelta(days=365)).astimezone(UTC)),
        signal_requirement=canonical_all_factors_required_policy(),
        signal_freshness=canonical_signal_freshness_policy(trading_calendar=calendar),
        path_forecast=_path_config(),
    )


def _tick(command: ContinuousResearchCommand, suffix: str) -> RuntimeTickCommand:
    return RuntimeTickCommand.create(
        idempotency_key=f"{command.run_id}:{suffix}",
        run_id=command.run_id,
        trading_date=command.trading_date,
        observed_at=DECISION.value.astimezone(UTC),
        request_scope_hash=command.request_scope_hash,
        provider_configuration_id=command.provider_configuration_id,
        provider_configuration_hash=command.provider_configuration_hash,
        research_configuration_id=command.research_configuration_id,
        research_configuration_hash=command.research_configuration_hash,
    )


def _qualify_runtime_models(
    *,
    repositories: RepositoryFactory,
    configuration: ControlledOperationRuntimeConfiguration,
    purpose: RuntimePurpose,
    observed: datetime,
    code_revision: str,
) -> None:
    repository = repositories.model_governance()
    registry = PersistentModelRegistry(repository)
    policy = ModelGovernancePolicy.create(
        name=f"free-data-{purpose.value.lower()}-e2e",
        version="1",
        purpose=purpose,
        allowed_lifecycle_statuses=(ModelLifecycleStatus.RESEARCH,),
        required_evidence_kinds=(QualificationEvidenceKind.DATASET_INTEGRITY,),
        allowed_data_eligibilities=(DataEligibility.EXPLORATORY,),
        production_authorization=False,
    )
    repository.record_policy(
        policy,
        actor="e2e-governance",
        reason="real mode-specific positive-path authority",
        created_at=observed - timedelta(minutes=10),
        idempotency_key=f"policy-{purpose.value}",
    )
    configured = {
        StateResearchStage.MARKET_REGIME: configuration.research.market_regime,
        StateResearchStage.THEME_ROTATION: configuration.research.theme_rotation,
        StateResearchStage.CAPITAL_STATE: configuration.research.capital_evolution,
        StateResearchStage.CANDIDATE: configuration.research.candidate_discovery,
        StateResearchStage.SIGNAL: configuration.signal_model,
        StateResearchStage.FORECAST: configuration.path_forecast,
    }
    for stage, slot in FREE_DATA_MODEL_SLOTS.items():
        model = configured[stage]
        feature_ids = (
            ()
            if stage
            in {
                StateResearchStage.MARKET_REGIME,
                StateResearchStage.THEME_ROTATION,
                StateResearchStage.CAPITAL_STATE,
            }
            else (FeatureDefinitionId(f"e2e-{stage.value.lower()}-feature-v1"),)
        )
        definition = ModelDefinition(
            model_id=model.model_id,
            name=f"FreeData {stage.value} E2E",
            version=model.model_version,
            family="free-data-canonical-e2e",
            role=(ModelRole.CONTEXT if not feature_ids else ModelRole.CANDIDATE),
            target_id=TargetId("free-data-e2e-target-v1"),
            universe_id=UniverseId("free-data-e2e-universe-v1"),
            feature_ids=feature_ids,
            implementation_ref=f"market_regime_alpha.e2e:{stage.value.lower()}",
            parameter_hash=model.configuration_hash,
            decision_time_convention="14:55 Asia/Shanghai",
            horizon="research-only",
            supported_data_eligibilities=(DataEligibility.EXPLORATORY,),
        )
        registered = registry.register(
            definition,
            idempotency_key=f"register-{purpose.value}-{stage.value}",
        )
        research = registry.transition(
            definition.model_id,
            expected_version=registered.version,
            idempotency_key=f"research-{purpose.value}-{stage.value}",
            to_status=ModelLifecycleStatus.RESEARCH,
            changed_at=observed - timedelta(minutes=9),
            reason="explicit Research/Shadow engineering qualification",
            evidence_refs=(f"e2e:{purpose.value}:{stage.value}",),
            evidence_level=EvidenceLevel.EXPLORATORY,
        )
        protocol = ArtifactLineageReference(
            "VALIDATION_PROTOCOL",
            ArtifactId(f"free-data-{purpose.value.lower()}-protocol-v1"),
            canonical_hash({"protocol": purpose.value}),
        )
        lineage = repository.record_version_lineage(
            ModelVersionLineage.create(
                model_id=definition.model_id,
                model_version=definition.version,
                definition_hash=definition.definition_hash,
                target_id=definition.target_id,
                universe_contract_id=definition.universe_id,
                feature_definition_ids=definition.feature_ids,
                model_parameter_hash=definition.parameter_hash,
                configuration=ArtifactLineageReference(
                    "MODEL_CONFIGURATION",
                    model.configuration_id,
                    model.configuration_hash,
                ),
                implementation_ref=definition.implementation_ref,
                code_revision=code_revision,
                code_hash=canonical_hash({"code_revision": code_revision}),
                validation_protocol_refs=(protocol,),
                supported_data_eligibilities=definition.supported_data_eligibilities,
                created_at=observed - timedelta(minutes=8),
            ),
            actor="e2e-governance",
            reason="bind actual Runtime model/config version",
            idempotency_key=f"lineage-{purpose.value}-{stage.value}",
        )
        repository.record_evidence(
            ModelQualificationEvidence.create(
                model_id=definition.model_id,
                definition_hash=definition.definition_hash,
                lineage_id=lineage.lineage_id,
                lineage_hash=lineage.lineage_hash,
                evidence_kind=QualificationEvidenceKind.DATASET_INTEGRITY,
                outcome=QualificationEvidenceOutcome.SATISFIED,
                evidence=ArtifactLineageReference(
                    "DATASET_INTEGRITY",
                    ArtifactId(f"e2e-evidence-{purpose.value.lower()}-{stage.value.lower()}"),
                    canonical_hash({"evidence": purpose.value, "stage": stage.value}),
                ),
                validation_protocol_ref=protocol,
                available_at=observed - timedelta(minutes=7),
                recorded_at=observed - timedelta(minutes=7),
                actor="e2e-reviewer",
                reason="positive-path engineering evidence",
            ),
            idempotency_key=f"evidence-{purpose.value}-{stage.value}",
        )
        repository.qualify(
            model_id=definition.model_id,
            policy_id=policy.policy_id,
            actor="e2e-reviewer",
            reason="approve mode-specific exploratory execution",
            approval_ref=f"e2e:{purpose.value}:{stage.value}",
            decided_at=observed - timedelta(minutes=6),
            expected_registry_version=research.version,
            idempotency_key=f"qualify-{purpose.value}-{stage.value}",
        )
        repository.assign(
            runtime_scope="CONTROLLED_OPERATION",
            model_slot=slot,
            purpose=purpose,
            lane=AssignmentLane.CHAMPION,
            model_id=definition.model_id,
            policy_id=policy.policy_id,
            expected_governance_revision=repository.current_revision(),
            effective_at=observed - timedelta(minutes=5),
            actor="e2e-governance",
            reason="mode-specific positive-path Champion",
            approval_ref=f"e2e-assignment:{purpose.value}:{stage.value}",
            idempotency_key=f"assign-{purpose.value}-{stage.value}",
        )


def _continuous_command(symbols, calendar, configuration, authority_mode):
    policy = default_continuous_decision_window_policy()
    return ContinuousResearchCommand.create(
        idempotency_key=f"selector-{authority_mode.value}",
        trading_date=DECISION.value.date(),
        requested_symbols=symbols,
        trading_calendar_id=calendar.artifact_id,
        trading_calendar_hash=calendar.content_hash,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        provider_configuration_id=ArtifactId("selector-provider-config"),
        provider_configuration_hash=canonical_hash({"provider": "selector"}),
        research_configuration_id=configuration.configuration_id,
        research_configuration_hash=configuration.configuration_hash,
        code_revision="selector-purpose-e2e",
        authority_mode=authority_mode,
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )


def _child_request_from_claim(command, claim, observed):
    from market_regime_alpha.application.continuous_research.journal import (
        RuntimeArtifactReference,
    )
    from market_regime_alpha.application.continuous_research.ports import (
        ChildExecutionRequest,
    )

    digest = canonical_hash({"fixture": "child-request"})
    return ChildExecutionRequest(
        trading_date=command.trading_date,
        as_of_time=observed,
        run_id=command.run_id,
        tick_id=claim.tick_id,
        tick_sequence=claim.tick_sequence,
        claim_id=claim.claim_id,
        fencing_token=claim.fencing_token,
        tick_version=claim.tick_version,
        lease_acquired_at=claim.lease_acquired_at,
        lease_expires_at=claim.lease_expires_at,
        heartbeat_at=claim.heartbeat_at,
        provider_attempt_id=1,
        source_manifest_id=ArtifactId("selector-source-manifest"),
        source_manifest_hash=digest,
        evidence_commit_id=ArtifactId("selector-evidence"),
        evidence_commit_hash=digest,
        decision_id=ArtifactId("selector-decision"),
        decision_hash=digest,
        input_references=(RuntimeArtifactReference("EVIDENCE", ArtifactId("selector-input"), digest),),
        configuration_references=(
            RuntimeArtifactReference("CONFIGURATION", configuration_id(command), command.research_configuration_hash),
        ),
        authority_mode=command.authority_mode,
    )


def configuration_id(command):
    return command.research_configuration_id
