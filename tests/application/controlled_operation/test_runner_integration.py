from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.canonical_lifecycle.runner import (
    LifecycleStageExecutionError,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import LifecycleRun
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleStageName,
)
from market_regime_alpha.application.controlled_operation import (
    ControlledOperationCommand,
    DecisionTimeOperationRunStatus,
    default_decision_time_operation_policy,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    publish_controlled_runtime_configuration,
    publish_controlled_source_manifest,
    publish_controlled_trading_calendar,
)
from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledOperationalEvidencePackage,
    load_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.research_config import (
    ControlledCandidateDiscoveryConfig,
    ControlledResearchPipelineConfig,
)
from market_regime_alpha.application.controlled_operation.replay import (
    _validate_stage_receipt_bindings,
    replay_controlled_operation,
)
from market_regime_alpha.application.controlled_operation.outcome_source_archive import (
    OutcomeRawSourcePayload,
    OutcomeSettlementSourceArchive,
    RECORDED_OUTCOME_BARS_SOURCE_KIND,
    decode_recorded_outcome_bars,
    encode_recorded_outcome_bars,
    publish_outcome_settlement_source_archive,
)
from market_regime_alpha.application.controlled_operation.runner import (
    ControlledDecisionTimeOperationRunner,
    ControlledOperationDataBlocked,
    ControlledOperationInputPaths,
    ControlledOperationSettlementInputPaths,
)
from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)
from market_regime_alpha.application.controlled_operation.sqlite_journal import (
    SQLiteDecisionTimeOperationJournal,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    publish_supplemental_research_evidence,
)
from market_regime_alpha.cli.replay_controlled_operation import main as replay_cli
from market_regime_alpha.cli.report_controlled_operation import main as report_cli
from market_regime_alpha.cli.settle_controlled_operation import main as settle_cli
from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId, ProviderId
from market_regime_alpha.core.time import DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite import (
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeBatch,
    PublicSourceAcquisitionStage,
    publish_public_source_stage_artifact,
)
from market_regime_alpha.data.source_manifest import SourceFieldFinality, SourceManifest
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.features.technical.catalog import (
    intraday_overlay_feature_set,
    static_technical_feature_set,
)
from market_regime_alpha.forecasting import PATH_FORECAST_CONFIG_SCHEMA, PathForecastConfig
from market_regime_alpha.forecasting.contracts import PathForecastStatus
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
from market_regime_alpha.signals import (
    canonical_all_factors_required_policy,
    canonical_signal_freshness_policy,
    canonical_signal_input_mapping_v2,
    canonical_signal_model_configuration_v2,
)
from market_regime_alpha.strategies.entry import EntryBarrierSpec, build_entry_path_target_contract
from market_regime_alpha.universe import (
    ListingStatus,
    OperationalLiquidityEvidence,
    OperationalUniverseArtifact,
    OperationalUniverseRecord,
    STStatus,
    SuspensionStatus,
    publish_operational_universe,
)
from tests.application.operational_research.test_bridge import _supplemental
from tests.daily_decision.conftest import DailyDecisionFixture, daily_decision_fixture


_daily_decision_fixture = daily_decision_fixture
SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc
HASH = "sha256:" + "b" * 64


def _sessions(end: date, count: int) -> tuple[date, ...]:
    values: list[date] = []
    current = end
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current)
        current -= timedelta(days=1)
    return tuple(sorted(values))


