"""Candidate Discovery V2 contracts, legacy factors and model."""

from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateSet,
    CandidateSelectionStatus,
)
from market_regime_alpha.research.candidate_discovery.model import (
    discover_candidates_v2,
)

__all__ = [
    "CandidateSelectionStatus",
    "CandidateSet",
    "discover_candidates_v2",
]

