"""Aggregate-oriented PostgreSQL repositories for target contexts."""

from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
    PostgresRuntimeRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.artifacts import (
    PostgresArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.market import (
    PostgresMarketRepository,
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

__all__ = [
    "PostgresAuditRepository",
    "PostgresArtifactRepository",
    "PostgresCommandReceiptRepository",
    "PostgresMarketRepository",
    "PostgresRuntimeRepository",
    "PostgresResearchArtifactRepository",
    "PostgresResearchDefinitionRepository",
    "PostgresSelectionRepository",
]
