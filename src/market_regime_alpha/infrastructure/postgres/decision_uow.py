"""Independent short PostgreSQL transaction for Decision Support."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

import psycopg

from market_regime_alpha.decision_support.errors import (
    DecisionAuthorityIntegrityError,
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
)
from market_regime_alpha.decision_support.ports import DecisionSupportUnitOfWork
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.decision_inputs import (
    PostgresDecisionDependencyRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.decision_runs import (
    PostgresDecisionRunRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
)
from market_regime_alpha.infrastructure.postgres.runtime_finalization import (
    PostgresRuntimeCommandFinalization,
)


class PostgresDecisionSupportUnitOfWork:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False
        self._decision_runs: PostgresDecisionRunRepository | None = None
        self._dependencies: PostgresDecisionDependencyRepository | None = None
        self._receipts: PostgresCommandReceiptRepository | None = None
        self._audit: PostgresAuditRepository | None = None
        self._runtime_finalization: PostgresRuntimeCommandFinalization | None = None

    def __enter__(self) -> PostgresDecisionSupportUnitOfWork:
        if self._used or self._connection is not None:
            raise RuntimeError(
                "PostgresDecisionSupportUnitOfWork cannot be nested or reused"
            )
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        self._decision_runs = PostgresDecisionRunRepository(self._connection)
        self._dependencies = PostgresDecisionDependencyRepository(self._connection)
        self._receipts = PostgresCommandReceiptRepository(self._connection)
        self._audit = PostgresAuditRepository(self._connection)
        self._runtime_finalization = PostgresRuntimeCommandFinalization(
            self._connection
        )
        return self

    @property
    def decision_runs(self) -> PostgresDecisionRunRepository:
        if self._decision_runs is None:
            raise RuntimeError("Decision Support unit of work is not active")
        return self._decision_runs

    @property
    def dependencies(self) -> PostgresDecisionDependencyRepository:
        if self._dependencies is None:
            raise RuntimeError("Decision Support unit of work is not active")
        return self._dependencies

    @property
    def receipts(self) -> PostgresCommandReceiptRepository:
        if self._receipts is None:
            raise RuntimeError("Decision Support unit of work is not active")
        return self._receipts

    @property
    def audit(self) -> PostgresAuditRepository:
        if self._audit is None:
            raise RuntimeError("Decision Support unit of work is not active")
        return self._audit

    @property
    def runtime_finalization(self) -> PostgresRuntimeCommandFinalization:
        if self._runtime_finalization is None:
            raise RuntimeError("Decision Support unit of work is not active")
        return self._runtime_finalization

    def commit(self) -> None:
        if self._connection is None:
            raise RuntimeError("Decision Support unit of work is not active")
        if self._committed:
            raise RuntimeError("Decision Support unit of work already committed")
        try:
            self._connection.commit()
        except psycopg.Error as exc:
            if exc.sqlstate in {"40001", "40P01"}:
                raise DecisionRetryableTransactionError(str(exc.sqlstate)) from exc
            if not isinstance(exc, psycopg.OperationalError):
                raise
            raise DecisionCommitOutcomeUnknownError(
                "PostgreSQL connection failed while committing OPEN_DECISION_RUN"
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
                replacement = DecisionRetryableTransactionError(exception.sqlstate)
            elif exception.sqlstate.startswith(("22", "23")) or exception.sqlstate == "55000":
                replacement = DecisionAuthorityIntegrityError(
                    "PostgreSQL rejected Decision Authority invariants"
                )
        if self._connection is not None and not self._committed:
            self._connection.rollback()
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._scope = None
        self._connection = None
        self._decision_runs = None
        self._dependencies = None
        self._receipts = None
        self._audit = None
        self._runtime_finalization = None
        if replacement is not None:
            raise replacement from exception


class PostgresDecisionSupportUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> DecisionSupportUnitOfWork:
        return PostgresDecisionSupportUnitOfWork(self._pool)


__all__ = [
    "PostgresDecisionSupportUnitOfWork",
    "PostgresDecisionSupportUnitOfWorkProvider",
]