def _path_config() -> PathForecastConfig:
    return PathForecastConfig(
        profile_id="controlled-path-profile-v1",
        model_id=ModelId("empirical-path-forecast-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a-share-controlled-1455-v1",
        decision_time_local="14:55",
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        target_contract=build_entry_path_target_contract(
            EntryBarrierSpec(
                upper_return=0.03,
                lower_return=-0.02,
                horizon_sessions=5,
                price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
            )
        ),
        horizon_label="5_TRADING_SESSIONS",
        return_quantile_levels=(0.25, 0.5, 0.75),
        minimum_usable_samples=20,
        aggregation_method="EMPIRICAL_LINEAR_QUANTILE_MEAN_EXCURSION_V1",
        schema_version=PATH_FORECAST_CONFIG_SCHEMA,
    )


def _settlement_inputs(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...],
    decision_date: date,
) -> ControlledOperationSettlementInputPaths:
    session_date = decision_date + timedelta(days=1)
    minute_start = datetime.combine(session_date, time(9, 30), tzinfo=SHANGHAI).astimezone(UTC)
    available_at = datetime.combine(session_date, time(15, 1), tzinfo=SHANGHAI).astimezone(UTC)
    raw = AcquiredSourcePayload(
        provider_id=ProviderId("recorded-outcome-provider"),
        product="t-plus-one-minute-and-daily",
        locator="fixture://controlled/t-plus-one",
        raw_payload=b"immutable-recorded-t-plus-one-fixture",
        retrieved_time=RetrievedAt(available_at),
        limitations=("ENGINEERING_FIXTURE",),
    )
    minute_bars = tuple(
        CanonicalMarketBar.create(
            symbol=symbol,
            exchange=Exchange(symbol[-2:]),
            asset_type=AssetType.A_SHARE,
            timeframe=Timeframe.MINUTE_1,
            market_date=session_date,
            event_start=minute_start + timedelta(minutes=index),
            event_end=minute_start + timedelta(minutes=index + 1),
            available_at=minute_start + timedelta(minutes=index + 1),
            open=Decimal("10.00") + Decimal(index) / Decimal("1000"),
            high=Decimal("10.02") + Decimal(index) / Decimal("1000"),
            low=Decimal("9.98") + Decimal(index) / Decimal("1000"),
            close=Decimal("10.01") + Decimal(index) / Decimal("1000"),
            previous_close=None,
            volume=Decimal("1000"),
            volume_unit=VolumeUnit.SHARES,
            amount=Decimal("10000"),
            turnover_rate=None,
            adjustment_mode=AdjustmentMode.RAW,
            adjustment_factor=Decimal("1"),
            trading_status=TradingStatus.TRADING,
            price_limit_state=PriceLimitState.NORMAL,
            source_artifact_id=raw.source_artifact_id,
            source_content_hash=raw.raw_hash,
        )
        for symbol in symbols
        for index in range(60)
    )
    daily_bars = tuple(
        CanonicalMarketBar.create(
            symbol=symbol,
            exchange=Exchange(symbol[-2:]),
            asset_type=AssetType.A_SHARE,
            timeframe=Timeframe.DAILY,
            market_date=session_date,
            event_start=minute_start,
            event_end=datetime.combine(session_date, time(15), tzinfo=SHANGHAI).astimezone(UTC),
            available_at=available_at,
            open=Decimal("10.00"),
            high=Decimal("10.40"),
            low=Decimal("9.80"),
            close=Decimal("10.20"),
            previous_close=Decimal("9.90"),
            volume=Decimal("1000000"),
            volume_unit=VolumeUnit.SHARES,
            amount=Decimal("10000000"),
            turnover_rate=None,
            adjustment_mode=AdjustmentMode.RAW,
            adjustment_factor=Decimal("1"),
            trading_status=TradingStatus.TRADING,
            price_limit_state=PriceLimitState.NORMAL,
            source_artifact_id=raw.source_artifact_id,
            source_content_hash=raw.raw_hash,
        )
        for symbol in symbols
    )
    recorded_payload = encode_recorded_outcome_bars((*minute_bars, *daily_bars))
    raw = AcquiredSourcePayload(
        provider_id=ProviderId("recorded-outcome-provider"),
        product="t-plus-one-minute-and-daily",
        locator="fixture://controlled/t-plus-one",
        raw_payload=recorded_payload,
        retrieved_time=RetrievedAt(available_at),
        limitations=("ENGINEERING_FIXTURE",),
    )
    recorded_bars = decode_recorded_outcome_bars(
        recorded_payload,
        source_artifact_id=raw.source_artifact_id,
        source_content_hash=raw.raw_hash,
    )
    manifest = SourceManifest(
        provider_profile_id="recorded-outcome-controlled-v1",
        decision_time=DecisionTime(available_at),
        source_artifacts=(raw.reference,),
        fields=(),
        source_conflicts=(),
        limitations=("ENGINEERING_FIXTURE", "FACTUAL_OUTCOME_ONLY"),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=SourceManifest.SCHEMA_V2,
    )
    manifest_path = publish_controlled_source_manifest(
        root=tmp_path / "outcome-manifests",
        artifact=manifest,
    )
    archive_payloads = (
        OutcomeRawSourcePayload(
            source_artifact_id=raw.source_artifact_id,
            source_kind=RECORDED_OUTCOME_BARS_SOURCE_KIND,
            media_type="application/json",
            payload=raw.raw_payload,
        ),
    )
    archive = OutcomeSettlementSourceArchive.create(
        source_manifest=manifest,
        next_session_date=session_date,
        raw_payloads=archive_payloads,
        created_at=available_at,
        limitations=(
            "ENGINEERING_FIXTURE",
            "FACTUAL_OUTCOME_SOURCE_ONLY",
            "PROVIDER_NOT_QUALIFIED",
        ),
    )
    archive_path = publish_outcome_settlement_source_archive(
        root=tmp_path / "outcome-source-archives",
        artifact=archive,
        raw_payloads=archive_payloads,
    )
    dataset = MarketDataDatasetArtifact.create(
        decision_time=available_at,
        created_at=available_at,
        bars=recorded_bars,
        expected_symbols=symbols,
        expected_timeframes=(Timeframe.DAILY, Timeframe.MINUTE_1),
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="outcome-raw-v1",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=((manifest.source_manifest_id, manifest.content_hash),),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("ENGINEERING_FIXTURE", "FACTUAL_OUTCOME_ONLY"),
    )
    dataset_path = publish_market_data_dataset(root=tmp_path / "outcome-datasets", artifact=dataset)
    return ControlledOperationSettlementInputPaths(
        outcome_source_archive=archive_path,
        outcome_source_manifest=manifest_path,
        outcome_dataset=dataset_path,
    )


