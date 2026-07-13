from __future__ import annotations

from market_regime_alpha.dividend_t.buy_point_quality import (
    BUY_POINT_SUBTYPE_BREAKOUT_CONFIRMED,
    BUY_POINT_SUBTYPE_PULLBACK_LOW_BUY,
    breakout_buy_confirmation_allowed,
    buy_point_overheat_reasons,
    calibrated_buy_win_rate_5d,
    classify_buy_point_subtype,
)
from market_regime_alpha.dividend_t.signal_intent import PrimarySetupCode


def test_overheat_reasons_flag_uptrend_volume_breakout_inflow_cluster() -> None:
    reasons = buy_point_overheat_reasons(
        trend_state="UPTREND",
        volume_price_state="VOLUME_BREAKOUT",
        volume_price_score=84.0,
        volume_breakout_score=88.0,
        high_volume_stall_score=45.0,
        capital_flow_confirmation_state="CONFIRMED_INFLOW",
        up_probability_1d=0.57,
        pretrade_volume_ratio_to_prev=1.2,
        breakout_confirmed=True,
        breakout_score=90.0,
    )

    assert reasons
    assert any("5 日命中率偏低" in reason for reason in reasons)


def test_breakout_confirmation_requires_low_heat_follow_through() -> None:
    assert not breakout_buy_confirmation_allowed(
        sell_pressure_score=58.0,
        vwap_support_score=72.0,
        post_breakout_volume_persistence_score=78.0,
        high_volume_stall_score=55.0,
        up_probability_1d=0.57,
        overheated=False,
    )
    assert breakout_buy_confirmation_allowed(
        sell_pressure_score=58.0,
        vwap_support_score=72.0,
        post_breakout_volume_persistence_score=78.0,
        high_volume_stall_score=55.0,
        up_probability_1d=0.55,
        overheated=False,
    )


def test_classify_buy_point_subtype_uses_primary_setup_only() -> None:
    assert classify_buy_point_subtype(PrimarySetupCode.PULLBACK_LOW_BUY) == BUY_POINT_SUBTYPE_PULLBACK_LOW_BUY
    assert classify_buy_point_subtype(PrimarySetupCode.BREAKOUT_CONFIRMED) == BUY_POINT_SUBTYPE_BREAKOUT_CONFIRMED
    assert classify_buy_point_subtype(None) == "none"


def test_reporting_subtype_does_not_parse_reason_or_market_features() -> None:
    assert classify_buy_point_subtype(PrimarySetupCode.TREND_FOLLOW) == "trend_follow"


def test_calibrated_buy_win_rate_shrinks_breakout_raw_estimate() -> None:
    calibrated = calibrated_buy_win_rate_5d(
        subtype=BUY_POINT_SUBTYPE_BREAKOUT_CONFIRMED,
        raw_estimated_win_rate=0.63,
    )

    assert calibrated < 0.55
