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
from .tencent_composite_acquisition import (
    TencentCompositeAcquirer,
    frames_for_accepted_symbols,
    merge_acquisition,
)
from .tencent_composite_artifacts import (
    write_tencent_composite_quality_failure,
    write_tencent_composite_run,
)
from .tencent_composite_contracts import (
    TENCENT_COMPOSITE_DECISION_CONVENTION,
    TENCENT_COMPOSITE_SCHEMA_VERSION,
    CompositeAcquisitionResult,
    CompositeBar,
    CompositeDispositionCode,
    CompositeQualityReport,
    CompositeSourceKind,
    PreparedCompositeData,
    build_tencent_composite_dataset_contract,
)
from .tencent_composite_quality import (
    TencentCompositeQualityGateError,
    prepare_composite_data,
)
from .tencent_composite_runner import (
    TencentCompositeCandidateRun,
    r5_b1_exploratory_specs,
    run_tencent_composite_candidate_experiment,
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
    XUNTOU_ST_INTERVAL_CONVENTION,
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
    "TENCENT_COMPOSITE_DECISION_CONVENTION",
    "TENCENT_COMPOSITE_SCHEMA_VERSION",
    "CompositeAcquisitionResult",
    "CompositeBar",
    "CompositeDispositionCode",
    "CompositeQualityReport",
    "CompositeSourceKind",
    "PreparedCompositeData",
    "TencentCompositeAcquirer",
    "TencentCompositeCandidateRun",
    "TencentCompositeQualityGateError",
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
    "XUNTOU_ST_INTERVAL_CONVENTION",
    "XUNTOU_SYMBOL_NORMALIZATION_VERSION",
    "XUNTOU_UNIVERSE_EFFECTIVE_TIME_CONVENTION",
    "XuntouP0EvidenceClassification",
    "XuntouProviderAdapterError",
    "XuntouProviderAdapterErrorCode",
    "adapt_generic_provider_export_mapping",
    "adapt_xuntou_p0_native_mapping",
    "build_provider_rehearsal_market_artifact",
    "build_tencent_composite_dataset_contract",
    "frames_for_accepted_symbols",
    "load_generic_provider_export_bundle",
    "load_xuntou_p0_native_bundle",
    "merge_acquisition",
    "prepare_composite_data",
    "r5_b1_exploratory_specs",
    "run_tencent_composite_candidate_experiment",
    "write_tencent_composite_quality_failure",
    "write_tencent_composite_run",
]
