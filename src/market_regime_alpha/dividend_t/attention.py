"""Market attention scoring for the dividend T-trading monitor.

This estimates the eight attention attributes from observable intraday bars.
It is an approximation of market attention, not a claim to know all investor
intentions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from market_regime_alpha.dividend_t.scoring import clamp


ATTENTION_ATTRIBUTE_NAMES = (
    "profit_seeking",
    "visibility",
    "attention_trend",
    "attention_diversion",
    "feedback",
    "fast_exhaustion",
    "capital_difference",
    "macro_heat",
)


@dataclass(frozen=True)
class AttentionScore:
    score: float
    g_score: float
    attributes: dict[str, float] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()


def estimate_attention(frame: Any, *, benchmark_strength: float | None = None) -> AttentionScore:
    data = _prepare(frame)
    latest = data.iloc[-1]
    previous = data.iloc[-2]

    close = float(latest["close"])
    prev_close = float(previous["close"])
    interval_return = close / prev_close - 1.0 if prev_close > 0 else 0.0
    amount = _latest_amount(latest)
    amount_ma = _rolling_mean(data, "amount", 24)
    volume_ma = _rolling_mean(data, "volume", 24)
    volume = float(latest["volume"])

    short_amount_ma = _rolling_mean(data.tail(6), "amount", 6)
    long_amount_ma = _rolling_mean(data, "amount", min(48, len(data)))

    profit_seeking = _score_between(interval_return, -0.012, 0.018)
    visibility = _ratio_score(amount, amount_ma, neutral=50.0)
    attention_trend = _ratio_score(short_amount_ma, long_amount_ma, neutral=50.0)
    attention_diversion = 50.0 if benchmark_strength is None else clamp(50.0 + benchmark_strength * 50.0, 0.0, 100.0)
    feedback = clamp((profit_seeking + visibility) / 2.0, 0.0, 100.0)

    volume_spike = volume / volume_ma if volume_ma > 0 else 1.0
    body_return = abs(close / float(latest["open"]) - 1.0) if float(latest["open"]) > 0 else 0.0
    exhaustion_penalty = clamp((volume_spike - 1.6) * 35.0 - body_return * 1200.0, 0.0, 100.0)
    fast_exhaustion = clamp(100.0 - exhaustion_penalty, 0.0, 100.0)

    capital_difference = _ratio_score(amount, data["amount"].median(), neutral=50.0)
    macro_heat = 50.0 if benchmark_strength is None else clamp(50.0 + benchmark_strength * 40.0, 0.0, 100.0)

    attributes = {
        "profit_seeking": round(profit_seeking, 2),
        "visibility": round(visibility, 2),
        "attention_trend": round(attention_trend, 2),
        "attention_diversion": round(attention_diversion, 2),
        "feedback": round(feedback, 2),
        "fast_exhaustion": round(fast_exhaustion, 2),
        "capital_difference": round(capital_difference, 2),
        "macro_heat": round(macro_heat, 2),
    }
    score = sum(attributes.values()) / len(attributes)
    reasons = _attention_reasons(attributes)
    return AttentionScore(score=round(score, 2), g_score=round(score / 20.0, 2), attributes=attributes, reasons=reasons)


def _prepare(frame: Any) -> Any:
    import pandas as pd

    if len(frame) < 8:
        raise ValueError("at least 8 intraday bars are required to estimate market attention")
    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values("timestamp").reset_index(drop=True)
    if "amount" not in data.columns:
        data["amount"] = data["close"] * data["volume"]
    data["amount"] = data["amount"].fillna(data["close"] * data["volume"])
    return data


def _latest_amount(row: Any) -> float:
    amount = row.get("amount")
    if amount == amount and amount is not None:
        return float(amount)
    return float(row["close"]) * float(row["volume"])


def _rolling_mean(frame: Any, column: str, window: int) -> float:
    values = frame[column].tail(max(1, min(window, len(frame))))
    return float(values.mean())


def _score_between(value: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    return clamp((value - low) / (high - low) * 100.0, 0.0, 100.0)


def _ratio_score(value: float, baseline: float, *, neutral: float) -> float:
    if baseline <= 0:
        return neutral
    ratio = value / baseline
    return clamp(50.0 + (ratio - 1.0) * 45.0, 0.0, 100.0)


def _attention_reasons(attributes: dict[str, float]) -> tuple[str, ...]:
    reasons: list[str] = []
    if attributes["visibility"] >= 70:
        reasons.append("成交额显著高于近端均值，映入机会增强。")
    if attributes["attention_trend"] >= 65:
        reasons.append("短期成交额相对长均值上升，关注度处于增量状态。")
    if attributes["fast_exhaustion"] <= 45:
        reasons.append("出现放量但价格推进不足，关注资金可能存在快耗。")
    if attributes["feedback"] >= 65:
        reasons.append("上涨与放量形成正反馈。")
    if not reasons:
        reasons.append("关注度处于中性区间，暂未出现强增量或快耗信号。")
    return tuple(reasons)
