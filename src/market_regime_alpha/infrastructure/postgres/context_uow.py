"""One short PostgreSQL transaction for Context Authority."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, cast

import psycopg

from market_regime_alpha.decision_support.errors import (
    ContextAuthorityIntegrityError,
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
)
from market_regime_alpha.decision_support.ports import (
    ContextArtifactRepository,
    ContextUnitOfWork,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.decision_context_inputs import (
    PostgresContextDependencyRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.decision_context import (
    PostgresContextRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.target_artifacts import (
    PostgresTargetArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.runtime_finalization import (
    PostgresRuntimeCommandFinalization,
)


class PostgresContextUnitOfWork:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False

    def __enter__(self) -> PostgresContextUnitOfWork:
        if self._used:
            raise RuntimeError("PostgresContextUnitOfWork cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        return self

    def _active(self) -> psycopg.Connection[Any]:
        if self._connection is None:
            raise RuntimeError("PostgresContextUnitOfWork is not active")
        return self._connection

    @property
    def contexts(self) -> PostgresContextRepository:
        return PostgresContextRepository(self._active())

    @property
    def dependencies(self) -> PostgresContextDependencyRepository:
        return PostgresContextDependencyRepository(self._active())

    @property
    def artifacts(self) -> ContextArtifactRepository:
        return cast(
            ContextArtifactRepository,
            PostgresTargetArtifactRepository(self._active()),
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
        try:
            self._active().commit()
        except psycopg.Error as exc:
            if exc.sqlstate in {"40001", "40P01"}:
                raise DecisionRetryableTransactionError(str(exc.sqlstate)) from exc
            if exc.sqlstate is not None and (
                exc.sqlstate.startswith(("22", "23")) or exc.sqlstate == "55000"
            ):
                raise ContextAuthorityIntegrityError(
                    "PostgreSQL rejected Context Authority invariants"
                ) from exc
            if isinstance(exc, psycopg.OperationalError):
                raise DecisionCommitOutcomeUnknownError(
                    "PostgreSQL acknowledgement was lost during Context commit"
                ) from exc
            raise
        self._committed = True

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        replacement: BaseException | None = None
        if isinstance(exception, psycopg.Error) and exception.sqlstate is not None:
            if exception.sqlstate in {"40001", "40P01"}:
                replacement = DecisionRetryableTransactionError(exception.sqlstate)
            elif exception.sqlstate.startswith(("22", "23")) or exception.sqlstate == "55000":
                replacement = ContextAuthorityIntegrityError(
                    "PostgreSQL rejected Context Authority invariants"
                )
        if self._connection is not None and not self._committed:
            self._connection.rollback()
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._scope = None
        self._connection = None
        if replacement is not None:
            raise replacement from exception


class PostgresContextUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> ContextUnitOfWork:
        return cast(ContextUnitOfWork, PostgresContextUnitOfWork(self._pool))


__all__ = ["PostgresContextUnitOfWork", "PostgresContextUnitOfWorkProvider"]
