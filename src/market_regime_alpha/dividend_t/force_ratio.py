"""Buy-pressure / sell-pressure force-ratio model."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime_alpha.dividend_t.attention import AttentionScore
from market_regime_alpha.dividend_t.certainty import CertaintyScore
from market_regime_alpha.dividend_t.dynamic_weights import DynamicWeights
from market_regime_alpha.dividend_t.memory import MemoryScore
from market_regime_alpha.dividend_t.scoring import clamp, risk_reward_score
from market_regime_alpha.dividend_t.sell_pressure import SellPressureEstimate


@dataclass(frozen=True)
class ForceRatioEstimate:
    buy_pressure: float
    sell_pressure: float
    force_ratio: float
    purchase_rate: float
    sell_rate: float
    k_score: float
    weighted_score: float
    reasons: tuple[str, ...]


def estimate_force_ratio(
    *,
    attention: AttentionScore,
    certainty: CertaintyScore,
    memory: MemoryScore,
    sell_pressure: SellPressureEstimate,
    risk_reward_ratio: float,
    current_amount: float,
    weights: DynamicWeights,
) -> ForceRatioEstimate:
    k_score = risk_reward_score(risk_reward_ratio)
    certainty_component = clamp(certainty.z_score / 5.0, 0.0, 1.0)
    k_component = clamp(k_score / 5.0, 0.0, 1.0)
    memory_component = clamp(memory.score / 100.0, 0.0, 1.0)

    purchase_rate = clamp(
        (certainty_component ** 1.25) * (k_component ** 1.15) * (0.70 + 0.60 * memory_component),
        0.01,
        1.25,
    )
    attention_amount = max(current_amount, 1.0) * clamp(attention.g_score / 3.0, 0.25, 2.0)
    buy_pressure = attention_amount * purchase_rate

    sell_rate = sell_pressure.sell_rate
    estimated_sell_pressure = max(sell_pressure.max_sellable_amount * sell_rate, 1.0)
    force_ratio = buy_pressure / estimated_sell_pressure

    weighted_score = (
        weights.attention * attention.score
        + weights.certainty * certainty.score
        + weights.risk_reward * (k_score * 20.0)
        + weights.sell_pressure * (100.0 - sell_pressure.score)
        + weights.memory * memory.score
    )
    reasons = _force_reasons(force_ratio, purchase_rate, sell_rate)
    return ForceRatioEstimate(
        buy_pressure=round(buy_pressure, 2),
        sell_pressure=round(estimated_sell_pressure, 2),
        force_ratio=round(force_ratio, 4),
        purchase_rate=round(purchase_rate, 4),
        sell_rate=round(sell_rate, 4),
        k_score=round(k_score, 2),
        weighted_score=round(clamp(weighted_score, 0.0, 100.0), 2),
        reasons=reasons,
    )


def _force_reasons(force_ratio: float, purchase_rate: float, sell_rate: float) -> tuple[str, ...]:
    reasons: list[str] = []
    if force_ratio >= 1.25:
        reasons.append("估算买盘力量高于卖盘力量，适合等待支撑位低吸确认。")
    elif force_ratio <= 0.85:
        reasons.append("估算卖盘力量高于买盘力量，优先考虑卖 T 或等待。")
    else:
        reasons.append("估算买卖力量接近平衡，默认观察。")
    if purchase_rate >= 0.7:
        reasons.append("购买率由确定性、盈亏比和记忆共同抬升。")
    if sell_rate >= 0.55:
        reasons.append("卖出率偏高，冲高时兑现压力需要优先处理。")
    return tuple(reasons)
