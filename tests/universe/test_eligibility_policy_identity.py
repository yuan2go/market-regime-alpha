from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.universe.artifacts import (
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)
from market_regime_alpha.universe.eligibility_policy import (
    RawTradingEligibilityObservation,
    TradingEligibilityPolicy,
    materialize_historical_trading_eligibility,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION_AT = datetime(2026, 7, 15, 14, 55, tzinfo=TZ)


def test_same_results_under_different_policy_config_have_different_artifact_identity() -> None:
    universe = build_historical_pit_universe_artifact(
        source_dataset_id=DatasetId("dataset-universe-v1"),
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention="AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START",
        records=(
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),
        ),
    )
    observations = (
        RawTradingEligibilityObservation(
            as_of=AsOfTime(DECISION_AT),
            available_at=AvailabilityTime(DECISION_AT),
            symbol="000001.SZ",
            is_suspended=False,
            is_st=False,
            prev_close=10.0,
            limit_up_price=11.0,
            limit_down_price=9.0,
            limit_regime="MAIN_BOARD_10PCT",
        ),
    )
    exclude_st = TradingEligibilityPolicy(
        policy_name="fixture-policy",
        version="v1",
        exclude_st=True,
        require_prev_close=True,
        require_limit_metadata=True,
    )
    include_st = TradingEligibilityPolicy(
        policy_name="fixture-policy",
        version="v1",
        exclude_st=False,
        require_prev_close=True,
        require_limit_metadata=True,
    )

    first = materialize_historical_trading_eligibility(
        source_dataset_id=DatasetId("dataset-eligibility-v1"),
        universe_artifact=universe,
        policy=exclude_st,
        decision_times=(DecisionTime(DECISION_AT),),
        observations=observations,
    )
    second = materialize_historical_trading_eligibility(
        source_dataset_id=DatasetId("dataset-eligibility-v1"),
        universe_artifact=universe,
        policy=include_st,
        decision_times=(DecisionTime(DECISION_AT),),
        observations=observations,
    )

    assert first.snapshots[0].records == second.snapshots[0].records
    assert first.policy_version == second.policy_version
    assert first.policy_artifact_id != second.policy_artifact_id
    assert first.artifact_id != second.artifact_id
