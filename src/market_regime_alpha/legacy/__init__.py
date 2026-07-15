"""Explicit compatibility boundaries for Legacy Research Assets."""

from .dataset_contract_adapter import adapt_legacy_dataset_manifest
from .eligibility_sidecar_adapter import (
    LEGACY_ELIGIBILITY_AVAILABILITY_CONVENTION,
    LegacyEligibilitySidecarAdapterError,
    adapt_legacy_eligibility_mapping,
    load_legacy_eligibility_sidecar,
)
from .macd_experiment_adapter import (
    LegacyMACDExperimentIdentityLike,
    adapt_legacy_macd_experiment_identity,
)
from .trading_calendar_adapter import (
    LegacyTradingCalendarAdapterError,
    adapt_legacy_trading_calendar_mapping,
    load_legacy_trading_calendar_sidecar,
)
from .universe_sidecar_adapter import (
    LegacyUniverseSidecarAdapterError,
    adapt_legacy_universe_mapping,
    load_legacy_universe_sidecar,
)

__all__ = [
    "LEGACY_ELIGIBILITY_AVAILABILITY_CONVENTION",
    "LegacyEligibilitySidecarAdapterError",
    "LegacyMACDExperimentIdentityLike",
    "LegacyTradingCalendarAdapterError",
    "LegacyUniverseSidecarAdapterError",
    "adapt_legacy_dataset_manifest",
    "adapt_legacy_eligibility_mapping",
    "adapt_legacy_macd_experiment_identity",
    "adapt_legacy_trading_calendar_mapping",
    "adapt_legacy_universe_mapping",
    "load_legacy_eligibility_sidecar",
    "load_legacy_trading_calendar_sidecar",
    "load_legacy_universe_sidecar",
]
