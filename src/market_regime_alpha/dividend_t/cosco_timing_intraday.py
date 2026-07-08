"""Intraday confirmation helpers for the COSCO timing engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from market_regime_alpha.dividend_t.cosco_timing_types import IntradayContext
from market_regime_alpha.dividend_t.models import TrendState
from market_regime_alpha.dividend_t.scoring import clamp

def _intraday_context(frame: Any, *, levels: dict[str, float]) -> IntradayContext:
    data = frame.copy().sort_values("timestamp").reset_index(drop=True)
    latest = data.iloc[-1]
    current = float(latest["close"])
    atr = levels["atr"]
    support = levels["support"]
    resistance = levels["resistance"]
    recent = data.tail(min(6, len(data)))
    recent_low = float(recent["low"].min())
    recent_high = float(recent["high"].max())
    previous_close = float(data["close"].iloc[-2]) if len(data) >= 2 else current
    close_three_bars_ago = float(data["close"].iloc[-4]) if len(data) >= 4 else previous_close
    average_volume = float(data["volume"].tail(min(20, len(data))).mean())
    latest_volume = float(latest["volume"])
    last_time = latest["timestamp"].to_pydatetime() if hasattr(latest["timestamp"], "to_pydatetime") else latest["timestamp"]
    late_session = isinstance(last_time, datetime) and (last_time.hour > 14 or (last_time.hour == 14 and last_time.minute >= 30))

    near_support = current <= support + 0.90 * atr
    near_resistance = current >= resistance - 0.90 * atr
    rebound_from_low = current >= recent_low + 0.20 * atr
    five_min_reclaim = current >= support + 0.12 * atr and current >= close_three_bars_ago
    close_above_open = current >= float(latest["open"])
    support_confirmed = near_support and rebound_from_low and five_min_reclaim and close_above_open
    stalling_near_high = current <= previous_close or current <= recent_high - 0.12 * atr
    resistance_confirmed = near_resistance and stalling_near_high and latest_volume >= average_volume * 0.85

    score = 50.0
    reasons: list[str] = []
    if support_confirmed:
        score += 24.0
        reasons.append("5 分钟支撑有收回和反抽，盘中承接初步确认。")
    elif near_support:
        score -= 8.0
        reasons.append("价格靠近支撑，但 5 分钟承接没有确认。")

    if resistance_confirmed:
        score += 18.0
        reasons.append("5 分钟接近压力且出现滞涨，适合优先处理卖 T。")
    elif near_resistance:
        score += 4.0

    if late_session:
        score -= 8.0
        reasons.append("当前处于 14:30 后，买回隔夜风险上升。")

    if current < support:
        score -= 16.0
        reasons.append("价格跌破 5 分钟支撑，原买回逻辑作废。")

    if support_confirmed:
        state = "SUPPORT_CONFIRMED"
    elif resistance_confirmed:
        state = "RESISTANCE_CONFIRMED"
    elif late_session:
        state = "LATE_SESSION"
    else:
        state = "UNCONFIRMED"

    return IntradayContext(
        score=round(clamp(score, 20.0, 90.0), 2),
        state=state,
        support_confirmed=support_confirmed,
        resistance_confirmed=resistance_confirmed,
        late_session=late_session,
        near_support=near_support,
        near_resistance=near_resistance,
        rebound_from_low=rebound_from_low,
        five_min_reclaim=five_min_reclaim,
        reasons=tuple(reasons[:5]),
    )


def _trend_state(frame: Any) -> TrendState:
    data = frame.copy().sort_values("timestamp").reset_index(drop=True)
    close = data["close"]
    ma5 = float(close.tail(min(5, len(close))).mean())
    ma20 = float(close.tail(min(20, len(close))).mean())
    ma48 = float(close.tail(min(48, len(close))).mean())
    last = float(close.iloc[-1])
    recent_high = float(data["high"].tail(min(48, len(data))).max())

    if last >= recent_high * 0.985 and last < ma5:
        return TrendState.EXHAUSTION
    if last > ma5 > ma20 > ma48:
        return TrendState.UPTREND
    if last < ma5 < ma20 < ma48:
        return TrendState.DOWNTREND
    return TrendState.RANGE
