"""Research Platform Kernel V1."""

from market_regime_alpha.platform.contracts import (
    DefinitionStatus,
    EvidenceLevel,
    EvaluationProtocolId,
    MetricId,
    ModelDefinition,
    ModelLifecycleStatus,
    ModelRole,
    ObservableDefinition,
    ObservableId,
    PredictionDisposition,
    ResearchHypothesisId,
    TheoryDefinition,
    TheoryId,
)
from market_regime_alpha.platform.experiment_governance import (
    ExperimentBudget,
    ExperimentGovernance,
    FrozenExperimentProtocol,
    PrimaryChangeDimension,
    ResearchHypothesis,
)
from market_regime_alpha.platform.model_registry import ModelRegistration, ModelRegistry
from market_regime_alpha.platform.prediction_artifacts import (
    PREDICTION_RUN_ARTIFACT_FILES,
    publish_prediction_run_artifact,
)
from market_regime_alpha.platform.prediction_reader import (
    VerifiedPredictionRunArtifact,
    load_verified_prediction_run_artifact,
)
from market_regime_alpha.platform.prediction_run import PredictionRun
from market_regime_alpha.platform.multi_model_slice import (
    CompositeCandidateModelSpec,
    MultiModelCandidateSliceRun,
    SingleFeatureCandidateModelSpec,
    build_default_candidate_slice_specs,
    run_multi_model_candidate_slice,
)
from market_regime_alpha.platform.target_evaluation import (
    EvaluationProtocol,
    MetricDefinition,
    MetricDirection,
    MissingTargetPolicy,
    PriceMark,
    ReturnBasis,
    TargetKind,
    TargetProtocol,
)

__all__ = [
    "CompositeCandidateModelSpec",
    "DefinitionStatus",
    "EvidenceLevel",
    "EvaluationProtocol",
    "EvaluationProtocolId",
    "ExperimentBudget",
    "ExperimentGovernance",
    "FrozenExperimentProtocol",
    "MetricDefinition",
    "MetricDirection",
    "MetricId",
    "MissingTargetPolicy",
    "ModelDefinition",
    "ModelLifecycleStatus",
    "ModelRegistration",
    "ModelRegistry",
    "ModelRole",
    "MultiModelCandidateSliceRun",
    "ObservableDefinition",
    "ObservableId",
    "PredictionDisposition",
    "PredictionRun",
    "PREDICTION_RUN_ARTIFACT_FILES",
    "PriceMark",
    "PrimaryChangeDimension",
    "ResearchHypothesis",
    "ResearchHypothesisId",
    "ReturnBasis",
    "SingleFeatureCandidateModelSpec",
    "TargetKind",
    "TargetProtocol",
    "TheoryDefinition",
    "TheoryId",
    "VerifiedPredictionRunArtifact",
    "build_default_candidate_slice_specs",
    "load_verified_prediction_run_artifact",
    "publish_prediction_run_artifact",
    "run_multi_model_candidate_slice",
]
