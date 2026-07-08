"""Signal-strength scoring for the COSCO timing engine."""

from __future__ import annotations

from market_regime_alpha.dividend_t.certainty import CertaintyScore
from market_regime_alpha.dividend_t.chan import BUY_POINTS, SELL_POINTS, ChanStructure
from market_regime_alpha.dividend_t.cosco_timing_capital_flow import _capital_flow_confirms_buy
from market_regime_alpha.dividend_t.cosco_timing_types import (
    BreakoutSetup,
    CapitalFlowEstimate,
    DailyContext,
    IntradayContext,
    MultiPeriodTrend,
    SignalStrength,
    TrendProbability,
    VolumePriceStructure,
)
from market_regime_alpha.dividend_t.force_ratio import ForceRatioEstimate
from market_regime_alpha.dividend_t.scoring import clamp
from market_regime_alpha.dividend_t.sell_pressure import SellPressureEstimate

def _signal_strength(
    *,
    action: str,
    force: ForceRatioEstimate,
    certainty: CertaintyScore,
    sell_pressure: SellPressureEstimate,
    daily_context: DailyContext,
    intraday_context: IntradayContext,
    multi_period_trend: MultiPeriodTrend,
    capital_flow: CapitalFlowEstimate,
    volume_price_structure: VolumePriceStructure,
    trend_probability: TrendProbability,
    breakout_setup: BreakoutSetup,
    chan_structure: ChanStructure,
    risk_reward_ratio: float,
) -> SignalStrength:
    score = _buy_signal_strength_score(
        force=force,
        certainty=certainty,
        sell_pressure=sell_pressure,
        daily_context=daily_context,
        intraday_context=intraday_context,
        multi_period_trend=multi_period_trend,
        capital_flow=capital_flow,
        chan_structure=chan_structure,
        volume_price_structure=volume_price_structure,
        risk_reward_ratio=risk_reward_ratio,
    )
    score += clamp((trend_probability.up_1d - 0.52) * 80.0, -6.0, 8.0)
    score += clamp((trend_probability.up_3d - 0.52) * 60.0, -5.0, 7.0)
    score -= clamp((trend_probability.down_1d - 0.55) * 80.0, 0.0, 8.0)
    if action == "BREAKOUT_BUY_TIMING":
        score += clamp((breakout_setup.score - 62.0) * 0.60, -4.0, 16.0)
        score += clamp((volume_price_structure.volume_breakout_score - 65.0) * 0.18, -3.0, 8.0)
        score += clamp((volume_price_structure.post_breakout_volume_persistence_score - 60.0) * 0.14, -2.0, 6.0)
    elif action == "WATCH_BREAKOUT_NEXT_DAY":
        score = max(score, min(64.0, breakout_setup.score - 4.0))
    if action in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"} and chan_structure.buy_point_type in BUY_POINTS:
        score += clamp((chan_structure.score - 58.0) * 0.20, 2.0, 8.0)
    if chan_structure.sell_point_type in SELL_POINTS:
        score -= 12.0
    if action in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"} and _capital_flow_confirms_buy(capital_flow, min_score=60.0):
        score += clamp((capital_flow.confirmation_score - 58.0) * 0.18, 2.0, 8.0)
    if action in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"}:
        if volume_price_structure.low_volume_pullback_score >= 70.0:
            score += 4.0
        if volume_price_structure.vwap_support_score >= 68.0:
            score += 3.0
        if volume_price_structure.high_volume_stall_score >= 72.0:
            score -= 7.0
        if volume_price_structure.price_up_volume_down_score >= 76.0:
            score -= 5.0
    score = clamp(score, 0.0, 100.0)
    if action not in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"}:
        score = min(score, 49.0)
    reward_risk = clamp(risk_reward_ratio, 0.5, 4.0)
    if action == "BREAKOUT_BUY_TIMING":
        reward_risk = clamp(max(reward_risk, 1.35 + breakout_setup.score / 100.0), 0.5, 4.0)
    model_win_rate = 0.55 * trend_probability.up_1d + 0.45 * trend_probability.up_3d
    if action == "BREAKOUT_BUY_TIMING":
        model_win_rate = max(model_win_rate, clamp(0.48 + (breakout_setup.score - 60.0) * 0.003, 0.45, 0.62))
    strength_win_rate = 0.46 + (score - 50.0) * 0.004
    estimated_win_rate = clamp(0.55 * model_win_rate + 0.45 * strength_win_rate, 0.38, 0.66)
    kelly = max(0.0, estimated_win_rate - (1.0 - estimated_win_rate) / reward_risk)
    label = _signal_strength_label(score)
    reasons = (
        f"买入强度={score:.1f}，等级={label}。",
        f"概率门控={trend_probability.state}，1日上行={trend_probability.up_1d:.1%}，3日上行={trend_probability.up_3d:.1%}。",
        f"突破状态={breakout_setup.state}，突破分={breakout_setup.score:.1f}。",
        f"量价结构={volume_price_structure.state}，V={volume_price_structure.score:.1f}，放量突破={volume_price_structure.volume_breakout_score:.1f}，VWAP={volume_price_structure.vwap_support_score:.1f}。",
        f"缠论结构={chan_structure.structure_type}，买点={chan_structure.buy_point_type}，卖点={chan_structure.sell_point_type}，C={chan_structure.score:.1f}。",
        f"资金流确认={capital_flow.confirmation_state}，确认分={capital_flow.confirmation_score:.1f}，来源={capital_flow.source_type}。",
        f"估计胜率={estimated_win_rate:.1%}，盈亏比={reward_risk:.2f}，Kelly={kelly:.1%}。",
        "Kelly 只用于手动仓位参考，回测会再做折扣、总仓位上限和单次主动买入约束。",
    )
    return SignalStrength(
        score=round(score, 2),
        label=label,
        estimated_win_rate=round(estimated_win_rate, 4),
        reward_risk_ratio=round(reward_risk, 4),
        kelly_fraction=round(kelly, 4),
        reasons=reasons,
    )


