"""Research identity, evidence, and rehearsal input-bundle contracts."""

from .experiment_identity import ExperimentIdentity
from .provider_export_adapter import (
    GENERIC_PROVIDER_EXPORT_BUNDLE_SCHEMA_VERSION,
    GenericProviderExportAdapterError,
    adapt_generic_provider_export_mapping,
    load_generic_provider_export_bundle,
)
from .provider_rehearsal_market_artifact import (
    PROVIDER_REHEARSAL_MARKET_ARTIFACT_SCHEMA_VERSION,
    ProviderRehearsalMarketArtifact,
    build_provider_rehearsal_market_artifact,
)
from .xuntou_provider_adapter import (
    XUNTOU_AVAILABILITY_CONVENTION,
    XUNTOU_BAR_FINALITY_CONVENTION,
    XUNTOU_BUYABILITY_CONVENTION,
    XUNTOU_CALENDAR_CLOSE_CONVENTION,
    XUNTOU_DECISION_SNAPSHOT_CONVENTION,
    XUNTOU_LIQUIDITY_MEASURE_ID,
    XUNTOU_P0_MAPPING_CONTRACT_VERSION,
    XUNTOU_P0_NATIVE_BUNDLE_SCHEMA_VERSION,
    XUNTOU_P0_PROVIDER_ID,
    XUNTOU_PRICE_ADJUSTMENT_BASIS,
    XUNTOU_SYMBOL_NORMALIZATION_VERSION,
    XUNTOU_UNIVERSE_EFFECTIVE_TIME_CONVENTION,
    XuntouP0EvidenceClassification,
    XuntouProviderAdapterError,
    XuntouProviderAdapterErrorCode,
    adapt_xuntou_p0_native_mapping,
    load_xuntou_p0_native_bundle,
)

__all__ = [
    "ExperimentIdentity",
    "GENERIC_PROVIDER_EXPORT_BUNDLE_SCHEMA_VERSION",
    "GenericProviderExportAdapterError",
    "PROVIDER_REHEARSAL_MARKET_ARTIFACT_SCHEMA_VERSION",
    "ProviderRehearsalMarketArtifact",
    "XUNTOU_AVAILABILITY_CONVENTION",
    "XUNTOU_BAR_FINALITY_CONVENTION",
    "XUNTOU_BUYABILITY_CONVENTION",
    "XUNTOU_CALENDAR_CLOSE_CONVENTION",
    "XUNTOU_DECISION_SNAPSHOT_CONVENTION",
    "XUNTOU_LIQUIDITY_MEASURE_ID",
    "XUNTOU_P0_MAPPING_CONTRACT_VERSION",
    "XUNTOU_P0_NATIVE_BUNDLE_SCHEMA_VERSION",
    "XUNTOU_P0_PROVIDER_ID",
    "XUNTOU_PRICE_ADJUSTMENT_BASIS",
    "XUNTOU_SYMBOL_NORMALIZATION_VERSION",
    "XUNTOU_UNIVERSE_EFFECTIVE_TIME_CONVENTION",
    "XuntouP0EvidenceClassification",
    "XuntouProviderAdapterError",
    "XuntouProviderAdapterErrorCode",
    "adapt_generic_provider_export_mapping",
    "adapt_xuntou_p0_native_mapping",
    "build_provider_rehearsal_market_artifact",
    "load_generic_provider_export_bundle",
    "load_xuntou_p0_native_bundle",
]
