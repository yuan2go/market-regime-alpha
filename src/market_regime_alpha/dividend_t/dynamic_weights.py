"""Dynamic weights for the COSCO 5-minute manual timing model."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime_alpha.dividend_t.models import TrendState


@dataclass(frozen=True)
class DynamicWeights:
    attention: float
    certainty: float
    risk_reward: float
    sell_pressure: float
    memory: float

    def as_dict(self) -> dict[str, float]:
        return {
            "attention": self.attention,
            "certainty": self.certainty,
            "risk_reward": self.risk_reward,
            "sell_pressure": self.sell_pressure,
            "memory": self.memory,
        }


def build_dynamic_weights(
    *,
    trend_state: TrendState,
    memory_score: float,
    sell_pressure_score: float,
) -> DynamicWeights:
    weights = {
        "attention": 0.22,
        "certainty": 0.30,
        "risk_reward": 0.22,
        "sell_pressure": 0.18,
        "memory": 0.08,
    }
    if trend_state == TrendState.UPTREND:
        weights["attention"] += 0.04
        weights["risk_reward"] -= 0.02
        weights["sell_pressure"] -= 0.02
    elif trend_state == TrendState.DOWNTREND:
        weights["sell_pressure"] += 0.08
        weights["risk_reward"] += 0.04
        weights["attention"] -= 0.06
        weights["certainty"] -= 0.06
    elif trend_state == TrendState.EXHAUSTION:
        weights["sell_pressure"] += 0.08
        weights["attention"] -= 0.04
        weights["risk_reward"] -= 0.02

    if memory_score >= 65:
        weights["memory"] += 0.04
        weights["certainty"] -= 0.02
        weights["attention"] -= 0.02
    elif memory_score <= 40:
        weights["sell_pressure"] += 0.04
        weights["memory"] += 0.02
        weights["attention"] -= 0.03
        weights["certainty"] -= 0.03

    if sell_pressure_score >= 70:
        weights["sell_pressure"] += 0.04
        weights["risk_reward"] += 0.02
        weights["attention"] -= 0.03
        weights["certainty"] -= 0.03

    total = sum(weights.values())
    normalized = {key: round(value / total, 4) for key, value in weights.items()}
    return DynamicWeights(**normalized)
