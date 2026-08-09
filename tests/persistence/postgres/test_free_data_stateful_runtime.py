from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path

import psycopg
import pytest

from market_regime_alpha.application.continuous_research.composition import (
    FreeDataPreparationInvocation,
)
from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
)
from market_regime_alpha.application.continuous_research.free_data_runtime import (
    CanonicalFreeDataProvider,
    CanonicalFreeDataResearchComposition,
    ControlledRuntimeModelSelector,
)
from market_regime_alpha.application.continuous_research.journal import (
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
from market_regime_alpha.application.decision_system.research_summary import (
    ResearchDailySummaryOutcome,
    ResearchStageResult,
    ResearchStageStatus,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    publish_controlled_runtime_configuration,
)
from market_regime_alpha.application.controlled_operation.outcome_evidence import (
    TradeHorizonDefinition,
    build_trade_horizon_outcome_evidence,
)
from market_regime_alpha.application.controlled_operation.outcome_source_archive import (
    OutcomeRawSourcePayload,
    OutcomeSettlementSourceArchive,
    RECORDED_OUTCOME_BARS_SOURCE_KIND,
    encode_recorded_outcome_bars,
    load_outcome_settlement_source_archive,
    publish_outcome_settlement_source_archive,
)
from market_regime_alpha.application.controlled_operation.postgres_prospective_outcome import (
    PostgresProspectiveOutcomeRepository,
    ProspectiveOutcomeConflict,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    SettlementSessionStatus,
)
from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)
from market_regime_alpha.application.free_data_operation import (
    FreeDataInstrument,
    FreeDataOperationScale,
    FreeDataOperationService,
    FreeDataPreparationRequest,
)
from market_regime_alpha.application.operational_research.contracts import (
    CapitalObservationEvidence,
    ETFThemeMappingEvidence,
    PITThemeMembershipEvidence,
    StatefulETFObservationEvidence,
    SupplementalResearchEvidenceBundle,
    ThemeObservationEvidence,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    publish_supplemental_research_evidence,
)
from market_regime_alpha.application.runtime_operations.observability import (
    PostgresRuntimeObservability,
)
from market_regime_alpha.application.runtime_operations.disaster_recovery import (
    backup_restore_verify,
)
from market_regime_alpha.application.runtime_operations.query import (
    CanonicalDagNodeType,
    PostgresCanonicalRuntimeQuery,
)
from market_regime_alpha.application.research_evaluation import (
    EvaluationSampleDisposition,
    FrozenResearchEvaluationDataset,
    PostgresResearchEvaluationDatasetRepository,
    build_evaluation_decision_slice,
    publish_research_evaluation_dataset,
)
from market_regime_alpha.application.shadow_research import (
    PostgresShadowResearchRepository,
    ShadowResearchConflict,
    ShadowSessionCommand,
    ShadowSessionStatus,
)
from market_regime_alpha.application.state_system.runtime import (
    StateResearchStage,
)
from market_regime_alpha.core.identity import ArtifactId, FeatureDefinitionId, ProviderId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility, SourceArtifactReference
from market_regime_alpha.data.providers.public_composite import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    BaoStockFreeSupplementalClient,
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeBatch,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    TencentFreeOperationalProfile,
)
from market_regime_alpha.data.free_operational_policy import (
    canonical_free_operational_evidence_policy,
)
from market_regime_alpha.data.source_manifest import SourceFieldFinality, SourceManifest
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting.path import (
    PATH_FORECAST_SAMPLE_SCHEMA,
    PathForecastSample,
)
from market_regime_alpha.forecasting.sample_provider import PathForecastSampleBatch
from market_regime_alpha.market_data import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    FormalPitStatus,
    MarketDataDatasetArtifact,
    PriceAdjustmentPolicy,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
    load_verified_market_data_dataset,
    publish_market_data_dataset,
)
from market_regime_alpha.market_data.minute_source import (
    MinuteSourceRequest,
    MinuteSourceResponse,
)
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.repository_factory import RepositoryFactory
from market_regime_alpha.persistence.settings import DatabaseSettings
from market_regime_alpha.research.platform_v2.inputs import (
    ETFObservation,
    MarketObservation,
    SymbolResearchObservation,
)
from market_regime_alpha.strategies.entry.contracts import (
    EntryPathObservationStatus,
    EntryPathReasonCode,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.signals.decimal_model import SignalModelConfigurationV2
from tests.application.daily_loop.public_fixture import DECISION
from tests.application.daily_loop.test_runner import _qualified_stage_clients
from tests.persistence.postgres.conftest import TEST_DATABASE_URL_ENV
from tests.persistence.postgres.test_free_data_continuous_runtime import (
    _calendar,
    _configuration,
    _qualify_runtime_models,
    _tick,
)


@pytest.mark.parametrize(
    (
        "authority_mode",
        "liquidity_eligible",
        "watch_only",
        "crash_before_summary",
        "expected_outcome",
        "operational_producer",
    ),
    (
        (
            RuntimeAuthorityMode.RESEARCH,
            True,
            False,
            False,
            ResearchDailySummaryOutcome.RESEARCH_CANDIDATE,
            True,
        ),
        (
            RuntimeAuthorityMode.SHADOW,
            True,
            False,
            False,
            ResearchDailySummaryOutcome.RESEARCH_CANDIDATE,
            True,
        ),
        (
            RuntimeAuthorityMode.RESEARCH,
            False,
            False,
            False,
            ResearchDailySummaryOutcome.NO_ACTION,
            False,
        ),
        (
            RuntimeAuthorityMode.RESEARCH,
            True,
            True,
            False,
            ResearchDailySummaryOutcome.WATCH,
            False,
        ),
        (
            RuntimeAuthorityMode.RESEARCH,
            True,
            False,
            True,
            ResearchDailySummaryOutcome.RESEARCH_CANDIDATE,
            True,
        ),
    ),
)
def test_real_stateful_positive_path_reaches_research_candidate(
    tmp_path: Path,
    postgres_factory: PostgresConnectionFactory,
    monkeypatch: pytest.MonkeyPatch,
    authority_mode: RuntimeAuthorityMode,
    liquidity_eligible: bool,
    watch_only: bool,
    crash_before_summary: bool,
    expected_outcome: ResearchDailySummaryOutcome,
    operational_producer: bool,
) -> None:
    policy, history, status, quote = _qualified_stage_clients()
    if operational_producer:
        quote.batch = replace(
            quote.batch,
            quotes=tuple(
                replace(
                    item,
                    previous_close=10.0,
                    open_price=10.1,
                    high_price=10.4,
                    low_price=10.3,
                    change_fraction=0.04,
                )
                for item in quote.batch.quotes
            ),
        )
    calendar = _calendar()
    configuration = _outcome_configuration(calendar, watch_only=watch_only)
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
    decision = DECISION.value.astimezone(UTC)
    runtime_now = [decision - timedelta(seconds=1)]
    evidence_policy = canonical_free_operational_evidence_policy()
    evidence_policy = replace(
        evidence_policy,
        themes=tuple(
            replace(item, effective_from=DECISION.value.date())
            for item in evidence_policy.themes
        ),
    )
    etf_history = _RecordedEtfHistoryClient(runtime_now)
    minute_calls: list[tuple[str, datetime, datetime]] = []

    def minute_factory(symbol: str, _attempt: int, _timeout: float):
        return _MinuteClient(symbol, runtime_now, minute_calls)

    def advance(seconds: float) -> None:
        runtime_now[0] += timedelta(seconds=seconds)

    service = FreeDataOperationService(
        repositories=repositories,
        output_root=tmp_path / "stateful-runtime",
        code_revision="free-data-stateful-e2e",
        clock=lambda: runtime_now[0],
        live_profile=TencentFreeOperationalProfile(
            history_client=history,
            security_status_client=status,
            current_client=quote,
            supplemental_client=(
                BaoStockFreeSupplementalClient(
                    history_client=etf_history,
                    policy=evidence_policy,
                    provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
                    clock=lambda: runtime_now[0],
                )
                if operational_producer
                else None
            ),
        ),
        minute_client_factory=minute_factory,
        sleeper=advance,
        forecast_sample_provider=_HistoricalSampleProvider(decision),
        operational_supplemental_policy=(
            evidence_policy if operational_producer else None
        ),
    )
    captured_executions = []
    original_service_run = service.run

    def record_service_execution(*args, **kwargs):
        execution = original_service_run(*args, **kwargs)
        captured_executions.append(execution)
        return execution

    monkeypatch.setattr(service, "run", record_service_execution)
    free_request = FreeDataPreparationRequest(
        scale=FreeDataOperationScale.SMOKE,
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        decision_time=DECISION,
        created_at=decision,
        code_revision="free-data-stateful-e2e",
        instruments=tuple(
            FreeDataInstrument(symbol=symbol, asset_type=AssetType.A_SHARE)
            for symbol in policy.symbols
        ),
        membership_source="CANONICAL_STATEFUL_E2E",
        minimum_history_sessions=21,
        liquidity_lookback_sessions=21,
        minimum_median_daily_amount=Decimal("1"),
        configuration_hash=configuration.configuration_hash,
    )
    supplemental_path = publish_supplemental_research_evidence(
        root=tmp_path / "supplemental",
        bundle=_complete_supplemental(
            policy.symbols,
            decision,
            liquidity_eligible=liquidity_eligible,
        ),
    )
    continuous_policy = default_continuous_decision_window_policy()
    command = ContinuousResearchCommand.create(
        idempotency_key=f"free-data-stateful-positive-e2e-{authority_mode.value}",
        trading_date=DECISION.value.date(),
        requested_symbols=policy.symbols,
        trading_calendar_id=calendar.artifact_id,
        trading_calendar_hash=calendar.content_hash,
        policy_id=continuous_policy.policy_id,
        policy_hash=continuous_policy.content_hash,
        provider_configuration_id=ArtifactId("canonical-free-data-profile-v1"),
        provider_configuration_hash=canonical_hash(
            {"profile": TENCENT_FREE_OPERATIONAL_PROFILE_ID}
        ),
        research_configuration_id=configuration.configuration_id,
        research_configuration_hash=configuration.configuration_hash,
        code_revision="free-data-stateful-e2e",
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
        supplemental_evidence_path=(
            None if operational_producer else supplemental_path
        ),
    )
    runtime_now[0] = decision - timedelta(minutes=25)
    service.prepare_static_sources(
        request=free_request,
        runtime_configuration_path=configuration_path,
    )
    runtime_now[0] = decision - timedelta(seconds=1)
    service.prepare(
        request=free_request,
        runtime_configuration_path=configuration_path,
        idempotency_key=invocation.idempotency_key,
        supplemental_evidence_path=invocation.supplemental_evidence_path,
    )
    _qualify_runtime_models(
        repositories=repositories,
        configuration=configuration,
        purpose=authority_mode.runtime_purpose,
        observed=decision,
        code_revision="free-data-stateful-e2e",
    )
    provider = CanonicalFreeDataProvider(
        service=service,
        invocation_builder=lambda _: invocation,
        clock=lambda: runtime_now[0],
    )
    journal = repositories.continuous_research(clock=lambda: runtime_now[0])
    summary_repository = repositories.decision_system(
        clock=lambda: runtime_now[0]
    )
    state_repository = repositories.state_system(clock=lambda: runtime_now[0])

    def build_runner() -> ContinuousResearchTickRunner:
        composition = CanonicalFreeDataResearchComposition(
            service=service,
            invocation_builder=lambda _: invocation,
            model_selector=ControlledRuntimeModelSelector(
                repositories.model_governance()
            ),
            summary_repository=summary_repository,
            state_repository=state_repository,
            clock=lambda: runtime_now[0],
        )
        return ContinuousResearchTickRunner(
            journal=journal,
            provider=provider,
            children=composition,
            policy=continuous_policy,
            clock=lambda: runtime_now[0],
        )

    runner = build_runner()
    tick = _tick(command, "positive")
    provider_request = ProviderAcquisitionRequest(
        provider_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        product="BAOSTOCK_TENCENT_CANONICAL_FREE_DATA",
        request_hash=free_request.command_hash,
        provider_revision="canonical-free-data-profile-v1",
    )

    if crash_before_summary:
        original_save = summary_repository.save_research_summary

        def simulated_process_crash(*args, **kwargs):
            raise _SimulatedProcessCrash

        monkeypatch.setattr(
            summary_repository,
            "save_research_summary",
            simulated_process_crash,
        )
        with pytest.raises(_SimulatedProcessCrash):
            runner.execute(
                run_command=command,
                tick_command=tick,
                provider_request=provider_request,
            )
        calls_before_restart = tuple(minute_calls)
        monkeypatch.setattr(
            summary_repository,
            "save_research_summary",
            original_save,
        )
        runtime_now[0] += timedelta(seconds=31)
        result = build_runner().execute(
            run_command=command,
            tick_command=tick,
            provider_request=provider_request,
        )
        assert tuple(minute_calls) == calls_before_restart
    else:
        result = runner.execute(
            run_command=command,
            tick_command=tick,
            provider_request=provider_request,
        )

    assert result.tick.status is ContinuousTickStatus.COMPLETED, result.tick.last_error
    summary = repositories.decision_system().get_research_summary_for_tick(
        run_id=command.run_id,
        tick_id=tick.tick_id,
        runtime_mode=authority_mode,
    )
    assert summary.outcome is expected_outcome
    state_child = next(
        item
        for item in result.child_references
        if item.child_kind is ContinuousChildKind.STATE_SYSTEM
    )
    assert summary.state_system_receipt.artifact_id == state_child.child_receipt_id
    assert summary.state_system_receipt.content_hash == state_child.child_receipt_hash
    assert summary.candidate_set is not None
    assert summary.created_at >= decision
    by_stage = {item.stage: item for item in summary.stages}
    assert all(item.status is ResearchStageStatus.COMPLETED for item in summary.stages)
    if liquidity_eligible:
        assert by_stage[StateResearchStage.CANDIDATE].result is ResearchStageResult.RESEARCH_QUALIFIED
        expected_signal_result = (
            ResearchStageResult.WATCH
            if watch_only
            else ResearchStageResult.RESEARCH_QUALIFIED
        )
        assert by_stage[StateResearchStage.SIGNAL].result is expected_signal_result
        assert by_stage[StateResearchStage.FORECAST].result is ResearchStageResult.RESEARCH_QUALIFIED
        assert minute_calls
        assert all(started <= received <= decision for _, started, received in minute_calls)
    else:
        assert by_stage[StateResearchStage.CANDIDATE].result is ResearchStageResult.EMPTY
        assert by_stage[StateResearchStage.SIGNAL].result is ResearchStageResult.EMPTY
        assert by_stage[StateResearchStage.FORECAST].result is ResearchStageResult.EMPTY
        assert minute_calls == []
    assert by_stage[StateResearchStage.OBSERVATION].stage_completed_at < decision
    assert any(
        item.product == "ifzq.gtimg.cn:minute"
        for item in summary.provider_contracts
    ) is liquidity_eligible
    assert len({symbol for symbol, _, _ in minute_calls}) <= 5
    with postgres_factory.connection(read_only=True) as connection:
        pool_member_count = connection.execute(
            "SELECT count(*) FROM dynamic_stock_pool_member"
        ).fetchone()
    assert pool_member_count == (len(policy.symbols),)
    if liquidity_eligible:
        assert {item.child_kind for item in result.child_references} == set(
            ContinuousChildKind
        )
    assert summary.no_order and summary.no_fill and summary.no_broker
    assert summary.no_position_mutation_from_shadow
    assert summary.evidence_ceiling.value == "FREE_DATA_EXPLORATORY"
    assert replay_continuous_research(journal, command.run_id).integrity_status == "VERIFIED"
    inspection = PostgresCanonicalRuntimeQuery(
        postgres_factory, clock=lambda: runtime_now[0]
    ).inspect_run(command.run_id)
    projected_types = {item.node_type for item in inspection.nodes}
    assert {
        CanonicalDagNodeType.DATASET,
        CanonicalDagNodeType.FEATURE,
        CanonicalDagNodeType.STATE,
        CanonicalDagNodeType.POOL,
        CanonicalDagNodeType.CANDIDATE,
        CanonicalDagNodeType.SIGNAL,
        CanonicalDagNodeType.FORECAST,
        CanonicalDagNodeType.SUMMARY,
    } <= projected_types
    assert (CanonicalDagNodeType.MINUTE in projected_types) is liquidity_eligible
    trace = PostgresRuntimeObservability(
        postgres_factory, clock=lambda: runtime_now[0]
    ).trace_run(command.run_id)
    assert any(item["stage"] == "SUMMARY" for item in trace["observations"])
    assert trace["decision_input"] is False
    if authority_mode is RuntimeAuthorityMode.SHADOW:
        shadow_repository = PostgresShadowResearchRepository(
            postgres_factory, clock=lambda: runtime_now[0]
        )
        shadow_command = ShadowSessionCommand.create(
            idempotency_key=f"{command.run_id}:shadow-session",
            run_id=command.run_id,
            trading_date=command.trading_date,
            runtime_mode=RuntimeAuthorityMode.SHADOW,
            scheduled_at=decision - timedelta(minutes=25),
            operator_observation="RECORDED_PROVIDER_ENGINEERING_EVIDENCE",
        )
        with postgres_factory.connection(read_only=True) as connection:
            before_trade_counts = connection.execute(
                "SELECT (SELECT count(*) FROM manual_fills), "
                "(SELECT count(*) FROM position_book_events)"
            ).fetchone()
        shadow_session = shadow_repository.schedule(shadow_command)
        shadow_session = shadow_repository.mark_running(
            shadow_command.session_id,
            expected_version=shadow_session.version,
        )
        frozen = shadow_repository.freeze(
            shadow_command.session_id,
            summary_id=summary.summary_id,
            decision_frozen_at=summary.created_at,
            expected_version=shadow_session.version,
        )
        with pytest.raises(ShadowResearchConflict, match="status/version CAS"):
            shadow_repository.mark_outcome_pending(
                shadow_command.session_id,
                expected_version=shadow_session.version,
            )
        frozen_session = shadow_repository.get_session(shadow_command.session_id)
        pending = shadow_repository.mark_outcome_pending(
            shadow_command.session_id,
            expected_version=frozen_session.version,
        )
        assert pending.status is ShadowSessionStatus.OUTCOME_PENDING
        assert shadow_repository.replay(frozen.decision_id) == frozen
        assert frozen.no_order and frozen.no_fill and frozen.no_broker
        assert frozen.no_position_mutation
        assert captured_executions
        execution = captured_executions[-1]
        assert execution.decision is not None
        selected_symbols = tuple(
            item.symbol for item in execution.decision.candidate_set.selected
        )
        settlement_dataset, source_archive = _recorded_outcome_dataset(
            tmp_path=tmp_path,
            symbols=selected_symbols,
            decision_time=summary.decision_time,
        )
        next_session_date = summary.trading_date + timedelta(days=1)
        factual_outcome = build_trade_horizon_outcome_evidence(
            operation_package=execution.decision.package,
            candidate_set=execution.decision.candidate_set,
            signal=execution.decision.signal,
            forecasts=execution.decision.forecasts,
            decision_dataset=(
                execution.preparation.controlled_preparation.daily_dataset
            ),
            settlement_dataset=settlement_dataset,
            next_session_date=next_session_date,
            horizon=TradeHorizonDefinition.create(include_session_close=False),
            created_at=source_archive.created_at,
        )
        outcome_repository = PostgresProspectiveOutcomeRepository(
            postgres_factory, clock=lambda: source_archive.created_at
        )
        outcome = outcome_repository.build(
            decision_id=frozen.decision_id,
            source_archive=source_archive,
            settlement_dataset=settlement_dataset,
            factual_evidence=factual_outcome,
            next_session_date=next_session_date,
            session_status=SettlementSessionStatus.TRADING_DAY,
            created_at=source_archive.created_at,
        )
        with pytest.raises(
            ProspectiveOutcomeConflict,
            match="status/version CAS",
        ):
            outcome_repository.settle(
                outcome,
                expected_shadow_version=pending.version - 1,
            )
        settled = outcome_repository.settle(
            outcome, expected_shadow_version=pending.version
        )
        assert settled == outcome
        assert settled.availability_status is OutcomeAvailabilityStatus.COMPLETE
        assert all(item.price_1000 is not None for item in settled.observations)
        assert outcome_repository.settle(
            outcome, expected_shadow_version=pending.version
        ) == outcome
        assert outcome_repository.replay(
            outcome.settlement_id,
            source_archive=source_archive,
            settlement_dataset=settlement_dataset,
            factual_evidence=factual_outcome,
        ) == outcome
        evaluation_slice = build_evaluation_decision_slice(
            decision=frozen,
            outcome=outcome,
            candidate_set=execution.decision.candidate_set,
        )
        evaluation_dataset = FrozenResearchEvaluationDataset.create(
            protocol_id="exploratory-shadow-evaluation-v1",
            protocol_hash=canonical_hash(
                {
                    "inclusion": "SELECTED_CANDIDATE_WITH_SETTLED_OUTCOME",
                    "version": 1,
                }
            ),
            slices=(evaluation_slice,),
            created_at=source_archive.created_at,
        )
        evaluation_path = publish_research_evaluation_dataset(
            root=tmp_path / "evaluation-datasets",
            dataset=evaluation_dataset,
        )
        evaluation_repository = PostgresResearchEvaluationDatasetRepository(
            postgres_factory,
            clock=lambda: source_archive.created_at,
        )
        assert evaluation_repository.register(
            evaluation_dataset,
            artifact_path=evaluation_path,
        ) == evaluation_dataset
        assert evaluation_repository.replay(
            evaluation_dataset.dataset_id
        ) == evaluation_dataset
        assert evaluation_dataset.included_count == len(selected_symbols)
        assert all(
            item.disposition is EvaluationSampleDisposition.INCLUDED
            for item in evaluation_slice.samples
        )
        recovery = backup_restore_verify(
            source_factory=postgres_factory,
            database_url=os.environ[TEST_DATABASE_URL_ENV],
            artifact_root=tmp_path / "stateful-runtime",
            backup_root=tmp_path / "dr-backup",
            verified_at=source_archive.created_at,
            table_names=(
                "capital_state",
                "continuous_research_run",
                "continuous_runtime_tick",
                "dynamic_stock_pool",
                "dynamic_stock_pool_member",
                "etf_rotation_state",
                "formal_pit_validation_evidence",
                "market_regime_state",
                "model_runtime_assignment",
                "prospective_outcome_settlement",
                "research_daily_summary",
                "research_evaluation_dataset",
                "state_runtime_candidate_artifact",
                "theme_rotation_state",
            ),
        )
        assert recovery.migration_head == 37
        assert recovery.continuous_replay_hashes == (
            (
                str(command.run_id),
                replay_continuous_research(journal, command.run_id).replay_hash,
            ),
        )
        assert recovery.source_artifacts.content_hash == (
            recovery.restored_artifacts.content_hash
        )
        with postgres_factory.connection() as connection, pytest.raises(
            psycopg.errors.RaiseException,
            match="research_evaluation_dataset is append-only",
        ):
            connection.execute(
                "UPDATE research_evaluation_dataset "
                "SET dataset_hash = %s WHERE dataset_id = %s",
                (
                    canonical_hash({"forged": "evaluation"}),
                    str(evaluation_dataset.dataset_id),
                ),
            )
        with postgres_factory.connection() as connection, pytest.raises(
            psycopg.errors.RaiseException,
            match="prospective_outcome_settlement is append-only",
        ):
            connection.execute(
                "UPDATE prospective_outcome_settlement "
                "SET settlement_hash = %s WHERE settlement_id = %s",
                (canonical_hash({"forged": True}), str(outcome.settlement_id)),
            )
        with postgres_factory.connection(read_only=True) as connection:
            after_trade_counts = connection.execute(
                "SELECT (SELECT count(*) FROM manual_fills), "
                "(SELECT count(*) FROM position_book_events)"
            ).fetchone()
        assert after_trade_counts == before_trade_counts
        with postgres_factory.connection() as connection:
            with pytest.raises(psycopg.errors.RaiseException):
                connection.execute(
                    "UPDATE shadow_research_decision SET payload_json = payload_json "
                    "WHERE decision_id = %s",
                    (str(frozen.decision_id),),
                )
    if operational_producer:
        assert etf_history.calls == 1
        assert any(
            item.product == "query_history_k_data_plus:daily:adjustflag=3"
            and item.provider_id == str(BAOSTOCK_PUBLIC_PROVIDER_ID)
            for item in summary.provider_contracts
        )

    restarted = runner.execute(
        run_command=command,
        tick_command=tick,
        provider_request=provider_request,
    )
    assert restarted.child_references == result.child_references
    assert len(minute_calls) == len({symbol for symbol, _, _ in minute_calls})
    if operational_producer:
        assert etf_history.calls == 1


class _SimulatedProcessCrash(BaseException):
    """Bypass ordinary Exception handling to model abrupt process loss."""


def _recorded_outcome_dataset(
    *,
    tmp_path: Path,
    symbols: tuple[str, ...],
    decision_time: datetime,
):
    next_session_date = decision_time.astimezone(DECISION.value.tzinfo).date() + timedelta(
        days=1
    )
    source_id = ArtifactId("recorded-shadow-outcome-source-v1")
    placeholder_hash = canonical_hash({"recorded-shadow-outcome": "placeholder"})

    def bars(source_hash: str) -> tuple[CanonicalMarketBar, ...]:
        result: list[CanonicalMarketBar] = []
        for symbol in symbols:
            exchange = Exchange.SH if symbol.endswith(".SH") else Exchange.SZ
            start = datetime.combine(
                next_session_date,
                datetime.min.time().replace(hour=9, minute=30),
                tzinfo=DECISION.value.tzinfo,
            ).astimezone(UTC)
            for index in range(60):
                price = Decimal("10") + Decimal(index) / Decimal("100")
                result.append(
                    CanonicalMarketBar.create(
                        symbol=symbol,
                        exchange=exchange,
                        asset_type=AssetType.A_SHARE,
                        timeframe=Timeframe.MINUTE_1,
                        market_date=next_session_date,
                        event_start=start + timedelta(minutes=index),
                        event_end=start + timedelta(minutes=index + 1),
                        available_at=start + timedelta(minutes=index + 1),
                        open=price,
                        high=price + Decimal("0.02"),
                        low=price - Decimal("0.02"),
                        close=price + Decimal("0.01"),
                        previous_close=None,
                        volume=Decimal("1000"),
                        volume_unit=VolumeUnit.SHARES,
                        amount=Decimal("10000"),
                        turnover_rate=None,
                        adjustment_mode=AdjustmentMode.RAW,
                        adjustment_factor=Decimal("1"),
                        trading_status=TradingStatus.TRADING,
                        price_limit_state=PriceLimitState.NORMAL,
                        source_artifact_id=source_id,
                        source_content_hash=source_hash,
                    )
                )
        return tuple(result)

    raw_payload = encode_recorded_outcome_bars(bars(placeholder_hash))
    source_hash = "sha256:" + sha256(raw_payload).hexdigest()
    canonical_bars = bars(source_hash)
    assert encode_recorded_outcome_bars(canonical_bars) == raw_payload
    retrieved = max(item.available_at for item in canonical_bars) + timedelta(
        seconds=1
    )
    manifest = SourceManifest(
        provider_profile_id="RECORDED_OUTCOME_ENGINEERING_V1",
        decision_time=DecisionTime(retrieved),
        source_artifacts=(
            SourceArtifactReference(
                artifact_id=source_id,
                provider_id=ProviderId("provider-recorded-outcome-engineering"),
                retrieved_at=RetrievedAt(retrieved),
                content_hash=source_hash,
                locator="recorded://shadow-outcome/t-plus-one-minute",
            ),
        ),
        fields=(),
        source_conflicts=(),
        limitations=(
            "ENGINEERING_RECORDED_ONLY",
            "NOT_PROSPECTIVE_EVIDENCE",
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=SourceManifest.SCHEMA_V2,
    )
    artifact = MarketDataDatasetArtifact.create(
        decision_time=retrieved,
        created_at=retrieved,
        bars=canonical_bars,
        expected_symbols=symbols,
        expected_timeframes=(Timeframe.MINUTE_1,),
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="recorded-shadow-outcome-raw-v1",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=(
            (manifest.source_manifest_id, manifest.content_hash),
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=(
            "ENGINEERING_RECORDED_ONLY",
            "NOT_PROSPECTIVE_EVIDENCE",
        ),
    )
    dataset_path = publish_market_data_dataset(
        root=tmp_path / "recorded-outcome-dataset", artifact=artifact
    )
    archive = OutcomeSettlementSourceArchive.create(
        source_manifest=manifest,
        next_session_date=next_session_date,
        raw_payloads=(
            OutcomeRawSourcePayload(
                source_artifact_id=source_id,
                source_kind=RECORDED_OUTCOME_BARS_SOURCE_KIND,
                media_type="application/json",
                payload=raw_payload,
            ),
        ),
        created_at=retrieved,
    )
    archive_path = publish_outcome_settlement_source_archive(
        root=tmp_path / "recorded-outcome-archive",
        artifact=archive,
        raw_payloads=(
            OutcomeRawSourcePayload(
                source_artifact_id=source_id,
                source_kind=RECORDED_OUTCOME_BARS_SOURCE_KIND,
                media_type="application/json",
                payload=raw_payload,
            ),
        ),
    )
    return (
        load_verified_market_data_dataset(dataset_path),
        load_outcome_settlement_source_archive(archive_path),
    )


class _RecordedEtfHistoryClient:
    def __init__(self, runtime_now: list[datetime]) -> None:
        self._runtime_now = runtime_now
        self.calls = 0

    def acquire(self, request) -> PublicCompositeBatch:
        self.calls += 1
        source = AcquiredSourcePayload(
            provider_id=BAOSTOCK_PUBLIC_PROVIDER_ID,
            product="query_history_k_data_plus:daily:adjustflag=3",
            locator="recorded://baostock/etf/510300.SH",
            raw_payload=b"recorded-provider-etf-history-v1",
            retrieved_time=RetrievedAt(self._runtime_now[0]),
            limitations=("RECORDED_PROVIDER_ENGINEERING_EVIDENCE",),
        )
        bars = tuple(
            PublicBar(
                symbol="510300.SH",
                event_time=request.decision_time.value
                - timedelta(days=25 - index),
                available_time=None,
                source_artifact_id=source.source_artifact_id,
                open=4.0 + index * 0.01,
                high=4.05 + index * 0.01,
                low=3.95 + index * 0.01,
                close=4.02 + index * 0.01,
                volume=10_000_000 + index * 100_000,
                amount=100_000_000 + index * 1_000_000,
                unit="CNY",
                adjustment_basis="BAOSTOCK_ADJUSTFLAG_3",
                finality=SourceFieldFinality.UNKNOWN,
            )
            for index in range(21)
        )
        return PublicCompositeBatch(
            raw_payloads=(source,),
            bars=bars,
            quotes=(),
            source_conflicts=(),
            limitations=("RECORDED_PROVIDER_ENGINEERING_EVIDENCE",),
        )


def _outcome_configuration(
    calendar,
    *,
    watch_only: bool,
) -> ControlledOperationRuntimeConfiguration:
    configuration = _configuration(calendar)
    if not watch_only:
        return configuration
    watch_signal = SignalModelConfigurationV2.create(
        configuration_version="free-data-watch-only-e2e-v1",
        price_action_min_return=Decimal("1"),
        volume_confirmation_min_ratio=Decimal("100"),
        trend_confirmation_min_return=Decimal("1"),
        vwap_min_relative_return=Decimal("1"),
        overheat_max_return=Decimal("100"),
        minimum_confirmations=4,
    )
    return ControlledOperationRuntimeConfiguration.create(
        static_feature_set=configuration.static_feature_set,
        intraday_feature_set=configuration.intraday_feature_set,
        research=configuration.research,
        signal_model=watch_signal,
        signal_mapping=configuration.signal_mapping,
        signal_requirement=configuration.signal_requirement,
        signal_freshness=configuration.signal_freshness,
        path_forecast=configuration.path_forecast,
        feature_max_workers=configuration.feature_max_workers,
        minute_concurrency_limit=configuration.minute_concurrency_limit,
        minute_per_request_timeout_seconds=(
            configuration.minute_per_request_timeout_seconds
        ),
        minute_max_attempts=configuration.minute_max_attempts,
        minute_retry_backoff_seconds=(
            configuration.minute_retry_backoff_seconds
        ),
        provider_profile_id=configuration.provider_profile_id,
        limitations=configuration.limitations,
    )


def _complete_supplemental(
    symbols: tuple[str, ...],
    decision: datetime,
    *,
    liquidity_eligible: bool = True,
) -> SupplementalResearchEvidenceBundle:
    decision_time = DecisionTime(decision)
    available = AvailabilityTime(decision - timedelta(seconds=10))
    source_id = ArtifactId("free-supplemental-positive-source-v1")
    source_manifest = SourceManifest(
        provider_profile_id="FREE_SUPPLEMENTAL_EXPLICIT_V1",
        decision_time=decision_time,
        source_artifacts=(
            SourceArtifactReference(
                artifact_id=source_id,
                provider_id=ProviderId("provider-free-supplemental-explicit"),
                retrieved_at=RetrievedAt(available.value),
                content_hash=canonical_hash({"free-supplemental": "positive"}),
                locator="postgres://free-supplemental/positive-v1",
            ),
        ),
        fields=(),
        source_conflicts=(),
        limitations=("FREE_DATA_EXPLORATORY", "FORMAL_PIT_NOT_ESTABLISHED"),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=SourceManifest.SCHEMA_V2,
    )
    theme = ThemeObservationEvidence(
        theme_id="theme-positive",
        theme_name="Positive Theme",
        benchmark_id="000300.SH",
        proxy_etf_ids=("510001.SH",),
        available_at=available,
        source_artifact_id=source_id,
        relative_strength_1d=0.08,
        relative_strength_3d=0.10,
        relative_strength_5d=0.12,
        relative_strength_10d=0.15,
        amount_expansion=0.60,
        breadth=0.85,
        new_high_breadth=0.70,
        leader_strength=0.90,
        participation_change=0.50,
        rank_persistence=0.90,
        confidence=1.0,
        reason_codes=("FREE_SUPPLEMENTAL_POSITIVE",),
    )
    capital = CapitalObservationEvidence(
        theme_id=theme.theme_id,
        available_at=available,
        source_artifact_id=source_id,
        etf_amount_expansion=0.70,
        amount_persistence=0.85,
        capital_concentration=0.60,
        diffusion_score=0.80,
        reason_codes=("PUBLIC_PROXY_NOT_ACTOR_INTENT",),
    )
    return SupplementalResearchEvidenceBundle(
        source_manifest=source_manifest,
        decision_time=decision_time,
        market_observation=MarketObservation(
            available_at=available,
            source_artifact_id=source_id,
            market_direction_return=0.03,
            market_intraday_range_to_cutoff=0.01,
            market_amount_change_same_cutoff=0.50,
            candidate_breadth_at_cutoff=0.90,
            limit_structure_score=0.50,
            coverage=1.0,
            reason_codes=("FREE_SUPPLEMENTAL_POSITIVE",),
        ),
        theme_observations=(theme,),
        capital_observations=(capital,),
        symbol_observations=tuple(
            SymbolResearchObservation(
                symbol=symbol,
                available_at=available,
                source_artifact_id=source_id,
                symbol_relative_strength=0.30,
                symbol_amount_expansion=0.50,
                theme_participation_contribution=0.40,
                leader_correlation=0.80,
                leader_lag=0.0,
                rank_persistence=0.90,
                amount_persistence=0.80,
                liquidity_eligible=liquidity_eligible,
                history_complete=True,
                status_known=True,
                source_feature_ids=(FeatureDefinitionId("free-symbol-positive-v1"),),
                reason_codes=("FREE_SUPPLEMENTAL_POSITIVE",),
            )
            for symbol in symbols
        ),
        theme_memberships=tuple(
            PITThemeMembershipEvidence(
                symbol=symbol,
                primary_theme_id=theme.theme_id,
                supporting_theme_ids=(),
                available_at=available,
                source_artifact_id=source_id,
            )
            for symbol in symbols
        ),
        etf_theme_mappings=(
            ETFThemeMappingEvidence(
                etf_id="510001.SH",
                theme_id=theme.theme_id,
                available_at=available,
                source_artifact_id=source_id,
            ),
        ),
        etf_observations=(
            ETFObservation(
                etf_id="510001.SH",
                theme_id=theme.theme_id,
                available_at=available,
                source_artifact_id=source_id,
                relative_strength=0.30,
                amount_expansion=0.50,
            ),
        ),
        stock_daily_bars=(),
        missing_evidence=(),
        reason_codes=("EXPLICIT_FREE_SUPPLEMENTAL_COMPLETE",),
        created_at=available.value,
        data_eligibility=DataEligibility.EXPLORATORY,
        stateful_etf_observations=(
            StatefulETFObservationEvidence(
                etf_id="510001.SH",
                benchmark_id="000300.SH",
                available_at=available,
                source_artifact_id=source_id,
                relative_strength_1d=0.30,
                relative_strength_3d=0.35,
                relative_strength_5d=0.40,
                relative_strength_10d=0.45,
                benchmark_excess=0.30,
                amount_change=0.70,
                amount_persistence=0.90,
                volume_change=0.60,
                drawdown=0.05,
                volatility=0.10,
                diffusion=0.90,
                liquidity=1.0,
                data_coverage=1.0,
                reason_codes=("FREE_SUPPLEMENTAL_POSITIVE",),
            ),
        ),
    )


class _MinuteClient:
    def __init__(
        self,
        symbol: str,
        runtime_now: list[datetime],
        calls: list[tuple[str, datetime, datetime]],
    ) -> None:
        self._symbol = symbol
        self._runtime_now = runtime_now
        self._calls = calls

    def fetch(self, request: MinuteSourceRequest) -> MinuteSourceResponse:
        observed = self._runtime_now[0]
        self._calls.append((self._symbol, observed, observed))
        code = f"{self._symbol[-2:].lower()}{self._symbol[:6]}"
        rows = [
            f"{1440 + index:04d} {10 + index / 100:.3f} "
            f"{1000 + index * 100} {100000 + index * 10000}"
            for index in range(15)
        ]
        payload = json.dumps(
            {
                "code": 0,
                "data": {
                    code: {
                        "data": {
                            "date": request.decision_time.strftime("%Y%m%d"),
                            "data": rows,
                        }
                    }
                },
            },
            separators=(",", ":"),
        ).encode()
        return MinuteSourceResponse(
            request=request,
            request_started_at=observed,
            response_received_at=observed,
            http_status=200,
            content_type="application/json",
            raw_payload=payload,
            provider_timestamp=request.decision_time.strftime("%Y%m%d"),
            limitations=("ENGINEERING_POSITIVE_PATH",),
        )


class _HistoricalSampleProvider:
    def __init__(self, decision: datetime) -> None:
        self._decision = decision

    def load_samples(self, *, signal_snapshot, configuration, decision_time):
        samples = tuple(
            PathForecastSample(
                sample_id=ArtifactId(
                    f"free-path-sample-{signal_snapshot.symbol}-{index:02d}"
                ),
                source_artifact_id=ArtifactId(
                    f"free-path-outcome-{signal_snapshot.symbol}-{index:02d}"
                ),
                source_content_hash=canonical_hash(
                    {"symbol": signal_snapshot.symbol, "sample": index}
                ),
                symbol=signal_snapshot.symbol,
                target_id=configuration.target_contract.target_id,
                sample_decision_time=DecisionTime(
                    self._decision - timedelta(days=40 - index)
                ),
                available_at=AvailabilityTime(
                    self._decision - timedelta(days=39 - index)
                ),
                observation_status=EntryPathObservationStatus.AVAILABLE,
                observation_reason_code=EntryPathReasonCode.OUTCOME_RESOLVED,
                realized_mfe=0.04 + index / 1000,
                realized_mae=-0.01,
                realized_return=0.02 + index / 2000,
                schema_version=PATH_FORECAST_SAMPLE_SCHEMA,
            )
            for index in range(configuration.minimum_usable_samples)
        )
        return PathForecastSampleBatch(
            samples=samples,
            reason_codes=("EXPLORATORY_HISTORICAL_SAMPLES_BOUND",),
            limitations=("FORMAL_OOS_NOT_ESTABLISHED",),
        )
