"""PostgreSQL manual execution and traceability adapters."""

from market_regime_alpha.execution.sqlite_repository import (
    SQLiteManualExecutionRepository,
)
from market_regime_alpha.execution.sqlite_traceability import (
    SQLiteTraceableManualExecutionRepository,
)
from market_regime_alpha.persistence.postgres.adapter import (
    PostgresRepositoryAdapter,
)


class PostgresManualExecutionRepository(
    PostgresRepositoryAdapter,
    SQLiteManualExecutionRepository,
):
    """PostgreSQL implementation of ManualExecutionRepository."""


class PostgresTraceableManualExecutionRepository(
    PostgresRepositoryAdapter,
    SQLiteTraceableManualExecutionRepository,
):
    """PostgreSQL implementation of TraceableManualExecutionRepository."""


__all__ = [
    "PostgresManualExecutionRepository",
    "PostgresTraceableManualExecutionRepository",
]
