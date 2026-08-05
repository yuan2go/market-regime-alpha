"""Strict manifest for read-only SQLite authority imports."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.persistence.postgres.schema import (
    EXPECTED_AUTHORITY_TABLES,
)


SQLITE_MIGRATION_MANIFEST_SCHEMA = "sqlite-to-postgres-migration-manifest-v1"
POSTGRES_METADATA_TABLES = frozenset(
    {"schema_migrations", "runtime_database_bindings"}
)
SUPPORTED_IMPORT_TABLES = EXPECTED_AUTHORITY_TABLES - POSTGRES_METADATA_TABLES
_SQL_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class SQLiteMigrationSource:
    name: str
    path: Path
    expected_file_hash: str | None
    expected_schema_hash: str
    tables: tuple[str, ...]
    quiescent: bool

    def __post_init__(self) -> None:
        require_text("SQLite migration source name", self.name)
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ValueError("SQLite migration source path must be absolute")
        if not self.path.is_file():
            raise ValueError(f"SQLite migration source is missing: {self.path}")
        if self.expected_file_hash is not None:
            require_sha256("expected_file_hash", self.expected_file_hash)
        require_sha256("expected_schema_hash", self.expected_schema_hash)
        if not self.quiescent:
            raise ValueError("SQLite migration source must be declared quiescent")
        if not self.tables or self.tables != tuple(sorted(set(self.tables))):
            raise ValueError("SQLite migration source tables must be non-empty and sorted")
        unsupported = set(self.tables) - SUPPORTED_IMPORT_TABLES
        if unsupported:
            raise ValueError(f"unsupported SQLite authority tables: {sorted(unsupported)}")
        _assert_quiescent(self.path)
        actual_file_hash = sqlite_file_hash(self.path)
        if (
            self.expected_file_hash is not None
            and actual_file_hash != self.expected_file_hash
        ):
            raise ValueError(f"SQLite migration source hash mismatch: {self.name}")
        actual_schema_hash = sqlite_schema_hash(self.path, self.tables)
        if actual_schema_hash != self.expected_schema_hash:
            raise ValueError(f"SQLite migration source schema mismatch: {self.name}")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "expected_file_hash": self.expected_file_hash,
            "expected_schema_hash": self.expected_schema_hash,
            "tables": list(self.tables),
            "quiescent": self.quiescent,
        }


@dataclass(frozen=True, slots=True)
class SQLiteMigrationManifest:
    schema_version: str
    sources: tuple[SQLiteMigrationSource, ...]
    content_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != SQLITE_MIGRATION_MANIFEST_SCHEMA:
            raise ValueError("unsupported SQLite migration manifest schema")
        require_sha256("manifest content_hash", self.content_hash)
        names = tuple(item.name for item in self.sources)
        if names != tuple(sorted(set(names))):
            raise ValueError("SQLite migration source names must be unique and sorted")
        tables = tuple(table for source in self.sources for table in source.tables)
        if len(tables) != len(set(tables)):
            raise ValueError("SQLite authority table ownership must be unique")
        if self.content_hash != canonical_hash(self.semantic_payload()):
            raise ValueError("SQLite migration manifest content hash mismatch")

    @classmethod
    def create(
        cls,
        sources: tuple[SQLiteMigrationSource, ...],
    ) -> SQLiteMigrationManifest:
        ordered = tuple(sorted(sources, key=lambda item: item.name))
        payload = {
            "schema_version": SQLITE_MIGRATION_MANIFEST_SCHEMA,
            "sources": [item.to_canonical_dict() for item in ordered],
        }
        return cls(
            schema_version=SQLITE_MIGRATION_MANIFEST_SCHEMA,
            sources=ordered,
            content_hash=canonical_hash(payload),
        )

    @classmethod
    def from_json(cls, path: Path) -> SQLiteMigrationManifest:
        payload = _object(json.loads(path.read_text(encoding="utf-8")), "manifest")
        if set(payload) != {"schema_version", "sources", "content_hash"}:
            raise ValueError("SQLite migration manifest fields mismatch")
        raw_sources = payload["sources"]
        if not isinstance(raw_sources, list):
            raise ValueError("SQLite migration manifest sources must be an array")
        sources = tuple(_source(item) for item in raw_sources)
        return cls(
            schema_version=str(payload["schema_version"]),
            sources=sources,
            content_hash=str(payload["content_hash"]),
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sources": [item.to_canonical_dict() for item in self.sources],
        }

    def to_canonical_dict(self) -> dict[str, object]:
        return {**self.semantic_payload(), "content_hash": self.content_hash}


def sqlite_file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sqlite_schema_hash(path: Path, tables: tuple[str, ...]) -> str:
    if not tables or tables != tuple(sorted(set(tables))):
        raise ValueError("schema hash tables must be non-empty and sorted")
    for table in tables:
        if table not in SUPPORTED_IMPORT_TABLES or not _SQL_IDENTIFIER.fullmatch(table):
            raise ValueError(f"unsupported SQLite authority table: {table}")
    connection = _read_only_connection(path)
    try:
        payload: dict[str, object] = {}
        for table in tables:
            columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            if not columns:
                raise ValueError(f"SQLite authority table is missing: {table}")
            foreign_keys = connection.execute(
                f'PRAGMA foreign_key_list("{table}")'
            ).fetchall()
            payload[table] = {
                "columns": [list(row) for row in columns],
                "foreign_keys": [list(row) for row in foreign_keys],
            }
        return canonical_hash(payload)
    finally:
        connection.close()


def _source(value: object) -> SQLiteMigrationSource:
    payload = _object(value, "source")
    if set(payload) != {
        "name",
        "path",
        "expected_file_hash",
        "expected_schema_hash",
        "tables",
        "quiescent",
    }:
        raise ValueError("SQLite migration source fields mismatch")
    raw_tables = payload["tables"]
    if not isinstance(raw_tables, list) or not all(
        isinstance(item, str) for item in raw_tables
    ):
        raise ValueError("SQLite migration source tables must be an array of strings")
    expected_file_hash = payload["expected_file_hash"]
    if expected_file_hash is not None and not isinstance(expected_file_hash, str):
        raise ValueError("expected_file_hash must be a string or null")
    if type(payload["quiescent"]) is not bool:
        raise ValueError("quiescent must be a bool")
    return SQLiteMigrationSource(
        name=str(payload["name"]),
        path=Path(str(payload["path"])),
        expected_file_hash=expected_file_hash,
        expected_schema_hash=str(payload["expected_schema_hash"]),
        tables=tuple(raw_tables),
        quiescent=payload["quiescent"],
    )


def _assert_quiescent(path: Path) -> None:
    for suffix in ("-wal", "-journal"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.exists() and sidecar.stat().st_size > 0:
            raise ValueError(f"SQLite migration source is not quiescent: {path}")


def _read_only_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"SQLite migration {label} must be an object")
    return value


__all__ = [
    "POSTGRES_METADATA_TABLES",
    "SQLITE_MIGRATION_MANIFEST_SCHEMA",
    "SUPPORTED_IMPORT_TABLES",
    "SQLiteMigrationManifest",
    "SQLiteMigrationSource",
    "sqlite_file_hash",
    "sqlite_schema_hash",
]
