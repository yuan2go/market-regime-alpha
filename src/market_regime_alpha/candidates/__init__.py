"""Canonical Candidate Discovery contracts and rehearsal dataset construction."""

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

__all__ = [
    "CandidateDatasetRow",
    "CandidateExpiryTime",
    "CandidateFeatureValue",
    "CandidatePopulation",
    "CandidatePrediction",
    "CandidateResearchDataset",
    "CandidateTargetValue",
    "TargetContract",
    "TargetMaterialization",
    "TargetObservation",
    "TargetObservationStatus",
    "build_candidate_population",
    "build_candidate_research_dataset",
]
