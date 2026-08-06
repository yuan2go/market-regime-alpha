"""All-or-nothing import from quiescent SQLite authorities into PostgreSQL."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from typing import Any

import psycopg
from psycopg import sql

from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_json
from market_regime_alpha.persistence.migration_manifest import (
    SUPPORTED_IMPORT_TABLES,
    SQLiteMigrationManifest,
    SQLiteMigrationSource,
    sqlite_file_hash,
    sqlite_schema_hash,
)
from market_regime_alpha.persistence.migration_report import (
    MigrationReport,
    MigrationReportPublisher,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    EXPECTED_AUTHORITY_TABLES,
    verify_postgres_authority_schema,
)
from market_regime_alpha.persistence.settings import DatabaseSettings


FaultInjector = Callable[[str], None]
Clock = Callable[[], datetime]


class SQLiteToPostgresMigrationError(RuntimeError):
    """Raised when import evidence cannot prove an exact safe migration."""


@dataclass(frozen=True, slots=True)
class PlannedSQLiteSource:
    source: SQLiteMigrationSource
    file_hash: str
    schema_hash: str


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    manifest: SQLiteMigrationManifest
    settings: DatabaseSettings
    sources: tuple[PlannedSQLiteSource, ...]


@dataclass(frozen=True, slots=True)
class _Column:
    name: str
    data_type: str
    udt_name: str


@dataclass(frozen=True, slots=True)
class _TableShape:
    table: str
    columns: tuple[_Column, ...]
    primary_key: tuple[str, ...]


class SQLiteToPostgresMigrator:
    def __init__(
        self,
        *,
        postgres_factory: PostgresConnectionFactory | None = None,
        clock: Clock | None = None,
        code_revision: str | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self._factory = postgres_factory
        self._clock = clock or _utc_now
        self._code_revision = code_revision or _git_revision()
        self._fault_injector = fault_injector

    def plan(
        self,
        manifest: SQLiteMigrationManifest,
        settings: DatabaseSettings,
    ) -> MigrationPlan:
        planned = tuple(
            PlannedSQLiteSource(
                source=source,
                file_hash=sqlite_file_hash(source.path),
                schema_hash=sqlite_schema_hash(source.path, source.tables),
            )
            for source in manifest.sources
        )
        for item in planned:
            if (
                item.source.expected_file_hash is not None
                and item.file_hash != item.source.expected_file_hash
            ):
                raise SQLiteToPostgresMigrationError(
                    f"SQLite source changed before planning: {item.source.name}"
                )
            if item.schema_hash != item.source.expected_schema_hash:
                raise SQLiteToPostgresMigrationError(
                    f"SQLite schema changed before planning: {item.source.name}"
                )
        return MigrationPlan(manifest=manifest, settings=settings, sources=planned)

    def execute(self, plan: MigrationPlan, output_root: Path) -> MigrationReport:
        owns_factory = self._factory is None
        factory = self._factory or PostgresConnectionFactory(plan.settings)
        try:
            PostgresMigrator().apply_all(factory)
            with ExitStack() as stack:
                sources = {
                    item.source.name: stack.enter_context(
                        _sqlite_snapshot(item.source.path)
                    )
                    for item in plan.sources
                }
                self._verify_source_snapshots(plan)
                with factory.connection() as connection:
                    verify_postgres_authority_schema(connection)
                    with connection.transaction():
                        self._require_empty_target(connection)
                        self._inject("after_target_empty_check")
                        selected = {
                            table: item
                            for item in plan.sources
                            for table in item.source.tables
                        }
                        shapes = {
                            table: _postgres_table_shape(connection, table)
                            for table in selected
                        }
                        ordered = _dependency_order(connection, tuple(selected))
                        evidence: list[
                            tuple[
                                str,
                                int,
                                int,
                                str,
                                str,
                                str | None,
                                str | None,
                            ]
                        ] = []
                        for table in ordered:
                            planned_source = selected[table]
                            source_connection = sources[planned_source.source.name]
                            shape = shapes[table]
                            _verify_sqlite_columns(source_connection, shape)
                            (
                                source_count,
                                source_digest,
                                source_min,
                                source_max,
                            ) = _sqlite_table_evidence(
                                source_connection,
                                shape,
                            )
                            _copy_table(
                                source_connection,
                                connection,
                                shape,
                            )
                            self._inject(f"after_copy:{table}")
                            (
                                target_count,
                                target_digest,
                                target_min,
                                target_max,
                            ) = _postgres_table_evidence(
                                connection,
                                shape,
                            )
                            if (
                                source_count != target_count
                                or source_digest != target_digest
                                or source_min != target_min
                                or source_max != target_max
                            ):
                                raise SQLiteToPostgresMigrationError(
                                    f"SQLite/PostgreSQL table parity mismatch: {table}"
                                )
                            evidence.append(
                                (
                                    table,
                                    source_count,
                                    target_count,
                                    source_digest,
                                    target_digest,
                                    source_min,
                                    source_max,
                                )
                            )
                        sequence_repairs = _repair_identity_sequences(
                            connection,
                            tuple(selected),
                        )
                        _validate_canonical_json(connection, tuple(selected))
                        self._verify_source_snapshots(plan)
                        report = self._build_report(
                            connection=connection,
                            plan=plan,
                            table_evidence=tuple(sorted(evidence)),
                            sequence_repairs=sequence_repairs,
                        )
                        self._inject("before_commit")
            MigrationReportPublisher().publish(report, output_root)
            return report
        except SQLiteToPostgresMigrationError:
            raise
        except Exception as exc:
            raise SQLiteToPostgresMigrationError(
                f"SQLite-to-PostgreSQL import failed: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            if owns_factory:
                factory.close()

    def _verify_source_snapshots(self, plan: MigrationPlan) -> None:
        for item in plan.sources:
            if sqlite_file_hash(item.source.path) != item.file_hash:
                raise SQLiteToPostgresMigrationError(
                    f"SQLite source changed during import: {item.source.name}"
                )
            if sqlite_schema_hash(item.source.path, item.source.tables) != item.schema_hash:
                raise SQLiteToPostgresMigrationError(
                    f"SQLite schema changed during import: {item.source.name}"
                )

    def _require_empty_target(self, connection: psycopg.Connection[Any]) -> None:
        business_tables = sorted(EXPECTED_AUTHORITY_TABLES - {"schema_migrations"})
        non_empty = []
        for table in business_tables:
            row = connection.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
            ).fetchone()
            assert row is not None
            if int(row[0]) != 0:
                non_empty.append(table)
        if non_empty:
            raise SQLiteToPostgresMigrationError(
                f"PostgreSQL import target is not empty: {non_empty}"
            )

    def _build_report(
        self,
        *,
        connection: psycopg.Connection[Any],
        plan: MigrationPlan,
        table_evidence: tuple[
            tuple[str, int, int, str, str, str | None, str | None], ...
        ],
        sequence_repairs: tuple[tuple[str, str, int, bool], ...],
    ) -> MigrationReport:
        migration_rows = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        version_row = connection.execute("SHOW server_version").fetchone()
        assert version_row is not None
        schema_row = connection.execute("SELECT current_schema()").fetchone()
        assert schema_row is not None
        return MigrationReport.create(
            manifest_hash=plan.manifest.content_hash,
            created_at=self._clock(),
            code_revision=self._code_revision,
            postgres_server_version=str(version_row[0]),
            postgres_schema=str(schema_row[0]),
            applied_migrations=tuple(
                (int(row[0]), str(row[1]), str(row[2]))
                for row in migration_rows
            ),
            sources=tuple(
                (item.source.name, item.file_hash, item.schema_hash)
                for item in plan.sources
            ),
            tables=table_evidence,
            sequence_repairs=sequence_repairs,
        )

    def _inject(self, seam: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(seam)


def _postgres_table_shape(
    connection: psycopg.Connection[Any],
    table: str,
) -> _TableShape:
    if table not in SUPPORTED_IMPORT_TABLES:
        raise SQLiteToPostgresMigrationError(f"unsupported import table: {table}")
    columns = connection.execute(
        """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    primary_key = connection.execute(
        """
        SELECT attribute.attname
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN unnest(constraint_record.conkey) WITH ORDINALITY
          AS key(attnum, ordinality) ON true
        JOIN pg_catalog.pg_attribute AS attribute
          ON attribute.attrelid = constraint_record.conrelid
         AND attribute.attnum = key.attnum
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = current_schema()
          AND relation.relname = %s
          AND constraint_record.contype = 'p'
        ORDER BY key.ordinality
        """,
        (table,),
    ).fetchall()
    if not columns or not primary_key:
        raise SQLiteToPostgresMigrationError(
            f"PostgreSQL import table shape is incomplete: {table}"
        )
    return _TableShape(
        table=table,
        columns=tuple(_Column(str(row[0]), str(row[1]), str(row[2])) for row in columns),
        primary_key=tuple(str(row[0]) for row in primary_key),
    )


