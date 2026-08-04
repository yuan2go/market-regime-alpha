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
    FeatureMaterializationRunner,
    FeatureMaterializationStatus,
    load_verified_feature_artifact_v2,
    load_verified_feature_bundle_v2,
    load_verified_feature_replay_report,
    publish_feature_replay_report,
    replay_feature_bundle_v2,
)

__all__ = [
    "FeatureConfiguration",
    "FeatureBundleState",
    "FeatureDefinitionV2",
    "FeatureOutputDefinition",
    "FeatureParameter",
    "FeatureParameterType",
    "FeatureMaterializationRunner",
    "FeatureMaterializationStatus",
    "FeatureSetConfiguration",
    "FeatureValidationStatus",
    "MissingnessPolicy",
    "RequiredFeatureCoveragePolicy",
    "TimeframePolicy",
    "ValueType",
    "load_verified_feature_artifact_v2",
    "load_verified_feature_bundle_v2",
    "load_verified_feature_replay_report",
    "publish_feature_replay_report",
    "replay_feature_bundle_v2",
]
