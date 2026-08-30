"""Independent one-transaction Target registration unit of work."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.target_artifacts import (
    PostgresTargetArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.target_definitions import (
    PostgresTargetDefinitionRepository,
)
from market_regime_alpha.infrastructure.postgres.runtime_finalization import (
    PostgresRuntimeCommandFinalization,
)
from market_regime_alpha.research_qualification.ports.target_uow import (
    TargetUnitOfWork,
)
from market_regime_alpha.runtime.errors import RuntimeStateConflictError


class PostgresTargetUnitOfWork:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False
        self._target_definitions: PostgresTargetDefinitionRepository | None = None
        self._target_artifacts: PostgresTargetArtifactRepository | None = None
        self._receipts: PostgresCommandReceiptRepository | None = None
        self._audit: PostgresAuditRepository | None = None
        self._runtime_finalization: PostgresRuntimeCommandFinalization | None = None

    def __enter__(self) -> PostgresTargetUnitOfWork:
        if self._connection is not None or self._used:
            raise RuntimeError("PostgresTargetUnitOfWork cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        self._target_definitions = PostgresTargetDefinitionRepository(self._connection)
        self._target_artifacts = PostgresTargetArtifactRepository(self._connection)
        self._receipts = PostgresCommandReceiptRepository(self._connection)
        self._audit = PostgresAuditRepository(self._connection)
        self._runtime_finalization = PostgresRuntimeCommandFinalization(
            self._connection
        )
        return self

    @property
    def target_definitions(self) -> PostgresTargetDefinitionRepository:
        if self._target_definitions is None:
            raise RuntimeError("PostgresTargetUnitOfWork is not active")
        return self._target_definitions

    @property
    def target_artifacts(self) -> PostgresTargetArtifactRepository:
        if self._target_artifacts is None:
            raise RuntimeError("PostgresTargetUnitOfWork is not active")
        return self._target_artifacts

    @property
    def receipts(self) -> PostgresCommandReceiptRepository:
        if self._receipts is None:
            raise RuntimeError("PostgresTargetUnitOfWork is not active")
        return self._receipts

    @property
    def audit(self) -> PostgresAuditRepository:
        if self._audit is None:
            raise RuntimeError("PostgresTargetUnitOfWork is not active")
        return self._audit

    @property
    def runtime_finalization(self) -> PostgresRuntimeCommandFinalization:
        if self._runtime_finalization is None:
            raise RuntimeError("PostgresTargetUnitOfWork is not active")
        return self._runtime_finalization

    def commit(self) -> None:
        if self._connection is None:
            raise RuntimeError("PostgresTargetUnitOfWork is not active")
        if self._committed:
            raise RuntimeError("PostgresTargetUnitOfWork already committed")
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
            and (
                exception.sqlstate.startswith(("22", "23"))
                or exception.sqlstate in {"40001", "55000"}
            )
        )
        if self._connection is not None and not self._committed:
            self._connection.rollback()
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._scope = None
        self._connection = None
        self._target_definitions = None
        self._target_artifacts = None
        self._receipts = None
        self._audit = None
        self._runtime_finalization = None
        if deterministic_database_rejection:
            raise RuntimeStateConflictError(
                "PostgreSQL rejected the Target command's canonical invariants"
            ) from exception


class PostgresTargetUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> TargetUnitOfWork:
        return PostgresTargetUnitOfWork(self._pool)


__all__ = ["PostgresTargetUnitOfWork", "PostgresTargetUnitOfWorkProvider"]
