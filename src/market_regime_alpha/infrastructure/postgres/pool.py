"""Bounded target connection pool with explicit verified-schema sessions."""

from __future__ import annotations

from contextlib import contextmanager
from functools import partial
import re
from typing import Any, Iterator

import psycopg
from psycopg_pool import ConnectionPool


_APPLICATION_NAME = "market-regime-alpha-refoundation"
_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


class TargetPostgresPool:
    """Own connections for target UoWs; schema verification happens in bootstrap."""

    def __init__(
        self,
        database_url: str,
        *,
        min_size: int = 1,
        max_size: int = 4,
        application_schema: str = "mra",
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        if not _SCHEMA_NAME.fullmatch(application_schema):
            raise ValueError("application_schema must be a lowercase SQL identifier")
        if isinstance(min_size, bool) or min_size < 0:
            raise ValueError("min_size must be non-negative")
        if isinstance(max_size, bool) or max_size < max(1, min_size):
            raise ValueError("max_size must be at least one and >= min_size")
        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=min_size,
            max_size=max_size,
            timeout=10.0,
            max_idle=60.0,
            max_lifetime=1800.0,
            kwargs={"autocommit": False},
            configure=partial(
                _configure_connection,
                application_schema=application_schema,
            ),
            open=False,
            name="mra-refoundation",
        )

    @contextmanager
    def connection(self, *, read_only: bool = False) -> Iterator[psycopg.Connection[Any]]:
        self._pool.open(wait=False)
        connection = self._pool.getconn()
        try:
            connection.read_only = read_only
            yield connection
        finally:
            if connection.info.transaction_status != 0:
                connection.rollback()
            connection.read_only = False
            self._pool.putconn(connection)

    def close(self) -> None:
        self._pool.close()


def _configure_connection(
    connection: psycopg.Connection[Any],
    *,
    application_schema: str,
) -> None:
    settings = {
        "search_path": f"{application_schema}, pg_catalog",
        "timezone": "UTC",
        "application_name": _APPLICATION_NAME,
        "statement_timeout": "30s",
        "lock_timeout": "5s",
        "idle_in_transaction_session_timeout": "60s",
    }
    for name, value in settings.items():
        connection.execute("SELECT set_config(%s, %s, false)", (name, value))
    connection.commit()


__all__ = ["TargetPostgresPool"]
