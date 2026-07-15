from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates.contracts import CandidatePopulation
from market_regime_alpha.candidates.rehearsal_calendar_targets import (
    materialize_r5_opportunity_targets_from_calendar,
)
from market_regime_alpha.candidates.rehearsal_opportunity_targets import (
    R5_NEXT_SESSION_MFE_TARGET_ID,
)
from market_regime_alpha.core.identity import DatasetId, UniverseId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.data.rehearsal import RehearsalDecisionSnapshot, RehearsalNextSessionBar
from market_regime_alpha.data.trading_calendar import TradingSession, build_trading_calendar_artifact


TZ = ZoneInfo("Asia/Shanghai")
DECISION_AT = datetime(2026, 7, 15, 14, 55, tzinfo=TZ)
SOURCE_DATASET_ID = DatasetId("dataset-r5-calendar-target-v1")


def _session(day: date) -> TradingSession:
    return TradingSession(
        trade_date=day,
        session_close=datetime(day.year, day.month, day.day, 15, 0, tzinfo=TZ),
    )


def _calendar():
    return build_trading_calendar_artifact(
        source_dataset_id=SOURCE_DATASET_ID,
        market="CN_A_SHARE",
        calendar_version="fixture-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            _session(date(2026, 7, 15)),
            _session(date(2026, 7, 20)),
        ),
    )


def _population() -> CandidatePopulation:
    return CandidatePopulation(
        universe_id=UniverseId("universe-r5-calendar-target-v1"),
        decision_time=DecisionTime(DECISION_AT),
        symbols=("000001.SZ",),
        source_dataset_ids=(SOURCE_DATASET_ID,),
    )


def test_calendar_resolved_target_materializer_skips_non_session_dates() -> None:
    population = _population()
    bundle = materialize_r5_opportunity_targets_from_calendar(
        population=population,
        calendar=_calendar(),
        source_dataset_id=SOURCE_DATASET_ID,
        decision_snapshots=(
            RehearsalDecisionSnapshot(
                "000001.SZ",
                population.decision_time,
                100.0,
                AvailabilityTime(DECISION_AT),
            ),
        ),
        next_session_bars=(
            RehearsalNextSessionBar(
                "000001.SZ",
                date(2026, 7, 20),
                101.0,
                110.0,
                96.0,
                105.0,
                AvailabilityTime(datetime(2026, 7, 20, 15, 5, tzinfo=TZ)),
            ),
        ),
        materialized_at=AsOfTime(datetime(2026, 7, 20, 15, 30, tzinfo=TZ)),
        code_revision="abc123",
        config_hash="r5-calendar-targets-v1",
    )

    mfe = bundle.get(R5_NEXT_SESSION_MFE_TARGET_ID)
    assert mfe.observations[0].value == pytest.approx(0.10)


def test_calendar_resolved_target_materializer_rejects_bar_from_skipped_date() -> None:
    population = _population()
    with pytest.raises(ValueError, match="resolved next_session_date"):
        materialize_r5_opportunity_targets_from_calendar(
            population=population,
            calendar=_calendar(),
            source_dataset_id=SOURCE_DATASET_ID,
            decision_snapshots=(
                RehearsalDecisionSnapshot(
                    "000001.SZ",
                    population.decision_time,
                    100.0,
                    AvailabilityTime(DECISION_AT),
                ),
            ),
            next_session_bars=(
                RehearsalNextSessionBar(
                    "000001.SZ",
                    date(2026, 7, 16),
                    101.0,
                    110.0,
                    96.0,
                    105.0,
                    AvailabilityTime(datetime(2026, 7, 16, 15, 5, tzinfo=TZ)),
                ),
            ),
            materialized_at=AsOfTime(datetime(2026, 7, 20, 15, 30, tzinfo=TZ)),
            code_revision="abc123",
            config_hash="r5-calendar-targets-v1",
        )