def _buy_signal_strength_score(
    *,
    force: ForceRatioEstimate,
    certainty: CertaintyScore,
    sell_pressure: SellPressureEstimate,
    daily_context: DailyContext,
    intraday_context: IntradayContext,
    multi_period_trend: MultiPeriodTrend,
    capital_flow: CapitalFlowEstimate,
    chan_structure: ChanStructure,
    volume_price_structure: VolumePriceStructure | None = None,
    risk_reward_ratio: float,
) -> float:
    risk_reward_component = clamp((risk_reward_ratio / 2.5) * 100.0, 20.0, 100.0)
    sell_pressure_component = clamp(100.0 - sell_pressure.score, 0.0, 100.0)
    volume_price_score = 50.0 if volume_price_structure is None else volume_price_structure.score
    score = (
        0.22 * force.weighted_score
        + 0.10 * volume_price_score
        + 0.15 * certainty.score
        + 0.12 * daily_context.score
        + 0.11 * intraday_context.score
        + 0.10 * risk_reward_component
        + 0.08 * sell_pressure_component
        + 0.06 * multi_period_trend.score
        + 0.06 * capital_flow.score
        + 0.02 * chan_structure.score
    )
    if volume_price_structure is not None:
        if volume_price_structure.volume_breakout_score >= 72.0:
            score += 5.0
        if volume_price_structure.low_volume_pullback_score >= 72.0:
            score += 5.0
        if volume_price_structure.post_breakout_volume_persistence_score >= 72.0:
            score += 4.0
        if volume_price_structure.vwap_support_score >= 68.0:
            score += 3.0
        if volume_price_structure.high_volume_stall_score >= 72.0:
            score -= 7.0
        if volume_price_structure.price_up_volume_down_score >= 76.0:
            score -= 5.0
    if _capital_flow_confirms_buy(capital_flow, min_score=60.0):
        score += clamp((capital_flow.confirmation_score - 58.0) * 0.22, 2.0, 9.0)
    if force.force_ratio >= 1.20:
        score += 6.0
    elif force.force_ratio >= 1.02:
        score += 3.0
    if daily_context.state == "WEAK":
        score -= 16.0
    if multi_period_trend.monthly_state == "DOWN":
        score -= 8.0
    if capital_flow.state == "OUTFLOW":
        score -= 6.0
    if capital_flow.confirmation_state == "CONFIRMED_OUTFLOW":
        score -= 8.0
    if intraday_context.support_confirmed:
        score += 6.0
    elif intraday_context.near_support and intraday_context.five_min_reclaim:
        score += 3.0
    if chan_structure.buy_point_type == "buy3":
        score += 7.0
    elif chan_structure.buy_point_type in {"buy1", "buy2", "range_buy"}:
        score += 5.0
    if chan_structure.sell_point_type in SELL_POINTS or chan_structure.structure_type == "breakdown":
        score -= 14.0
    if intraday_context.late_session and not daily_context.allow_overnight:
        score -= 8.0
    return clamp(score, 0.0, 100.0)


def _signal_strength_label(score: float) -> str:
    if score >= 78.0:
        return "强"
    if score >= 66.0:
        return "中强"
    if score >= 56.0:
        return "试探"
    if score >= 45.0:
        return "弱"
    return "无效"
