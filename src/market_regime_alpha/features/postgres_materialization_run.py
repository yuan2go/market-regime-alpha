"""PostgreSQL Feature Materialization run authority."""

from __future__ import annotations

from datetime import datetime, timedelta
import sqlite3
from typing import Callable, cast

from market_regime_alpha.features.materialization_run import (
    DEFAULT_FEATURE_TASK_LEASE,
    SQLiteFeatureMaterializationRunRepository,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.dbapi import (
    PostgresDBAPIConnection,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    verify_postgres_authority_schema,
)


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)


class PostgresFeatureMaterializationRunRepository(
    SQLiteFeatureMaterializationRunRepository
):
    """Feature run/task leases backed by PostgreSQL fencing constraints."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _utc_now,
        lease_duration: timedelta = DEFAULT_FEATURE_TASK_LEASE,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be a PostgresConnectionFactory")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not isinstance(lease_duration, timedelta) or lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self._postgres_factory = factory
        self._clock = clock
        self._lease_duration = lease_duration
        PostgresMigrator().apply_all(factory)
        with factory.connection(read_only=True) as connection:
            verify_postgres_authority_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        bridge = PostgresDBAPIConnection.acquire(self._postgres_factory)
        return cast(sqlite3.Connection, bridge)


__all__ = ["PostgresFeatureMaterializationRunRepository"]
