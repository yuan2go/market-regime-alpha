"""One short PostgreSQL transaction for Market Provider qualification."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, Callable
from uuid import UUID

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.provider_qualifications import (
    PostgresProviderQualificationRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
)
from market_regime_alpha.infrastructure.postgres.research_transaction import (
    classify_research_postgres_error,
    commit_research_transaction,
)
from market_regime_alpha.infrastructure.postgres.runtime_finalization import (
    PostgresRuntimeCommandFinalization,
)
from market_regime_alpha.market.ports import ProviderQualificationUnitOfWork


class PostgresProviderQualificationUnitOfWork:
    def __init__(
        self,
        pool: TargetPostgresPool,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._pool = pool
        self._id_factory = id_factory
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False

    def __enter__(self) -> PostgresProviderQualificationUnitOfWork:
        if self._used:
            raise RuntimeError(
                "PostgresProviderQualificationUnitOfWork cannot be nested or reused"
            )
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        return self

    def _active(self) -> psycopg.Connection[Any]:
        if self._connection is None:
            raise RuntimeError("ProviderQualification UoW is not active")
        return self._connection

    @property
    def provider_qualifications(self) -> PostgresProviderQualificationRepository:
        return PostgresProviderQualificationRepository(
            self._active(),
            id_factory=self._id_factory,
        )

    @property
    def receipts(self) -> PostgresCommandReceiptRepository:
        return PostgresCommandReceiptRepository(self._active())

    @property
    def audit(self) -> PostgresAuditRepository:
        return PostgresAuditRepository(self._active())

    @property
    def runtime_finalization(self) -> PostgresRuntimeCommandFinalization:
        return PostgresRuntimeCommandFinalization(self._active())

    def commit(self) -> None:
        commit_research_transaction(self._active())
        self._committed = True

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        replacement = classify_research_postgres_error(
            exception,
            owner="ProviderQualification",
        )
        if self._connection is not None and not self._committed:
            try:
                self._connection.rollback()
            except psycopg.Error:
                if exception is None:
                    raise
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._scope = None
        self._connection = None
        if replacement is not None:
            raise replacement from exception


class PostgresProviderQualificationUnitOfWorkProvider:
    def __init__(
        self,
        pool: TargetPostgresPool,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._pool = pool
        self._id_factory = id_factory

    def __call__(self) -> ProviderQualificationUnitOfWork:
        return PostgresProviderQualificationUnitOfWork(
            self._pool,
            id_factory=self._id_factory,
        )


__all__ = [
    "PostgresProviderQualificationUnitOfWork",
    "PostgresProviderQualificationUnitOfWorkProvider",
]
