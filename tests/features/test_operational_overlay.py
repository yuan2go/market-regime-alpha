from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from tests.postgres_path_repositories import feature_repository_factory

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.features import (
    FeatureMaterializationExecutionMode,
    FeatureMaterializationRunner,
)
from market_regime_alpha.features.operational_overlay import (
    CandidateIntradayFeatureOverlay,
    StaticUniverseFeatureBundle,
    load_candidate_intraday_feature_overlay,
    load_static_universe_feature_bundle,
    publish_candidate_intraday_feature_overlay,
    publish_static_universe_feature_bundle,
)
from market_regime_alpha.features.materialization_v2 import (
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.features.technical.catalog import (
    intraday_overlay_feature_set,
    static_technical_feature_set,
)
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
from market_regime_alpha.signals import (
    CandidateFeatureViewV2,
    SignalInputAssemblerV3,
    SignalState,
    canonical_all_factors_required_policy,
    canonical_signal_freshness_policy,
    canonical_signal_input_mapping_v2,
    canonical_signal_model_configuration_v2,
    load_candidate_feature_view_v2,
    publish_candidate_feature_view_v2,
    run_signal_model_v3,
)
from market_regime_alpha.universe import (
    ListingStatus,
    OperationalLiquidityEvidence,
    OperationalUniverseArtifact,
    OperationalUniverseRecord,
    STStatus,
    SuspensionStatus,
)
from tests.features.test_materialization_runner_v2 import (
    CREATED_AT,
    DECISION_TIME,
    MANIFEST_HASH,
    SOURCE_HASH,
    _verified_dataset,
)
from tests.signals.test_feature_input_assembly_v2 import _candidate_set


UTC = timezone.utc


def _universe() -> OperationalUniverseArtifact:
    source = ArtifactId("operational-universe-source")
    record = OperationalUniverseRecord(
        symbol="600000.SH",
        asset_type=AssetType.A_SHARE,
        exchange=Exchange.SH,
        membership_source="CONTROLLED_TEST_SELECTION",
        listing_status=ListingStatus.LISTED,
        st_status=STStatus.NOT_ST,
        suspension_status=SuspensionStatus.NOT_SUSPENDED,
        liquidity_evidence=OperationalLiquidityEvidence(
            lookback_sessions=20,
            observed_sessions=20,
            median_daily_amount=Decimal("100000000"),
            minimum_daily_amount=Decimal("50000000"),
            available_at=datetime(2026, 8, 4, 1, 50, tzinfo=UTC),
            source_artifact_id=source,
            source_content_hash=SOURCE_HASH,
        ),
        history_sessions_observed=250,
        history_sessions_required=250,
        included=True,
        inclusion_reasons=("CONTROLLED_TEST_ELIGIBLE",),
        exclusion_reasons=(),
        source_artifact_references=((source, SOURCE_HASH),),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    return OperationalUniverseArtifact.create(
        decision_date=DECISION_TIME.date(),
        effective_at=datetime(2026, 8, 4, 1, 45, tzinfo=UTC),
        available_at=datetime(2026, 8, 4, 2, 0, tzinfo=UTC),
        records=(record,),
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        data_eligibility=DataEligibility.EXPLORATORY,
        source_artifact_references=((source, SOURCE_HASH),),
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )


def _minute_dataset(tmp_path: Path, *, missing_amount: bool = False):
    bars = tuple(
        CanonicalMarketBar.create(
            symbol="600000.SH",
            exchange=Exchange.SH,
            asset_type=AssetType.A_SHARE,
            timeframe=Timeframe.MINUTE_5,
            market_date=DECISION_TIME.date(),
            event_start=datetime(2026, 8, 4, 1, 30, tzinfo=UTC)
            + timedelta(minutes=5 * index),
            event_end=datetime(2026, 8, 4, 1, 35, tzinfo=UTC)
            + timedelta(minutes=5 * index),
            available_at=datetime(2026, 8, 4, 1, 35, tzinfo=UTC)
            + timedelta(minutes=5 * index),
            open=Decimal("10") + Decimal(index) / Decimal("100"),
            high=Decimal("10.05") + Decimal(index) / Decimal("100"),
            low=Decimal("9.95") + Decimal(index) / Decimal("100"),
            close=Decimal("10.02") + Decimal(index) / Decimal("100"),
            previous_close=Decimal("9.9") if index == 0 else None,
            volume=Decimal(1000 + index * 10),
            volume_unit=VolumeUnit.SHARES,
            amount=None
            if missing_amount
            else (Decimal("10.02") + Decimal(index) / Decimal("100"))
            * Decimal(1000 + index * 10),
            turnover_rate=None,
            adjustment_mode=AdjustmentMode.RAW,
            adjustment_factor=Decimal("1"),
            trading_status=TradingStatus.TRADING,
            price_limit_state=PriceLimitState.NORMAL,
            source_artifact_id=ArtifactId(f"minute-source-{index}"),
            source_content_hash=SOURCE_HASH,
        )
        for index in range(12)
    )
    artifact = MarketDataDatasetArtifact.create(
        decision_time=DECISION_TIME,
        created_at=CREATED_AT,
        bars=bars,
        expected_symbols=("600000.SH",),
        expected_timeframes=(Timeframe.MINUTE_5,),
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="minute-raw-v1",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=((ArtifactId("minute-source-manifest"), MANIFEST_HASH),),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )
    package = publish_market_data_dataset(root=tmp_path / "minute-market", artifact=artifact)
    return load_verified_market_data_dataset(package)


def _calendar(daily=None):
    shanghai = timezone(timedelta(hours=8))
    dates = (
        tuple(
            sorted(
                {
                    item.market_date
                    for item in daily.bars
                    if item.timeframe is Timeframe.DAILY
                }
                | {DECISION_TIME.date()}
            )
        )
        if daily is not None
        else (DECISION_TIME.date(),)
    )
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("calendar-source"),
        market="A_SHARE",
        calendar_version="overlay-test-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                trade_date=trade_date,
                session_close=datetime.combine(
                    trade_date, time(15), tzinfo=shanghai
                ),
            )
            for trade_date in dates
        ),
    )


