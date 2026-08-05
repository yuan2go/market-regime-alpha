from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3

import pytest

from market_regime_alpha.persistence.migration_manifest import (
    SQLiteMigrationManifest,
    SQLiteMigrationSource,
    sqlite_file_hash,
    sqlite_schema_hash,
)
from market_regime_alpha.persistence.migration_report import MigrationReportReader
from market_regime_alpha.persistence.settings import DatabaseSettings
from market_regime_alpha.persistence.sqlite_to_postgres import (
    SQLiteToPostgresMigrationError,
    SQLiteToPostgresMigrator,
)
from tests.persistence.postgres.conftest import TEST_DATABASE_URL_ENV


def _settings() -> DatabaseSettings:
    return DatabaseSettings.from_sources(
        database_url=os.environ[TEST_DATABASE_URL_ENV],
        sqlite_path=None,
        environ={},
    )


def _source(tmp_path: Path) -> SQLiteMigrationSource:
    path = tmp_path / "governance.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE governance_commands (
                idempotency_key TEXT PRIMARY KEY,
                aggregate_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                result_version INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO governance_commands VALUES (?, ?, ?, ?, ?, ?)",
            (
                "import-1",
                "MODEL",
                "model-1",
                "sha256:" + "a" * 64,
                3,
                "2026-08-05T04:00:00Z",
            ),
        )
    tables = ("governance_commands",)
    return SQLiteMigrationSource(
        name="governance",
        path=path.resolve(),
        expected_file_hash=sqlite_file_hash(path),
        expected_schema_hash=sqlite_schema_hash(path, tables),
        tables=tables,
        quiescent=True,
    )


def _identity_source(tmp_path: Path) -> SQLiteMigrationSource:
    path = tmp_path / "feature.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE feature_materialization_run (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                schema_version TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                command_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO feature_materialization_run VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                7,
                "feature-materialization-run-v2",
                "import-feature-7",
                "sha256:" + "7" * 64,
                "RUNNING",
                1,
                "2026-08-05T04:00:00Z",
                "2026-08-05T04:00:00Z",
            ),
        )
    tables = ("feature_materialization_run",)
    return SQLiteMigrationSource(
        name="feature",
        path=path.resolve(),
        expected_file_hash=sqlite_file_hash(path),
        expected_schema_hash=sqlite_schema_hash(path, tables),
        tables=tables,
        quiescent=True,
    )


def test_schema_only_zero_to_zero_import_publishes_verified_report(
    postgres_factory,
    tmp_path: Path,
) -> None:
    migrator = SQLiteToPostgresMigrator(
        postgres_factory=postgres_factory,
        clock=lambda: datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
        code_revision="b" * 40,
    )
    plan = migrator.plan(SQLiteMigrationManifest.create(()), _settings())

    report = migrator.execute(plan, tmp_path / "reports")

    assert report.source_row_count == report.target_row_count == 0
    assert report.tables == ()
    assert len(report.applied_migrations) == 18
    assert MigrationReportReader().read(
        tmp_path / "reports" / report.report_id
    ) == report


def test_fixture_import_compares_digest_and_rejects_nonempty_target(
    postgres_factory,
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    migrator = SQLiteToPostgresMigrator(
        postgres_factory=postgres_factory,
        code_revision="c" * 40,
    )
    plan = migrator.plan(SQLiteMigrationManifest.create((source,)), _settings())

    report = migrator.execute(plan, tmp_path / "reports")

    assert report.source_row_count == report.target_row_count == 1
    assert report.tables[0][0] == "governance_commands"
    assert report.tables[0][3] == report.tables[0][4]
    with postgres_factory.connection(read_only=True) as connection:
        row = connection.execute(
            "SELECT idempotency_key, result_version FROM governance_commands"
        ).fetchone()
    assert row == ("import-1", 3)
    with pytest.raises(SQLiteToPostgresMigrationError, match="not empty"):
        migrator.execute(plan, tmp_path / "second-report")


def test_injected_fault_rolls_back_every_imported_row_and_report(
    postgres_factory,
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)

    def fail_after_copy(seam: str) -> None:
        if seam == "after_copy:governance_commands":
            raise RuntimeError("injected migration fault")

    migrator = SQLiteToPostgresMigrator(
        postgres_factory=postgres_factory,
        code_revision="d" * 40,
        fault_injector=fail_after_copy,
    )
    plan = migrator.plan(SQLiteMigrationManifest.create((source,)), _settings())

    with pytest.raises(SQLiteToPostgresMigrationError, match="injected"):
        migrator.execute(plan, tmp_path / "reports")

    with postgres_factory.connection(read_only=True) as connection:
        count = connection.execute(
            "SELECT count(*) FROM governance_commands"
        ).fetchone()
    assert count == (0,)
    assert not (tmp_path / "reports").exists()


def test_import_repairs_identity_sequence_after_explicit_ids(
    postgres_factory,
    tmp_path: Path,
) -> None:
    source = _identity_source(tmp_path)
    migrator = SQLiteToPostgresMigrator(
        postgres_factory=postgres_factory,
        code_revision="e" * 40,
    )
    plan = migrator.plan(SQLiteMigrationManifest.create((source,)), _settings())

    report = migrator.execute(plan, tmp_path / "reports")

    assert report.sequence_repairs == (
        ("feature_materialization_run", "run_id", 7, True),
    )
    with postgres_factory.connection() as connection:
        row = connection.execute(
            """
            INSERT INTO feature_materialization_run(
                schema_version, idempotency_key, command_hash, status,
                version, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING run_id
            """,
            (
                "feature-materialization-run-v2",
                "after-import",
                "sha256:" + "8" * 64,
                "RUNNING",
                1,
                "2026-08-05T05:00:00Z",
                "2026-08-05T05:00:00Z",
            ),
        ).fetchone()
    assert row == (8,)
