"""Target PostgreSQL read adapters."""

from market_regime_alpha.infrastructure.postgres.queries.candidate import (
    PostgresCandidateQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.archive_operations import (
    PostgresArchiveOperationsReadPort,
)
from market_regime_alpha.infrastructure.postgres.queries.archive_inspection import (
    PostgresArchiveInspectionPort,
)
from market_regime_alpha.infrastructure.postgres.queries.archive_verification import (
    PostgresArchiveVerificationPort,
)
from market_regime_alpha.infrastructure.postgres.queries.archive_sessions import (
    PostgresArchiveTradingSessionReadPort,
)
from market_regime_alpha.infrastructure.postgres.queries.candidate_research_inputs import (
    PostgresCandidateResearchDependencyQueries,
    PostgresCandidateResearchInputLoader,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_inputs import (
    PostgresDecisionInputPreparationProvider,
    PostgresDecisionResearchQualificationInputProvider,
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
from market_regime_alpha.infrastructure.postgres.queries.market_revision_lineage import (
    PostgresMarketRevisionLineageReadPort,
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
from market_regime_alpha.infrastructure.postgres.queries.research_qualification import (
    PostgresResearchQualificationAdmissionReadPort,
)
from market_regime_alpha.infrastructure.postgres.queries.research_qualification_verification import (
    PostgresResearchQualificationVerificationProvider,
)

__all__ = [
    "PostgresCandidateQueryProvider",
    "PostgresArchiveOperationsReadPort",
    "PostgresArchiveInspectionPort",
    "PostgresArchiveVerificationPort",
    "PostgresArchiveTradingSessionReadPort",
    "PostgresCandidateResearchDependencyQueries",
    "PostgresCandidateResearchInputLoader",
    "PostgresDecisionInputPreparationProvider",
    "PostgresDecisionResearchQualificationInputProvider",
    "PostgresDecisionRunQueryProvider",
    "PostgresDecisionRunVerificationProvider",
    "PostgresMarketQueries",
    "PostgresMarketQueryProvider",
    "PostgresMarketRevisionLineageReadPort",
    "PostgresOutcomeDependencyRepository",
    "PostgresOutcomeInputPreparationProvider",
    "PostgresOutcomeQueryProvider",
    "PostgresOutcomeVerificationProvider",
    "PostgresResearchSourceQueries",
    "PostgresResearchEvaluationVerificationProvider",
    "PostgresResearchQualificationAdmissionReadPort",
    "PostgresResearchQualificationVerificationProvider",
    "PostgresSelectionMarketQueries",
]
