"""Small native psycopg seams shared by bounded repositories."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from typing import cast

import psycopg
from psycopg.rows import DictRow, dict_row

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    verify_postgres_authority_schema,
)


PostgresConnection = psycopg.Connection[DictRow]


class NativePostgresRepository:
    """Own migration verification and expose direct psycopg connections."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        migrate: bool = False,
        read_only: bool = False,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be a PostgresConnectionFactory")
        if not isinstance(migrate, bool):
            raise TypeError("migrate must be a bool")
        if not isinstance(read_only, bool):
            raise TypeError("read_only must be a bool")
        self._postgres_factory = factory
        self._read_only = read_only
        if migrate:
            PostgresMigrator().apply_all(factory)
        with factory.connection(read_only=True) as connection:
            verify_postgres_authority_schema(connection)

    @contextmanager
    def _connect(self) -> Iterator[PostgresConnection]:
        with self._postgres_factory.connection(
            read_only=self._read_only
        ) as connection:
            previous = connection.row_factory
            connection.row_factory = dict_row
            try:
                yield cast(PostgresConnection, connection)
            finally:
                connection.row_factory = previous


def acquire_scope_lock(
    connection: PostgresConnection,
    *,
    namespace: str,
    identity: object,
) -> None:
    """Serialize first-write races only inside one explicit aggregate scope."""

    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("lock namespace must be non-empty")
    key = f"market-regime-alpha:{namespace}:{identity}"
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (key,),
    )


def aware_datetime(value: object, *, label: str) -> datetime:
    """Validate a native TIMESTAMPTZ value at the domain restoration seam."""

    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"stored {label} must be an aware datetime")
    return value


def date_value(value: object, *, label: str) -> date:
    """Validate a native PostgreSQL DATE value."""

    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"stored {label} must be a date")
    return value


__all__ = [
    "NativePostgresRepository",
    "PostgresConnection",
    "acquire_scope_lock",
    "aware_datetime",
    "date_value",
]
