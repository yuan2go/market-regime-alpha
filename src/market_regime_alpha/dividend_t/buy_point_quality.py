"""Buy-point subtype classification and 5-day hit-rate priors."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime_alpha.dividend_t.signal_intent import PrimarySetupCode

BUY_POINT_SUBTYPE_NONE = "none"
BUY_POINT_SUBTYPE_PULLBACK_LOW_BUY = "pullback_low_buy"
BUY_POINT_SUBTYPE_VWAP_RECLAIM = "vwap_reclaim"
BUY_POINT_SUBTYPE_TREND_FOLLOW = "trend_follow"
BUY_POINT_SUBTYPE_BREAKOUT_WATCH = "breakout_watch"
BUY_POINT_SUBTYPE_BREAKOUT_CONFIRMED = "breakout_confirmed"
BUY_POINT_SUBTYPE_OVERHEAT_BLOCKED = "overheat_blocked"

BUY_ACTIONS = frozenset({"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"})
WATCH_BREAKOUT_ACTIONS = frozenset({"WATCH_BREAKOUT_NEXT_DAY", "WAIT_BREAKOUT_FOLLOW_THROUGH"})


@dataclass(frozen=True)
class BuyPointPrior:
    subtype: str
    sample_count: int
    hit_rate_5d: float
    average_return_5d: float


# Empirical priors from the current local 20-symbol, 1-year 5m hit-rate report.
# They are intentionally conservative and shrink downstream toward the raw model.
BUY_POINT_5D_PRIORS: dict[str, BuyPointPrior] = {
    BUY_POINT_SUBTYPE_PULLBACK_LOW_BUY: BuyPointPrior(BUY_POINT_SUBTYPE_PULLBACK_LOW_BUY, 99, 0.4848, 0.0021),
    BUY_POINT_SUBTYPE_VWAP_RECLAIM: BuyPointPrior(BUY_POINT_SUBTYPE_VWAP_RECLAIM, 215, 0.4605, -0.0009),
    BUY_POINT_SUBTYPE_TREND_FOLLOW: BuyPointPrior(BUY_POINT_SUBTYPE_TREND_FOLLOW, 367, 0.4360, -0.0019),
    BUY_POINT_SUBTYPE_BREAKOUT_CONFIRMED: BuyPointPrior(BUY_POINT_SUBTYPE_BREAKOUT_CONFIRMED, 51, 0.2941, -0.0168),
    BUY_POINT_SUBTYPE_BREAKOUT_WATCH: BuyPointPrior(BUY_POINT_SUBTYPE_BREAKOUT_WATCH, 51, 0.2941, -0.0168),
    BUY_POINT_SUBTYPE_OVERHEAT_BLOCKED: BuyPointPrior(BUY_POINT_SUBTYPE_OVERHEAT_BLOCKED, 138, 0.3188, -0.0149),
    BUY_POINT_SUBTYPE_NONE: BuyPointPrior(BUY_POINT_SUBTYPE_NONE, 418, 0.4187, -0.0037),
}


BUY_POINT_SUBTYPE_BY_SETUP: dict[PrimarySetupCode, str] = {
    PrimarySetupCode.PULLBACK_LOW_BUY: BUY_POINT_SUBTYPE_PULLBACK_LOW_BUY,
    PrimarySetupCode.VWAP_RECLAIM: BUY_POINT_SUBTYPE_VWAP_RECLAIM,
    PrimarySetupCode.INTRADAY_REVERSAL: "reversal",
    PrimarySetupCode.RANGE_LOW_BUY: "range_low",
    PrimarySetupCode.FORCE_REVERSAL_PROBE: "reversal",
    PrimarySetupCode.TREND_FOLLOW: BUY_POINT_SUBTYPE_TREND_FOLLOW,
    PrimarySetupCode.TREND_PULLBACK_FOLLOW: "trend_pullback",
    PrimarySetupCode.BREAKOUT_CONFIRMED: BUY_POINT_SUBTYPE_BREAKOUT_CONFIRMED,
    PrimarySetupCode.THIRD_BUY_FOLLOW: "third_buy",
    PrimarySetupCode.STRONG_LAUNCH_FOLLOW: "strong_launch",
    PrimarySetupCode.ATTENTION_FEEDBACK_FOLLOW: "attention_feedback",
}


def classify_buy_point_subtype(primary_setup_code: PrimarySetupCode | str | None) -> str:
    """Return a stable reporting subtype from the branch-owned primary setup."""

    if isinstance(primary_setup_code, str):
        try:
            primary_setup_code = PrimarySetupCode(primary_setup_code)
        except ValueError:
            return BUY_POINT_SUBTYPE_NONE
    return BUY_POINT_SUBTYPE_BY_SETUP.get(primary_setup_code, BUY_POINT_SUBTYPE_NONE)


def buy_point_overheat_reasons(
    *,
    trend_state: str = "RANGE",
    volume_price_state: str = "NEUTRAL",
    volume_price_score: float = 50.0,
    volume_breakout_score: float = 50.0,
    high_volume_stall_score: float = 0.0,
    capital_flow_confirmation_state: str = "UNCONFIRMED",
    up_probability_1d: float = 0.50,
    pretrade_volume_ratio_to_prev: float = 1.0,
    breakout_confirmed: bool = False,
    breakout_score: float = 0.0,
) -> tuple[str, ...]:
    """Detect setups that historically lowered 5-day buy-point hit rate."""

    reasons: list[str] = []
    if (
        trend_state == "UPTREND"
        and str(volume_price_state).upper() == "VOLUME_BREAKOUT"
        and capital_flow_confirmation_state == "CONFIRMED_INFLOW"
    ):
        reasons.append("强趋势+放量突破+确认流入组合在当前样本中 5 日命中率偏低，按过热处理。")
    if str(volume_price_state).upper() == "VOLUME_BREAKOUT" and up_probability_1d > 0.56:
        reasons.append("放量突破叠加 1 日上行概率过高，容易对应短线过热而非高胜率买点。")
    if volume_price_score >= 80.0 and up_probability_1d > 0.56:
        reasons.append("量价分和上行概率同时过高，当前样本中后续 5 日回落概率上升。")
    if pretrade_volume_ratio_to_prev > 1.0 and str(volume_price_state).upper() == "VOLUME_BREAKOUT":
        reasons.append("买点前成交量已经放大，未经过回踩确认前不追涨。")
    if high_volume_stall_score >= 72.0 and (trend_state == "UPTREND" or str(volume_price_state).upper() == "VOLUME_BREAKOUT" or breakout_confirmed):
        reasons.append("高量滞涨分过高，先视为派发/承接不足风险。")
    if breakout_confirmed and breakout_score >= 88.0 and up_probability_1d > 0.56:
        reasons.append("高分突破且上行概率过热，突破买点先降级为观察。")
    return tuple(reasons)


def is_overheated_buy_point(**kwargs: object) -> bool:
    return bool(buy_point_overheat_reasons(**kwargs))


def breakout_buy_confirmation_allowed(
    *,
    sell_pressure_score: float,
    vwap_support_score: float,
    post_breakout_volume_persistence_score: float,
    high_volume_stall_score: float,
    up_probability_1d: float,
    overheated: bool,
) -> bool:
    """Strict confirmation gate before a breakout can remain a real buy point."""

    return (
        not overheated
        and sell_pressure_score < 60.0
        and vwap_support_score >= 70.0
        and post_breakout_volume_persistence_score >= 76.0
        and high_volume_stall_score < 60.0
        and up_probability_1d <= 0.56
    )


def calibrated_buy_win_rate_5d(*, subtype: str, raw_estimated_win_rate: float) -> float:
    """Shrink the raw formula estimate toward observed 5-day hit-rate priors."""

    prior = BUY_POINT_5D_PRIORS.get(subtype, BUY_POINT_5D_PRIORS[BUY_POINT_SUBTYPE_NONE])
    weight = min(max(prior.sample_count / (prior.sample_count + 120.0), 0.0), 0.82)
    calibrated = weight * prior.hit_rate_5d + (1.0 - weight) * raw_estimated_win_rate
    return round(min(max(calibrated, 0.32), 0.58), 4)
