"""PostgreSQL Composite Operational Evidence adapter."""

from market_regime_alpha.application.operational_research.sqlite_composite_repository import (
    SQLiteCompositeOperationalRepository,
)
from market_regime_alpha.persistence.postgres.adapter import (
    PostgresRepositoryAdapter,
)


class PostgresCompositeOperationalRepository(
    PostgresRepositoryAdapter,
    SQLiteCompositeOperationalRepository,
):
    """PostgreSQL implementation of CompositeOperationalRepository."""


__all__ = ["PostgresCompositeOperationalRepository"]
