"""Deterministic stateful research contracts for WP-STATE-01."""

from market_regime_alpha.research.state_system.capital import (
    CapitalObservation,
    CapitalState,
    CapitalStateEvaluation,
    CapitalTransition,
    StatefulCapitalState,
    evaluate_capital_state,
)
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import (
    CapitalStateConfiguration,
    DynamicPoolConfiguration,
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
from market_regime_alpha.research.state_system.etf_rotation import (
    EtfRotationEvaluation,
    EtfRotationObservation,
    EtfRotationState,
    EtfRotationTransition,
    StatefulEtfRotation,
    evaluate_etf_rotation,
)
from market_regime_alpha.research.state_system.theme_rotation import (
    StatefulThemeRotation,
    ThemeRotationEvaluation,
    ThemeRotationObservation,
    ThemeRotationState,
    ThemeRotationTransition,
    evaluate_theme_rotation,
)
from market_regime_alpha.research.state_system.pool import (
    DynamicPoolEvaluation,
    DynamicPoolEvaluationStatus,
    DynamicPoolStateContext,
    DynamicStockPoolVersion,
    PoolEligibilityObservation,
    evaluate_dynamic_pool,
)

__all__ = [
    "CapitalStateConfiguration",
    "CapitalObservation",
    "CapitalState",
    "CapitalStateEvaluation",
    "CapitalTransition",
    "EtfRotationConfiguration",
    "DynamicPoolConfiguration",
    "DynamicPoolEvaluation",
    "DynamicPoolEvaluationStatus",
    "DynamicPoolStateContext",
    "DynamicStockPoolVersion",
    "EtfRotationEvaluation",
    "EtfRotationObservation",
    "EtfRotationState",
    "EtfRotationTransition",
    "MarketStateConfiguration",
    "MarketRegimeObservation",
    "MarketRegimeState",
    "MarketRegimeTransition",
    "MarketStateEvaluation",
    "MissingDataPolicy",
    "PoolEligibilityObservation",
    "StateLineage",
    "StatefulMarketRegime",
    "StatefulEtfRotation",
    "StatefulCapitalState",
    "StatefulThemeRotation",
    "ThemeRotationConfiguration",
    "ThemeRotationEvaluation",
    "ThemeRotationObservation",
    "ThemeRotationState",
    "ThemeRotationTransition",
    "TransitionThresholds",
    "evaluate_market_state",
    "evaluate_etf_rotation",
    "evaluate_capital_state",
    "evaluate_dynamic_pool",
    "evaluate_theme_rotation",
]
