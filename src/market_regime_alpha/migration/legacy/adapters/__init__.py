"""Adapters that expose Legacy calculations without granting canonical authority."""

from market_regime_alpha.migration.legacy.adapters.moving_average import (
    LegacyMovingAverageAdapter,
)
from market_regime_alpha.migration.legacy.adapters.technical_observables import (
    LegacyTechnicalFamily,
    LegacyTechnicalObservableAdapter,
    LegacyTechnicalResult,
    LegacyTechnicalResultState,
    LegacyTechnicalValue,
)

__all__ = [
    "LegacyMovingAverageAdapter",
    "LegacyTechnicalFamily",
    "LegacyTechnicalObservableAdapter",
    "LegacyTechnicalResult",
    "LegacyTechnicalResultState",
    "LegacyTechnicalValue",
]