def _input_paths(tmp_path: Path, fixture: DailyDecisionFixture):
    decision = fixture.source_manifest.decision_time.value.astimezone(UTC)
    fixture_symbols = tuple(sorted(fixture.reconciliation.population.symbols))
    generated_symbols = tuple(f"{600100 + index:06d}.SH" for index in range(80))
    symbols = tuple(sorted((*fixture_symbols, *generated_symbols)))
    sessions = _sessions(decision.date() - timedelta(days=1), 70)
    raw = AcquiredSourcePayload(
        provider_id=ProviderId("recorded-daily-provider"),
        product="daily-history",
        locator="fixture://controlled/daily-history",
        raw_payload=b"immutable-recorded-daily-history-fixture",
        retrieved_time=RetrievedAt(decision - timedelta(minutes=15)),
        limitations=("ENGINEERING_FIXTURE",),
    )
    bars = tuple(
        PublicBar(
            symbol=symbol,
            event_time=datetime.combine(session, time(15), tzinfo=SHANGHAI),
            available_time=None,
            source_artifact_id=raw.source_artifact_id,
            open=10.0 + index / 100,
            high=10.2 + index / 100,
            low=9.8 + index / 100,
            close=10.1 + index / 100,
            volume=1_000_000.0 + index * 10_000,
            amount=20_000_000.0 + index * 100_000,
            unit="CNY",
            adjustment_basis="RAW",
            finality=SourceFieldFinality.UNKNOWN,
        )
        for symbol in symbols
        for index, session in enumerate(sessions)
    )
    daily_source = publish_public_source_stage_artifact(
        root=tmp_path / "source-stages",
        stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        batch=PublicCompositeBatch(
            raw_payloads=(raw,),
            bars=bars,
            quotes=(),
            source_conflicts=(),
            limitations=("ENGINEERING_FIXTURE",),
        ),
        acquisition_key="controlled-integration-daily-source",
    )
    daily_manifest = SourceManifest(
        provider_profile_id="recorded-daily-controlled-v1",
        decision_time=DecisionTime(decision),
        source_artifacts=(raw.reference,),
        fields=(),
        source_conflicts=(),
        limitations=("ENGINEERING_FIXTURE",),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=SourceManifest.SCHEMA_V2,
    )
    daily_manifest_path = publish_controlled_source_manifest(root=tmp_path / "daily-manifests", artifact=daily_manifest)
    all_sessions = tuple(
        sorted(
            set(
                (
                    *sessions,
                    decision.date(),
                    decision.date() + timedelta(days=1),
                )
            )
        )
    )
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("recorded-calendar-source"),
        market="A_SHARE",
        calendar_version="controlled-integration-calendar-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                trade_date=item,
                session_close=datetime.combine(item, time(15), tzinfo=SHANGHAI),
            )
            for item in all_sessions
        ),
    )
    calendar_path = publish_controlled_trading_calendar(root=tmp_path / "calendars", artifact=calendar)
    universe_source = ArtifactId("controlled-integration-universe-source")
    universe = OperationalUniverseArtifact.create(
        decision_date=decision.date(),
        effective_at=decision - timedelta(hours=1),
        available_at=decision - timedelta(minutes=30),
        records=tuple(
            OperationalUniverseRecord(
                symbol=symbol,
                asset_type=AssetType.A_SHARE,
                exchange=Exchange(symbol[-2:]),
                membership_source="CONTROLLED_RECORDED_FIXTURE_NOT_SMOKE_DEFAULT",
                listing_status=ListingStatus.LISTED,
                st_status=STStatus.NOT_ST,
                suspension_status=SuspensionStatus.NOT_SUSPENDED,
                liquidity_evidence=OperationalLiquidityEvidence(
                    lookback_sessions=20,
                    observed_sessions=20,
                    median_daily_amount=Decimal("100000000"),
                    minimum_daily_amount=Decimal("50000000"),
                    available_at=decision - timedelta(minutes=31),
                    source_artifact_id=universe_source,
                    source_content_hash=HASH,
                ),
                history_sessions_observed=70,
                history_sessions_required=61,
                included=True,
                inclusion_reasons=("CONTROLLED_FIXTURE_ELIGIBLE",),
                exclusion_reasons=(),
                source_artifact_references=((universe_source, HASH),),
                data_eligibility=DataEligibility.EXPLORATORY,
            )
            for symbol in symbols
        ),
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        data_eligibility=DataEligibility.EXPLORATORY,
        source_artifact_references=((universe_source, HASH),),
        limitations=("CONTROLLED_EXPLORATORY_UNIVERSE", "FORMAL_PIT_NOT_ESTABLISHED"),
    )
    universe_path = publish_operational_universe(root=tmp_path / "universes", artifact=universe)
    base_supplemental = _supplemental(fixture)
    supplemental = replace(
        base_supplemental,
        symbol_observations=tuple(
            replace(
                base_supplemental.symbol_observations[index % len(fixture_symbols)],
                symbol=symbol,
            )
            for index, symbol in enumerate(symbols)
        ),
        theme_memberships=tuple(
            replace(
                base_supplemental.theme_memberships[index % len(fixture_symbols)],
                symbol=symbol,
            )
            for index, symbol in enumerate(symbols)
        ),
        created_at=decision,
    )
    supplemental_path = publish_supplemental_research_evidence(root=tmp_path / "supplemental", bundle=supplemental)
    configuration = ControlledOperationRuntimeConfiguration.create(
        static_feature_set=static_technical_feature_set(effective_from=decision - timedelta(days=365)),
        intraday_feature_set=intraday_overlay_feature_set(effective_from=decision - timedelta(days=365)),
        research=ControlledResearchPipelineConfig.create(
            candidate_discovery=ControlledCandidateDiscoveryConfig.create(top_n=5, minimum_candidate_population=5)
        ),
        signal_model=canonical_signal_model_configuration_v2(),
        signal_mapping=canonical_signal_input_mapping_v2(effective_from=decision - timedelta(days=365)),
        signal_requirement=canonical_all_factors_required_policy(),
        signal_freshness=canonical_signal_freshness_policy(trading_calendar=calendar),
        path_forecast=_path_config(),
        feature_max_workers=4,
        minute_concurrency_limit=5,
        minute_per_request_timeout_seconds=2,
        minute_max_attempts=2,
        minute_retry_backoff_seconds=0,
    )
    configuration_path = publish_controlled_runtime_configuration(root=tmp_path / "configurations", artifact=configuration)
    return (
        ControlledOperationInputPaths(
            trading_calendar=calendar_path,
            operational_universe=universe_path,
            daily_source_stage=daily_source,
            daily_source_manifest=daily_manifest_path,
            supplemental_research_evidence=supplemental_path,
            runtime_configuration=configuration_path,
        ),
        calendar,
        universe,
        configuration,
        decision,
    )


