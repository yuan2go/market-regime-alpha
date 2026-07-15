"""Explicit compatibility boundaries for Legacy Research Assets."""

from .dataset_contract_adapter import adapt_legacy_dataset_manifest
from .macd_experiment_adapter import (
    LegacyMACDExperimentIdentityLike,
    adapt_legacy_macd_experiment_identity,
)
from .trading_calendar_adapter import (
    LegacyTradingCalendarAdapterError,
    adapt_legacy_trading_calendar_mapping,
    load_legacy_trading_calendar_sidecar,
)

__all__ = [
    "LegacyMACDExperimentIdentityLike",
    "LegacyTradingCalendarAdapterError",
    "adapt_legacy_dataset_manifest",
    "adapt_legacy_macd_experiment_identity",
    "adapt_legacy_trading_calendar_mapping",
    "load_legacy_trading_calendar_sidecar",
]