def _verify_sqlite_columns(
    connection: sqlite3.Connection,
    shape: _TableShape,
) -> None:
    rows = connection.execute(f'PRAGMA table_info("{shape.table}")').fetchall()
    actual = tuple(str(row[1]) for row in rows)
    expected = tuple(item.name for item in shape.columns)
    if set(actual) != set(expected):
        raise SQLiteToPostgresMigrationError(
            f"SQLite/PostgreSQL columns differ for {shape.table}"
        )


def _copy_table(
    source: sqlite3.Connection,
    target: psycopg.Connection[Any],
    shape: _TableShape,
) -> None:
    column_names = tuple(item.name for item in shape.columns)
    select_sql = _sqlite_select(shape.table, column_names, shape.primary_key)
    copy_sql = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(shape.table),
        sql.SQL(", ").join(sql.Identifier(item) for item in column_names),
    )
    with target.cursor().copy(copy_sql) as copy:
        for row in source.execute(select_sql):
            copy.write_row(
                tuple(
                    _copy_value(value, column)
                    for value, column in zip(row, shape.columns, strict=True)
                )
            )


def _sqlite_table_evidence(
    connection: sqlite3.Connection,
    shape: _TableShape,
) -> tuple[int, str, str | None, str | None]:
    columns = tuple(item.name for item in shape.columns)
    return _row_evidence(
        connection.execute(_sqlite_select(shape.table, columns, shape.primary_key)),
        shape.columns,
        shape.primary_key,
    )


