"""Narrow one-transaction Market/PIT unit of work."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from types import TracebackType
from typing import Any

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories import (
    PostgresArtifactRepository,
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
    PostgresMarketRepository,
    PostgresRuntimeRepository,
)
from market_regime_alpha.market.ports import MarketUnitOfWork
from market_regime_alpha.runtime.errors import RuntimeStateConflictError
from market_regime_alpha.runtime.ports import AttemptClaim


class PostgresMarketRuntimeFinalization:
    """Expose only live-fence validation and terminal Step mutation to Market."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._runtime = PostgresRuntimeRepository(connection)

    def lock_live(self, claim: AttemptClaim) -> None:
        self._runtime.lock_live_claim(claim)

    def succeed(
        self,
        claim: AttemptClaim,
        *,
        receipt_id,
        result_hash: str,
    ) -> tuple[int, int]:
        return self._runtime.succeed_attempt(
            claim,
            receipt_id=receipt_id,
            result_hash=result_hash,
        )

    def fail(
        self,
        claim: AttemptClaim,
        *,
        receipt_id,
        error_class: str,
        error_code: str,
    ) -> tuple[str, int, int]:
        return self._runtime.fail_attempt(
            claim,
            receipt_id=receipt_id,
            error_class=error_class,
            error_code=error_code,
        )


class PostgresMarketUnitOfWork:
    """Market owner plus the minimum receipt/audit/Artifact/fence ports."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False
        self._market: PostgresMarketRepository | None = None
        self._artifacts: PostgresArtifactRepository | None = None
        self._receipts: PostgresCommandReceiptRepository | None = None
        self._audit: PostgresAuditRepository | None = None
        self._runtime_finalization: PostgresMarketRuntimeFinalization | None = None

    def __enter__(self) -> PostgresMarketUnitOfWork:
        if self._connection is not None or self._used:
            raise RuntimeError("PostgresMarketUnitOfWork cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        self._market = PostgresMarketRepository(self._connection)
        self._artifacts = PostgresArtifactRepository(self._connection)
        self._receipts = PostgresCommandReceiptRepository(self._connection)
        self._audit = PostgresAuditRepository(self._connection)
        self._runtime_finalization = PostgresMarketRuntimeFinalization(self._connection)
        return self

    @property
    def market(self) -> PostgresMarketRepository:
        if self._market is None:
            raise RuntimeError("PostgresMarketUnitOfWork is not active")
        return self._market

    @property
    def artifacts(self) -> PostgresArtifactRepository:
        if self._artifacts is None:
            raise RuntimeError("PostgresMarketUnitOfWork is not active")
        return self._artifacts

    @property
    def receipts(self) -> PostgresCommandReceiptRepository:
        if self._receipts is None:
            raise RuntimeError("PostgresMarketUnitOfWork is not active")
        return self._receipts

    @property
    def audit(self) -> PostgresAuditRepository:
        if self._audit is None:
            raise RuntimeError("PostgresMarketUnitOfWork is not active")
        return self._audit

    @property
    def runtime_finalization(self) -> PostgresMarketRuntimeFinalization:
        if self._runtime_finalization is None:
            raise RuntimeError("PostgresMarketUnitOfWork is not active")
        return self._runtime_finalization

    def commit(self) -> None:
        if self._connection is None:
            raise RuntimeError("PostgresMarketUnitOfWork is not active")
        if self._committed:
            raise RuntimeError("PostgresMarketUnitOfWork already committed")
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
                or exception.sqlstate == "55000"
            )
        )
        if self._connection is not None and not self._committed:
            self._connection.rollback()
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._scope = None
        self._connection = None
        self._market = None
        self._artifacts = None
        self._receipts = None
        self._audit = None
        self._runtime_finalization = None
        if deterministic_database_rejection:
            raise RuntimeStateConflictError(
                "PostgreSQL rejected the Market command's canonical invariants"
            ) from exception


class PostgresMarketUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> MarketUnitOfWork:
        return PostgresMarketUnitOfWork(self._pool)


class PostgresMarketDatabaseClock:
    """Read PostgreSQL acquisition time without spanning Provider or byte I/O."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def now(self) -> datetime:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise AssertionError("PostgreSQL clock query must return one row")
        return row[0]


__all__ = [
    "PostgresMarketRuntimeFinalization",
    "PostgresMarketDatabaseClock",
    "PostgresMarketUnitOfWork",
    "PostgresMarketUnitOfWorkProvider",
]
