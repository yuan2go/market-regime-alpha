"""Canonical Candidate Discovery contracts and R5 rehearsal research APIs."""

from .baselines import CandidateRankingRejection, CandidateRankingRun, rank_candidates_by_feature
from .contracts import (
    CandidateExpiryTime,
    CandidatePopulation,
    CandidatePrediction,
    TargetContract,
    build_candidate_population,
)
from .dataset import (
    CandidateDatasetRow,
    CandidateFeatureValue,
    CandidateResearchDataset,
    CandidateTargetValue,
    TargetMaterialization,
    TargetObservation,
    TargetObservationStatus,
    build_candidate_research_dataset,
)
from .evaluation import (
    CandidatePanelEvaluation,
    CandidateSliceEvaluation,
    evaluate_candidate_ranking_panel,
    evaluate_candidate_ranking_slice,
)
from .historical_population import build_candidate_population_from_historical_artifacts
from .panel import CandidateResearchPanel, assemble_candidate_research_panel
from .rehearsal_calendar_targets import materialize_r5_opportunity_targets_from_calendar
from .rehearsal_opportunity_targets import (
    R5_NEXT_SESSION_MAE_TARGET_ID,
    R5_NEXT_SESSION_MFE_TARGET_ID,
    materialize_r5_next_session_opportunity_targets,
    r5_next_session_opportunity_target_contracts,
)
from .rehearsal_targets import (
    R5_NEXT_SESSION_RETURN_TARGET_ID,
    materialize_r5_next_session_return_target,
    r5_next_session_return_target_contract,
)
from .target_bundle import TargetMaterializationBundle, bundle_target_materializations

__all__ = [
    "CandidateDatasetRow",
    "CandidateExpiryTime",
    "CandidateFeatureValue",
    "CandidatePanelEvaluation",
    "CandidatePopulation",
    "CandidatePrediction",
    "CandidateRankingRejection",
    "CandidateRankingRun",
    "CandidateResearchDataset",
    "CandidateResearchPanel",
    "CandidateSliceEvaluation",
    "CandidateTargetValue",
    "R5_NEXT_SESSION_MAE_TARGET_ID",
    "R5_NEXT_SESSION_MFE_TARGET_ID",
    "R5_NEXT_SESSION_RETURN_TARGET_ID",
    "TargetContract",
    "TargetMaterialization",
    "TargetMaterializationBundle",
    "TargetObservation",
    "TargetObservationStatus",
    "assemble_candidate_research_panel",
    "build_candidate_population",
    "build_candidate_population_from_historical_artifacts",
    "build_candidate_research_dataset",
    "bundle_target_materializations",
    "evaluate_candidate_ranking_panel",
    "evaluate_candidate_ranking_slice",
    "materialize_r5_next_session_opportunity_targets",
    "materialize_r5_next_session_return_target",
    "materialize_r5_opportunity_targets_from_calendar",
    "r5_next_session_opportunity_target_contracts",
    "r5_next_session_return_target_contract",
    "rank_candidates_by_feature",
]