def _postgres_table_evidence(
    connection: psycopg.Connection[Any],
    shape: _TableShape,
) -> tuple[int, str, str | None, str | None]:
    query = sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
        sql.SQL(", ").join(sql.Identifier(item.name) for item in shape.columns),
        sql.Identifier(shape.table),
        sql.SQL(", ").join(sql.Identifier(item) for item in shape.primary_key),
    )
    return _row_evidence(connection.execute(query), shape.columns, shape.primary_key)


def _row_evidence(
    rows: Iterable[Iterable[object]],
    columns: tuple[_Column, ...],
    primary_key: tuple[str, ...] | None = None,
) -> tuple[int, str, str | None, str | None]:
    digest = sha256()
    count = 0
    first_key: str | None = None
    last_key: str | None = None
    key_indexes = (
        tuple(
            next(index for index, column in enumerate(columns) if column.name == name)
            for name in primary_key
        )
        if primary_key is not None
        else ()
    )
    for row in rows:
        values = tuple(row)
        encoded = {
            "values": [
                _typed_value(value, column)
                for value, column in zip(values, columns, strict=True)
            ]
        }
        digest.update(canonical_json(encoded).encode("utf-8"))
        digest.update(b"\n")
        if key_indexes:
            key = canonical_json(
                {
                    "values": [
                        _typed_value(values[index], columns[index])
                        for index in key_indexes
                    ]
                }
            )
            first_key = first_key or key
            last_key = key
        count += 1
    return count, f"sha256:{digest.hexdigest()}", first_key, last_key


def _typed_value(value: object, column: _Column) -> dict[str, object]:
    if value is None:
        return {"type": "null", "value": None}
    normalized: object
    if column.data_type == "boolean":
        normalized = _boolean(value)
    elif column.data_type in {"smallint", "integer", "bigint"}:
        normalized = int(str(value))
    elif column.data_type in {"numeric", "decimal"}:
        normalized = format(Decimal(str(value)), "f")
    elif column.data_type in {"real", "double precision"}:
        normalized = repr(float(str(value)))
    elif column.data_type == "date":
        normalized = value.isoformat() if isinstance(value, date) else str(value)
    elif column.data_type == "timestamp with time zone":
        instant = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        )
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SQLiteToPostgresMigrationError(
                f"naive timestamp in {column.name}"
            )
        normalized = canonical_datetime(instant)
    elif column.data_type == "bytea":
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise SQLiteToPostgresMigrationError(
                f"invalid bytea value in {column.name}"
            )
        normalized = bytes(value).hex()
    else:
        normalized = str(value)
    return {"type": column.udt_name, "value": normalized}


def _copy_value(value: object, column: _Column) -> object:
    if value is None:
        return None
    if column.data_type == "boolean":
        return _boolean(value)
    if column.data_type == "timestamp with time zone":
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if column.data_type == "date" and not isinstance(value, date):
        return date.fromisoformat(str(value))
    return value


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str) and value.lower() in {"0", "false"}:
        return False
    if isinstance(value, str) and value.lower() in {"1", "true"}:
        return True
    raise SQLiteToPostgresMigrationError("invalid boolean value in SQLite source")


