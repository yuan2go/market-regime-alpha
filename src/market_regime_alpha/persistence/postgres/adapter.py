"""Shared connection seam for bounded-context PostgreSQL adapters."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3
from typing import cast

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


class PostgresRepositoryAdapter:
    """Initialize and expose the compatibility connection to domain logic."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        migrate: bool = True,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be a PostgresConnectionFactory")
        if not isinstance(migrate, bool):
            raise TypeError("migrate must be a bool")
        self._postgres_factory = factory
        if migrate:
            PostgresMigrator().apply_all(factory)
        with factory.connection(read_only=True) as connection:
            verify_postgres_authority_schema(connection)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._postgres_factory.connection() as connection:
            bridge = PostgresDBAPIConnection(connection)
            yield cast(sqlite3.Connection, bridge)
