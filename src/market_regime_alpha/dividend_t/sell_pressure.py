"""Sell-pressure and maximum sellable market structure estimates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_regime_alpha.dividend_t.scoring import clamp


@dataclass(frozen=True)
class SellPressureEstimate:
    score: float
    max_sellable_amount: float
    sell_rate: float
    resistance_pressure: float
    profit_taking_pressure: float
    trapped_pressure: float
    volume_stalling_pressure: float
    reasons: tuple[str, ...]


def estimate_sell_pressure(frame: Any, *, lookback: int = 60) -> SellPressureEstimate:
    data = _prepare(frame).tail(lookback).copy()
    if len(data) < 8:
        raise ValueError("at least 8 bars are required to estimate sell pressure")

    latest = data.iloc[-1]
    previous = data.iloc[-2]
    close = float(latest["close"])
    high_max = float(data["high"].max())
    support = float(data["low"].tail(min(24, len(data))).min())
    amount_sum = float(data["amount"].sum())

    near_resistance = close / high_max if high_max > 0 else 0.0
    resistance_pressure = clamp((near_resistance - 0.92) / 0.08 * 100.0, 0.0, 100.0)

    profitable_amount = float(data.loc[data["close"] < close, "amount"].sum())
    profit_taking_pressure = clamp(profitable_amount / amount_sum * 100.0 if amount_sum > 0 else 50.0, 0.0, 100.0)

    trapped_amount = float(data.loc[data["close"] > close, "amount"].sum())
    trapped_pressure = clamp(trapped_amount / amount_sum * 100.0 if amount_sum > 0 else 50.0, 0.0, 100.0)

    volume_ma = float(data["volume"].tail(min(24, len(data))).mean())
    interval_return = close / float(previous["close"]) - 1.0 if float(previous["close"]) > 0 else 0.0
    volume_stalling_pressure = 0.0
    if volume_ma > 0:
        volume_ratio = float(latest["volume"]) / volume_ma
        if volume_ratio > 1.2 and interval_return <= 0.004:
            volume_stalling_pressure = clamp((volume_ratio - 1.2) * 55.0 + (0.004 - interval_return) * 4000.0, 0.0, 100.0)

    score = (
        0.30 * resistance_pressure
        + 0.25 * profit_taking_pressure
        + 0.25 * trapped_pressure
        + 0.20 * volume_stalling_pressure
    )
    # For a 5-minute timing signal, use the interval-sized expected sellable
    # amount instead of the whole lookback turnover. The full lookback turnover
    # describes market structure, but only a fraction can realistically turn into
    # immediate sell pressure in the next bar.
    interval_amount = float(data["amount"].tail(min(12, len(data))).mean())
    max_sellable_amount = interval_amount * (0.60 + clamp(score / 100.0, 0.0, 1.0) * 2.40)
    sell_rate = clamp((score / 100.0) ** 1.25, 0.02, 0.95)

    reasons = _sell_pressure_reasons(
        support=support,
        close=close,
        resistance_pressure=resistance_pressure,
        profit_taking_pressure=profit_taking_pressure,
        trapped_pressure=trapped_pressure,
        volume_stalling_pressure=volume_stalling_pressure,
    )
    return SellPressureEstimate(
        score=round(score, 2),
        max_sellable_amount=round(max_sellable_amount, 2),
        sell_rate=round(sell_rate, 4),
        resistance_pressure=round(resistance_pressure, 2),
        profit_taking_pressure=round(profit_taking_pressure, 2),
        trapped_pressure=round(trapped_pressure, 2),
        volume_stalling_pressure=round(volume_stalling_pressure, 2),
        reasons=reasons,
    )


def _prepare(frame: Any) -> Any:
    import pandas as pd

    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values("timestamp").reset_index(drop=True)
    if "amount" not in data.columns:
        data["amount"] = data["close"] * data["volume"]
    data["amount"] = data["amount"].fillna(data["close"] * data["volume"])
    return data


def _sell_pressure_reasons(
    *,
    support: float,
    close: float,
    resistance_pressure: float,
    profit_taking_pressure: float,
    trapped_pressure: float,
    volume_stalling_pressure: float,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if resistance_pressure >= 65:
        reasons.append("价格接近近期高点，前高/箱体压力上升。")
    if profit_taking_pressure >= 65:
        reasons.append("近期成交中较多筹码已有浮盈，短线获利盘压力偏高。")
    if trapped_pressure >= 55:
        reasons.append("上方成交区间仍有套牢筹码，反弹压力未完全释放。")
    if volume_stalling_pressure >= 45:
        reasons.append("出现放量推进不足，主动卖出率可能上升。")
    if close <= support * 1.02:
        reasons.append("价格靠近支撑，卖压释放后可观察承接。")
    if not reasons:
        reasons.append("卖压处于中性区间，未出现明确高位兑现或放量滞涨。")
    return tuple(reasons)
