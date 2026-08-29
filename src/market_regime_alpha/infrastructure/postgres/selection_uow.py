"""Independent one-transaction Selection Core unit of work."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any
import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.runtime_finalization import (
    PostgresRuntimeCommandFinalization,
)
from market_regime_alpha.infrastructure.postgres.queries.selection_market import (
    PostgresSelectionMarketQueries,
)
from market_regime_alpha.infrastructure.postgres.repositories import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
    PostgresSelectionRepository,
)
from market_regime_alpha.runtime.errors import RuntimeStateConflictError
from market_regime_alpha.selection.ports import SelectionUnitOfWork


class PostgresSelectionUnitOfWork:
    """Selection Authority plus narrow Market reads and cross-cutting ports."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False
        self._selection: PostgresSelectionRepository | None = None
        self._market_queries: PostgresSelectionMarketQueries | None = None
        self._receipts: PostgresCommandReceiptRepository | None = None
        self._audit: PostgresAuditRepository | None = None
        self._runtime_finalization: PostgresRuntimeCommandFinalization | None = None

    def __enter__(self) -> PostgresSelectionUnitOfWork:
        if self._connection is not None or self._used:
            raise RuntimeError("PostgresSelectionUnitOfWork cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        self._selection = PostgresSelectionRepository(self._connection)
        self._market_queries = PostgresSelectionMarketQueries(self._connection)
        self._receipts = PostgresCommandReceiptRepository(self._connection)
        self._audit = PostgresAuditRepository(self._connection)
        self._runtime_finalization = PostgresRuntimeCommandFinalization(
            self._connection
        )
        return self

    @property
    def selection(self) -> PostgresSelectionRepository:
        if self._selection is None:
            raise RuntimeError("PostgresSelectionUnitOfWork is not active")
        return self._selection

    @property
    def market_queries(self) -> PostgresSelectionMarketQueries:
        if self._market_queries is None:
            raise RuntimeError("PostgresSelectionUnitOfWork is not active")
        return self._market_queries

    @property
    def receipts(self) -> PostgresCommandReceiptRepository:
        if self._receipts is None:
            raise RuntimeError("PostgresSelectionUnitOfWork is not active")
        return self._receipts

    @property
    def audit(self) -> PostgresAuditRepository:
        if self._audit is None:
            raise RuntimeError("PostgresSelectionUnitOfWork is not active")
        return self._audit

    @property
    def runtime_finalization(self) -> PostgresRuntimeCommandFinalization:
        if self._runtime_finalization is None:
            raise RuntimeError("PostgresSelectionUnitOfWork is not active")
        return self._runtime_finalization

    def commit(self) -> None:
        if self._connection is None:
            raise RuntimeError("PostgresSelectionUnitOfWork is not active")
        if self._committed:
            raise RuntimeError("PostgresSelectionUnitOfWork already committed")
        self._connection.commit()
        self._committed = True

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        deterministic_database_rejection = (
            isinstance(exception, psycopg.Error)
            and exception.sqlstate is not None
            and (exception.sqlstate.startswith(("22", "23")) or exception.sqlstate in {"40001", "55000"})
        )
        if self._connection is not None and not self._committed:
            self._connection.rollback()
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._scope = None
        self._connection = None
        self._selection = None
        self._market_queries = None
        self._receipts = None
        self._audit = None
        self._runtime_finalization = None
        if deterministic_database_rejection:
            raise RuntimeStateConflictError("PostgreSQL rejected the Selection command's canonical invariants") from exception


class PostgresSelectionUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> SelectionUnitOfWork:
        return PostgresSelectionUnitOfWork(self._pool)


__all__ = [
    "PostgresSelectionUnitOfWork",
    "PostgresSelectionUnitOfWorkProvider",
]
