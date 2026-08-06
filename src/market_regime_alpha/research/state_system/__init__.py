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

__all__ = [
    "CapitalStateConfiguration",
    "EtfRotationConfiguration",
    "MarketStateConfiguration",
    "MissingDataPolicy",
    "StateLineage",
    "ThemeRotationConfiguration",
    "TransitionThresholds",
]
