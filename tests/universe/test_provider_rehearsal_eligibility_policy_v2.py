from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.time import AsOfTime, AvailabilityTime
from market_regime_alpha.universe.contracts import TradingEligibilityStatus
from market_regime_alpha.universe.eligibility_policy import (
    DecisionBuyabilityStatus,
    RawTradingEligibilityObservation,
    TradingEligibilityReason,
    r5_provider_rehearsal_trading_eligibility_policy_v2,
    r5_rehearsal_trading_eligibility_policy_v1,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION_AT = datetime(2026, 7, 15, 14, 55, tzinfo=TZ)
LIQUIDITY_MEASURE = "AVG_AMOUNT_20D_CNY"
MIN_LIQUIDITY = 50_000_000.0


def _raw(
    *,
    listing_age_calendar_days: int | None = 120,
    liquidity_value: float | None = 80_000_000.0,
    liquidity_measure_id: str | None = LIQUIDITY_MEASURE,
    decision_buyability: DecisionBuyabilityStatus | None = DecisionBuyabilityStatus.BUYABLE,
    is_suspended: bool | None = False,
    is_st: bool | None = False,
) -> RawTradingEligibilityObservation:
    return RawTradingEligibilityObservation(
        as_of=AsOfTime(DECISION_AT),
        available_at=AvailabilityTime(DECISION_AT),
        symbol="000001.SZ",
        is_suspended=is_suspended,
        is_st=is_st,
        prev_close=10.0,
        limit_up_price=11.0,
        limit_down_price=9.0,
        limit_regime="MAIN_BOARD_10PCT",
        listing_age_calendar_days=listing_age_calendar_days,
        liquidity_value=liquidity_value,
        liquidity_measure_id=liquidity_measure_id,
        decision_buyability=decision_buyability,
    )


def _policy():
    return r5_provider_rehearsal_trading_eligibility_policy_v2(
        minimum_liquidity_value=MIN_LIQUIDITY,
        liquidity_measure_id=LIQUIDITY_MEASURE,
        minimum_listing_age_calendar_days=60,
    )


def test_provider_rehearsal_v2_complete_evidence_is_eligible() -> None:
    status, reasons = _policy().evaluate(_raw())

    assert status is TradingEligibilityStatus.ELIGIBLE
    assert reasons == ()


@pytest.mark.parametrize(
    ("observation", "reason"),
    [
        (_raw(listing_age_calendar_days=59), TradingEligibilityReason.LISTING_AGE_BELOW_MINIMUM.value),
        (_raw(liquidity_value=49_999_999.0), TradingEligibilityReason.LIQUIDITY_BELOW_MINIMUM.value),
        (_raw(decision_buyability=DecisionBuyabilityStatus.NOT_BUYABLE), TradingEligibilityReason.DECISION_NOT_BUYABLE.value),
    ],
)
def test_provider_rehearsal_v2_hard_exclusions(observation, reason: str) -> None:
    status, reasons = _policy().evaluate(observation)

    assert status is TradingEligibilityStatus.INELIGIBLE
    assert reason in reasons


@pytest.mark.parametrize(
    ("observation", "reason"),
    [
        (_raw(listing_age_calendar_days=None), TradingEligibilityReason.LISTING_AGE_MISSING.value),
        (
            _raw(liquidity_value=None, liquidity_measure_id=None),
            TradingEligibilityReason.LIQUIDITY_VALUE_MISSING.value,
        ),
        (
            _raw(liquidity_value=80_000_000.0, liquidity_measure_id="MEDIAN_AMOUNT_20D_CNY"),
            TradingEligibilityReason.LIQUIDITY_MEASURE_MISMATCH.value,
        ),
        (_raw(decision_buyability=None), TradingEligibilityReason.DECISION_BUYABILITY_MISSING.value),
        (
            _raw(decision_buyability=DecisionBuyabilityStatus.UNKNOWN),
            TradingEligibilityReason.DECISION_BUYABILITY_UNKNOWN.value,
        ),
    ],
)
def test_provider_rehearsal_v2_missing_or_mismatched_evidence_is_unknown(observation, reason: str) -> None:
    status, reasons = _policy().evaluate(observation)

    assert status is TradingEligibilityStatus.UNKNOWN
    assert reason in reasons


def test_v1_remains_legacy_compatible_without_v2_evidence() -> None:
    observation = RawTradingEligibilityObservation(
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

    status, reasons = r5_rehearsal_trading_eligibility_policy_v1().evaluate(observation)

    assert status is TradingEligibilityStatus.ELIGIBLE
    assert reasons == ()


def test_v2_does_not_silently_downgrade_to_v1_when_provider_evidence_is_missing() -> None:
    observation = RawTradingEligibilityObservation(
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

    status, reasons = _policy().evaluate(observation)

    assert status is TradingEligibilityStatus.UNKNOWN
    assert TradingEligibilityReason.LISTING_AGE_MISSING.value in reasons
    assert TradingEligibilityReason.LIQUIDITY_VALUE_MISSING.value in reasons
    assert TradingEligibilityReason.DECISION_BUYABILITY_MISSING.value in reasons


def test_v2_policy_identity_changes_with_liquidity_threshold_and_measure() -> None:
    baseline = _policy()
    stricter = r5_provider_rehearsal_trading_eligibility_policy_v2(
        minimum_liquidity_value=100_000_000.0,
        liquidity_measure_id=LIQUIDITY_MEASURE,
    )
    different_measure = r5_provider_rehearsal_trading_eligibility_policy_v2(
        minimum_liquidity_value=MIN_LIQUIDITY,
        liquidity_measure_id="MEDIAN_AMOUNT_20D_CNY",
    )

    assert baseline.policy_artifact_id != stricter.policy_artifact_id
    assert baseline.policy_artifact_id != different_measure.policy_artifact_id
    assert baseline.policy_version == "r5-provider-rehearsal-trading-eligibility@v2"
