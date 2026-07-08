"""Volume-price structure scoring for TuiShen-style timing.

The estimator uses only OHLCV bars. It should be read as a candle/volume
structure score, not as real order-flow or Level-2 capital-flow evidence.
"""

from __future__ import annotations

from typing import Any

from market_regime_alpha.dividend_t.cosco_timing_capital_flow import _vwap
from market_regime_alpha.dividend_t.cosco_timing_types import VolumePriceStructure
from market_regime_alpha.dividend_t.scoring import clamp


def estimate_volume_price_structure(frame: Any) -> VolumePriceStructure:
    """Estimate real volume-price structure from recent 5-minute bars."""
    data = frame.copy().sort_values("timestamp").reset_index(drop=True)
    if len(data) < 30:
        return VolumePriceStructure(
            score=50.0,
            state="INSUFFICIENT",
            volume_expansion_ratio=1.0,
            price_efficiency=0.0,
            reasons=("量价结构样本不足：至少需要 30 根 5 分钟 K 线。",),
        )

    data["trade_date"] = data["timestamp"].dt.date
    latest_day = data["trade_date"].iloc[-1]
    today = data[data["trade_date"] == latest_day].copy()
    prior = data[data["trade_date"] != latest_day].copy()
    if len(today) < 6:
        today = data.tail(min(len(data), 48)).copy()
        prior = data.iloc[: max(0, len(data) - len(today))].copy()

    current = float(data["close"].iloc[-1])
    recent_window = min(6, len(today))
    recent = today.tail(recent_window)
    base_window = prior.tail(min(len(prior), 240)) if len(prior) else data.iloc[: -recent_window].tail(min(len(data), 240))
    if len(base_window) == 0:
        base_window = data.iloc[:-recent_window] if len(data) > recent_window else data

    recent_base = float(recent["close"].iloc[0])
    day_open = float(today["open"].iloc[0])
    recent_return = current / recent_base - 1.0 if recent_base > 0 else 0.0
    day_return = current / day_open - 1.0 if day_open > 0 else 0.0
    recent_volume = float(recent["volume"].mean())
    base_volume = float(base_window["volume"].mean()) if len(base_window) else recent_volume
    volume_expansion = recent_volume / base_volume if base_volume > 0 else 1.0

    resistance_source = prior.tail(min(len(prior), 160)) if len(prior) else data.iloc[:-recent_window].tail(min(len(data), 160))
    prior_resistance = float(resistance_source["high"].max()) if len(resistance_source) else float(data["high"].iloc[:-1].max())
    day_high = float(today["high"].max())
    day_low = float(today["low"].min())
    day_range = max(day_high - day_low, current * 0.002)
    close_position = (current - day_low) / day_range
    latest = data.iloc[-1]
    upper_wick = (float(latest["high"]) - current) / max(float(latest["high"]) - float(latest["low"]), current * 0.002)
    today_vwap = _vwap(today)
    recent_above_vwap_share = float((recent["close"] >= today_vwap).mean()) if today_vwap > 0 else 0.5
    vwap_distance = current / today_vwap - 1.0 if today_vwap > 0 else 0.0

    recent_body_move = abs(current - recent_base)
    recent_path = float((recent["high"] - recent["low"]).sum())
    price_efficiency = recent_body_move / max(recent_path, current * 0.002)
    pullback_from_high = current / day_high - 1.0 if day_high > 0 else 0.0
    above_breakout = current >= prior_resistance * 1.001 or (day_high >= prior_resistance * 1.002 and current >= prior_resistance)
    holds_breakout = current >= prior_resistance * 0.995 if prior_resistance > 0 else False
    volume_sustained = volume_expansion >= 0.88 or (volume_expansion >= 0.72 and recent_above_vwap_share >= 0.67)

    volume_breakout_score = 35.0
    if above_breakout:
        volume_breakout_score += 28.0
    if volume_expansion >= 1.45:
        volume_breakout_score += 22.0
    elif volume_expansion >= 1.15:
        volume_breakout_score += 14.0
    elif volume_expansion >= 0.95:
        volume_breakout_score += 6.0
    if recent_return >= 0.008:
        volume_breakout_score += 10.0
    elif recent_return >= 0.003:
        volume_breakout_score += 5.0
    if recent_above_vwap_share >= 0.67:
        volume_breakout_score += 6.0
    volume_breakout_score = clamp(volume_breakout_score, 0.0, 100.0)

    low_volume_pullback_score = 25.0
    mild_pullback = -0.035 <= pullback_from_high <= -0.002 and day_return >= -0.02
    if mild_pullback:
        low_volume_pullback_score += 26.0
    if volume_expansion <= 0.82:
        low_volume_pullback_score += 20.0
    elif volume_expansion <= 1.00:
        low_volume_pullback_score += 10.0
    if current >= today_vwap * 0.995 or recent_above_vwap_share >= 0.50:
        low_volume_pullback_score += 12.0
    if close_position >= 0.38:
        low_volume_pullback_score += 8.0
    low_volume_pullback_score = clamp(low_volume_pullback_score, 0.0, 100.0)

    high_volume_stall_score = 20.0
    if volume_expansion >= 1.45:
        high_volume_stall_score += 28.0
    elif volume_expansion >= 1.20:
        high_volume_stall_score += 16.0
    if recent_return <= 0.002:
        high_volume_stall_score += 18.0
    if day_return >= 0.015 and close_position <= 0.55:
        high_volume_stall_score += 12.0
    if upper_wick >= 0.45:
        high_volume_stall_score += 14.0
    if current < today_vwap and today_vwap > 0:
        high_volume_stall_score += 8.0
    high_volume_stall_score = clamp(high_volume_stall_score, 0.0, 100.0)

    price_up_volume_down_score = 15.0
    if day_return > 0.012 and volume_expansion < 0.82:
        price_up_volume_down_score += 34.0
    elif recent_return > 0.004 and volume_expansion < 0.92:
        price_up_volume_down_score += 22.0
    if close_position >= 0.72 and recent_above_vwap_share >= 0.67:
        price_up_volume_down_score += 10.0
    if above_breakout and volume_expansion < 0.95:
        price_up_volume_down_score += 18.0
    price_up_volume_down_score = clamp(price_up_volume_down_score, 0.0, 100.0)

    vwap_support_score = 40.0
    if current >= today_vwap * 1.002:
        vwap_support_score += 20.0
    elif current >= today_vwap * 0.998:
        vwap_support_score += 12.0
    else:
        vwap_support_score -= 12.0
    vwap_support_score += clamp((recent_above_vwap_share - 0.50) * 55.0, -10.0, 18.0)
    vwap_support_score += clamp(vwap_distance * 900.0, -8.0, 10.0)
    vwap_support_score = clamp(vwap_support_score, 0.0, 100.0)

    persistence_score = 35.0
    if above_breakout or holds_breakout:
        persistence_score += 22.0
    if volume_sustained:
        persistence_score += 16.0
    if recent_return >= -0.002:
        persistence_score += 10.0
    if recent_above_vwap_share >= 0.67:
        persistence_score += 9.0
    if high_volume_stall_score >= 72.0:
        persistence_score -= 20.0
    if price_up_volume_down_score >= 72.0:
        persistence_score -= 10.0
    persistence_score = clamp(persistence_score, 0.0, 100.0)

    score = (
        0.24 * volume_breakout_score
        + 0.18 * low_volume_pullback_score
        + 0.18 * vwap_support_score
        + 0.20 * persistence_score
        + 0.10 * clamp(50.0 + price_efficiency * 100.0, 0.0, 100.0)
        - 0.15 * high_volume_stall_score
        - 0.08 * price_up_volume_down_score
        + 18.0
    )
    score = clamp(score, 0.0, 100.0)

    reasons: list[str] = []
    if volume_breakout_score >= 70.0:
        reasons.append(f"放量突破结构：量能 {volume_expansion:.2f} 倍，突破近端压力 {prior_resistance:.3f}。")
    if low_volume_pullback_score >= 70.0:
        reasons.append("缩量回踩结构：回踩没有明显放量砸盘，且价格仍靠近 VWAP/日内中上部。")
    if high_volume_stall_score >= 70.0:
        reasons.append("放量滞涨风险：量能放大但短线涨幅不足或上影明显。")
    if price_up_volume_down_score >= 70.0:
        reasons.append("价涨量缩风险：价格上涨但量能未跟随，突破延续性存疑。")
    if vwap_support_score >= 65.0:
        reasons.append("承接 VWAP：最近 5 分钟收盘多数站在 VWAP 上方。")
    if persistence_score >= 68.0:
        reasons.append("突破后量能持续性较好：突破/回踩后未出现明显缩量失守。")
    if not reasons:
        reasons.append("量价结构中性：未形成高质量放量突破、缩量回踩或明确分歧风险。")

    if high_volume_stall_score >= 76.0:
        state = "HIGH_VOLUME_STALL"
    elif price_up_volume_down_score >= 76.0:
        state = "PRICE_UP_VOLUME_DOWN"
    elif volume_breakout_score >= 72.0 and persistence_score >= 64.0:
        state = "VOLUME_BREAKOUT"
    elif low_volume_pullback_score >= 72.0:
        state = "LOW_VOLUME_PULLBACK"
    elif vwap_support_score >= 66.0 and score >= 62.0:
        state = "VWAP_ACCUMULATION"
    else:
        state = "NEUTRAL"

    return VolumePriceStructure(
        score=round(score, 2),
        state=state,
        volume_breakout_score=round(volume_breakout_score, 2),
        low_volume_pullback_score=round(low_volume_pullback_score, 2),
        high_volume_stall_score=round(high_volume_stall_score, 2),
        price_up_volume_down_score=round(price_up_volume_down_score, 2),
        vwap_support_score=round(vwap_support_score, 2),
        post_breakout_volume_persistence_score=round(persistence_score, 2),
        volume_expansion_ratio=round(volume_expansion, 4),
        price_efficiency=round(price_efficiency, 4),
        reasons=tuple(reasons[:6]),
    )
