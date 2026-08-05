"""PostgreSQL discovery index for Controlled operation packages."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Callable, Iterable, cast

from market_regime_alpha.application.controlled_operation.evidence_package import (
    load_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.longitudinal_index import (
    SQLiteLongitudinalOperationalIndex,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.dbapi import (
    PostgresDBAPIConnection,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    verify_postgres_authority_schema,
)


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class PostgresLongitudinalOperationalIndex(SQLiteLongitudinalOperationalIndex):
    """Append-only PostgreSQL index; packages remain evidence authority."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be a PostgresConnectionFactory")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._postgres_factory = factory
        self._clock = clock
        PostgresMigrator().apply_all(factory)
        with factory.connection(read_only=True) as connection:
            verify_postgres_authority_schema(connection)

    @classmethod
    def rebuild(
        cls,
        *,
        path: Path | None = None,
        packages: Iterable[tuple[Path, str]],
        clock: Clock = _utc_now,
        factory: PostgresConnectionFactory | None = None,
    ) -> PostgresLongitudinalOperationalIndex:
        if path is not None:
            raise ValueError("PostgreSQL rebuild does not accept a SQLite path")
        if factory is None:
            raise TypeError("factory must be a PostgresConnectionFactory")
        index = cls(factory, clock=clock)
        if index.query():
            raise FileExistsError("PostgreSQL Longitudinal rebuild target is not empty")
        for package_path, locator in packages:
            index.append(
                package=load_controlled_operation_package(package_path),
                package_locator=locator,
            )
        return index

    def _connect(self) -> sqlite3.Connection:
        bridge = PostgresDBAPIConnection.acquire(self._postgres_factory)
        return cast(sqlite3.Connection, bridge)


__all__ = ["PostgresLongitudinalOperationalIndex"]
