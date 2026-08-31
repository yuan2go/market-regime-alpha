"""Independent serializable short PostgreSQL transaction for Outcome."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.outcome_inputs import (
    PostgresOutcomeDependencyRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.outcomes import (
    PostgresOutcomeRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
)
from market_regime_alpha.infrastructure.postgres.runtime_finalization import (
    PostgresRuntimeCommandFinalization,
)
from market_regime_alpha.outcome.errors import (
    OutcomeAuthorityIntegrityError,
    OutcomeCommitResultUnknownError,
    OutcomeRetryableTransactionError,
)
from market_regime_alpha.outcome.ports import OutcomeUnitOfWork


class PostgresOutcomeUnitOfWork:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False
        self._outcomes: PostgresOutcomeRepository | None = None
        self._dependencies: PostgresOutcomeDependencyRepository | None = None
        self._receipts: PostgresCommandReceiptRepository | None = None
        self._audit: PostgresAuditRepository | None = None
        self._runtime_finalization: PostgresRuntimeCommandFinalization | None = None

    def __enter__(self) -> PostgresOutcomeUnitOfWork:
        if self._used or self._connection is not None:
            raise RuntimeError("PostgresOutcomeUnitOfWork cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        self._connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        self._outcomes = PostgresOutcomeRepository(self._connection)
        self._dependencies = PostgresOutcomeDependencyRepository(self._connection)
        self._receipts = PostgresCommandReceiptRepository(self._connection)
        self._audit = PostgresAuditRepository(self._connection)
        self._runtime_finalization = PostgresRuntimeCommandFinalization(
            self._connection
        )
        return self

    @property
    def outcomes(self) -> PostgresOutcomeRepository:
        if self._outcomes is None:
            raise RuntimeError("Outcome unit of work is not active")
        return self._outcomes

    @property
    def dependencies(self) -> PostgresOutcomeDependencyRepository:
        if self._dependencies is None:
            raise RuntimeError("Outcome unit of work is not active")
        return self._dependencies

    @property
    def receipts(self) -> PostgresCommandReceiptRepository:
        if self._receipts is None:
            raise RuntimeError("Outcome unit of work is not active")
        return self._receipts

    @property
    def audit(self) -> PostgresAuditRepository:
        if self._audit is None:
            raise RuntimeError("Outcome unit of work is not active")
        return self._audit

    @property
    def runtime_finalization(self) -> PostgresRuntimeCommandFinalization:
        if self._runtime_finalization is None:
            raise RuntimeError("Outcome unit of work is not active")
        return self._runtime_finalization

    def commit(self) -> None:
        if self._connection is None:
            raise RuntimeError("Outcome unit of work is not active")
        if self._committed:
            raise RuntimeError("Outcome unit of work already committed")
        try:
            self._connection.commit()
        except psycopg.Error as exc:
            if exc.sqlstate in {"40001", "40P01"}:
                raise OutcomeRetryableTransactionError(str(exc.sqlstate)) from exc
            if not isinstance(exc, psycopg.OperationalError):
                raise
            raise OutcomeCommitResultUnknownError(
                "PostgreSQL connection failed while committing Outcome revision"
            ) from exc
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
                replacement = OutcomeRetryableTransactionError(exception.sqlstate)
            elif exception.sqlstate.startswith(("22", "23")) or (
                exception.sqlstate == "55000"
            ):
                replacement = OutcomeAuthorityIntegrityError(
                    "PostgreSQL rejected Outcome Authority invariants"
                )
            elif isinstance(exception, psycopg.OperationalError) and (
                exception.sqlstate.startswith("08")
            ):
                replacement = OutcomeRetryableTransactionError(exception.sqlstate)
        elif isinstance(exception, psycopg.OperationalError):
            replacement = OutcomeRetryableTransactionError("08000")
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
        self._outcomes = None
        self._dependencies = None
        self._receipts = None
        self._audit = None
        self._runtime_finalization = None
        if replacement is not None:
            raise replacement from exception


class PostgresOutcomeUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> OutcomeUnitOfWork:
        return PostgresOutcomeUnitOfWork(self._pool)


__all__ = ["PostgresOutcomeUnitOfWork", "PostgresOutcomeUnitOfWorkProvider"]