def _mismatched_settlement_inputs(
    tmp_path: Path,
    inputs: ControlledOperationSettlementInputPaths,
) -> ControlledOperationSettlementInputPaths:
    verified = load_verified_market_data_dataset(inputs.outcome_dataset)
    original = verified.bars[0]
    altered = CanonicalMarketBar.create(
        symbol=original.symbol,
        exchange=original.exchange,
        asset_type=original.asset_type,
        timeframe=original.timeframe,
        market_date=original.market_date,
        event_start=original.event_start,
        event_end=original.event_end,
        available_at=original.available_at,
        open=original.open,
        high=original.high + Decimal("0.001"),
        low=original.low,
        close=original.close,
        previous_close=original.previous_close,
        volume=original.volume,
        volume_unit=original.volume_unit,
        amount=original.amount,
        turnover_rate=original.turnover_rate,
        adjustment_mode=original.adjustment_mode,
        adjustment_factor=original.adjustment_factor,
        adjustment_factor_id=original.adjustment_factor_id,
        adjustment_factor_hash=original.adjustment_factor_hash,
        trading_status=original.trading_status,
        price_limit_state=original.price_limit_state,
        source_artifact_id=original.source_artifact_id,
        source_content_hash=original.source_content_hash,
    )
    expected = verified.artifact
    artifact = MarketDataDatasetArtifact.create(
        decision_time=expected.decision_time,
        created_at=expected.created_at,
        bars=(altered, *verified.bars[1:]),
        expected_symbols=expected.coverage.expected_symbols,
        expected_timeframes=expected.coverage.expected_timeframes,
        adjustment_policy=expected.adjustment_policy,
        source_manifest_references=expected.source_manifest_references,
        data_eligibility=expected.data_eligibility,
        formal_pit_status=expected.formal_pit_status,
        limitations=expected.limitations,
    )
    path = publish_market_data_dataset(
        root=tmp_path / "mismatched-outcome-datasets",
        artifact=artifact,
    )
    return replace(inputs, outcome_dataset=path)


