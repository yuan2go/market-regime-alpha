"""One short transaction for Evaluation and controlled Outcome access."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, Callable
from uuid import UUID

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.research_evaluation_inputs import PostgresTransactionalOutcomeAcquisition
from market_regime_alpha.infrastructure.postgres.repositories.research_evaluations import PostgresEvaluationRepository
from market_regime_alpha.infrastructure.postgres.repositories.runtime import PostgresAuditRepository, PostgresCommandReceiptRepository
from market_regime_alpha.infrastructure.postgres.repositories.target_artifacts import PostgresTargetArtifactRepository
from market_regime_alpha.infrastructure.postgres.runtime_finalization import PostgresRuntimeCommandFinalization
from market_regime_alpha.research_qualification.ports.evaluation_uow import EvaluationUnitOfWork
from market_regime_alpha.runtime.errors import RuntimeStateConflictError


class PostgresEvaluationUnitOfWork:
    def __init__(self, pool: TargetPostgresPool, *, id_factory: Callable[[], UUID]) -> None:
        self._pool = pool
        self._id_factory = id_factory
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False

    def __enter__(self) -> PostgresEvaluationUnitOfWork:
        if self._used:
            raise RuntimeError("PostgresEvaluationUnitOfWork cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        return self

    def _active(self) -> psycopg.Connection[Any]:
        if self._connection is None:
            raise RuntimeError("PostgresEvaluationUnitOfWork is not active")
        return self._connection

    @property
    def evaluations(self) -> PostgresEvaluationRepository:
        return PostgresEvaluationRepository(self._active(), id_factory=self._id_factory)

    @property
    def outcome_acquisition(self) -> PostgresTransactionalOutcomeAcquisition:
        return PostgresTransactionalOutcomeAcquisition(self._active(), id_factory=self._id_factory)

    @property
    def artifacts(self) -> PostgresTargetArtifactRepository:
        return PostgresTargetArtifactRepository(self._active())

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
        self._active().commit()
        self._committed = True

    def __exit__(self, exception_type: type[BaseException] | None, exception: BaseException | None, traceback: TracebackType | None) -> None:
        deterministic = isinstance(exception, psycopg.Error) and exception.sqlstate is not None and (exception.sqlstate.startswith(("22", "23")) or exception.sqlstate == "55000")
        if self._connection is not None and not self._committed:
            self._connection.rollback()
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._connection = None
        self._scope = None
        if deterministic:
            raise RuntimeStateConflictError("PostgreSQL rejected Evaluation invariants") from exception


class PostgresEvaluationUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool, *, id_factory: Callable[[], UUID]) -> None:
        self._pool = pool
        self._id_factory = id_factory

    def __call__(self) -> EvaluationUnitOfWork:
        return PostgresEvaluationUnitOfWork(self._pool, id_factory=self._id_factory)


__all__ = ["PostgresEvaluationUnitOfWork", "PostgresEvaluationUnitOfWorkProvider"]
