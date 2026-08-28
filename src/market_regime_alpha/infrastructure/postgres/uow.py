"""One PostgreSQL transaction per Application command."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories import (
    PostgresAuditRepository,
    PostgresArtifactRepository,
    PostgresCommandReceiptRepository,
    PostgresRuntimeRepository,
)
from market_regime_alpha.runtime.ports import RuntimeUnitOfWork


class PostgresUnitOfWork:
    """Own exactly one transaction and repositories bound to its connection."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._connection_scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False
        self._runtime: PostgresRuntimeRepository | None = None
        self._receipts: PostgresCommandReceiptRepository | None = None
        self._audit: PostgresAuditRepository | None = None
        self._artifacts: PostgresArtifactRepository | None = None

    def __enter__(self) -> PostgresUnitOfWork:
        if self._connection is not None or self._used:
            raise RuntimeError("PostgresUnitOfWork cannot be nested or reused")
        self._used = True
        self._connection_scope = self._pool.connection()
        self._connection = self._connection_scope.__enter__()
        self._runtime = PostgresRuntimeRepository(self._connection)
        self._receipts = PostgresCommandReceiptRepository(self._connection)
        self._audit = PostgresAuditRepository(self._connection)
        self._artifacts = PostgresArtifactRepository(self._connection)
        return self

    @property
    def runtime(self) -> PostgresRuntimeRepository:
        if self._runtime is None:
            raise RuntimeError("PostgresUnitOfWork is not active")
        return self._runtime

    @property
    def receipts(self) -> PostgresCommandReceiptRepository:
        if self._receipts is None:
            raise RuntimeError("PostgresUnitOfWork is not active")
        return self._receipts

    @property
    def audit(self) -> PostgresAuditRepository:
        if self._audit is None:
            raise RuntimeError("PostgresUnitOfWork is not active")
        return self._audit

    @property
    def artifacts(self) -> PostgresArtifactRepository:
        if self._artifacts is None:
            raise RuntimeError("PostgresUnitOfWork is not active")
        return self._artifacts

    def commit(self) -> None:
        if self._connection is None:
            raise RuntimeError("PostgresUnitOfWork is not active")
        if self._committed:
            raise RuntimeError("PostgresUnitOfWork already committed")
        self._connection.commit()
        self._committed = True

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._connection is not None and not self._committed:
            self._connection.rollback()
        if self._connection_scope is not None:
            self._connection_scope.__exit__(exception_type, exception, traceback)
        self._connection_scope = None
        self._connection = None
        self._runtime = None
        self._receipts = None
        self._audit = None
        self._artifacts = None


class PostgresUnitOfWorkProvider:
    """Construct one bounded UoW, not a repository/service locator."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> RuntimeUnitOfWork:
        return PostgresUnitOfWork(self._pool)


__all__ = ["PostgresUnitOfWork", "PostgresUnitOfWorkProvider"]
