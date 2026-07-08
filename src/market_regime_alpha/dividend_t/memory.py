"""Specific-situation memory for repeated intraday setups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_regime_alpha.dividend_t.scoring import clamp


RECENCY_WEIGHTS = (0.50, 0.30, 0.15, 0.03)


@dataclass(frozen=True)
class MemoryScore:
    score: float
    setup: str
    samples: int
    weighted_forward_return: float
    reasons: tuple[str, ...]


def estimate_memory(frame: Any, *, setup: str, horizon_bars: int = 3) -> MemoryScore:
    data = _prepare(frame)
    if len(data) < max(20, horizon_bars + 8):
        return MemoryScore(
            score=50.0,
            setup=setup,
            samples=0,
            weighted_forward_return=0.0,
            reasons=("历史样本不足，特定情境记忆按中性处理。",),
        )

    events = _event_indices(data, setup=setup, horizon_bars=horizon_bars)
    if not events:
        return MemoryScore(
            score=50.0,
            setup=setup,
            samples=0,
            weighted_forward_return=0.0,
            reasons=("没有找到相似情境，特定情境记忆按中性处理。",),
        )

    recent_events = events[-4:][::-1]
    weighted_return = 0.0
    used_weight = 0.0
    last_index = len(data) - 1
    for event, weight in zip(recent_events, RECENCY_WEIGHTS):
        forward_return = event["forward_return"]
        age_bars = last_index - event["index"]
        decay = max(0.35, 1.0 - age_bars / 240.0)
        final_weight = weight * decay
        weighted_return += forward_return * final_weight
        used_weight += final_weight

    weighted_return = weighted_return / used_weight if used_weight > 0 else 0.0
    score = clamp(50.0 + weighted_return * 900.0, 0.0, 100.0)
    reasons = _memory_reasons(setup, len(events), weighted_return)
    return MemoryScore(
        score=round(score, 2),
        setup=setup,
        samples=len(events),
        weighted_forward_return=round(weighted_return, 5),
        reasons=reasons,
    )


def classify_current_setup(frame: Any) -> str:
    data = _prepare(frame)
    return _classify_setup_at(data, len(data) - 1)


def _event_indices(frame: Any, *, setup: str, horizon_bars: int) -> list[dict[str, float]]:
    events: list[dict[str, float]] = []
    for index in range(12, len(frame) - horizon_bars):
        if _classify_setup_at(frame, index) != setup:
            continue
        close = float(frame["close"].iloc[index])
        future_close = float(frame["close"].iloc[index + horizon_bars])
        if close <= 0:
            continue
        events.append({"index": float(index), "forward_return": future_close / close - 1.0})
    return events


def _classify_setup_at(frame: Any, index: int) -> str:
    latest = frame.iloc[index]
    previous = frame.iloc[max(0, index - 1)]
    close = float(latest["close"])
    start_24 = max(0, index - 23)
    start_48 = max(0, index - 47)
    recent_low = float(frame["low"].iloc[start_24 : index + 1].min())
    recent_high = float(frame["high"].iloc[start_48 : index + 1].max())
    volume_ma = float(frame["volume"].iloc[start_24 : index + 1].mean())
    volume = float(latest["volume"])

    if close <= recent_low * 1.025 and volume <= volume_ma:
        return "support_shrinking_pullback"
    if close >= recent_high * 0.975 and volume > volume_ma * 1.15 and close <= float(previous["close"]) * 1.006:
        return "resistance_volume_stalling"
    if close > float(previous["close"]) and volume > volume_ma * 1.1:
        return "positive_feedback"
    return "neutral_range"


def _prepare(frame: Any) -> Any:
    import pandas as pd

    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values("timestamp").reset_index(drop=True)
    if "amount" not in data.columns:
        data["amount"] = data["close"] * data["volume"]
    data["amount"] = data["amount"].fillna(data["close"] * data["volume"])
    return data


def _memory_reasons(setup: str, samples: int, weighted_return: float) -> tuple[str, ...]:
    direction = "正向" if weighted_return > 0 else "负向" if weighted_return < 0 else "中性"
    return (f"当前情境 {setup} 找到 {samples} 次历史样本，近端加权后续收益为{direction}。",)
