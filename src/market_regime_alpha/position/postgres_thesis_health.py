"""PostgreSQL Thesis-health observation adapter."""

from market_regime_alpha.persistence.postgres.adapter import (
    PostgresRepositoryAdapter,
)
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)


class PostgresThesisHealthRepository(
    PostgresRepositoryAdapter,
    SQLiteThesisHealthRepository,
):
    """PostgreSQL implementation of ThesisHealthRepository."""


__all__ = ["PostgresThesisHealthRepository"]