def _dependency_order(
    connection: psycopg.Connection[Any],
    tables: tuple[str, ...],
) -> tuple[str, ...]:
    selected = set(tables)
    rows = connection.execute(
        """
        SELECT child.relname, parent.relname
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS child
          ON child.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_class AS parent
          ON parent.oid = constraint_record.confrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = child.relnamespace
        WHERE namespace.nspname = current_schema()
          AND constraint_record.contype = 'f'
        """
    ).fetchall()
    dependencies: dict[str, set[str]] = {table: set() for table in selected}
    for child, parent in rows:
        child_name, parent_name = str(child), str(parent)
        if child_name in selected and parent_name in selected and child_name != parent_name:
            dependencies[child_name].add(parent_name)
    result: list[str] = []
    while dependencies:
        ready = sorted(table for table, deps in dependencies.items() if not deps)
        if not ready:
            raise SQLiteToPostgresMigrationError(
                f"cyclic PostgreSQL import dependencies: {sorted(dependencies)}"
            )
        for table in ready:
            result.append(table)
            dependencies.pop(table)
        for deps in dependencies.values():
            deps.difference_update(ready)
    return tuple(result)


def _repair_identity_sequences(
    connection: psycopg.Connection[Any],
    tables: tuple[str, ...],
) -> tuple[tuple[str, str, int, bool], ...]:
    repairs = []
    for table in sorted(tables):
        rows = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND is_identity = 'YES'
            ORDER BY ordinal_position
            """,
            (table,),
        ).fetchall()
        for row in rows:
            column = str(row[0])
            maximum = connection.execute(
                sql.SQL("SELECT max({}), count(*) FROM {}").format(
                    sql.Identifier(column),
                    sql.Identifier(table),
                )
            ).fetchone()
            assert maximum is not None
            is_called = int(maximum[1]) > 0
            value = int(maximum[0]) if is_called else 1
            schema = connection.execute("SELECT current_schema()").fetchone()
            assert schema is not None
            sequence = connection.execute(
                "SELECT pg_get_serial_sequence(%s, %s)",
                (f'{schema[0]}.{table}', column),
            ).fetchone()
            if sequence is None or sequence[0] is None:
                raise SQLiteToPostgresMigrationError(
                    f"identity sequence is missing: {table}.{column}"
                )
            connection.execute(
                "SELECT setval(%s::regclass, %s, %s)",
                (str(sequence[0]), value, is_called),
            )
            repairs.append((table, column, value, is_called))
    return tuple(repairs)


def _validate_canonical_json(
    connection: psycopg.Connection[Any],
    tables: tuple[str, ...],
) -> None:
    for table in sorted(tables):
        columns = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name LIKE '%%json'
            ORDER BY ordinal_position
            """,
            (table,),
        ).fetchall()
        for row in columns:
            column = str(row[0])
            values = connection.execute(
                sql.SQL("SELECT {} FROM {} WHERE {} IS NOT NULL").format(
                    sql.Identifier(column),
                    sql.Identifier(table),
                    sql.Identifier(column),
                )
            )
            for value_row in values:
                raw = str(value_row[0])
                payload = json.loads(raw)
                if not isinstance(payload, dict) or canonical_json(payload) != raw:
                    raise SQLiteToPostgresMigrationError(
                        f"non-canonical JSON in {table}.{column}"
                    )


def _sqlite_select(
    table: str,
    columns: tuple[str, ...],
    order_by: tuple[str, ...],
) -> str:
    quoted_columns = ", ".join(f'"{item}"' for item in columns)
    quoted_order = ", ".join(f'"{item}"' for item in order_by)
    return f'SELECT {quoted_columns} FROM "{table}" ORDER BY {quoted_order}'


class _SQLiteSnapshot:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"{self._path.resolve().as_uri()}?mode=ro",
            uri=True,
        )
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        self._connection = connection
        return connection

    def __exit__(self, *_: object) -> None:
        assert self._connection is not None
        self._connection.rollback()
        self._connection.close()


def _sqlite_snapshot(path: Path) -> _SQLiteSnapshot:
    return _SQLiteSnapshot(path)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _git_revision() -> str:
    configured = os.getenv("GITHUB_SHA")
    if configured:
        return configured
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


__all__ = [
    "MigrationPlan",
    "PlannedSQLiteSource",
    "SQLiteToPostgresMigrationError",
    "SQLiteToPostgresMigrator",
]
