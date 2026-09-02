"""One fence-first PostgreSQL transaction for Signal and Forecast."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, cast

import psycopg

from market_regime_alpha.decision_support.errors import (
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
    InferenceAuthorityIntegrityError,
)
from market_regime_alpha.decision_support.ports import InferenceUnitOfWork
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.decision_inference_inputs import (
    PostgresInferenceDependencyRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.decision_inference import (
    PostgresInferenceRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.model_forecasts import (
    PostgresModelForecastRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.target_artifacts import (
    PostgresTargetArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
)
from market_regime_alpha.infrastructure.postgres.runtime_finalization import (
    PostgresRuntimeCommandFinalization,
)


class PostgresInferenceUnitOfWork:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False

    def __enter__(self) -> PostgresInferenceUnitOfWork:
        if self._used:
            raise RuntimeError("PostgresInferenceUnitOfWork cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        return self

    def _active(self) -> psycopg.Connection[Any]:
        if self._connection is None:
            raise RuntimeError("PostgresInferenceUnitOfWork is not active")
        return self._connection

    @property
    def inference(self) -> PostgresInferenceRepository:
        return PostgresInferenceRepository(self._active())

    @property
    def dependencies(self) -> PostgresInferenceDependencyRepository:
        return PostgresInferenceDependencyRepository(self._active())

    @property
    def model_forecasts(self) -> PostgresModelForecastRepository:
        return PostgresModelForecastRepository(self._active())

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
        try:
            self._active().commit()
        except psycopg.Error as exc:
            _raise_commit_error(exc)
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
                replacement = InferenceAuthorityIntegrityError(
                    "PostgreSQL rejected Signal/Forecast invariants"
                )
        if self._connection is not None and not self._committed:
            self._connection.rollback()
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._scope = None
        self._connection = None
        if replacement is not None:
            raise replacement from exception


class PostgresInferenceUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> InferenceUnitOfWork:
        return cast(InferenceUnitOfWork, PostgresInferenceUnitOfWork(self._pool))


def _raise_commit_error(exc: psycopg.Error) -> None:
    if exc.sqlstate in {"40001", "40P01"}:
        raise DecisionRetryableTransactionError(str(exc.sqlstate)) from exc
    if exc.sqlstate is not None and (
        exc.sqlstate.startswith(("22", "23")) or exc.sqlstate == "55000"
    ):
        raise InferenceAuthorityIntegrityError(
            "PostgreSQL rejected Signal/Forecast invariants"
        ) from exc
    if isinstance(exc, psycopg.OperationalError):
        raise DecisionCommitOutcomeUnknownError(
            "PostgreSQL acknowledgement was lost during inference commit"
        ) from exc
    raise exc


__all__ = ["PostgresInferenceUnitOfWork", "PostgresInferenceUnitOfWorkProvider"]