def _minute_payload(symbol: str, market_date: date) -> bytes:
    code = f"{symbol[-2:].lower()}{symbol[:6]}"
    rows = [f"{1440 + index:04d} {10 + index / 1000:.3f} {100 + index * 100} {100000 + index * 100000}" for index in range(15)]
    return json.dumps(
        {"code": 0, "data": {code: {"data": {"date": market_date.strftime("%Y%m%d"), "data": rows}}}},
        separators=(",", ":"),
    ).encode()


class _RecordedMinuteClient:
    def __init__(self, *, symbol: str, observed_at: datetime) -> None:
        self._symbol = symbol
        self._observed_at = observed_at

    def fetch(self, request: MinuteSourceRequest) -> MinuteSourceResponse:
        return MinuteSourceResponse(
            request=request,
            request_started_at=self._observed_at,
            response_received_at=self._observed_at,
            http_status=200,
            content_type="application/json",
            raw_payload=_minute_payload(self._symbol, request.decision_time.date()),
            provider_timestamp=request.decision_time.date().strftime("%Y%m%d"),
            limitations=("ENGINEERING_FIXTURE",),
        )


class _FailingMinuteClient:
    def fetch(self, request: MinuteSourceRequest) -> MinuteSourceResponse:
        raise TimeoutError(f"recorded timeout for {request.symbol}")


