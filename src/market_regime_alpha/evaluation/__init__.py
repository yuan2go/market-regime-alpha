"""Platform-level evaluation contracts."""

from market_regime_alpha.evaluation.contracts import EvaluationReport
from market_regime_alpha.evaluation.lifecycle import (
    ROLLING_SCORECARD_SCHEMA,
    TRADE_EVALUATION_CONFIG_SCHEMA,
    TRADE_OUTCOME_SCHEMA,
    AttributionComponent,
    AttributionRecord,
    RollingScorecard,
    RollingScorecardBuilder,
    ScorecardStatus,
    TradeEvaluationConfig,
    TradeOutcome,
    TradeOutcomeEvaluator,
    TradePathObservation,
)

__all__ = [
    "ROLLING_SCORECARD_SCHEMA",
    "TRADE_EVALUATION_CONFIG_SCHEMA",
    "TRADE_OUTCOME_SCHEMA",
    "AttributionComponent",
    "AttributionRecord",
    "EvaluationReport",
    "RollingScorecard",
    "RollingScorecardBuilder",
    "ScorecardStatus",
    "TradeEvaluationConfig",
    "TradeOutcome",
    "TradeOutcomeEvaluator",
    "TradePathObservation",
]
