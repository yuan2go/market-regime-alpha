"""PostgreSQL implementation of the Daily Runtime Journal."""

from market_regime_alpha.application.daily_loop.sqlite_repository import (
    SQLiteDailyRunRepository,
)
from market_regime_alpha.persistence.postgres.adapter import (
    PostgresRepositoryAdapter,
)


class PostgresDailyRunRepository(
    PostgresRepositoryAdapter,
    SQLiteDailyRunRepository,
):
    """Durable PostgreSQL DailyRun journal without SQLite fallback."""


__all__ = ["PostgresDailyRunRepository"]
