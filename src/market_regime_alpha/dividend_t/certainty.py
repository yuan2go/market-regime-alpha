"""Upside certainty estimates based on Tuishen's six decision bases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from market_regime_alpha.dividend_t.attention import AttentionScore
from market_regime_alpha.dividend_t.cosco_profile import CoscoProfile
from market_regime_alpha.dividend_t.memory import MemoryScore
from market_regime_alpha.dividend_t.scoring import clamp
from market_regime_alpha.dividend_t.sell_pressure import SellPressureEstimate


@dataclass(frozen=True)
class CertaintyScore:
    score: float
    z_score: float
    bases: dict[str, float] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()


def estimate_certainty(
    frame: Any,
    *,
    profile: CoscoProfile,
    attention: AttentionScore,
    memory: MemoryScore,
    sell_pressure: SellPressureEstimate,
) -> CertaintyScore:
    shape_score = _shape_probability(frame)
    bases = {
        "fundamental_improvement": profile.base_fundamental_score,
        "homogeneous_valuation": profile.valuation_margin_score,
        "shape_probability": shape_score,
        "market_attention": attention.score,
        "max_sellable_inverse": clamp(100.0 - sell_pressure.score, 0.0, 100.0),
        "specific_memory": memory.score,
    }
    score = (
        0.24 * bases["fundamental_improvement"]
        + 0.18 * bases["homogeneous_valuation"]
        + 0.20 * bases["shape_probability"]
        + 0.14 * bases["market_attention"]
        + 0.10 * bases["max_sellable_inverse"]
        + 0.14 * bases["specific_memory"]
    )
    reasons = _certainty_reasons(bases)
    return CertaintyScore(
        score=round(clamp(score, 0.0, 100.0), 2),
        z_score=round(clamp(score / 20.0, 0.0, 5.0), 2),
        bases={key: round(value, 2) for key, value in bases.items()},
        reasons=reasons,
    )


def _shape_probability(frame: Any) -> float:
    data = frame.copy().sort_values("timestamp").reset_index(drop=True)
    close = data["close"]
    ma5 = float(close.tail(min(5, len(close))).mean())
    ma20 = float(close.tail(min(20, len(close))).mean())
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    recent_low = float(data["low"].tail(min(24, len(data))).min())
    recent_high = float(data["high"].tail(min(48, len(data))).max())

    score = 50.0
    if last > ma5 > ma20:
        score += 22.0
    elif last < ma5 < ma20:
        score -= 22.0
    if last <= recent_low * 1.025 and last >= prev * 0.995:
        score += 14.0
    if last >= recent_high * 0.98:
        score -= 10.0
    if last > prev:
        score += 6.0
    return clamp(score, 0.0, 100.0)


def _certainty_reasons(bases: dict[str, float]) -> tuple[str, ...]:
    reasons: list[str] = []
    if bases["shape_probability"] >= 70:
        reasons.append("形态概率偏强，短周期结构支持修复或延续。")
    if bases["market_attention"] >= 65:
        reasons.append("市场关注度对上涨确定性有正向贡献。")
    if bases["specific_memory"] >= 60:
        reasons.append("相似情境的特定记忆偏正向。")
    if bases["max_sellable_inverse"] <= 35:
        reasons.append("最大可卖量逆向分偏低，上方卖压会压低确定性。")
    if not reasons:
        reasons.append("六大判断依据合成后处于中性区间。")
    return tuple(reasons)
