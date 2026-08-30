"""Aggregate-oriented PostgreSQL repositories for target contexts."""

from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
    PostgresRuntimeRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.artifacts import (
    PostgresArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.candidate import (
    PostgresCandidateRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.candidate_artifacts import (
    PostgresCandidateArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.market import (
    PostgresMarketRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.decision_runs import (
    PostgresDecisionRunRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.selection import (
    PostgresSelectionRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.research_artifacts import (
    PostgresResearchArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.research_definitions import (
    PostgresResearchDefinitionRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.target_artifacts import (
    PostgresTargetArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.target_definitions import (
    PostgresTargetDefinitionRepository,
)

__all__ = [
    "PostgresAuditRepository",
    "PostgresArtifactRepository",
    "PostgresCommandReceiptRepository",
    "PostgresCandidateArtifactRepository",
    "PostgresCandidateRepository",
    "PostgresDecisionRunRepository",
    "PostgresMarketRepository",
    "PostgresRuntimeRepository",
    "PostgresResearchArtifactRepository",
    "PostgresResearchDefinitionRepository",
    "PostgresSelectionRepository",
    "PostgresTargetArtifactRepository",
    "PostgresTargetDefinitionRepository",
]
