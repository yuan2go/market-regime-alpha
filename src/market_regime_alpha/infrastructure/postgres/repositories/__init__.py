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

__all__ = [
    "PostgresAuditRepository",
    "PostgresArtifactRepository",
    "PostgresCommandReceiptRepository",
    "PostgresMarketRepository",
    "PostgresRuntimeRepository",
    "PostgresSelectionRepository",
]
