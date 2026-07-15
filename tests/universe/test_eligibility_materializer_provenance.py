from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.universe.artifacts import (
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)
from market_regime_alpha.universe.eligibility_policy import (
    RawTradingEligibilityObservation,
    materialize_historical_trading_eligibility,
    r5_rehearsal_trading_eligibility_policy_v1,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION_AT = datetime(2026, 7, 15, 14, 55, tzinfo=TZ)


def _universe():
    return build_historical_pit_universe_artifact(
        source_dataset_id=DatasetId("dataset-universe-v1"),
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention="AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START",
        records=(HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),),
    )


def _observation() -> RawTradingEligibilityObservation:
    return RawTradingEligibilityObservation(
        as_of=AsOfTime(DECISION_AT),
        available_at=AvailabilityTime(DECISION_AT),
        symbol="000001.SZ",
        is_suspended=False,
        is_st=False,
        prev_close=10.0,
        limit_up_price=11.0,
        limit_down_price=9.0,
        limit_regime="MAIN_BOARD_10PCT",
    )


def test_boolean_cannot_masquerade_as_price_value() -> None:
    with pytest.raises(TypeError, match="prev_close must not be boolean"):
        RawTradingEligibilityObservation(
            as_of=AsOfTime(DECISION_AT),
            available_at=AvailabilityTime(DECISION_AT),
            symbol="000001.SZ",
            is_suspended=False,
            is_st=False,
            prev_close=True,  # type: ignore[arg-type]
            limit_up_price=11.0,
            limit_down_price=9.0,
            limit_regime="MAIN_BOARD_10PCT",
        )


def test_raw_evidence_convention_changes_eligibility_artifact_identity() -> None:
    policy = r5_rehearsal_trading_eligibility_policy_v1()
    first = materialize_historical_trading_eligibility(
        source_dataset_id=DatasetId("dataset-eligibility-v1"),
        universe_artifact=_universe(),
        policy=policy,
        decision_times=(DecisionTime(DECISION_AT),),
        observations=(_observation(),),
        raw_evidence_convention="PROVIDER_A_EXPLICIT_AVAILABLE_AT",
    )
    second = materialize_historical_trading_eligibility(
        source_dataset_id=DatasetId("dataset-eligibility-v1"),
        universe_artifact=_universe(),
        policy=policy,
        decision_times=(DecisionTime(DECISION_AT),),
        observations=(_observation(),),
        raw_evidence_convention="PROVIDER_B_EXPLICIT_AVAILABLE_AT",
    )

    assert first.snapshots[0].records == second.snapshots[0].records
    assert first.policy_artifact_id == second.policy_artifact_id
    assert first.materializer_version == second.materializer_version
    assert first.raw_evidence_convention != second.raw_evidence_convention
    assert first.artifact_id != second.artifact_id