def _composition(tmp_path: Path, *, missing_amount: bool = False):
    daily = _verified_dataset(tmp_path / "daily", include_minutes=False)
    static_set = static_technical_feature_set(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    static_receipt = FeatureMaterializationRunner(
        max_workers=2,
        repository_factory=feature_repository_factory(
            tmp_path / "static-features.postgres-scope",
            fallback_clock=lambda: CREATED_AT,
        ),
    ).run(
        verified_dataset=daily,
        feature_set=static_set,
        decision_time=DECISION_TIME,
        created_at=CREATED_AT,
        selected_symbols=("600000.SH",),
        code_revision="overlay-test",
        output_root=tmp_path / "static-features",
        idempotency_key="static",
        execution_mode=FeatureMaterializationExecutionMode.START_NEW,
    )
    static_verified = load_verified_feature_bundle_v2(
        tmp_path / "static-features" / static_receipt.bundle_locator,
        artifact_root=tmp_path / "static-features" / "feature-artifacts",
    )
    static = StaticUniverseFeatureBundle.create(
        universe=_universe(),
        daily_dataset=daily,
        feature_bundle=static_verified,
        run_receipt=static_receipt,
        code_revision="overlay-test",
    )
    minute = _minute_dataset(tmp_path, missing_amount=missing_amount)
    intraday_set = intraday_overlay_feature_set(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    intraday_receipt = FeatureMaterializationRunner(
        max_workers=2,
        repository_factory=feature_repository_factory(
            tmp_path / "intraday-features.postgres-scope",
            fallback_clock=lambda: CREATED_AT,
        ),
    ).run(
        verified_dataset=minute,
        feature_set=intraday_set,
        decision_time=DECISION_TIME,
        created_at=CREATED_AT,
        selected_symbols=("600000.SH",),
        code_revision="overlay-test",
        output_root=tmp_path / "intraday-features",
        idempotency_key="intraday",
        execution_mode=FeatureMaterializationExecutionMode.START_NEW,
    )
    intraday_verified = load_verified_feature_bundle_v2(
        tmp_path / "intraday-features" / intraday_receipt.bundle_locator,
        artifact_root=tmp_path / "intraday-features" / "feature-artifacts",
    )
    candidate = _candidate_set()
    calendar = _calendar(daily)
    overlay = CandidateIntradayFeatureOverlay.create(
        candidate_set=candidate,
        static_bundle=static,
        minute_dataset=minute,
        intraday_feature_bundle=intraday_verified,
        trading_calendar=calendar,
    )
    view = CandidateFeatureViewV2.create(
        candidate_set=candidate,
        static_bundle=static,
        intraday_overlay=overlay,
    )
    return static, overlay, view, static_verified, intraday_verified, daily, minute, candidate, calendar


def test_static_overlay_and_candidate_view_v2_remain_separate_and_round_trip(
    tmp_path: Path,
) -> None:
    static, overlay, view, *_ = _composition(tmp_path)

    static_package = publish_static_universe_feature_bundle(
        root=tmp_path / "static-packages", artifact=static
    )
    overlay_package = publish_candidate_intraday_feature_overlay(
        root=tmp_path / "overlay-packages", artifact=overlay
    )
    view_package = publish_candidate_feature_view_v2(
        root=tmp_path / "view-packages", view=view
    )

    assert load_static_universe_feature_bundle(static_package) == static
    assert load_candidate_intraday_feature_overlay(overlay_package) == overlay
    assert load_candidate_feature_view_v2(view_package) == view
    assert all(item.timeframe is Timeframe.DAILY for item in view.static_feature_references)
    assert all(item.timeframe is not Timeframe.DAILY for item in view.intraday_feature_references)
    assert set(view.static_feature_references).isdisjoint(view.intraday_feature_references)
    assert len(view.static_feature_references) == 5
    assert len(view.intraday_feature_references) == 2


def test_overlay_rejects_candidate_outside_static_universe(tmp_path: Path) -> None:
    static, _, _, _, intraday, _, minute, _, calendar = _composition(tmp_path)
    with pytest.raises(ValueError, match="scope exceeds"):
        CandidateIntradayFeatureOverlay.create(
            candidate_set=_candidate_set(symbol="000001.SZ"),
            static_bundle=static,
            minute_dataset=minute,
            intraday_feature_bundle=intraday,
            trading_calendar=calendar,
        )


def test_signal_v3_assembles_five_factors_from_candidate_view_v2(
    tmp_path: Path,
) -> None:
    (
        static,
        overlay,
        view,
        static_verified,
        intraday_verified,
        daily,
        minute,
        candidate,
        calendar,
    ) = _composition(tmp_path)
    mapping = canonical_signal_input_mapping_v2(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    requirements = canonical_all_factors_required_policy()
    freshness = canonical_signal_freshness_policy(trading_calendar=calendar)
    observations = SignalInputAssemblerV3().assemble(
        candidate_set=candidate,
        candidate_feature_view=view,
        feature_bundle=static_verified,
        verified_dataset=daily,
        static_bundle=static,
        intraday_overlay=overlay,
        intraday_feature_bundle=intraday_verified,
        minute_dataset=minute,
        mapping_configuration=mapping,
        requirement_policy=requirements,
        freshness_policy=freshness,
        trading_calendar=calendar,
        decision_time=DecisionTime(DECISION_TIME),
    )
    signal = run_signal_model_v3(
        candidate_set=candidate,
        candidate_feature_view=view,
        feature_bundle=static_verified,
        verified_dataset=daily,
        mapping_configuration=mapping,
        requirement_policy=requirements,
        freshness_policy=freshness,
        trading_calendar=calendar,
        signal_configuration=canonical_signal_model_configuration_v2(),
        observations=observations,
        decision_time=DecisionTime(DECISION_TIME),
        created_at=CREATED_AT,
        code_revision="overlay-test",
    )

    assert len(observations[0].factors) == 5
    assert all(item.value is not None for item in observations[0].factors)
    assert signal.candidate_feature_view.schema_version == "candidate-feature-view-v2"
    assert signal.snapshots[0].signal_state is not SignalState.DATA_INSUFFICIENT


def test_missing_candidate_vwap_is_data_insufficient_without_daily_substitution(
    tmp_path: Path,
) -> None:
    (
        static,
        overlay,
        view,
        static_verified,
        intraday_verified,
        daily,
        minute,
        candidate,
        calendar,
    ) = _composition(tmp_path, missing_amount=True)
    mapping = canonical_signal_input_mapping_v2(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    requirements = canonical_all_factors_required_policy()
    freshness = canonical_signal_freshness_policy(trading_calendar=calendar)
    observations = SignalInputAssemblerV3().assemble(
        candidate_set=candidate,
        candidate_feature_view=view,
        feature_bundle=static_verified,
        verified_dataset=daily,
        static_bundle=static,
        intraday_overlay=overlay,
        intraday_feature_bundle=intraday_verified,
        minute_dataset=minute,
        mapping_configuration=mapping,
        requirement_policy=requirements,
        freshness_policy=freshness,
        trading_calendar=calendar,
        decision_time=DecisionTime(DECISION_TIME),
    )
    signal = run_signal_model_v3(
        candidate_set=candidate,
        candidate_feature_view=view,
        feature_bundle=static_verified,
        verified_dataset=daily,
        mapping_configuration=mapping,
        requirement_policy=requirements,
        freshness_policy=freshness,
        trading_calendar=calendar,
        signal_configuration=canonical_signal_model_configuration_v2(),
        observations=observations,
        decision_time=DecisionTime(DECISION_TIME),
        created_at=CREATED_AT,
        code_revision="overlay-test",
    )

    vwap = next(
        item
        for item in observations[0].factors
        if item.factor_name.value == "PRICE_VS_VWAP_RETURN"
    )
    assert vwap.value is None
    assert "FIELD_UNAVAILABLE_AMOUNT" in vwap.missing_reason_codes
    assert signal.snapshots[0].signal_state is SignalState.DATA_INSUFFICIENT
