"""Stable public Selection ports."""

from market_regime_alpha.selection.ports.candidate_artifacts import (
    CandidateArtifactBinding,
    CandidateArtifactByteStore,
    CandidateArtifactRepository,
)
from market_regime_alpha.selection.ports.candidate_queries import (
    CandidateQueryProvider,
)
from market_regime_alpha.selection.ports.candidate_repository import (
    CandidateRepository,
)
from market_regime_alpha.selection.ports.candidate_uow import (
    CandidateUnitOfWork,
    CandidateUnitOfWorkProvider,
)
from market_regime_alpha.selection.ports.market import SelectionMarketQueries
from market_regime_alpha.selection.ports.repository import SelectionRepository
from market_regime_alpha.selection.ports.research_inputs import (
    CandidateResearchDependencyQueries,
    CandidateResearchInputLoader,
)
from market_regime_alpha.selection.ports.uow import (
    SelectionUnitOfWork,
    SelectionUnitOfWorkProvider,
)

__all__ = [
    "CandidateArtifactBinding",
    "CandidateArtifactByteStore",
    "CandidateArtifactRepository",
    "CandidateQueryProvider",
    "CandidateRepository",
    "CandidateResearchDependencyQueries",
    "CandidateResearchInputLoader",
    "CandidateUnitOfWork",
    "CandidateUnitOfWorkProvider",
    "SelectionMarketQueries",
    "SelectionRepository",
    "SelectionUnitOfWork",
    "SelectionUnitOfWorkProvider",
]
