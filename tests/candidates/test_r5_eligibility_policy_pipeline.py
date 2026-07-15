from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from market_regime_alpha.candidates import build_candidate_population_from_historical_artifacts
from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.legacy import (
    LEGACY_ELIGIBILITY_AVAILABILITY_CONVENTION,
    adapt_legacy_eligibility_mapping,
)
from market_regime_alpha.universe import (
    TRADING_ELIGIBILITY_MATERIALIZER_VERSION,
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
    materialize_historical_trading_eligibility,
    r5_rehearsal_trading_eligibility_policy_v1,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION_AT = datetime(2026, 7, 15, 14, 55, tzinfo=TZ)


def test_legacy_raw_eligibility_materializes_versioned_policy_and_candidate_population() -> None:
    universe = build_historical_pit_universe_artifact(
        source_dataset_id=DatasetId("dataset-universe-v1"),
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention="AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START",
        records=(
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000002.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000003.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000004.SZ", False),
        ),
    )
    raw_observations = adapt_legacy_eligibility_mapping(
        {
            "records": [
                {
                    "symbol": "000001.SZ",
                    "timestamp": "2026-07-15 14:55:00",
                    "is_suspended": False,
                    "is_st": False,
                    "prev_close": 10.0,
                    "limit_up_price": 11.0,
                    "limit_down_price": 9.0,
                    "limit_regime": "MAIN_BOARD_10PCT",
                },
                {
                    "symbol": "000002.SZ",
                    "timestamp": "2026-07-15 14:55:00",
                    "is_suspended": False,
                    "is_st": True,
                    "prev_close": 8.0,
                    "limit_up_price": 8.4,
                    "limit_down_price": 7.6,
                    "limit_regime": "ST_5PCT",
                },
                {
                    "symbol": "000003.SZ",
                    "timestamp": "2026-07-15 14:55:00",
                    "is_suspended": True,
                    "is_st": False,
                    "prev_close": 12.0,
                    "limit_up_price": 13.2,
                    "limit_down_price": 10.8,
                    "limit_regime": "MAIN_BOARD_10PCT",
                },
                {
                    "symbol": "000004.SZ",
                    "timestamp": "2026-07-15 14:55:00",
                    "is_suspended": False,
                    "is_st": False,
                    "prev_close": 20.0,
                    "limit_up_price": 22.0,
                    "limit_down_price": 18.0,
                    "limit_regime": "MAIN_BOARD_10PCT",
                },
            ]
        }
    )
    policy = r5_rehearsal_trading_eligibility_policy_v1()
    eligibility = materialize_historical_trading_eligibility(
        source_dataset_id=DatasetId("dataset-eligibility-sidecar-v1"),
        universe_artifact=universe,
        policy=policy,
        decision_times=(DecisionTime(DECISION_AT),),
        observations=raw_observations,
        raw_evidence_convention=LEGACY_ELIGIBILITY_AVAILABILITY_CONVENTION,
    )
    population = build_candidate_population_from_historical_artifacts(
        universe_artifact=universe,
        eligibility_artifact=eligibility,
        decision_time=DecisionTime(DECISION_AT),
    )

    assert eligibility.policy_artifact_id == policy.policy_artifact_id
    assert eligibility.policy_version == policy.policy_version
    assert eligibility.materializer_version == TRADING_ELIGIBILITY_MATERIALIZER_VERSION
    assert eligibility.raw_evidence_convention == LEGACY_ELIGIBILITY_AVAILABILITY_CONVENTION
    assert population.symbols == ("000001.SZ",)
    assert population.source_dataset_ids == (
        DatasetId("dataset-universe-v1"),
        DatasetId("dataset-eligibility-sidecar-v1"),
    )
