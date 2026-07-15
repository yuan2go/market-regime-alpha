from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates.historical_population import (
    build_candidate_population_from_historical_artifacts,
)
from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.core.time import AsOfTime, DecisionTime
from market_regime_alpha.universe.artifacts import (
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)
from market_regime_alpha.universe.contracts import TradingEligibilityStatus
from market_regime_alpha.universe.eligibility_artifacts import (
    HistoricalTradingEligibilityRecord,
    build_historical_trading_eligibility_artifact,
)


TZ = ZoneInfo("Asia/Shanghai")
DATASET_ID = DatasetId("dataset-r5-historical-artifacts-v1")
DECISION_AT = datetime(2026, 7, 15, 14, 55, tzinfo=TZ)


def _universe():
    return build_historical_pit_universe_artifact(
        source_dataset_id=DATASET_ID,
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention="AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START",
        records=(
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000002.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000003.SZ", False),
        ),
    )


def _eligibility():
    as_of = AsOfTime(DECISION_AT)
    return build_historical_trading_eligibility_artifact(
        source_dataset_id=DATASET_ID,
        policy_version="fixture-eligibility-v1",
        records=(
            HistoricalTradingEligibilityRecord(
                as_of,
                "000001.SZ",
                TradingEligibilityStatus.ELIGIBLE,
            ),
            HistoricalTradingEligibilityRecord(
                as_of,
                "000002.SZ",
                TradingEligibilityStatus.INELIGIBLE,
                ("SUSPENDED",),
            ),
            HistoricalTradingEligibilityRecord(
                as_of,
                "000003.SZ",
                TradingEligibilityStatus.ELIGIBLE,
            ),
        ),
    )


def test_candidate_population_requires_membership_and_explicit_eligibility() -> None:
    population = build_candidate_population_from_historical_artifacts(
        universe_artifact=_universe(),
        eligibility_artifact=_eligibility(),
        decision_time=DecisionTime(DECISION_AT),
    )

    assert population.symbols == ("000001.SZ",)
    assert len(population.source_dataset_ids) == 1


def test_historical_eligibility_does_not_carry_forward_earlier_snapshot() -> None:
    earlier = AsOfTime(datetime(2026, 7, 15, 14, 50, tzinfo=TZ))
    artifact = build_historical_trading_eligibility_artifact(
        source_dataset_id=DATASET_ID,
        policy_version="fixture-eligibility-v1",
        records=(
            HistoricalTradingEligibilityRecord(
                earlier,
                "000001.SZ",
                TradingEligibilityStatus.ELIGIBLE,
            ),
        ),
    )

    with pytest.raises(KeyError):
        artifact.snapshot_for_decision_time(DecisionTime(DECISION_AT))


def test_historical_eligibility_identity_changes_with_policy_version() -> None:
    as_of = AsOfTime(DECISION_AT)
    records = (
        HistoricalTradingEligibilityRecord(
            as_of,
            "000001.SZ",
            TradingEligibilityStatus.ELIGIBLE,
        ),
    )
    first = build_historical_trading_eligibility_artifact(
        source_dataset_id=DATASET_ID,
        policy_version="eligibility-v1",
        records=records,
    )
    second = build_historical_trading_eligibility_artifact(
        source_dataset_id=DATASET_ID,
        policy_version="eligibility-v2",
        records=records,
    )

    assert first.artifact_id != second.artifact_id


def test_historical_eligibility_rejects_duplicate_time_symbol_key() -> None:
    as_of = AsOfTime(DECISION_AT)
    with pytest.raises(ValueError, match="unique time-symbol keys"):
        build_historical_trading_eligibility_artifact(
            source_dataset_id=DATASET_ID,
            policy_version="eligibility-v1",
            records=(
                HistoricalTradingEligibilityRecord(
                    as_of,
                    "000001.SZ",
                    TradingEligibilityStatus.ELIGIBLE,
                ),
                HistoricalTradingEligibilityRecord(
                    as_of,
                    "000001.SZ",
                    TradingEligibilityStatus.INELIGIBLE,
                ),
            ),
        )
