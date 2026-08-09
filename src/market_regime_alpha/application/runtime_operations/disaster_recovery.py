"""PostgreSQL plus immutable-Artifact backup and isolated restore verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable
from urllib.parse import SplitResult, urlsplit, urlunsplit
import uuid

import psycopg
from psycopg import sql

from market_regime_alpha.application.canonical_lifecycle._immutable_io import (
    publish_immutable_text,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.continuous_research.replay import (
    replay_continuous_research,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.schema import (
    EXPECTED_AUTHORITY_TABLES,
    verify_postgres_authority_schema,
)
from market_regime_alpha.persistence.settings import DatabaseSettings


_RESTORE_DATABASE = re.compile(r"^mra_restore_[0-9a-f]{16}$")


@dataclass(frozen=True, slots=True)
class ArtifactInventoryEntry:
    relative_path: str
    size_bytes: int
    sha256_hex: str

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256_hex,
        }


@dataclass(frozen=True, slots=True)
class ArtifactInventory:
    root_name: str
    entries: tuple[ArtifactInventoryEntry, ...]
    content_hash: str

    @classmethod
    def create(cls, root: Path) -> ArtifactInventory:
        if not root.is_dir():
            raise ValueError("Artifact root must be an existing directory")
        entries = tuple(
            ArtifactInventoryEntry(
                relative_path=path.relative_to(root).as_posix(),
                size_bytes=path.stat().st_size,
                sha256_hex=_file_sha256(path),
            )
            for path in sorted(value for value in root.rglob("*") if value.is_file())
        )
        digest = canonical_hash(
            {
                "schema_version": "artifact-inventory/v1",
                "entries": [item.to_canonical_dict() for item in entries],
            }
        )
        return cls(root_name=root.name, entries=entries, content_hash=digest)

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "root_name": self.root_name,
            "entries": [item.to_canonical_dict() for item in self.entries],
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class DisasterRecoveryVerification:
    verification_id: ArtifactId
    verification_hash: str
    source_schema: str
    migration_head: int
    database_archive_sha256: str
    source_artifacts: ArtifactInventory
    restored_artifacts: ArtifactInventory
    table_fingerprints: tuple[tuple[str, str], ...]
    continuous_replay_hashes: tuple[tuple[str, str], ...]
    verified_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "disaster-recovery-verification/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "disaster-recovery-verification/v1":
            raise ValueError("unsupported Disaster Recovery verification schema")
        require_sha256("verification_hash", self.verification_hash)
        if not re.fullmatch(r"[0-9a-f]{64}", self.database_archive_sha256):
            raise ValueError("database archive hash must be raw SHA-256 hex")
        if self.source_artifacts.content_hash != self.restored_artifacts.content_hash:
            raise ValueError("restored Artifact inventory differs from source")
        if self.table_fingerprints != tuple(sorted(set(self.table_fingerprints))):
            raise ValueError("table fingerprints must be unique and sorted")
        if self.continuous_replay_hashes != tuple(
            sorted(set(self.continuous_replay_hashes))
        ):
            raise ValueError("Continuous replay hashes must be unique and sorted")
        _aware("verified_at", self.verified_at)
        required = {
            "ENGINEERING_RECOVERY_ONLY",
            "NO_LIVE_OR_PROSPECTIVE_EVIDENCE",
            "RESTORED_DATABASE_DROPPED_AFTER_VERIFICATION",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Disaster Recovery authority ceiling is incomplete")
        if canonical_hash(self.semantic_payload()) != self.verification_hash:
            raise ValueError("Disaster Recovery verification hash mismatch")
        if self.verification_id != _content_id(
            "disaster-recovery-verification", self.verification_hash
        ):
            raise ValueError("Disaster Recovery verification identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> DisasterRecoveryVerification:
        normalized = dict(values)
        normalized["table_fingerprints"] = tuple(
            sorted(set(values["table_fingerprints"]))
        )
        normalized["continuous_replay_hashes"] = tuple(
            sorted(set(values["continuous_replay_hashes"]))
        )
        normalized["limitations"] = tuple(sorted(set(values["limitations"])))
        digest = canonical_hash(_verification_payload(**normalized))
        return cls(
            verification_id=_content_id("disaster-recovery-verification", digest),
            verification_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, object]:
        return _verification_payload(
            source_schema=self.source_schema,
            migration_head=self.migration_head,
            database_archive_sha256=self.database_archive_sha256,
            source_artifacts=self.source_artifacts,
            restored_artifacts=self.restored_artifacts,
            table_fingerprints=self.table_fingerprints,
            continuous_replay_hashes=self.continuous_replay_hashes,
            verified_at=self.verified_at,
            limitations=self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "verification_id": str(self.verification_id),
            "verification_hash": self.verification_hash,
            **self.semantic_payload(),
        }


def backup_restore_verify(
    *,
    source_factory: PostgresConnectionFactory,
    database_url: str,
    artifact_root: Path,
    backup_root: Path,
    verified_at: datetime,
    table_names: Iterable[str] = EXPECTED_AUTHORITY_TABLES,
) -> DisasterRecoveryVerification:
    """Create a backup, restore into a fresh database, and compare authorities."""

    if backup_root.exists():
        raise ValueError("backup_root must not already exist")
    _aware("verified_at", verified_at)
    selected_tables = tuple(sorted(set(table_names)))
    if not selected_tables or not set(selected_tables).issubset(
        EXPECTED_AUTHORITY_TABLES
    ):
        raise ValueError("DR table selection must be a non-empty Authority subset")
    backup_root.mkdir(parents=True)
    archive_path = backup_root / "postgres.dump"
    copied_artifacts = backup_root / "artifacts"
    report_path = backup_root / "verification.json"
    source_inventory = ArtifactInventory.create(artifact_root)
    shutil.copytree(artifact_root, copied_artifacts)
    restored_inventory = ArtifactInventory.create(copied_artifacts)
    if source_inventory.content_hash != restored_inventory.content_hash:
        raise ValueError("Artifact copy inventory mismatch")

    _run_pg_tool(
        (
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            f"--schema={source_factory.application_schema}",
            f"--file={archive_path}",
            database_url,
        ),
        label="pg_dump",
    )
    archive_hash = _file_sha256(archive_path)
    source_fingerprints = _table_fingerprints(
        source_factory, selected_tables
    )
    source_replays = _continuous_replays(source_factory)
    restore_database = f"mra_restore_{uuid.uuid4().hex[:16]}"
    if not _RESTORE_DATABASE.fullmatch(restore_database):
        raise RuntimeError("generated restore database name is unsafe")
    admin_url = _database_url(database_url, "postgres")
    restored_url = _database_url(database_url, restore_database)
    restored_factory: PostgresConnectionFactory | None = None
    try:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(restore_database)
                )
            )
        _run_pg_tool(
            (
                "pg_restore",
                "--no-owner",
                "--no-privileges",
                f"--dbname={restored_url}",
                str(archive_path),
            ),
            label="pg_restore",
        )
        restored_factory = PostgresConnectionFactory(
            DatabaseSettings.from_sources(database_url=restored_url, environ={}),
            min_size=0,
            max_size=4,
            application_schema=source_factory.application_schema,
        )
        with restored_factory.connection(read_only=True) as connection:
            verify_postgres_authority_schema(connection)
            head_row = connection.execute(
                "SELECT max(version) FROM schema_migrations"
            ).fetchone()
        if head_row is None or head_row[0] is None:
            raise ValueError("restored database has no migration head")
        migration_head = int(head_row[0])
        restored_fingerprints = _table_fingerprints(
            restored_factory, selected_tables
        )
        if restored_fingerprints != source_fingerprints:
            raise ValueError("restored PostgreSQL Authority fingerprints differ")
        restored_replays = _continuous_replays(restored_factory)
        if restored_replays != source_replays:
            raise ValueError("restored Continuous Runtime replay hashes differ")
        verification = DisasterRecoveryVerification.create(
            source_schema=source_factory.application_schema,
            migration_head=migration_head,
            database_archive_sha256=archive_hash,
            source_artifacts=source_inventory,
            restored_artifacts=restored_inventory,
            table_fingerprints=source_fingerprints,
            continuous_replay_hashes=source_replays,
            verified_at=verified_at,
            limitations=(
                "ENGINEERING_RECOVERY_ONLY",
                "NO_LIVE_OR_PROSPECTIVE_EVIDENCE",
                "RESTORED_DATABASE_DROPPED_AFTER_VERIFICATION",
            ),
        )
        publish_immutable_text(
            path=report_path,
            payload=canonical_json(verification.to_canonical_dict()) + "\n",
            collision_message="Disaster Recovery verification identity conflict",
        )
        return verification
    finally:
        if restored_factory is not None:
            restored_factory.close()
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (restore_database,),
            )
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(restore_database)
                )
            )


def _table_fingerprints(
    factory: PostgresConnectionFactory,
    table_names: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    values: list[tuple[str, str]] = []
    with factory.connection(read_only=True) as connection:
        for table_name in table_names:
            rows = connection.execute(
                sql.SQL("SELECT to_jsonb(value)::text FROM {} AS value "
                        "ORDER BY to_jsonb(value)::text").format(
                    sql.Identifier(table_name)
                )
            ).fetchall()
            digest = sha256()
            for row in rows:
                digest.update(str(row[0]).encode("utf-8"))
                digest.update(b"\n")
            values.append(
                (
                    table_name,
                    canonical_hash(
                        {"row_count": len(rows), "rows_sha256": digest.hexdigest()}
                    ),
                )
            )
    return tuple(values)


def _continuous_replays(
    factory: PostgresConnectionFactory,
) -> tuple[tuple[str, str], ...]:
    with factory.connection(read_only=True) as connection:
        rows = connection.execute(
            "SELECT run_id FROM continuous_research_run ORDER BY run_id"
        ).fetchall()
    journal = PostgresContinuousResearchJournal(
        factory, apply_migrations=False
    )
    return tuple(
        (
            str(row[0]),
            replay_continuous_research(
                journal, ArtifactId(str(row[0]))
            ).replay_hash,
        )
        for row in rows
    )


def _database_url(value: str, database: str) -> str:
    parts = urlsplit(value)
    return urlunsplit(
        SplitResult(
            scheme=parts.scheme,
            netloc=parts.netloc,
            path=f"/{database}",
            query=parts.query,
            fragment=parts.fragment,
        )
    )


def _run_pg_tool(command: tuple[str, ...], *, label: str) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"{label} failed closed: {type(exc).__name__}") from exc


def _verification_payload(**values: Any) -> dict[str, object]:
    return {
        "schema_version": "disaster-recovery-verification/v1",
        "source_schema": values["source_schema"],
        "migration_head": values["migration_head"],
        "database_archive_sha256": values["database_archive_sha256"],
        "source_artifacts": values["source_artifacts"].to_canonical_dict(),
        "restored_artifacts": values["restored_artifacts"].to_canonical_dict(),
        "table_fingerprints": [
            {"table": table, "content_hash": digest}
            for table, digest in values["table_fingerprints"]
        ],
        "continuous_replay_hashes": [
            {"run_id": run_id, "replay_hash": digest}
            for run_id, digest in values["continuous_replay_hashes"]
        ],
        "verified_at": canonical_datetime(values["verified_at"]),
        "limitations": list(values["limitations"]),
    }


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _content_id(prefix: str, digest: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{digest.split(':', 1)[1][:24]}")


__all__ = [
    "ArtifactInventory",
    "ArtifactInventoryEntry",
    "DisasterRecoveryVerification",
    "backup_restore_verify",
]
