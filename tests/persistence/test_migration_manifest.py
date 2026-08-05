from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from market_regime_alpha.evidence.canonical import canonical_json
from market_regime_alpha.persistence.migration_manifest import (
    SQLITE_MIGRATION_MANIFEST_SCHEMA,
    SQLiteMigrationManifest,
    SQLiteMigrationSource,
    sqlite_file_hash,
    sqlite_schema_hash,
)


def _source(path: Path, *, name: str = "governance") -> SQLiteMigrationSource:
    tables = ("governance_commands",)
    return SQLiteMigrationSource(
        name=name,
        path=path.resolve(),
        expected_file_hash=sqlite_file_hash(path),
        expected_schema_hash=sqlite_schema_hash(path, tables),
        tables=tables,
        quiescent=True,
    )


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "source.sqlite3"
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
    return path


def test_manifest_round_trip_and_empty_schema_only_manifest(tmp_path: Path) -> None:
    source = _source(_database(tmp_path))
    manifest = SQLiteMigrationManifest.create((source,))
    path = tmp_path / "manifest.json"
    path.write_text(canonical_json(manifest.to_canonical_dict()), encoding="utf-8")

    assert SQLiteMigrationManifest.from_json(path) == manifest
    assert SQLiteMigrationManifest.create(()).sources == ()


def test_manifest_rejects_relative_missing_duplicate_and_unknown_sources(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    source = _source(database)
    with pytest.raises(ValueError, match="absolute"):
        SQLiteMigrationSource(
            name="relative",
            path=Path("source.sqlite3"),
            expected_file_hash=None,
            expected_schema_hash=source.expected_schema_hash,
            tables=source.tables,
            quiescent=True,
        )
    with pytest.raises(ValueError, match="missing"):
        SQLiteMigrationSource(
            name="missing",
            path=(tmp_path / "missing.sqlite3").resolve(),
            expected_file_hash=None,
            expected_schema_hash=source.expected_schema_hash,
            tables=source.tables,
            quiescent=True,
        )
    with pytest.raises(ValueError, match="names"):
        SQLiteMigrationManifest.create((source, source))
    other = _source(database, name="other")
    with pytest.raises(ValueError, match="ownership"):
        SQLiteMigrationManifest.create((source, other))
    with pytest.raises(ValueError, match="unsupported"):
        SQLiteMigrationSource(
            name="unknown",
            path=database.resolve(),
            expected_file_hash=None,
            expected_schema_hash=source.expected_schema_hash,
            tables=("unknown_table",),
            quiescent=True,
        )


def test_manifest_rejects_hash_schema_and_quiescence_mismatch(tmp_path: Path) -> None:
    database = _database(tmp_path)
    source = _source(database)
    with pytest.raises(ValueError, match="hash mismatch"):
        SQLiteMigrationSource(
            name="changed",
            path=database.resolve(),
            expected_file_hash="sha256:" + "0" * 64,
            expected_schema_hash=source.expected_schema_hash,
            tables=source.tables,
            quiescent=True,
        )
    with pytest.raises(ValueError, match="schema mismatch"):
        SQLiteMigrationSource(
            name="schema",
            path=database.resolve(),
            expected_file_hash=None,
            expected_schema_hash="sha256:" + "0" * 64,
            tables=source.tables,
            quiescent=True,
        )
    with pytest.raises(ValueError, match="quiescent"):
        SQLiteMigrationSource(
            name="live",
            path=database.resolve(),
            expected_file_hash=None,
            expected_schema_hash=source.expected_schema_hash,
            tables=source.tables,
            quiescent=False,
        )


def test_manifest_json_requires_exact_versioned_fields(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": SQLITE_MIGRATION_MANIFEST_SCHEMA,
                "sources": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fields mismatch"):
        SQLiteMigrationManifest.from_json(path)
