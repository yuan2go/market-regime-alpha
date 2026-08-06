"""Deterministic stateful research contracts for WP-STATE-01."""

from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import (
    CapitalStateConfiguration,
    EtfRotationConfiguration,
    MarketStateConfiguration,
    MissingDataPolicy,
    ThemeRotationConfiguration,
    TransitionThresholds,
)
from market_regime_alpha.research.state_system.market import (
    MarketRegimeObservation,
    MarketRegimeState,
    MarketRegimeTransition,
    MarketStateEvaluation,
    StatefulMarketRegime,
    evaluate_market_state,
)

__all__ = [
    "CapitalStateConfiguration",
    "EtfRotationConfiguration",
    "MarketStateConfiguration",
    "MarketRegimeObservation",
    "MarketRegimeState",
    "MarketRegimeTransition",
    "MarketStateEvaluation",
    "MissingDataPolicy",
    "StateLineage",
    "StatefulMarketRegime",
    "ThemeRotationConfiguration",
    "TransitionThresholds",
    "evaluate_market_state",
]
