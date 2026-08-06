"""Canonical feature contracts and explicitly scoped R5 rehearsal baselines."""

from .contracts import FeatureDefinition, FeatureMaterialization, FeatureObservation, FeatureRegistry
from .model_contracts import FeatureArtifact, FeatureComputationRequest, FeatureComputer
from .rehearsal_baselines import (
    LIQUIDITY_20S_ID,
    MOMENTUM_5S_ID,
    PRICE_VS_MA20_ID,
    VOLATILITY_20S_ID,
    materialize_r5_baseline_features,
    r5_baseline_feature_definitions,
)

__all__ = [
    "FeatureDefinition",
    "FeatureArtifact",
    "FeatureComputationRequest",
    "FeatureComputer",
    "FeatureMaterialization",
    "FeatureObservation",
    "FeatureRegistry",
    "LIQUIDITY_20S_ID",
    "MOMENTUM_5S_ID",
    "PRICE_VS_MA20_ID",
    "VOLATILITY_20S_ID",
    "materialize_r5_baseline_features",
    "r5_baseline_feature_definitions",
]
from market_regime_alpha.features.spine import (
    FeatureConfiguration,
    FeatureDefinitionV2,
    FeatureOutputDefinition,
    FeatureParameter,
    FeatureParameterType,
    FeatureSetConfiguration,
    FeatureValidationStatus,
    MissingnessPolicy,
    RequiredFeatureCoveragePolicy,
    TimeframePolicy,
    ValueType,
)
from market_regime_alpha.features.materialization_v2 import (
    FeatureBundleState,
    FeatureConfigurationInvalidError,
    FeatureComputationFailedError,
    FeatureMaterializationRunner,
    FeatureMaterializationStatus,
    FeatureReplayDivergenceError,
    load_verified_feature_artifact_v2,
    load_verified_feature_bundle_v2,
    load_verified_feature_replay_report,
    migrate_feature_bundle_encoding_v1_to_v2,
    publish_feature_replay_report,
    recompute_feature_bundle_v2,
    replay_feature_bundle_v2,
)
from market_regime_alpha.features.materialization_run import (
    FeatureMaterializationExecutionMode,
    FeatureMaterializationRunStatus,
    FeatureMaterializationTaskStatus,
)
from market_regime_alpha.features.postgres_materialization_run import (
    PostgresFeatureMaterializationRunRepository,
)
from market_regime_alpha.features.encoding_v2 import (
    FEATURE_ARTIFACT_ENCODING_V2,
    FEATURE_BUNDLE_ENCODING_V2,
    FeatureValueSelectionV2,
    read_feature_values_v2,
)

__all__ = [
    "FeatureConfiguration",
    "FEATURE_ARTIFACT_ENCODING_V2",
    "FEATURE_BUNDLE_ENCODING_V2",
    "FeatureBundleState",
    "FeatureConfigurationInvalidError",
    "FeatureComputationFailedError",
    "FeatureDefinitionV2",
    "FeatureOutputDefinition",
    "FeatureParameter",
    "FeatureParameterType",
    "FeatureMaterializationRunner",
    "FeatureMaterializationExecutionMode",
    "FeatureMaterializationRunStatus",
    "FeatureMaterializationStatus",
    "FeatureMaterializationTaskStatus",
    "FeatureReplayDivergenceError",
    "FeatureSetConfiguration",
    "FeatureValidationStatus",
    "FeatureValueSelectionV2",
    "MissingnessPolicy",
    "PostgresFeatureMaterializationRunRepository",
    "RequiredFeatureCoveragePolicy",
    "TimeframePolicy",
    "ValueType",
    "load_verified_feature_artifact_v2",
    "load_verified_feature_bundle_v2",
    "load_verified_feature_replay_report",
    "migrate_feature_bundle_encoding_v1_to_v2",
    "publish_feature_replay_report",
    "recompute_feature_bundle_v2",
    "replay_feature_bundle_v2",
    "read_feature_values_v2",
]
