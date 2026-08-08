"""Bounded PostgreSQL connection pooling with safe session defaults."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
import re
from threading import Lock
import time
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


@dataclass(frozen=True, slots=True)
class PostgresRuntimeMetrics:
    """Credential-free process metrics for PostgreSQL transaction coordination."""

    transaction_attempts: int
    transaction_retries: int
    scoped_advisory_locks: int
    scoped_lock_wait_seconds: float


class _MutablePostgresRuntimeMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._transaction_attempts = 0
        self._transaction_retries = 0
        self._scoped_advisory_locks = 0
        self._scoped_lock_wait_seconds = 0.0

    def record_transaction_attempt(self) -> None:
        with self._lock:
            self._transaction_attempts += 1

    def record_transaction_retry(self) -> None:
        with self._lock:
            self._transaction_retries += 1

    def record_scoped_lock(self, wait_seconds: float) -> None:
        with self._lock:
            self._scoped_advisory_locks += 1
            self._scoped_lock_wait_seconds += max(0.0, wait_seconds)

    def snapshot(self) -> PostgresRuntimeMetrics:
        with self._lock:
            return PostgresRuntimeMetrics(
                transaction_attempts=self._transaction_attempts,
                transaction_retries=self._transaction_retries,
                scoped_advisory_locks=self._scoped_advisory_locks,
                scoped_lock_wait_seconds=self._scoped_lock_wait_seconds,
            )


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
        if not isinstance(application_schema, str) or not _SCHEMA_NAME.fullmatch(application_schema):
            raise ValueError("application_schema must be a lowercase SQL identifier")
        self._database_url = database_url
        self.application_schema = application_schema
        self._runtime_metrics = _MutablePostgresRuntimeMetrics()
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
            # ``open(wait=True)`` is not safe to repeat while the pool's only
            # ready connection is checked out: psycopg_pool waits for the
            # initialization-ready signal again instead of growing the pool.
            # Opening is idempotent; ``getconn`` owns the bounded availability
            # wait and can request another connection for nested repository
            # reads.
            self._pool.open(wait=False)
            connection = self._pool.getconn()
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            locator = redact_database_url(self._database_url)
            raise PostgresConnectionUnavailable(
                "PostgreSQL database is unavailable: "
                f"{locator} ({type(exc).__name__})"
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

    @property
    def runtime_metrics(self) -> PostgresRuntimeMetrics:
        """Return a stable snapshot suitable for structured operational output."""

        return self._runtime_metrics.snapshot()

    def record_scoped_lock(self, wait_seconds: float) -> None:
        """Record one PostgreSQL scope lock without exposing SQL or secrets."""

        self._runtime_metrics.record_scoped_lock(wait_seconds)

    def run_transaction(
        self,
        operation: Callable[[psycopg.Connection[Any]], Any],
        *,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.01,
    ) -> Any:
        """Run one short unit of work with bounded PostgreSQL-native retries."""

        if not callable(operation):
            raise TypeError("operation must be callable")
        if isinstance(max_attempts, bool) or not 1 <= max_attempts <= 8:
            raise ValueError("max_attempts must be between one and eight")
        if isinstance(retry_backoff_seconds, bool) or retry_backoff_seconds < 0 or retry_backoff_seconds > 1:
            raise ValueError("retry_backoff_seconds must be between zero and one")
        for attempt in range(1, max_attempts + 1):
            self._runtime_metrics.record_transaction_attempt()
            try:
                with self.connection() as connection:
                    return operation(connection)
            except psycopg.Error as exc:
                if attempt == max_attempts or not is_retryable_transaction_error(exc):
                    raise
                self._runtime_metrics.record_transaction_retry()
                if retry_backoff_seconds:
                    time.sleep(retry_backoff_seconds * attempt)
        raise AssertionError("unreachable transaction retry state")

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
        "idle_in_transaction_session_timeout": "120s",
    }
    with connection.cursor() as cursor:
        for name, value in settings.items():
            cursor.execute("SELECT set_config(%s, %s, false)", (name, value))
    connection.commit()


def is_retryable_transaction_error(error: BaseException) -> bool:
    """Identify only PostgreSQL serialization/deadlock failures as retryable."""

    return isinstance(error, psycopg.Error) and error.sqlstate in {"40001", "40P01"}


__all__ = [
    "APPLICATION_NAME",
    "APPLICATION_SCHEMA",
    "PostgresConnectionFactory",
    "PostgresConnectionUnavailable",
    "PostgresRuntimeMetrics",
    "is_retryable_transaction_error",
]
