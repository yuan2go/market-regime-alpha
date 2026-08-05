"""PostgreSQL canonical lifecycle runtime journal."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import sqlite3
from typing import cast

from market_regime_alpha.application.canonical_lifecycle.postgres_schema import (
    verify_postgres_lifecycle_schema,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleJournalIntegrityError,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.persistence.postgres.adapter import (
    PostgresRepositoryAdapter,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.dbapi import (
    PostgresDBAPIConnection,
)


FaultInjector = Callable[[str], None]


class PostgresLifecycleRunRepository(
    PostgresRepositoryAdapter,
    SQLiteLifecycleRunRepository,
):
    """Fenced lifecycle journal with PostgreSQL snapshot transactions."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        fault_injector: FaultInjector | None = None,
        read_only: bool = False,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be a PostgresConnectionFactory")
        if fault_injector is not None and not callable(fault_injector):
            raise TypeError("fault_injector must be callable or None")
        if not isinstance(read_only, bool):
            raise TypeError("read_only must be a bool")
        self._fault_injector = fault_injector
        self._busy_timeout_seconds = 30.0
        self._read_only = read_only
        try:
            PostgresRepositoryAdapter.__init__(
                self,
                factory,
                migrate=not read_only,
            )
            with factory.connection(read_only=True) as connection:
                verify_postgres_lifecycle_schema(connection)
        except Exception as exc:
            raise LifecycleJournalIntegrityError(
                "PostgreSQL lifecycle journal schema is invalid"
            ) from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._postgres_factory.connection(
            read_only=self._read_only
        ) as connection:
            bridge = PostgresDBAPIConnection(connection)
            yield cast(sqlite3.Connection, bridge)


__all__ = ["PostgresLifecycleRunRepository"]
