"""Immutable evidence for an all-or-nothing SQLite-to-PostgreSQL import."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping
from uuid import uuid4

from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import parse_utc_second


MIGRATION_REPORT_SCHEMA = "sqlite-to-postgres-migration-report-v1"
REPORT_FILE = "migration-report.json"
CHECKSUM_FILE = "SHA256SUMS"


@dataclass(frozen=True, slots=True)
class MigrationReport:
    report_id: str
    content_hash: str
    manifest_hash: str
    created_at: datetime
    code_revision: str
    postgres_server_version: str
    postgres_schema: str
    applied_migrations: tuple[tuple[int, str, str], ...]
    sources: tuple[tuple[str, str, str], ...]
    tables: tuple[tuple[str, int, int, str, str, str | None, str | None], ...]
    sequence_repairs: tuple[tuple[str, str, int, bool], ...]
    source_row_count: int
    target_row_count: int
    result: str = "PASS"
    schema_version: str = MIGRATION_REPORT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != MIGRATION_REPORT_SCHEMA:
            raise ValueError("unsupported migration report schema")
        require_text("report_id", self.report_id)
        require_sha256("content_hash", self.content_hash)
        require_sha256("manifest_hash", self.manifest_hash)
        if self.result != "PASS":
            raise ValueError("only successful imports can publish a report")
        for label, value in (
            ("code_revision", self.code_revision),
            ("postgres_server_version", self.postgres_server_version),
            ("postgres_schema", self.postgres_schema),
        ):
            require_text(label, value)
        if self.source_row_count < 0 or self.target_row_count < 0:
            raise ValueError("migration report row counts cannot be negative")
        if self.source_row_count != self.target_row_count:
            raise ValueError("migration report source and target totals differ")
        migration_versions = tuple(item[0] for item in self.applied_migrations)
        if migration_versions != tuple(range(1, len(migration_versions) + 1)):
            raise ValueError("migration report versions must be contiguous")
        if any(
            len(checksum) != 64
            or any(character not in "0123456789abcdef" for character in checksum)
            for _, _, checksum in self.applied_migrations
        ):
            raise ValueError("migration report migration checksum is invalid")
        source_names = tuple(item[0] for item in self.sources)
        if source_names != tuple(sorted(set(source_names))):
            raise ValueError("migration report sources must be unique and sorted")
        for _, file_hash, schema_hash in self.sources:
            require_sha256("source file hash", file_hash)
            require_sha256("source schema hash", schema_hash)
        table_names = tuple(item[0] for item in self.tables)
        if table_names != tuple(sorted(set(table_names))):
            raise ValueError("migration report tables must be unique and sorted")
        for (
            _,
            source_count,
            target_count,
            source_digest,
            target_digest,
            primary_key_min,
            primary_key_max,
        ) in self.tables:
            if source_count < 0 or source_count != target_count:
                raise ValueError("migration report table counts differ")
            require_sha256("source table digest", source_digest)
            require_sha256("target table digest", target_digest)
            if source_digest != target_digest:
                raise ValueError("migration report table digests differ")
            if (primary_key_min is None) != (primary_key_max is None):
                raise ValueError("migration report primary-key range is incomplete")
            if source_count == 0 and primary_key_min is not None:
                raise ValueError("empty migration table cannot have a primary-key range")
            if source_count > 0 and primary_key_min is None:
                raise ValueError("non-empty migration table needs a primary-key range")
        if self.content_hash != canonical_hash(self.semantic_payload()):
            raise ValueError("migration report content hash mismatch")
        expected_id = f"postgres-migration-{self.content_hash.split(':', 1)[1][:24]}"
        if self.report_id != expected_id:
            raise ValueError("migration report identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        manifest_hash: str,
        created_at: datetime,
        code_revision: str,
        postgres_server_version: str,
        postgres_schema: str,
        applied_migrations: tuple[tuple[int, str, str], ...],
        sources: tuple[tuple[str, str, str], ...],
        tables: tuple[
            tuple[str, int, int, str, str, str | None, str | None], ...
        ],
        sequence_repairs: tuple[tuple[str, str, int, bool], ...],
    ) -> MigrationReport:
        source_total = sum(row[1] for row in tables)
        target_total = sum(row[2] for row in tables)
        values: dict[str, Any] = {
            "manifest_hash": manifest_hash,
            "created_at": created_at,
            "code_revision": code_revision,
            "postgres_server_version": postgres_server_version,
            "postgres_schema": postgres_schema,
            "applied_migrations": applied_migrations,
            "sources": sources,
            "tables": tables,
            "sequence_repairs": sequence_repairs,
            "source_row_count": source_total,
            "target_row_count": target_total,
            "result": "PASS",
            "schema_version": MIGRATION_REPORT_SCHEMA,
        }
        digest = canonical_hash(_semantic_payload(**values))
        return cls(
            report_id=f"postgres-migration-{digest.split(':', 1)[1][:24]}",
            content_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _semantic_payload(
            manifest_hash=self.manifest_hash,
            created_at=self.created_at,
            code_revision=self.code_revision,
            postgres_server_version=self.postgres_server_version,
            postgres_schema=self.postgres_schema,
            applied_migrations=self.applied_migrations,
            sources=self.sources,
            tables=self.tables,
            sequence_repairs=self.sequence_repairs,
            source_row_count=self.source_row_count,
            target_row_count=self.target_row_count,
            result=self.result,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "report_id": self.report_id,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> MigrationReport:
        expected = {
            "schema_version",
            "report_id",
            "content_hash",
            "manifest_hash",
            "created_at",
            "code_revision",
            "postgres_server_version",
            "postgres_schema",
            "applied_migrations",
            "sources",
            "tables",
            "sequence_repairs",
            "source_row_count",
            "target_row_count",
            "result",
        }
        if set(payload) != expected:
            raise ValueError("migration report fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            report_id=str(payload["report_id"]),
            content_hash=str(payload["content_hash"]),
            manifest_hash=str(payload["manifest_hash"]),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            code_revision=str(payload["code_revision"]),
            postgres_server_version=str(payload["postgres_server_version"]),
            postgres_schema=str(payload["postgres_schema"]),
            applied_migrations=tuple(
                (int(item["version"]), str(item["name"]), str(item["checksum"]))
                for item in _object_array(payload["applied_migrations"], "applied_migrations")
            ),
            sources=tuple(
                (str(item["name"]), str(item["file_hash"]), str(item["schema_hash"]))
                for item in _object_array(payload["sources"], "sources")
            ),
            tables=tuple(
                (
                    str(item["table"]),
                    int(item["source_count"]),
                    int(item["target_count"]),
                    str(item["source_digest"]),
                    str(item["target_digest"]),
                    (
                        str(item["primary_key_min"])
                        if item["primary_key_min"] is not None
                        else None
                    ),
                    (
                        str(item["primary_key_max"])
                        if item["primary_key_max"] is not None
                        else None
                    ),
                )
                for item in _object_array(payload["tables"], "tables")
            ),
            sequence_repairs=tuple(
                (
                    str(item["table"]),
                    str(item["column"]),
                    int(item["value"]),
                    bool(item["is_called"]),
                )
                for item in _object_array(payload["sequence_repairs"], "sequence_repairs")
            ),
            source_row_count=int(payload["source_row_count"]),
            target_row_count=int(payload["target_row_count"]),
            result=str(payload["result"]),
        )


class MigrationReportPublisher:
    def publish(self, report: MigrationReport, output_root: Path) -> Path:
        root = output_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        destination = root / report.report_id
        if destination.exists():
            if MigrationReportReader().read(destination) != report:
                raise ValueError("migration report identity collision")
            return destination
        temporary = root / f".{report.report_id}.{uuid4().hex}.tmp"
        temporary.mkdir()
        try:
            report_path = temporary / REPORT_FILE
            report_path.write_text(
                canonical_json(report.to_canonical_dict()) + "\n",
                encoding="utf-8",
            )
            digest = sha256(report_path.read_bytes()).hexdigest()
            (temporary / CHECKSUM_FILE).write_text(
                f"{digest}  {REPORT_FILE}\n",
                encoding="utf-8",
            )
            os.rename(temporary, destination)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return destination


class MigrationReportReader:
    def read(self, path: Path) -> MigrationReport:
        root = path.resolve()
        if not root.is_dir():
            raise ValueError("migration report path must be a directory")
        names = {item.name for item in root.iterdir()}
        if names != {REPORT_FILE, CHECKSUM_FILE}:
            raise ValueError("migration report file set mismatch")
        checksum_line = (root / CHECKSUM_FILE).read_text(encoding="utf-8")
        parts = checksum_line.rstrip("\n").split("  ", 1)
        if len(parts) != 2 or parts[1] != REPORT_FILE:
            raise ValueError("migration report checksum manifest is invalid")
        actual = sha256((root / REPORT_FILE).read_bytes()).hexdigest()
        if parts[0] != actual:
            raise ValueError("migration report checksum mismatch")
        payload = json.loads((root / REPORT_FILE).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("migration report payload must be an object")
        report = MigrationReport.from_canonical_dict(payload)
        if root.name != report.report_id:
            raise ValueError("migration report directory identity mismatch")
        return report


def _semantic_payload(
    *,
    manifest_hash: str,
    created_at: datetime,
    code_revision: str,
    postgres_server_version: str,
    postgres_schema: str,
    applied_migrations: tuple[tuple[int, str, str], ...],
    sources: tuple[tuple[str, str, str], ...],
    tables: tuple[
        tuple[str, int, int, str, str, str | None, str | None], ...
    ],
    sequence_repairs: tuple[tuple[str, str, int, bool], ...],
    source_row_count: int,
    target_row_count: int,
    result: str,
    schema_version: str,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "manifest_hash": manifest_hash,
        "created_at": canonical_datetime(created_at),
        "code_revision": code_revision,
        "postgres_server_version": postgres_server_version,
        "postgres_schema": postgres_schema,
        "applied_migrations": [
            {"version": version, "name": name, "checksum": checksum}
            for version, name, checksum in applied_migrations
        ],
        "sources": [
            {"name": name, "file_hash": file_hash, "schema_hash": schema_hash}
            for name, file_hash, schema_hash in sources
        ],
        "tables": [
            {
                "table": table,
                "source_count": source_count,
                "target_count": target_count,
                "source_digest": source_digest,
                "target_digest": target_digest,
                "primary_key_min": primary_key_min,
                "primary_key_max": primary_key_max,
            }
            for (
                table,
                source_count,
                target_count,
                source_digest,
                target_digest,
                primary_key_min,
                primary_key_max,
            ) in tables
        ],
        "sequence_repairs": [
            {
                "table": table,
                "column": column,
                "value": value,
                "is_called": is_called,
            }
            for table, column, value, is_called in sequence_repairs
        ],
        "source_row_count": source_row_count,
        "target_row_count": target_row_count,
        "result": result,
    }


def _object_array(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"migration report {label} must be an object array")
    return tuple(value)


__all__ = [
    "CHECKSUM_FILE",
    "MIGRATION_REPORT_SCHEMA",
    "REPORT_FILE",
    "MigrationReport",
    "MigrationReportPublisher",
    "MigrationReportReader",
]
