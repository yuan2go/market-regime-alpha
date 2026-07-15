"""Canonical shared contracts for the Market Regime Alpha V2 kernel."""

from .identity import (
    ArtifactId,
    DatasetId,
    ExperimentId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    ModelId,
    StableId,
    StrategyId,
    TargetId,
    UniverseId,
)
from .status import InputAvailabilityStatus
from .time import (
    AsOfTime,
    AvailabilityTime,
    DecisionTime,
    ExecutionEligibleTime,
    FinalizationTime,
    SemanticTime,
)

__all__ = [
    "ArtifactId",
    "AsOfTime",
    "AvailabilityTime",
    "DatasetId",
    "DecisionTime",
    "ExecutionEligibleTime",
    "ExperimentId",
    "FeatureDefinitionId",
    "FeatureMaterializationId",
    "FinalizationTime",
    "InputAvailabilityStatus",
    "ModelId",
    "SemanticTime",
    "StableId",
    "StrategyId",
    "TargetId",
    "UniverseId",
]
