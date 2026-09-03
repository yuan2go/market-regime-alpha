"""Narrow one-transaction Market archive unit of work."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.market_archive import (
    PostgresArchiveRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
)
from market_regime_alpha.infrastructure.postgres.runtime_finalization import (
    PostgresRuntimeCommandFinalization,
)
from market_regime_alpha.market.ports.archive import ArchiveUnitOfWork
from market_regime_alpha.runtime.errors import RuntimeStateConflictError


class PostgresArchiveUnitOfWork:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False
        self._archives: PostgresArchiveRepository | None = None
        self._receipts: PostgresCommandReceiptRepository | None = None
        self._audit: PostgresAuditRepository | None = None
        self._runtime_finalization: PostgresRuntimeCommandFinalization | None = None

    def __enter__(self) -> PostgresArchiveUnitOfWork:
        if self._used or self._connection is not None:
            raise RuntimeError("PostgresArchiveUnitOfWork cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        self._archives = PostgresArchiveRepository(self._connection)
        self._receipts = PostgresCommandReceiptRepository(self._connection)
        self._audit = PostgresAuditRepository(self._connection)
        self._runtime_finalization = PostgresRuntimeCommandFinalization(self._connection)
        return self

    @property
    def archives(self) -> PostgresArchiveRepository:
        if self._archives is None:
            raise RuntimeError("PostgresArchiveUnitOfWork is not active")
        return self._archives

    @property
    def receipts(self) -> PostgresCommandReceiptRepository:
        if self._receipts is None:
            raise RuntimeError("PostgresArchiveUnitOfWork is not active")
        return self._receipts

    @property
    def audit(self) -> PostgresAuditRepository:
        if self._audit is None:
            raise RuntimeError("PostgresArchiveUnitOfWork is not active")
        return self._audit

    @property
    def runtime_finalization(self) -> PostgresRuntimeCommandFinalization:
        if self._runtime_finalization is None:
            raise RuntimeError("PostgresArchiveUnitOfWork is not active")
        return self._runtime_finalization

    def commit(self) -> None:
        if self._connection is None:
            raise RuntimeError("PostgresArchiveUnitOfWork is not active")
        if self._committed:
            raise RuntimeError("PostgresArchiveUnitOfWork already committed")
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
            and (exception.sqlstate.startswith(("22", "23")) or exception.sqlstate == "55000")
        )
        if self._connection is not None and not self._committed:
            self._connection.rollback()
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._scope = None
        self._connection = None
        self._archives = None
        self._receipts = None
        self._audit = None
        self._runtime_finalization = None
        if deterministic_database_rejection:
            raise RuntimeStateConflictError(
                "PostgreSQL rejected the Market archive command's canonical invariants"
            ) from exception


class PostgresArchiveUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> ArchiveUnitOfWork:
        return PostgresArchiveUnitOfWork(self._pool)


__all__ = ["PostgresArchiveUnitOfWork", "PostgresArchiveUnitOfWorkProvider"]
