from __future__ import annotations

from importlib import resources
from pathlib import Path
import sqlite3

import pytest

from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleJournalIntegrityError,
)


MIGRATION_PACKAGE = "market_regime_alpha.application.canonical_lifecycle.migrations"


def _migration(name: str) -> str:
    return resources.files(MIGRATION_PACKAGE).joinpath(name).read_text(encoding="utf-8")


def _migration_010_baseline(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE pdl_schema_migrations(
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE pre_011_authority(
                authority_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            INSERT INTO pre_011_authority VALUES ('kept', 'migration-010-data');
            """
        )
        connection.executemany(
            "INSERT INTO pdl_schema_migrations(version, applied_at) VALUES (?, ?)",
            ((version, f"migration-{version}") for version in range(2, 11)),
        )


def _unique_signatures(
    connection: sqlite3.Connection, table: str
) -> set[tuple[str, ...]]:
    signatures: set[tuple[str, ...]] = set()
    for row in connection.execute(f"PRAGMA index_list({table})"):
        if int(row[2]) != 1:
            continue
        name = str(row[1]).replace("'", "''")
        signatures.add(
            tuple(
                str(item[2])
                for item in connection.execute(f"PRAGMA index_info('{name}')")
            )
        )
    return signatures


def test_migration_011_is_packaged_repeat_safe_and_preserves_002_through_010(
    tmp_path: Path,
) -> None:
    path = tmp_path / "migration.sqlite3"
    _migration_010_baseline(path)
    up = _migration("011_canonical_lifecycle_runtime_up.sql")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(up)
        connection.executescript(up)
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "lifecycle_runs",
            "lifecycle_stages",
            "lifecycle_attempts",
            "lifecycle_stage_receipts",
            "lifecycle_events",
        } <= tables
        assert connection.execute(
            "SELECT payload FROM pre_011_authority WHERE authority_id = 'kept'"
        ).fetchone() == ("migration-010-data",)
        assert connection.execute(
            "SELECT version FROM pdl_schema_migrations ORDER BY version"
        ).fetchall() == [(version,) for version in range(2, 12)]
        assert connection.execute(
            "SELECT COUNT(*) FROM pdl_schema_migrations WHERE version = 11"
        ).fetchone() == (1,)


def test_migration_011_has_required_unique_indexes_fks_checks_and_triggers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "schema.sqlite3"
    _migration_010_baseline(path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(_migration("011_canonical_lifecycle_runtime_up.sql"))
        assert {("idempotency_key",)} <= _unique_signatures(
            connection, "lifecycle_runs"
        )
        assert {("run_id", "stage_name")} <= _unique_signatures(
            connection, "lifecycle_stages"
        )
        assert {
            ("run_id", "stage_name", "attempt_number"),
            ("attempt_id", "run_id", "stage_name"),
        } <= _unique_signatures(connection, "lifecycle_attempts")
        assert {
            ("run_id", "stage_name", "receipt_hash"),
            ("receipt_id", "run_id", "stage_name"),
        } <= _unique_signatures(connection, "lifecycle_stage_receipts")
        assert {("run_id", "sequence_number")} <= _unique_signatures(
            connection, "lifecycle_events"
        )
        event_fks = connection.execute(
            "PRAGMA foreign_key_list(lifecycle_events)"
        ).fetchall()
        assert {str(row[2]) for row in event_fks} == {
            "lifecycle_runs",
            "lifecycle_stages",
            "lifecycle_attempts",
            "lifecycle_stage_receipts",
        }
        trigger_names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        assert {
            "lifecycle_attempts_no_delete",
            "lifecycle_attempts_terminal_immutable",
            "lifecycle_attempts_completion_only",
            "lifecycle_stage_receipts_no_update",
            "lifecycle_stage_receipts_no_delete",
            "lifecycle_events_no_update",
            "lifecycle_events_no_delete",
            "lifecycle_terminal_stages_immutable",
            "lifecycle_stages_no_delete",
            "lifecycle_runs_no_delete",
            "lifecycle_runs_identity_immutable",
        } <= trigger_names
        run_sql = str(
            connection.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'lifecycle_runs'"
            ).fetchone()[0]
        )
        assert "version > 0" in run_sql
        assert "claim_token >= 0" in run_sql
        assert "length(command_hash) = 71" in run_sql


def test_migration_011_down_is_isolated_from_002_through_010(tmp_path: Path) -> None:
    path = tmp_path / "down.sqlite3"
    _migration_010_baseline(path)
    with sqlite3.connect(path) as connection:
        connection.executescript(_migration("011_canonical_lifecycle_runtime_up.sql"))
        connection.executescript(_migration("011_canonical_lifecycle_runtime_down.sql"))
        assert connection.execute(
            "SELECT version FROM pdl_schema_migrations ORDER BY version"
        ).fetchall() == [(version,) for version in range(2, 11)]
        assert connection.execute(
            "SELECT payload FROM pre_011_authority"
        ).fetchall() == [("migration-010-data",)]
        lifecycle_tables = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name LIKE 'lifecycle_%'
            """
        ).fetchall()
        assert lifecycle_tables == []


def test_repository_rejects_spoofed_marker_with_weak_schema(tmp_path: Path) -> None:
    path = tmp_path / "weak.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE pdl_schema_migrations(
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT INTO pdl_schema_migrations VALUES (11, 'spoofed');
            CREATE TABLE lifecycle_runs(run_id TEXT PRIMARY KEY);
            """
        )
    with pytest.raises(LifecycleJournalIntegrityError):
        SQLiteLifecycleRunRepository(path)


def test_migration_resources_exist_at_stable_package_paths() -> None:
    package = resources.files(MIGRATION_PACKAGE)
    assert package.joinpath("011_canonical_lifecycle_runtime_up.sql").is_file()
    assert package.joinpath("011_canonical_lifecycle_runtime_down.sql").is_file()
