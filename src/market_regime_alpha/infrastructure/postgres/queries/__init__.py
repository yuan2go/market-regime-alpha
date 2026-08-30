"""Target PostgreSQL read adapters."""

from market_regime_alpha.infrastructure.postgres.queries.candidate import (
    PostgresCandidateQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.candidate_research_inputs import (
    PostgresCandidateResearchDependencyQueries,
    PostgresCandidateResearchInputLoader,
)
from market_regime_alpha.infrastructure.postgres.queries.market import (
    PostgresMarketQueries,
    PostgresMarketQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.selection_market import (
    PostgresSelectionMarketQueries,
)
from market_regime_alpha.infrastructure.postgres.queries.research_sources import (
    PostgresResearchSourceQueries,
)

__all__ = [
    "PostgresCandidateQueryProvider",
    "PostgresCandidateResearchDependencyQueries",
    "PostgresCandidateResearchInputLoader",
    "PostgresMarketQueries",
    "PostgresMarketQueryProvider",
    "PostgresResearchSourceQueries",
    "PostgresSelectionMarketQueries",
]
