"""Bounded PostgreSQL connection pooling with safe session defaults."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
import re
from typing import Any

import psycopg
from psycopg.pq import TransactionStatus
from psycopg_pool import ConnectionPool, PoolTimeout

from market_regime_alpha.persistence.settings import (
    DatabaseSettings,
    redact_database_url,
)


APPLICATION_SCHEMA = "market_regime_alpha"
APPLICATION_NAME = "market-regime-alpha"
_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


class PostgresConnectionUnavailable(RuntimeError):
    """Raised without credentials when the configured database is unavailable."""


class PostgresConnectionFactory:
    """Own a small pool suitable for the current CLI-first local runtime."""

    def __init__(
        self,
        settings: DatabaseSettings,
        *,
        min_size: int = 1,
        max_size: int = 4,
        timeout_seconds: float = 10.0,
        max_idle_seconds: float = 60.0,
        max_lifetime_seconds: float = 1800.0,
        application_schema: str = APPLICATION_SCHEMA,
    ) -> None:
        database_url = settings.require_database_url()
        if isinstance(min_size, bool) or min_size < 0:
            raise ValueError("min_size must be non-negative")
        if isinstance(max_size, bool) or max_size < max(1, min_size):
            raise ValueError("max_size must be at least one and >= min_size")
        for label, value in (
            ("timeout_seconds", timeout_seconds),
            ("max_idle_seconds", max_idle_seconds),
            ("max_lifetime_seconds", max_lifetime_seconds),
        ):
            if isinstance(value, bool) or value <= 0:
                raise ValueError(f"{label} must be positive")
        if not isinstance(application_schema, str) or not _SCHEMA_NAME.fullmatch(
            application_schema
        ):
            raise ValueError("application_schema must be a lowercase SQL identifier")
        self._database_url = database_url
        self.application_schema = application_schema
        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=min_size,
            max_size=max_size,
            timeout=float(timeout_seconds),
            max_idle=float(max_idle_seconds),
            max_lifetime=float(max_lifetime_seconds),
            kwargs={"autocommit": False},
            configure=partial(
                _configure_connection,
                application_schema=application_schema,
            ),
            open=False,
            name="market-regime-alpha",
        )

    @contextmanager
    def connection(
        self,
        *,
        read_only: bool = False,
    ) -> Iterator[psycopg.Connection[Any]]:
        if not isinstance(read_only, bool):
            raise TypeError("read_only must be a bool")
        try:
            self._pool.open(wait=True)
            connection = self._pool.getconn()
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            locator = redact_database_url(self._database_url)
            raise PostgresConnectionUnavailable(
                f"PostgreSQL database is unavailable: {locator}"
            ) from exc
        try:
            connection.read_only = read_only
            yield connection
            if connection.info.transaction_status is not TransactionStatus.IDLE:
                connection.commit()
        except BaseException:
            if connection.info.transaction_status is not TransactionStatus.IDLE:
                connection.rollback()
            raise
        finally:
            if connection.info.transaction_status is not TransactionStatus.IDLE:
                connection.rollback()
            connection.read_only = False
            self._pool.putconn(connection)

    def close(self) -> None:
        self._pool.close()

    def __enter__(self) -> PostgresConnectionFactory:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _configure_connection(
    connection: psycopg.Connection[Any],
    *,
    application_schema: str,
) -> None:
    settings = {
        "search_path": f"{application_schema}, pg_catalog",
        "timezone": "UTC",
        "application_name": APPLICATION_NAME,
        "statement_timeout": "30s",
        "lock_timeout": "5s",
        "idle_in_transaction_session_timeout": "30s",
    }
    with connection.cursor() as cursor:
        for name, value in settings.items():
            cursor.execute("SELECT set_config(%s, %s, false)", (name, value))
    connection.commit()
