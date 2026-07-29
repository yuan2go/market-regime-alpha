"""Formal Market Regime research-gate contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.evidence.envelope import ArtifactEnvelope


class MarketState(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_NEUTRAL = "RISK_NEUTRAL"
    RISK_OFF = "RISK_OFF"
    EXTREME_RISK = "EXTREME_RISK"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class TradePermission(str, Enum):
    ALLOW = "ALLOW"
    RESTRICT = "RESTRICT"
    PROHIBIT = "PROHIBIT"


class MarketDirection(str, Enum):
    UP = "UP"
    FLAT = "FLAT"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class MarketBreadth(str, Enum):
    STRONG = "STRONG"
    MIXED = "MIXED"
    WEAK = "WEAK"
    UNKNOWN = "UNKNOWN"


class MarketLiquidity(str, Enum):
    EXPANDING = "EXPANDING"
    STABLE = "STABLE"
    CONTRACTING = "CONTRACTING"
    UNKNOWN = "UNKNOWN"


class MarketVolatility(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class RiskAppetite(str, Enum):
    STRONG = "STRONG"
    NEUTRAL = "NEUTRAL"
    DEFENSIVE = "DEFENSIVE"
    EXTREME_DEFENSIVE = "EXTREME_DEFENSIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class MarketRegimeSnapshot:
    """Research gate only; never a buy/sell signal."""

    envelope: ArtifactEnvelope
    market_state: MarketState
    trade_permission: TradePermission
    maximum_gross_exposure: float
    confidence: float
    direction_score: float | None
    breadth_score: float | None
    liquidity_score: float | None
    volatility_score: float | None
    limit_structure_score: float | None
    market_direction: MarketDirection
    market_breadth: MarketBreadth
    market_liquidity: MarketLiquidity
    market_volatility: MarketVolatility
    risk_appetite: RiskAppetite
    observed_metrics: tuple[tuple[str, float], ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 0.0 <= self.maximum_gross_exposure <= 1.0:
            raise ValueError("maximum_gross_exposure must be within [0, 1]")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Market Regime confidence must be within [0, 1]")
        for value in (
            self.direction_score,
            self.breadth_score,
            self.liquidity_score,
            self.volatility_score,
            self.limit_structure_score,
        ):
            if value is not None and (not isfinite(value) or not -1.0 <= value <= 1.0):
                raise ValueError("Market Regime component scores must be within [-1, 1]")
        if (
            self.market_state is MarketState.DATA_INSUFFICIENT
            and (
                self.trade_permission is not TradePermission.PROHIBIT
                or self.maximum_gross_exposure != 0.0
            )
        ):
            raise ValueError("insufficient Market Regime must fail closed")
        self.envelope.verify_payload(self.artifact_payload())

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "market_state": self.market_state.value,
            "trade_permission": self.trade_permission.value,
            "maximum_gross_exposure": self.maximum_gross_exposure,
            "confidence": self.confidence,
            "direction_score": self.direction_score,
            "breadth_score": self.breadth_score,
            "liquidity_score": self.liquidity_score,
            "volatility_score": self.volatility_score,
            "limit_structure_score": self.limit_structure_score,
            "market_direction": self.market_direction.value,
            "market_breadth": self.market_breadth.value,
            "market_liquidity": self.market_liquidity.value,
            "market_volatility": self.market_volatility.value,
            "risk_appetite": self.risk_appetite.value,
            "observed_metrics": [
                {"metric": key, "value": value}
                for key, value in self.observed_metrics
            ],
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_canonical_dict(),
            **self.artifact_payload(),
        }

