"""PostgreSQL Controlled Decision-Time Operation journal."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Callable, cast

from market_regime_alpha.application.controlled_operation.sqlite_journal import (
    DEFAULT_CONTROLLED_OPERATION_LEASE,
    SQLiteDecisionTimeOperationJournal,
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
FaultInjector = Callable[[str], None]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class PostgresDecisionTimeOperationJournal(SQLiteDecisionTimeOperationJournal):
    """Parent operation journal using PostgreSQL lease and fencing guards."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _utc_now,
        lease_duration: timedelta = DEFAULT_CONTROLLED_OPERATION_LEASE,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be a PostgresConnectionFactory")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if fault_injector is not None and not callable(fault_injector):
            raise TypeError("fault_injector must be callable")
        self._postgres_factory = factory
        self._clock = clock
        self._lease_duration = lease_duration
        self._fault_injector = fault_injector
        PostgresMigrator().apply_all(factory)
        with factory.connection(read_only=True) as connection:
            verify_postgres_authority_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        bridge = PostgresDBAPIConnection.acquire(self._postgres_factory)
        return cast(sqlite3.Connection, bridge)


__all__ = ["PostgresDecisionTimeOperationJournal"]
