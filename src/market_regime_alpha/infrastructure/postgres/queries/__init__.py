"""Target PostgreSQL read adapters."""

from market_regime_alpha.infrastructure.postgres.queries.candidate import (
    PostgresCandidateQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.candidate_research_inputs import (
    PostgresCandidateResearchDependencyQueries,
    PostgresCandidateResearchInputLoader,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_inputs import (
    PostgresDecisionInputPreparationProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_runs import (
    PostgresDecisionRunQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_verification import (
    PostgresDecisionRunVerificationProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.market import (
    PostgresMarketQueries,
    PostgresMarketQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.outcome_inputs import (
    PostgresOutcomeDependencyRepository,
    PostgresOutcomeInputPreparationProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.outcomes import (
    PostgresOutcomeQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.outcome_verification import (
    PostgresOutcomeVerificationProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.selection_market import (
    PostgresSelectionMarketQueries,
)
from market_regime_alpha.infrastructure.postgres.queries.research_sources import (
    PostgresResearchSourceQueries,
)
from market_regime_alpha.infrastructure.postgres.queries.research_verification import (
    PostgresResearchEvaluationVerificationProvider,
)

__all__ = [
    "PostgresCandidateQueryProvider",
    "PostgresCandidateResearchDependencyQueries",
    "PostgresCandidateResearchInputLoader",
    "PostgresDecisionInputPreparationProvider",
    "PostgresDecisionRunQueryProvider",
    "PostgresDecisionRunVerificationProvider",
    "PostgresMarketQueries",
    "PostgresMarketQueryProvider",
    "PostgresOutcomeDependencyRepository",
    "PostgresOutcomeInputPreparationProvider",
    "PostgresOutcomeQueryProvider",
    "PostgresOutcomeVerificationProvider",
    "PostgresResearchSourceQueries",
    "PostgresResearchEvaluationVerificationProvider",
    "PostgresSelectionMarketQueries",
]
