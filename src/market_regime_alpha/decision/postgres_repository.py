"""PostgreSQL Opportunity and Thesis lifecycle adapter."""

from market_regime_alpha.decision.sqlite_repository import (
    SQLiteDecisionLifecycleRepository,
)
from market_regime_alpha.persistence.postgres.adapter import (
    PostgresRepositoryAdapter,
)


class PostgresDecisionLifecycleRepository(
    PostgresRepositoryAdapter,
    SQLiteDecisionLifecycleRepository,
):
    """PostgreSQL implementation of DecisionLifecycleRepository."""


__all__ = ["PostgresDecisionLifecycleRepository"]
