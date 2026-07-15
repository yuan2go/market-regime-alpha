from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates.contracts import CandidatePopulation
from market_regime_alpha.candidates.dataset import TargetObservationStatus
from market_regime_alpha.candidates.rehearsal_targets import (
    materialize_r5_next_session_return_target,
    r5_next_session_return_target_contract,
)
from market_regime_alpha.core.identity import DatasetId, UniverseId
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.data.rehearsal import (
    RehearsalDailyBar,
    RehearsalDecisionSnapshot,
    RehearsalNextSessionClose,
)
from market_regime_alpha.features.rehearsal_baselines import (
    LIQUIDITY_20S_ID,
    MOMENTUM_5S_ID,
    PRICE_VS_MA20_ID,
    VOLATILITY_20S_ID,
    materialize_r5_baseline_features,
    r5_baseline_feature_definitions,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION_AT = datetime(2026, 7, 15, 14, 55, tzinfo=TZ)
MATERIALIZED_AT = datetime(2026, 7, 16, 15, 30, tzinfo=TZ)
NEXT_SESSION_DATE = date(2026, 7, 16)
SOURCE_DATASET_ID = DatasetId("dataset-r5-rehearsal-bars-v1")
UNIVERSE_ID = UniverseId("universe-r5-rehearsal-20260715")


def _history(symbol: str, count: int, *, start_close: float) -> tuple[RehearsalDailyBar, ...]:
    start = date(2026, 6, 1)
    bars = []
    for index in range(count):
        session_date = start + timedelta(days=index)
        bars.append(
            RehearsalDailyBar(
                symbol=symbol,
                session_date=session_date,
                close=start_close + index,
                amount=1_000_000.0 + index * 10_000.0,
                available_at=AvailabilityTime(
                    datetime.combine(session_date, datetime.min.time(), tzinfo=TZ).replace(hour=15, minute=5)
                ),
            )
        )
    return tuple(bars)


def _population() -> CandidatePopulation:
    return CandidatePopulation(
        universe_id=UNIVERSE_ID,
        decision_time=DecisionTime(DECISION_AT),
        symbols=("000001.SZ", "000002.SZ", "000003.SZ"),
        source_dataset_ids=(SOURCE_DATASET_ID,),
    )


def test_rehearsal_feature_materializers_preserve_symbol_missingness() -> None:
    population = _population()
    bars = (
        *_history("000001.SZ", 25, start_close=100.0),
        *_history("000002.SZ", 10, start_close=50.0),
        *_history("000003.SZ", 25, start_close=80.0),
    )
    snapshots = (
        RehearsalDecisionSnapshot(
            "000001.SZ",
            population.decision_time,
            126.0,
            AvailabilityTime(DECISION_AT),
        ),
        RehearsalDecisionSnapshot(
            "000002.SZ",
            population.decision_time,
            61.0,
            AvailabilityTime(DECISION_AT),
        ),
    )

    definitions = r5_baseline_feature_definitions()
    materializations = materialize_r5_baseline_features(
        population=population,
        source_dataset_id=SOURCE_DATASET_ID,
        daily_bars=bars,
        decision_snapshots=snapshots,
        code_revision="abc123",
        config_hash="r5-baseline-features-v1",
    )
    by_id = {materialization.definition_id: materialization for materialization in materializations}

    assert tuple(definition.feature_id for definition in definitions) == (
        MOMENTUM_5S_ID,
        VOLATILITY_20S_ID,
        LIQUIDITY_20S_ID,
        PRICE_VS_MA20_ID,
    )
    assert len(materializations) == 4

    momentum = {item.symbol: item for item in by_id[MOMENTUM_5S_ID].observations}
    assert momentum["000001.SZ"].status is InputAvailabilityStatus.AVAILABLE
    assert momentum["000001.SZ"].value == pytest.approx(126.0 / 120.0 - 1.0)
    assert momentum["000002.SZ"].status is InputAvailabilityStatus.AVAILABLE
    assert momentum["000003.SZ"].status is InputAvailabilityStatus.MISSING

    volatility = {item.symbol: item for item in by_id[VOLATILITY_20S_ID].observations}
    assert volatility["000001.SZ"].status is InputAvailabilityStatus.AVAILABLE
    assert volatility["000002.SZ"].status is InputAvailabilityStatus.MISSING
    assert volatility["000003.SZ"].status is InputAvailabilityStatus.AVAILABLE

    liquidity = {item.symbol: item for item in by_id[LIQUIDITY_20S_ID].observations}
    assert liquidity["000001.SZ"].status is InputAvailabilityStatus.AVAILABLE
    assert liquidity["000002.SZ"].status is InputAvailabilityStatus.MISSING
    assert liquidity["000003.SZ"].status is InputAvailabilityStatus.AVAILABLE

    trend = {item.symbol: item for item in by_id[PRICE_VS_MA20_ID].observations}
    assert trend["000001.SZ"].status is InputAvailabilityStatus.AVAILABLE
    assert trend["000002.SZ"].status is InputAvailabilityStatus.MISSING
    assert trend["000003.SZ"].status is InputAvailabilityStatus.MISSING


def test_rehearsal_target_materializer_separates_available_missing_and_invalid() -> None:
    population = _population()
    snapshots = (
        RehearsalDecisionSnapshot(
            "000001.SZ",
            population.decision_time,
            126.0,
            AvailabilityTime(DECISION_AT),
        ),
        RehearsalDecisionSnapshot(
            "000002.SZ",
            population.decision_time,
            61.0,
            AvailabilityTime(DECISION_AT),
        ),
    )
    future_closes = (
        RehearsalNextSessionClose(
            "000001.SZ",
            NEXT_SESSION_DATE,
            129.0,
            AvailabilityTime(datetime(2026, 7, 16, 15, 5, tzinfo=TZ)),
        ),
        RehearsalNextSessionClose(
            "000003.SZ",
            NEXT_SESSION_DATE,
            110.0,
            AvailabilityTime(datetime(2026, 7, 16, 15, 5, tzinfo=TZ)),
        ),
    )

    target = r5_next_session_return_target_contract()
    materialization = materialize_r5_next_session_return_target(
        population=population,
        source_dataset_id=SOURCE_DATASET_ID,
        decision_snapshots=snapshots,
        next_session_date=NEXT_SESSION_DATE,
        next_session_closes=future_closes,
        materialized_at=AsOfTime(MATERIALIZED_AT),
        code_revision="abc123",
        config_hash="r5-next-session-target-v1",
    )
    observations = {item.symbol: item for item in materialization.observations}

    assert materialization.target_id == target.target_id
    assert observations["000001.SZ"].status is TargetObservationStatus.AVAILABLE
    assert observations["000001.SZ"].value == pytest.approx(129.0 / 126.0 - 1.0)
    assert observations["000002.SZ"].status is TargetObservationStatus.MISSING
    assert observations["000002.SZ"].value is None
    assert observations["000003.SZ"].status is TargetObservationStatus.INVALID
    assert observations["000003.SZ"].value is None


def test_rehearsal_target_materializer_rejects_wrong_resolved_session() -> None:
    population = _population()
    snapshot = RehearsalDecisionSnapshot(
        "000001.SZ",
        population.decision_time,
        126.0,
        AvailabilityTime(DECISION_AT),
    )
    wrong_date_close = RehearsalNextSessionClose(
        "000001.SZ",
        date(2026, 7, 17),
        129.0,
        AvailabilityTime(datetime(2026, 7, 17, 15, 5, tzinfo=TZ)),
    )

    with pytest.raises(ValueError, match="resolved next_session_date"):
        materialize_r5_next_session_return_target(
            population=population,
            source_dataset_id=SOURCE_DATASET_ID,
            decision_snapshots=(snapshot,),
            next_session_date=NEXT_SESSION_DATE,
            next_session_closes=(wrong_date_close,),
            materialized_at=AsOfTime(datetime(2026, 7, 17, 15, 30, tzinfo=TZ)),
            code_revision="abc123",
            config_hash="r5-next-session-target-v1",
        )


def test_rehearsal_feature_materializer_ignores_future_history_instead_of_leaking_it() -> None:
    population = _population()
    historical = _history("000001.SZ", 25, start_close=100.0)
    future_bar = RehearsalDailyBar(
        symbol="000001.SZ",
        session_date=date(2026, 7, 16),
        close=999.0,
        amount=999_000_000.0,
        available_at=AvailabilityTime(datetime(2026, 7, 16, 15, 5, tzinfo=TZ)),
    )
    snapshot = RehearsalDecisionSnapshot(
        "000001.SZ",
        population.decision_time,
        126.0,
        AvailabilityTime(DECISION_AT),
    )

    base = materialize_r5_baseline_features(
        population=population,
        source_dataset_id=SOURCE_DATASET_ID,
        daily_bars=historical,
        decision_snapshots=(snapshot,),
        code_revision="abc123",
        config_hash="r5-baseline-features-v1",
    )
    with_future = materialize_r5_baseline_features(
        population=population,
        source_dataset_id=SOURCE_DATASET_ID,
        daily_bars=(*historical, future_bar),
        decision_snapshots=(snapshot,),
        code_revision="abc123",
        config_hash="r5-baseline-features-v1",
    )

    assert base == with_future