def test_controlled_runner_uses_real_canonical_chain_and_is_idempotent(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
    capsys,
) -> None:
    inputs, calendar, universe, configuration, decision = _input_paths(tmp_path, daily_decision_fixture)
    policy = default_decision_time_operation_policy()
    command = ControlledOperationCommand.create(
        idempotency_key="controlled-runner-integration",
        decision_date=decision.date(),
        decision_time=decision,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        trading_calendar_id=calendar.artifact_id,
        trading_calendar_hash=calendar.content_hash,
        configuration_manifest_id=configuration.configuration_id,
        configuration_manifest_hash=configuration.configuration_hash,
        model_manifest_id=configuration.model_manifest_id,
        model_manifest_hash=configuration.model_manifest_hash,
        code_revision="controlled-integration-test",
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )
    observed = policy.decision_instant(decision.date()) - timedelta(seconds=30)
    current_time = [policy.static_ready_deadline_instant(decision.date())]
    factory_calls = 0
    wait_calls: list[float] = []
    crash_after_signal = [True]

    def factory(symbol: str, _attempt: int, _timeout: float):
        nonlocal factory_calls
        factory_calls += 1
        return _RecordedMinuteClient(symbol=symbol, observed_at=observed)

    def advance_to_decision(seconds: float) -> None:
        wait_calls.append(seconds)
        current_time[0] = policy.decision_instant(decision.date())

    def crash_once_after_signal(stage: LifecycleStageName, _run: LifecycleRun) -> None:
        if stage is LifecycleStageName.SIGNAL and crash_after_signal[0]:
            crash_after_signal[0] = False
            raise RuntimeError("SIMULATED_CONTROLLED_CANONICAL_CRASH")

    runner = ControlledDecisionTimeOperationRunner(
        journal=SQLiteDecisionTimeOperationJournal(tmp_path / "controlled-operation.sqlite3", clock=lambda: current_time[0]),
        output_root=tmp_path / "operations",
        clock=lambda: current_time[0],
        minute_client_factory=factory,
        sleeper=advance_to_decision,
        canonical_after_stage_hook=crash_once_after_signal,
    )
    runner.prepare(command=command, policy=policy, inputs=inputs)
    current_time[0] = observed
    with pytest.raises(
        LifecycleStageExecutionError,
        match="SIMULATED_CONTROLLED_CANONICAL_CRASH",
    ):
        runner.run_decision_window(command=command, policy=policy, inputs=inputs)
    calls_after_crash = factory_calls
    current_time[0] = policy.decision_instant(decision.date()) + timedelta(seconds=10)
    result = runner.resume(command=command, policy=policy, inputs=inputs)
    calls_after_first = factory_calls
    assert result.package.deadline_status == "RECOVERED_BEFORE_HARD_CUTOFF"
    current_time[0] = policy.hard_cutoff_instant(decision.date()) + timedelta(seconds=1)
    replayed_run = runner.run_decision_window(command=command, policy=policy, inputs=inputs)

    assert len(universe.symbols) == 100
    assert len(result.candidate_set.selected) == 5
    assert result.minute_coverage.succeeded_count == 5
    assert result.minute_coverage.failed_count == 0
    assert wait_calls == [30.0]
    assert calls_after_first == calls_after_crash
    assert result.package.status.value == "OUTCOME_PENDING"
    assert result.snapshot.status is DecisionTimeOperationRunStatus.OUTCOME_PENDING
    latency = {item.stage_name: item.elapsed_ms for item in result.package.stage_latencies}
    assert sum(
        latency[name]
        for name in (
            "CANDIDATE_MINUTE_ACQUISITION",
            "INTRADAY_DATASET",
            "INTRADAY_FEATURE_OVERLAY",
            "SIGNAL",
        )
    ) <= 30_000
    assert all(item.artifact.forecast.forecast_status is PathForecastStatus.DATA_INSUFFICIENT for item in result.forecasts)
    assert result.package == replayed_run.package
    assert factory_calls == calls_after_first
    settlement_inputs = _settlement_inputs(
        tmp_path,
        symbols=tuple(sorted(item.symbol for item in result.candidate_set.selected)),
        decision_date=decision.date(),
    )
    current_time[0] = datetime.combine(decision.date() + timedelta(days=1), time(15, 5), tzinfo=SHANGHAI).astimezone(UTC)
    with pytest.raises(
        ValueError,
        match="does not match immutable raw source archive",
    ):
        runner.settle(
            command=command,
            inputs=_mismatched_settlement_inputs(tmp_path, settlement_inputs),
        )
    settlement = runner.settle(command=command, inputs=settlement_inputs)
    replayed_settlement = runner.settle(command=command, inputs=settlement_inputs)

    assert settlement.package.status.value == "SETTLED"
    assert settlement.snapshot.status is DecisionTimeOperationRunStatus.SETTLED
    assert len(settlement.outcome.observations) == 5
    assert settlement.package == replayed_settlement.package
    assert settlement.longitudinal_record.outcome_status == "SETTLED"
    canonical_reference = next(
        item
        for item in settlement.package.evidence_references
        if item.reference_type == "CANONICAL_LIFECYCLE_RUN"
    )
    canonical_child = next(
        child
        for receipt in settlement.package.stage_receipts
        for child in receipt.child_run_references
        if child.reference_kind.value == "CANONICAL_LIFECYCLE_RUN"
    )
    assert canonical_child.child_receipt_hash == canonical_reference.content_hash
    expected_children: dict[str, set[tuple[str, str]]] = {}
    for receipt in settlement.package.stage_receipts:
        for child in receipt.child_run_references:
            expected_children.setdefault(child.reference_kind.value, set()).add(
                (child.child_run_id, child.child_receipt_hash)
            )
    receipt_with_child = next(
        item for item in settlement.package.stage_receipts if item.child_run_references
    )
    incomplete_package = cast(
        ControlledOperationalEvidencePackage,
        SimpleNamespace(
            evidence_references=settlement.package.evidence_references,
            supersedes_package_id=settlement.package.supersedes_package_id,
            supersedes_package_hash=settlement.package.supersedes_package_hash,
            stage_receipts=tuple(
                SimpleNamespace(
                    stage_name=item.stage_name,
                    output_references=item.output_references,
                    child_run_references=(
                        () if item is receipt_with_child else item.child_run_references
                    ),
                )
                for item in settlement.package.stage_receipts
            ),
        ),
    )
    with pytest.raises(ValueError, match="set is incomplete"):
        _validate_stage_receipt_bindings(
            incomplete_package,
            expected_children=expected_children,
        )
    canonical_database = settlement.package_path.parent.parent / "canonical-lifecycle.sqlite3"
    database_hash_before = sha256(canonical_database.read_bytes()).hexdigest()
    database_mtime_before = canonical_database.stat().st_mtime_ns
    replay = replay_controlled_operation(settlement.package_path)
    assert replay.replay_status == "STABLE"
    assert sha256(canonical_database.read_bytes()).hexdigest() == database_hash_before
    assert canonical_database.stat().st_mtime_ns == database_mtime_before
    assert not replay.network_accessed
    assert not replay.broker_invoked
    assert not replay.manual_trade_created
    assert not replay.fill_created
    assert (
        replay_cli(
            [
                "--package",
                str(settlement.package_path),
                "--sqlite-database",
                str(tmp_path / "controlled-operation.sqlite3"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["replay_status"] == "STABLE"
    assert (
        report_cli(
            [
                "--output-root",
                str(tmp_path / "operations"),
                "--database",
                str(tmp_path / "controlled-operation.sqlite3"),
                "--run-id",
                str(command.run_id),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["outcome_status"] == "SETTLED"
    assert (
        settle_cli(
            [
                "--output-root",
                str(tmp_path / "operations"),
                "--database",
                str(tmp_path / "controlled-operation.sqlite3"),
                "--run-id",
                str(command.run_id),
                "--outcome-source-manifest",
                str(settlement_inputs.outcome_source_manifest),
                "--outcome-source-archive",
                str(settlement_inputs.outcome_source_archive),
                "--outcome-dataset",
                str(settlement_inputs.outcome_dataset),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["outcome_status"] == "SETTLED"
    assert all(
        marker not in str(path).lower()
        for marker in ("opportunity", "manual-trade", "fill", "broker", "order")
        for path in (tmp_path / "operations").rglob("*")
    )


def test_controlled_runner_publishes_deadline_missed_when_wait_overshoots(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    inputs, calendar, _, configuration, decision = _input_paths(
        tmp_path,
        daily_decision_fixture,
    )
    policy = default_decision_time_operation_policy()
    command = ControlledOperationCommand.create(
        idempotency_key="controlled-runner-overshoot",
        decision_date=decision.date(),
        decision_time=decision,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        trading_calendar_id=calendar.artifact_id,
        trading_calendar_hash=calendar.content_hash,
        configuration_manifest_id=configuration.configuration_id,
        configuration_manifest_hash=configuration.configuration_hash,
        model_manifest_id=configuration.model_manifest_id,
        model_manifest_hash=configuration.model_manifest_hash,
        code_revision="controlled-overshoot-test",
        limitations=(
            "ENGINEERING_FIXTURE",
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )
    observed = policy.decision_instant(decision.date()) - timedelta(seconds=30)
    current_time = [policy.static_ready_deadline_instant(decision.date())]

    def factory(symbol: str, _attempt: int, _timeout: float):
        return _RecordedMinuteClient(symbol=symbol, observed_at=observed)

    def overshoot(_seconds: float) -> None:
        current_time[0] = policy.decision_instant(decision.date()) + timedelta(
            seconds=1
        )

    journal = SQLiteDecisionTimeOperationJournal(
        tmp_path / "controlled-operation.sqlite3",
        clock=lambda: current_time[0],
    )
    runner = ControlledDecisionTimeOperationRunner(
        journal=journal,
        output_root=tmp_path / "operations",
        clock=lambda: current_time[0],
        minute_client_factory=factory,
        sleeper=overshoot,
    )
    runner.prepare(command=command, policy=policy, inputs=inputs)
    current_time[0] = observed

    with pytest.raises(
        ControlledOperationDataBlocked,
        match="DECISION_TIME_START_MISSED",
    ):
        runner.run_decision_window(command=command, policy=policy, inputs=inputs)

    snapshot = journal.get(command.run_id)
    packages = tuple(
        load_controlled_operation_package(path)
        for path in (
            tmp_path
            / "operations"
            / str(command.run_id)
            / "operation-packages"
        ).iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    assert snapshot.status is DecisionTimeOperationRunStatus.DEADLINE_MISSED
    assert len(packages) == 1
    assert packages[0].status.value == "DEADLINE_MISSED"
    assert packages[0].deadline_status == "DEADLINE_MISSED"


def test_controlled_runner_archives_all_provider_failure_as_data_blocked(
    tmp_path: Path, daily_decision_fixture: DailyDecisionFixture
) -> None:
    inputs, calendar, _, configuration, decision = _input_paths(tmp_path, daily_decision_fixture)
    policy = default_decision_time_operation_policy()
    command = ControlledOperationCommand.create(
        idempotency_key="controlled-runner-all-provider-failure",
        decision_date=decision.date(),
        decision_time=decision,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        trading_calendar_id=calendar.artifact_id,
        trading_calendar_hash=calendar.content_hash,
        configuration_manifest_id=configuration.configuration_id,
        configuration_manifest_hash=configuration.configuration_hash,
        model_manifest_id=configuration.model_manifest_id,
        model_manifest_hash=configuration.model_manifest_hash,
        code_revision="controlled-integration-test",
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )
    observed = policy.decision_instant(decision.date()) - timedelta(seconds=30)
    current_time = [policy.static_ready_deadline_instant(decision.date())]
    runner = ControlledDecisionTimeOperationRunner(
        journal=SQLiteDecisionTimeOperationJournal(tmp_path / "controlled-operation.sqlite3", clock=lambda: current_time[0]),
        output_root=tmp_path / "operations",
        clock=lambda: current_time[0],
        minute_client_factory=lambda _symbol, _attempt, _timeout: _FailingMinuteClient(),
    )
    runner.prepare(command=command, policy=policy, inputs=inputs)
    current_time[0] = observed

    with pytest.raises(ValueError, match="NO_USABLE_SOURCE"):
        runner.run_decision_window(command=command, policy=policy, inputs=inputs)

    package_root = tmp_path / "operations" / str(command.run_id) / "operation-packages"
    packages = tuple(load_controlled_operation_package(path) for path in package_root.iterdir())
    assert len(packages) == 1
    assert packages[0].status.value == "DATA_BLOCKED"
    assert packages[0].minute_success_count == 0
    assert packages[0].minute_failure_count == packages[0].candidate_count == 5
