"""One short PostgreSQL transaction for Partition and member closure."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, Callable
from uuid import UUID

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.research_partition_inputs import (
    PostgresPartitionInputQueries,
)
from market_regime_alpha.infrastructure.postgres.repositories.research_partitions import (
    PostgresResearchPartitionRepository,
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
from market_regime_alpha.research_qualification.ports.partition_uow import PartitionUnitOfWork
from market_regime_alpha.runtime.errors import RuntimeStateConflictError


class PostgresPartitionUnitOfWork:
    def __init__(self, pool: TargetPostgresPool, *, id_factory: Callable[[], UUID]) -> None:
        self._pool = pool
        self._id_factory = id_factory
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False

    def __enter__(self) -> PostgresPartitionUnitOfWork:
        if self._used:
            raise RuntimeError("PostgresPartitionUnitOfWork cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        return self

    def _active(self) -> psycopg.Connection[Any]:
        if self._connection is None:
            raise RuntimeError("PostgresPartitionUnitOfWork is not active")
        return self._connection

    @property
    def inputs(self) -> PostgresPartitionInputQueries:
        return PostgresPartitionInputQueries(self._active())

    @property
    def partitions(self) -> PostgresResearchPartitionRepository:
        return PostgresResearchPartitionRepository(self._active(), id_factory=self._id_factory)

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
            raise RuntimeStateConflictError("PostgreSQL rejected ResearchPartition invariants") from exception


class PostgresPartitionUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool, *, id_factory: Callable[[], UUID]) -> None:
        self._pool = pool
        self._id_factory = id_factory

    def __call__(self) -> PartitionUnitOfWork:
        return PostgresPartitionUnitOfWork(self._pool, id_factory=self._id_factory)


__all__ = ["PostgresPartitionUnitOfWork", "PostgresPartitionUnitOfWorkProvider"]
