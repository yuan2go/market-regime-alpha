from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    LifecycleAuthorityCeiling,
)
from market_regime_alpha.application.canonical_lifecycle.stages.signal_forecast import (
    EntryAssessmentStageHandler,
    PathForecastStageHandler,
    SignalStageHandler,
)
from market_regime_alpha.application.controlled_operation.outcome_evidence import (
    OutcomeCompleteness,
    TradeHorizonDefinition,
    build_trade_horizon_outcome_evidence,
    load_trade_horizon_outcome_evidence,
    publish_trade_horizon_outcome_evidence,
    replay_trade_horizon_outcome_evidence,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
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
    canonical_all_factors_required_policy,
    canonical_signal_freshness_policy,
    canonical_signal_input_mapping_v2,
    canonical_signal_model_configuration_v2,
)
from tests.application.controlled_operation.test_evidence_package import HASH, _artifact
from tests.application.controlled_operation.test_signal_path_entry import _path_configuration
from tests.features.test_materialization_runner_v2 import CREATED_AT, DECISION_TIME
from tests.features.test_operational_overlay import _composition


UTC = timezone.utc


def _settlement_dataset(
    tmp_path: Path,
    *,
    minute_count: int = 60,
    minute_timeframe: Timeframe = Timeframe.MINUTE_1,
    include_daily: bool = True,
    name: str = "settlement-dataset",
):
    session_date = DECISION_TIME.date() + timedelta(days=1)
    minute_duration = minute_timeframe.duration
    assert minute_duration is not None
    minute_start = datetime.combine(session_date, datetime.min.time(), tzinfo=UTC) + timedelta(
        hours=1, minutes=30
    )
    minutes = tuple(
        CanonicalMarketBar.create(
            symbol="600000.SH",
            exchange=Exchange.SH,
            asset_type=AssetType.A_SHARE,
            timeframe=minute_timeframe,
            market_date=session_date,
            event_start=minute_start + minute_duration * index,
            event_end=minute_start + minute_duration * (index + 1),
            available_at=minute_start + minute_duration * (index + 1),
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
            source_artifact_id=ArtifactId("t1-minute-source"),
            source_content_hash=HASH,
        )
        for index in range(minute_count)
    )
    daily = CanonicalMarketBar.create(
        symbol="600000.SH",
        exchange=Exchange.SH,
        asset_type=AssetType.A_SHARE,
        timeframe=Timeframe.DAILY,
        market_date=session_date,
        event_start=minute_start,
        event_end=minute_start + timedelta(hours=5, minutes=30),
        available_at=minute_start + timedelta(hours=5, minutes=31),
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
        source_artifact_id=ArtifactId("t1-daily-source"),
        source_content_hash=HASH,
    )
    artifact = MarketDataDatasetArtifact.create(
        decision_time=daily.available_at,
        created_at=daily.available_at,
        bars=(*minutes, *((daily,) if include_daily else ())),
        expected_symbols=("600000.SH",),
        expected_timeframes=(Timeframe.DAILY, minute_timeframe),
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="outcome-raw-v1",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=((ArtifactId("t1-source-manifest"), HASH),),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("OUTCOME_FIXTURE",),
    )
    path = publish_market_data_dataset(root=tmp_path / name, artifact=artifact)
    return load_verified_market_data_dataset(path)


