"""Daily indicator helpers used by the dividend T-trading model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_regime_alpha.dividend_t.chan import analyze_chan_structure
from market_regime_alpha.dividend_t.models import TechnicalInputs, TrendState


@dataclass(frozen=True)
class TechnicalLevels:
    close: float
    support: float
    resistance: float
    risk_reward_ratio: float


def add_daily_indicators(frame: Any, *, atr_window: int = 14) -> Any:
    """Add MA and ATR columns to a pandas-like daily OHLCV frame."""
    import pandas as pd

    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values("timestamp").reset_index(drop=True)
    for window in (5, 10, 20, 60):
        data[f"ma{window}"] = data["close"].rolling(window).mean()

    previous_close = data["close"].shift(1)
    true_range = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - previous_close).abs(),
            (data["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    data["atr"] = true_range.rolling(atr_window).mean()
    data["volume_ma20"] = data["volume"].rolling(20).mean()
    return data


def estimate_levels(frame: Any, *, support_window: int = 20, resistance_window: int = 60) -> TechnicalLevels:
    if len(frame) < 2:
        raise ValueError("at least two bars are required to estimate technical levels")

    data = add_daily_indicators(frame) if "ma20" not in frame.columns else frame.copy()
    close = float(data["close"].iloc[-1])
    support = float(data["low"].tail(support_window).min())
    resistance = float(data["high"].tail(resistance_window).max())
    downside = max(close - support, close * 0.005)
    upside = max(resistance - close, 0.0)
    ratio = upside / downside if downside > 0 else 0.0
    return TechnicalLevels(close=close, support=support, resistance=resistance, risk_reward_ratio=ratio)


def infer_technical_inputs(frame: Any) -> TechnicalInputs:
    """Infer a conservative technical snapshot from daily bars."""
    data = add_daily_indicators(frame) if "ma20" not in frame.columns else frame.copy()
    latest = data.iloc[-1]
    previous = data.iloc[-2]
    levels = estimate_levels(data)
    chan = analyze_chan_structure(data, level=_infer_chan_level(data))

    close = float(latest["close"])
    ma20 = _float_or_none(latest.get("ma20"))
    ma60 = _float_or_none(latest.get("ma60"))
    volume = float(latest["volume"])
    volume_ma20 = _float_or_none(latest.get("volume_ma20"))

    if ma20 and ma60 and close > ma20 > ma60:
        trend = TrendState.UPTREND
        trend_quality = 85.0
    elif ma20 and ma60 and close < ma20 < ma60:
        trend = TrendState.DOWNTREND
        trend_quality = 35.0
    else:
        trend = TrendState.RANGE
        trend_quality = 65.0
    if chan.structure_type == "breakout":
        trend = TrendState.BREAKOUT
        trend_quality = max(trend_quality, 78.0)
    elif chan.structure_type == "breakdown":
        trend = TrendState.DOWNTREND
        trend_quality = min(trend_quality, 38.0)

    near_support = close <= levels.support * 1.03
    near_resistance = close >= levels.resistance * 0.97
    if chan.pivot_low is not None and chan.pivot_high is not None:
        pivot_width = max(chan.pivot_high - chan.pivot_low, close * 0.003)
        near_support = near_support or close <= chan.pivot_low + 0.30 * pivot_width
        near_resistance = near_resistance or close >= chan.pivot_high - 0.30 * pivot_width
    shrinking_pullback = close < float(previous["close"]) and bool(volume_ma20 and volume < volume_ma20)
    volume_stalling = near_resistance and bool(volume_ma20 and volume > volume_ma20 * 1.2) and close <= float(previous["close"]) * 1.01
    intraday_reversal = close > float(latest["open"]) and close > float(previous["close"])

    position_quality = min(100.0, max(35.0, levels.risk_reward_ratio / 3.0 * 100.0))
    if chan.buy_point_type in {"buy1", "buy2", "buy3", "range_buy"}:
        position_quality = max(position_quality, min(92.0, chan.score + 8.0))
    volume_structure = 80.0 if shrinking_pullback else 45.0 if volume_stalling else 65.0
    intraday_support = 80.0 if near_support and (shrinking_pullback or intraday_reversal) else 55.0

    return TechnicalInputs(
        position_quality=position_quality,
        volume_structure=volume_structure,
        trend_quality=trend_quality,
        intraday_support=intraday_support,
        chan_score=chan.score,
        trend_state=trend,
        near_support=near_support,
        near_resistance=near_resistance,
        shrinking_pullback=shrinking_pullback,
        volume_stalling=volume_stalling,
        intraday_reversal=intraday_reversal,
        sector_healthy=trend != TrendState.DOWNTREND,
        chan_structure_type=chan.structure_type,
        chan_trend_direction=chan.trend_direction,
        chan_divergence_type=chan.divergence_type,
        chan_buy_point_type=chan.buy_point_type,
        chan_sell_point_type=chan.sell_point_type,
        chan_pivot_low=chan.pivot_low,
        chan_pivot_high=chan.pivot_high,
        chan_invalid_price=chan.invalid_price,
    )


def _float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return result


def _infer_chan_level(frame: Any) -> str:
    if "source_freq" in frame.columns and len(frame["source_freq"].dropna()) > 0:
        value = str(frame["source_freq"].dropna().iloc[-1]).lower()
        if "30" in value:
            return "30m"
        if "5" in value:
            return "5m"
    return "daily"
