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
from .panel import CandidateResearchPanel, assemble_candidate_research_panel
from .rehearsal_targets import (
    R5_NEXT_SESSION_RETURN_TARGET_ID,
    materialize_r5_next_session_return_target,
    r5_next_session_return_target_contract,
)

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
    "R5_NEXT_SESSION_RETURN_TARGET_ID",
    "TargetContract",
    "TargetMaterialization",
    "TargetObservation",
    "TargetObservationStatus",
    "assemble_candidate_research_panel",
    "build_candidate_population",
    "build_candidate_research_dataset",
    "evaluate_candidate_ranking_panel",
    "evaluate_candidate_ranking_slice",
    "materialize_r5_next_session_return_target",
    "r5_next_session_return_target_contract",
    "rank_candidates_by_feature",
]
