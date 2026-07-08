"""Breakout setup detection for the COSCO timing engine."""

from __future__ import annotations

from typing import Any

from market_regime_alpha.dividend_t.attention import AttentionScore
from market_regime_alpha.dividend_t.certainty import CertaintyScore
from market_regime_alpha.dividend_t.chan import SELL_POINTS, ChanStructure
from market_regime_alpha.dividend_t.cosco_timing_capital_flow import _capital_flow_confirms_buy, _vwap
from market_regime_alpha.dividend_t.cosco_timing_daily import _daily_bars
from market_regime_alpha.dividend_t.cosco_timing_types import (
    BreakoutSetup,
    CapitalFlowEstimate,
    DailyContext,
    IntradayContext,
    MultiPeriodTrend,
    TrendProbability,
    VolumePriceStructure,
)
from market_regime_alpha.dividend_t.force_ratio import ForceRatioEstimate
from market_regime_alpha.dividend_t.models import TrendState
from market_regime_alpha.dividend_t.scoring import clamp
from market_regime_alpha.dividend_t.sell_pressure import SellPressureEstimate

def _breakout_setup(
    frame: Any,
    *,
    levels: dict[str, float],
    force: ForceRatioEstimate,
    attention: AttentionScore,
    certainty: CertaintyScore,
    sell_pressure: SellPressureEstimate,
    trend_state: TrendState,
    daily_context: DailyContext,
    intraday_context: IntradayContext,
    multi_period_trend: MultiPeriodTrend,
    capital_flow: CapitalFlowEstimate,
    volume_price_structure: VolumePriceStructure,
    trend_probability: TrendProbability,
    chan_structure: ChanStructure,
) -> BreakoutSetup:
    data = frame.copy().sort_values("timestamp").reset_index(drop=True)
    data["trade_date"] = data["timestamp"].dt.date
    latest_day = data["trade_date"].iloc[-1]
    today = data[data["trade_date"] == latest_day]
    prior_intraday = data[data["trade_date"] != latest_day]
    daily = _daily_bars(data)
    prior_daily = daily.iloc[:-1]
    current = levels["current"]
    atr = max(levels["atr"], current * 0.002)
    if len(today) == 0 or (len(prior_daily) < 2 and len(prior_intraday) < 96):
        return BreakoutSetup(
            score=0.0,
            state="INSUFFICIENT",
            breakout_level=None,
            trigger_price=None,
            day_return=0.0,
            recent_return=0.0,
            volume_expansion=0.0,
            distance_to_breakout=None,
            breakout_confirmed=False,
            pre_breakout_watch=False,
            reasons=("突破模块样本不足：至少需要 2 个历史交易日或 96 根历史 5 分钟线。",),
        )

    prior_resistance = float(prior_daily["high"].tail(min(8, len(prior_daily))).max())
    if len(prior_intraday) >= 48:
        prior_resistance = max(prior_resistance, float(prior_intraday["high"].tail(96).max()))
    trigger_price = prior_resistance + max(0.03 * atr, current * 0.0015)
    day_open = float(today["open"].iloc[0])
    day_high = float(today["high"].max())
    day_low = float(today["low"].min())
    day_return = current / day_open - 1.0 if day_open > 0 else 0.0
    recent_window = min(6, len(today))
    recent_base = float(today["close"].iloc[-recent_window])
    recent_return = current / recent_base - 1.0 if recent_base > 0 else 0.0
    recent_volume = float(today["volume"].tail(recent_window).mean())
    prior_volume = float(prior_intraday["volume"].tail(min(240, len(prior_intraday))).mean()) if len(prior_intraday) else recent_volume
    volume_expansion = recent_volume / prior_volume if prior_volume > 0 else 1.0
    today_vwap = _vwap(today)
    vwap_hold = current >= today_vwap * 1.001 if today_vwap > 0 else True
    above_breakout = current >= trigger_price or (day_high >= trigger_price and current >= prior_resistance + 0.05 * atr)
    distance_to_breakout = (prior_resistance - current) / current if current > 0 else None

    score = 35.0
    reasons: list[str] = []
    if above_breakout:
        score += 18.0
        reasons.append(f"价格突破近端压力 {prior_resistance:.3f}，触发价约 {trigger_price:.3f}。")
    if day_return >= 0.025:
        score += 18.0
        reasons.append(f"当日涨幅 {day_return:.1%}，属于强势启动。")
    elif day_return >= 0.012:
        score += 10.0
        reasons.append(f"当日涨幅 {day_return:.1%}，有启动迹象。")
    if recent_return >= 0.008:
        score += 9.0
        reasons.append(f"最近 {recent_window} 根 5 分钟涨幅 {recent_return:.1%}，短线加速度出现。")
    elif recent_return >= 0.004:
        score += 4.0
    if volume_expansion >= 1.30:
        score += 11.0
        reasons.append(f"最近量能放大到历史均量 {volume_expansion:.2f} 倍。")
    elif volume_expansion >= 0.95:
        score += 5.0
    if vwap_hold:
        score += 8.0
        reasons.append("当前价格站在当日 VWAP 上方，分时承接尚可。")
    score += clamp((volume_price_structure.volume_breakout_score - 58.0) * 0.18, -4.0, 10.0)
    score += clamp((volume_price_structure.vwap_support_score - 58.0) * 0.12, -3.0, 6.0)
    score += clamp((volume_price_structure.post_breakout_volume_persistence_score - 58.0) * 0.14, -3.0, 8.0)
    if volume_price_structure.volume_breakout_score >= 70.0:
        reasons.append(f"量价结构确认放量突破，V_break={volume_price_structure.volume_breakout_score:.1f}。")
    if volume_price_structure.high_volume_stall_score >= 72.0:
        score -= 8.0
        reasons.append(f"量价结构提示放量滞涨，stall={volume_price_structure.high_volume_stall_score:.1f}。")
    if volume_price_structure.price_up_volume_down_score >= 76.0:
        score -= 5.0
        reasons.append(f"量价结构提示价涨量缩，up_vol_down={volume_price_structure.price_up_volume_down_score:.1f}。")
    if trend_state == TrendState.UPTREND:
        score += 7.0
    elif trend_state == TrendState.DOWNTREND:
        score -= 8.0
    if daily_context.state == "STRONG":
        score += 8.0
    elif daily_context.state == "NEUTRAL":
        score += 3.0
    else:
        score -= 10.0
    flow_confirmed = _capital_flow_confirms_buy(capital_flow, min_score=62.0)
    score += clamp((capital_flow.score - 50.0) * 0.22, -7.0, 9.0)
    score += clamp((capital_flow.confirmation_score - 55.0) * 0.16, -4.0, 7.0)
    score += clamp((attention.score - 58.0) * 0.16, -4.0, 6.0)
    score += clamp((certainty.score - 58.0) * 0.12, -3.0, 5.0)
    if flow_confirmed:
        score += 5.0
        reasons.append(f"资金流确认={capital_flow.confirmation_state}，确认分 {capital_flow.confirmation_score:.1f}。")
    if chan_structure.buy_point_type == "buy3":
        score += 8.0
        reasons.append("缠论三买确认：突破中枢后回踩未回中枢。")
    elif chan_structure.structure_type == "breakout":
        score += 4.0
    if chan_structure.sell_point_type in SELL_POINTS:
        score -= 12.0
        reasons.append(f"缠论卖点={chan_structure.sell_point_type}，突破信号降级。")
    if force.weighted_score >= 52.0:
        score += 3.0
    if trend_probability.up_1d >= 0.52 and trend_probability.down_1d < 0.58:
        score += 4.0
    if sell_pressure.score >= 84.0:
        score -= 14.0
        reasons.append("最大可卖量压力过高，突破失败风险上升。")
    elif sell_pressure.score >= 74.0:
        score -= 5.0
    if multi_period_trend.monthly_state == "DOWN":
        score -= 10.0
        reasons.append("月线向下，突破只能按短线试错处理。")

    confirmed = (
        above_breakout
        and score >= 78.0
        and daily_context.fundamental_score >= 60.0
        and (day_return >= 0.018 or recent_return >= 0.010)
        and (
            volume_expansion >= (0.92 if chan_structure.buy_point_type == "buy3" else (0.98 if flow_confirmed else 1.10))
            or volume_price_structure.volume_breakout_score >= 70.0
        )
        and vwap_hold
        and volume_price_structure.high_volume_stall_score < 74.0
        and sell_pressure.score <= 82.0
        and chan_structure.sell_point_type not in SELL_POINTS
    )

    latest_daily = daily.iloc[-1]
    previous_daily = prior_daily.iloc[-1]
    prior_volume_ma = float(prior_daily["volume"].tail(min(5, len(prior_daily))).mean())
    previous_range = (float(previous_daily["high"]) - float(previous_daily["low"])) / float(previous_daily["close"])
    latest_range = (float(latest_daily["high"]) - float(latest_daily["low"])) / float(latest_daily["close"])
    latest_volume = float(latest_daily["volume"])
    close_series = daily["close"]
    ma5 = float(close_series.tail(min(5, len(close_series))).mean())
    ma5_previous = float(close_series.iloc[:-1].tail(min(5, len(close_series) - 1)).mean()) if len(close_series) >= 6 else ma5
    close_position = (current - day_low) / max(day_high - day_low, current * 0.002)
    near_breakout = distance_to_breakout is not None and -0.004 <= distance_to_breakout <= 0.026
    volume_not_exhausted = latest_volume <= prior_volume_ma * 1.18 if prior_volume_ma > 0 else True
    compressed = min(previous_range, latest_range) <= 0.035
    ma_ready = current >= ma5 * 0.995 and ma5 >= ma5_previous * 0.992
    pre_score = 42.0
    if near_breakout:
        pre_score += 18.0
    if compressed:
        pre_score += 10.0
    if ma_ready:
        pre_score += 9.0
    if close_position >= 0.55:
        pre_score += 6.0
    if volume_not_exhausted:
        pre_score += 5.0
    if capital_flow.score >= 46.0:
        pre_score += 5.0
    if _capital_flow_confirms_buy(capital_flow, min_score=60.0):
        pre_score += 6.0
    if sell_pressure.score <= 72.0:
        pre_score += 4.0
    if daily_context.state == "WEAK":
        pre_score -= 14.0
    if trend_probability.state == "DOWN_RISK":
        pre_score -= 10.0
    early_score = 40.0
    early_near_trigger = distance_to_breakout is not None and -0.006 <= distance_to_breakout <= 0.028
    early_acceleration = day_return >= 0.010 or recent_return >= 0.0045
    early_not_extended = day_return <= 0.034 and close_position <= 0.96
    if early_near_trigger:
        early_score += 18.0
    if early_acceleration:
        early_score += 14.0
    if volume_expansion >= 1.05:
        early_score += 9.0
    if volume_price_structure.volume_breakout_score >= 66.0:
        early_score += 7.0
    if volume_price_structure.vwap_support_score >= 66.0:
        early_score += 5.0
    if volume_price_structure.high_volume_stall_score >= 74.0:
        early_score -= 8.0
    if vwap_hold:
        early_score += 7.0
    if close_position >= 0.58:
        early_score += 6.0
    if capital_flow.score >= 58.0:
        early_score += 7.0
    elif _capital_flow_confirms_buy(capital_flow, min_score=60.0):
        early_score += 6.0
    elif capital_flow.short_flow_ratio >= 0.10:
        early_score += 5.0
    if sell_pressure.score <= 68.0:
        early_score += 4.0
    if daily_context.state == "WEAK":
        early_score -= 12.0
    if trend_probability.state == "DOWN_RISK":
        early_score -= 10.0
    early_start = (
        not confirmed
        and not intraday_context.late_session
        and early_score >= 74.0
        and early_near_trigger
        and early_acceleration
        and early_not_extended
        and (volume_expansion >= 0.95 or volume_price_structure.volume_breakout_score >= 66.0)
        and vwap_hold
        and (capital_flow.score >= 50.0 or _capital_flow_confirms_buy(capital_flow, min_score=60.0))
        and sell_pressure.score <= 74.0
        and chan_structure.sell_point_type not in SELL_POINTS
        and daily_context.fundamental_score >= 60.0
        and multi_period_trend.monthly_state != "DOWN"
    )
    if early_start:
        reasons.append(
            f"强势启动早期：距离压力 {distance_to_breakout:.1%}，当日涨幅 {day_return:.1%}，量能 {volume_expansion:.2f} 倍。"
        )
        reasons.append("价格站上 VWAP 且尚未明显过度延伸，适合先按试探仓跟随。")

    is_late_enough = intraday_context.late_session or data["timestamp"].iloc[-1].hour >= 14
    pre_watch = (
        not confirmed
        and not early_start
        and is_late_enough
        and pre_score >= 76.0
        and current < trigger_price
        and distance_to_breakout is not None
        and 0.002 <= distance_to_breakout <= 0.018
        and close_position >= 0.62
        and volume_expansion <= 1.25
        and (capital_flow.score >= 50.0 or _capital_flow_confirms_buy(capital_flow, min_score=60.0))
        and sell_pressure.score <= 66.0
        and daily_context.fundamental_score >= 60.0
        and multi_period_trend.monthly_state != "DOWN"
    )
    if pre_watch:
        reasons.append(f"次日突破预警：距离压力约 {distance_to_breakout:.1%}，触发价 {trigger_price:.3f}。")
        if compressed:
            reasons.append("前一日/当日波动压缩，存在蓄势条件。")
        if ma_ready:
            reasons.append("5 日均线修复，价格未明显脱离短线趋势。")

    if confirmed:
        state = "BREAKOUT_CONFIRMED"
    elif early_start:
        state = "EARLY_START"
        score = max(score, early_score)
    elif pre_watch:
        state = "PRE_BREAKOUT_WATCH"
        score = max(score, pre_score)
    else:
        state = "NONE"

    if not reasons:
        reasons.append("未形成强势突破或次日突破预警。")
    return BreakoutSetup(
        score=round(clamp(score, 0.0, 100.0), 2),
        state=state,
        breakout_level=round(prior_resistance, 3),
        trigger_price=round(trigger_price, 3),
        day_return=round(day_return, 4),
        recent_return=round(recent_return, 4),
        volume_expansion=round(volume_expansion, 4),
        distance_to_breakout=round(distance_to_breakout, 4) if distance_to_breakout is not None else None,
        breakout_confirmed=confirmed,
        pre_breakout_watch=pre_watch,
        reasons=tuple(reasons[:6]),
    )
