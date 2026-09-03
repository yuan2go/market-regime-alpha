"""Explicitly composed infrastructure Model adapters."""

from market_regime_alpha.infrastructure.models.deterministic_ridge import (
    DeterministicRidgePredictor,
    DeterministicRidgeTrainer,
)

__all__ = ["DeterministicRidgePredictor", "DeterministicRidgeTrainer"]
