"""Explicit compatibility boundaries for Legacy Research Assets."""

from .dataset_contract_adapter import adapt_legacy_dataset_manifest
from .macd_experiment_adapter import (
    LegacyMACDExperimentIdentityLike,
    adapt_legacy_macd_experiment_identity,
)

__all__ = [
    "LegacyMACDExperimentIdentityLike",
    "adapt_legacy_dataset_manifest",
    "adapt_legacy_macd_experiment_identity",
]
