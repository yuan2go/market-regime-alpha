"""One short PostgreSQL transaction for Opportunity and Thesis."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, cast

import psycopg

from market_regime_alpha.decision_support.errors import (
    DecisionAuthorityIntegrityError,
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
)
from market_regime_alpha.decision_support.ports import OpportunityArtifactRepository, OpportunityUnitOfWork
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.decision_opportunity_inputs import PostgresOpportunityDependencyRepository
from market_regime_alpha.infrastructure.postgres.repositories.decision_opportunities import PostgresOpportunityRepository
from market_regime_alpha.infrastructure.postgres.repositories.runtime import PostgresAuditRepository, PostgresCommandReceiptRepository
from market_regime_alpha.infrastructure.postgres.repositories.target_artifacts import PostgresTargetArtifactRepository
from market_regime_alpha.infrastructure.postgres.runtime_finalization import PostgresRuntimeCommandFinalization


class PostgresOpportunityUnitOfWork:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False

    def __enter__(self) -> PostgresOpportunityUnitOfWork:
        if self._used:
            raise RuntimeError("PostgresOpportunityUnitOfWork cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        return self

    def _active(self) -> psycopg.Connection[Any]:
        if self._connection is None:
            raise RuntimeError("PostgresOpportunityUnitOfWork is not active")
        return self._connection

    @property
    def opportunities(self) -> PostgresOpportunityRepository:
        return PostgresOpportunityRepository(self._active())

    @property
    def dependencies(self) -> PostgresOpportunityDependencyRepository:
        return PostgresOpportunityDependencyRepository(self._active())

    @property
    def artifacts(self) -> OpportunityArtifactRepository:
        return cast(OpportunityArtifactRepository, PostgresTargetArtifactRepository(self._active()))

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
            _raise_commit_error(exc)
        self._committed = True

    def __exit__(
        self, exception_type: type[BaseException] | None, exception: BaseException | None, traceback: TracebackType | None
    ) -> None:
        replacement = _replacement(exception)
        if self._connection is not None and not self._committed:
            self._connection.rollback()
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._scope = None
        self._connection = None
        if replacement is not None:
            raise replacement from exception


class PostgresOpportunityUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> OpportunityUnitOfWork:
        return cast(OpportunityUnitOfWork, PostgresOpportunityUnitOfWork(self._pool))


def _replacement(exception: BaseException | None) -> BaseException | None:
    if not isinstance(exception, psycopg.Error) or exception.sqlstate is None:
        return None
    if exception.sqlstate in {"40001", "40P01"}:
        return DecisionRetryableTransactionError(exception.sqlstate)
    if exception.sqlstate.startswith(("22", "23")) or exception.sqlstate == "55000":
        return DecisionAuthorityIntegrityError("PostgreSQL rejected Opportunity invariants")
    return None


def _raise_commit_error(exc: psycopg.Error) -> None:
    replacement = _replacement(exc)
    if replacement is not None:
        raise replacement from exc
    if isinstance(exc, psycopg.OperationalError):
        raise DecisionCommitOutcomeUnknownError("PostgreSQL acknowledgement was lost during Opportunity commit") from exc
    raise exc


__all__ = ["PostgresOpportunityUnitOfWork", "PostgresOpportunityUnitOfWorkProvider"]
