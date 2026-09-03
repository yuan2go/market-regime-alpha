"""Explicitly composed infrastructure Model adapters."""

from market_regime_alpha.infrastructure.models.backtest_deterministic_ridge import (
    DeterministicRidgeBacktestModelAdapter,
)
from market_regime_alpha.infrastructure.models.deterministic_ridge import (
    DeterministicRidgePredictor,
    DeterministicRidgeTrainer,
)

__all__ = [
    "DeterministicRidgeBacktestModelAdapter",
    "DeterministicRidgePredictor",
    "DeterministicRidgeTrainer",
]
