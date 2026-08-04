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