@pytest.mark.parametrize(
    ("minute_timeframe", "minute_count"),
    ((Timeframe.MINUTE_1, 60), (Timeframe.MINUTE_5, 12)),
)
def test_t1_outcome_is_factual_complete_immutable_and_replayable(
    tmp_path: Path,
    minute_timeframe: Timeframe,
    minute_count: int,
) -> None:
    (
        static,
        overlay,
        _,
        static_features,
        intraday_features,
        daily,
        minute,
        candidates,
        calendar,
    ) = _composition(tmp_path)
    signal = SignalStageHandler(
        configuration=canonical_signal_model_configuration_v2(),
        output_root=tmp_path / "signals",
        mapping_configuration=canonical_signal_input_mapping_v2(
            effective_from=datetime(2026, 1, 1, tzinfo=UTC)
        ),
        feature_set_configuration=static_features.artifact.feature_set,
        requirement_policy=canonical_all_factors_required_policy(),
        freshness_policy=canonical_signal_freshness_policy(trading_calendar=calendar),
    ).run_controlled_v2(
        candidate_set=candidates,
        static_bundle=static,
        static_feature_bundle=static_features,
        daily_dataset=daily,
        intraday_overlay=overlay,
        intraday_feature_bundle=intraday_features,
        minute_dataset=minute,
        trading_calendar=calendar,
        decision_time=DecisionTime(DECISION_TIME),
        created_at=CREATED_AT,
        code_revision="controlled-test",
    ).signal
    forecasts = PathForecastStageHandler(
        configuration=_path_configuration(), output_root=tmp_path / "forecasts"
    ).run_controlled(signal=signal).forecasts
    EntryAssessmentStageHandler(
        authority_ceiling=LifecycleAuthorityCeiling()
    ).run_controlled(
        signal=signal,
        forecasts=forecasts,
        output_root=tmp_path / "entry",
        created_at=CREATED_AT,
    )
    package = _artifact(
        decision_time=DECISION_TIME,
        daily_dataset_id=daily.artifact.dataset_id,
        daily_dataset_hash=daily.artifact.content_hash,
    )
    settlement = _settlement_dataset(
        tmp_path,
        minute_count=minute_count,
        minute_timeframe=minute_timeframe,
    )
    evidence = build_trade_horizon_outcome_evidence(
        operation_package=package,
        candidate_set=candidates,
        signal=signal,
        forecasts=forecasts,
        decision_dataset=daily,
        settlement_dataset=settlement,
        next_session_date=DECISION_TIME.date() + timedelta(days=1),
        horizon=TradeHorizonDefinition.create(),
        created_at=settlement.artifact.created_at,
    )
    path = publish_trade_horizon_outcome_evidence(root=tmp_path / "outcomes", artifact=evidence)

    observation = evidence.observations[0]
    assert observation.completeness is OutcomeCompleteness.COMPLETE
    assert observation.next_1030_price is not None
    assert observation.gross_return is not None
    assert observation.mfe is not None
    assert observation.mae is not None
    assert "FACTUAL_OBSERVATION_ONLY" in observation.limitations
    assert "NOT_A_FORMAL_H9_LABEL" in observation.limitations
    assert load_trade_horizon_outcome_evidence(path) == evidence
    assert replay_trade_horizon_outcome_evidence(path) == evidence

    missing_interval = build_trade_horizon_outcome_evidence(
        operation_package=package,
        candidate_set=candidates,
        signal=signal,
        forecasts=forecasts,
        decision_dataset=daily,
        settlement_dataset=_settlement_dataset(
            tmp_path,
            minute_count=minute_count - 1,
            minute_timeframe=minute_timeframe,
            name="settlement-missing-minute",
        ),
        next_session_date=DECISION_TIME.date() + timedelta(days=1),
        horizon=TradeHorizonDefinition.create(),
        created_at=settlement.artifact.created_at,
    ).observations[0]
    missing_close = build_trade_horizon_outcome_evidence(
        operation_package=package,
        candidate_set=candidates,
        signal=signal,
        forecasts=forecasts,
        decision_dataset=daily,
        settlement_dataset=_settlement_dataset(
            tmp_path,
            include_daily=False,
            minute_count=minute_count,
            minute_timeframe=minute_timeframe,
            name="settlement-missing-close",
        ),
        next_session_date=DECISION_TIME.date() + timedelta(days=1),
        horizon=TradeHorizonDefinition.create(),
        created_at=settlement.artifact.created_at,
    ).observations[0]

    assert missing_interval.completeness is OutcomeCompleteness.DATA_INCOMPLETE
    assert "MORNING_MINUTE_INTERVALS_INCOMPLETE" in missing_interval.reason_codes
    assert missing_interval.morning_high is None
    assert missing_interval.morning_low is None
    assert missing_interval.mfe is None
    assert missing_interval.mae is None
    assert missing_close.completeness is OutcomeCompleteness.DATA_INCOMPLETE
    assert missing_close.gross_return is not None
    assert missing_close.mfe is not None
    assert missing_close.mae is not None
