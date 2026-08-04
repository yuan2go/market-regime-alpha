"""Adapters that expose Legacy calculations without granting canonical authority."""

from market_regime_alpha.migration.legacy.adapters.moving_average import (
    LegacyMovingAverageAdapter,
)

__all__ = ["LegacyMovingAverageAdapter"]
