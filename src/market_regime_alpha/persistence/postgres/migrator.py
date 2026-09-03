"""Checksummed, serialized PostgreSQL authority migrations."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files
import re
from typing import Any, Final

import psycopg

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


MIGRATION_LOCK_KEY: Final[int] = 4_852_410_017
_BUSINESS_LOCK_TIMEOUT: Final[str] = "5s"
_MIGRATION_LOCK_TIMEOUT: Final[str] = "30s"
_MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{3})_(?P<name>[a-z0-9_]+)\.sql$")


class PostgresMigrationError(RuntimeError):
    """Base class for migration governance failures."""


class PostgresMigrationSequenceError(PostgresMigrationError):
    """Raised when packaged migrations are missing or reordered."""


class PostgresMigrationChecksumError(PostgresMigrationError):
    """Raised when an applied migration differs from packaged authority."""


@dataclass(frozen=True)
class PostgresMigration:
    version: int
    name: str
    checksum: str
    sql: str

    @classmethod
    def create(cls, version: int, name: str, sql_text: str) -> PostgresMigration:
        if isinstance(version, bool) or version <= 0:
            raise ValueError("migration version must be positive")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError("migration name must be lowercase snake case")
        if not isinstance(sql_text, str) or not sql_text.strip():
            raise ValueError("migration SQL must be non-empty")
        return cls(
            version=version,
            name=name,
            checksum=sha256(sql_text.encode("utf-8")).hexdigest(),
            sql=sql_text,
        )


@dataclass(frozen=True)
class AppliedMigration:
    version: int
    name: str
    checksum: str


def load_packaged_migrations() -> tuple[PostgresMigration, ...]:
    root = files("market_regime_alpha.persistence.postgres").joinpath("migrations")
    migrations: list[PostgresMigration] = []
    for resource in sorted(root.iterdir(), key=lambda item: item.name):
        match = _MIGRATION_NAME.fullmatch(resource.name)
        if match is None:
            continue
        version = int(match.group("version"))
        migrations.append(
            PostgresMigration.create(
                version,
                match.group("name"),
                resource.read_text(encoding="utf-8"),
            )
        )
    return tuple(migrations)


class PostgresMigrator:
    def __init__(
        self,
        *,
        migrations: tuple[PostgresMigration, ...] | None = None,
    ) -> None:
        self.migrations = (
            load_packaged_migrations() if migrations is None else migrations
        )
        expected = tuple(range(1, len(self.migrations) + 1))
        actual = tuple(item.version for item in self.migrations)
        if actual != expected:
            raise PostgresMigrationSequenceError(
                f"PostgreSQL migrations must be contiguous from 1: {actual}"
            )
        if len({item.name for item in self.migrations}) != len(self.migrations):
            raise PostgresMigrationSequenceError(
                "PostgreSQL migration names must be unique"
            )

    def apply_all(
        self,
        factory: PostgresConnectionFactory,
    ) -> tuple[AppliedMigration, ...]:
        newly_applied: list[AppliedMigration] = []
        with factory.connection() as connection:
            connection.execute(
                "SELECT set_config('lock_timeout', %s, false)",
                (_MIGRATION_LOCK_TIMEOUT,),
            )
            connection.commit()
            try:
                connection.execute(
                    "SELECT pg_advisory_lock(%s)",
                    (MIGRATION_LOCK_KEY,),
                )
                connection.commit()
                _ensure_registry(connection)
                applied = _load_registry(connection)
                connection.commit()
                _verify_applied(applied, self.migrations)
                for migration in self.migrations:
                    if migration.version in applied:
                        continue
                    with connection.transaction():
                        connection.execute(migration.sql, prepare=False)
                        connection.execute(
                            """
                            INSERT INTO schema_migrations(
                                version, name, checksum, applied_at
                            ) VALUES (%s, %s, %s, now())
                            """,
                            (
                                migration.version,
                                migration.name,
                                migration.checksum,
                            ),
                        )
                    newly_applied.append(
                        AppliedMigration(
                            version=migration.version,
                            name=migration.name,
                            checksum=migration.checksum,
                        )
                    )
            finally:
                if connection.info.transaction_status != 0:
                    connection.rollback()
                connection.execute(
                    "SELECT pg_advisory_unlock(%s)",
                    (MIGRATION_LOCK_KEY,),
                )
                connection.execute(
                    "SELECT set_config('lock_timeout', %s, false)",
                    (_BUSINESS_LOCK_TIMEOUT,),
                )
                connection.commit()
        return tuple(newly_applied)

    def verify_current(
        self,
        factory: PostgresConnectionFactory,
    ) -> tuple[AppliedMigration, ...]:
        """Verify the immutable registry without creating or changing schema."""

        with factory.connection(read_only=True) as connection:
            registry = connection.execute(
                "SELECT to_regclass('schema_migrations')"
            ).fetchone()
            if registry is None or registry[0] is None:
                raise PostgresMigrationSequenceError(
                    "PostgreSQL schema_migrations registry is missing; "
                    "run the explicit migration operator"
                )
            applied = _load_registry(connection)
        _verify_applied(applied, self.migrations)
        missing = sorted({item.version for item in self.migrations} - set(applied))
        if missing:
            raise PostgresMigrationSequenceError(
                f"database is behind packaged migration head; missing versions: {missing}"
            )
        return tuple(applied[version] for version in sorted(applied))


def _ensure_registry(connection: psycopg.Connection[Any]) -> None:
    with connection.transaction():
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version integer PRIMARY KEY CHECK (version > 0),
                name text NOT NULL UNIQUE,
                checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
                applied_at timestamptz NOT NULL
            )
            """
        )


def _load_registry(
    connection: psycopg.Connection[Any],
) -> dict[int, AppliedMigration]:
    rows = connection.execute(
        "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {
        int(row[0]): AppliedMigration(
            version=int(row[0]),
            name=str(row[1]),
            checksum=str(row[2]),
        )
        for row in rows
    }


def _verify_applied(
    applied: dict[int, AppliedMigration],
    packaged: tuple[PostgresMigration, ...],
) -> None:
    expected_by_version = {item.version: item for item in packaged}
    unknown = sorted(set(applied) - set(expected_by_version))
    if unknown:
        raise PostgresMigrationSequenceError(
            f"database contains unknown migration versions: {unknown}"
        )
    for version, stored in applied.items():
        expected = expected_by_version[version]
        if stored.name != expected.name or stored.checksum != expected.checksum:
            raise PostgresMigrationChecksumError(
                f"migration {version:03d} name or checksum drift"
            )
