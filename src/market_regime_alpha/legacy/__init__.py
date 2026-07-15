"""Explicit compatibility boundaries for Legacy Research Assets."""

from .macd_experiment_adapter import (
    LegacyMACDExperimentIdentityLike,
    adapt_legacy_macd_experiment_identity,
)

__all__ = [
    "LegacyMACDExperimentIdentityLike",
    "adapt_legacy_macd_experiment_identity",
]
