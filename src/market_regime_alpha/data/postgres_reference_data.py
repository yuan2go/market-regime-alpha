"""PostgreSQL publication index and historical Reader for reference snapshots."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.reference_data import (
    ETFThemeReferenceSnapshot,
    load_reference_snapshot,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class ReferenceDataConflict(ValueError):
    """Reference identity, lineage, time or Artifact conflict."""


class ReferenceDataIntegrityError(ValueError):
    """Stored Reference Snapshot failed canonical restoration."""


class PostgresETFThemeReferenceRepository:
    """Append-only index; content-addressed Artifact remains the fact payload."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be PostgresConnectionFactory")
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def publish(
        self,
        snapshot: ETFThemeReferenceSnapshot,
        *,
        artifact_path: Path,
    ) -> ETFThemeReferenceSnapshot:
        if artifact_path.name != f"{snapshot.snapshot_id}.json":
            raise ReferenceDataConflict("Reference Artifact is not content-addressed")
        if load_reference_snapshot(artifact_path) != snapshot:
            raise ReferenceDataConflict("Reference Artifact does not match Snapshot")

        def operation(connection: Any) -> None:
            existing = connection.execute(
                "SELECT snapshot_hash, artifact_locator "
                "FROM etf_theme_reference_snapshot WHERE snapshot_id = %s",
                (str(snapshot.snapshot_id),),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) != snapshot.content_hash
                    or str(existing[1]) != str(artifact_path.resolve())
                ):
                    raise ReferenceDataConflict("Reference Snapshot identity conflict")
                return
            version = connection.execute(
                "SELECT snapshot_id, snapshot_hash "
                "FROM etf_theme_reference_snapshot WHERE reference_version = %s",
                (snapshot.reference_version,),
            ).fetchone()
            if version is not None:
                raise ReferenceDataConflict(
                    "Reference version already identifies another Snapshot"
                )
            connection.execute(
                """
                INSERT INTO etf_theme_reference_snapshot(
                    snapshot_id, snapshot_hash, reference_version,
                    data_eligibility, evidence_ceiling, available_at,
                    payload_json, artifact_locator, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(snapshot.snapshot_id),
                    snapshot.content_hash,
                    snapshot.reference_version,
                    snapshot.data_eligibility.value,
                    snapshot.evidence_ceiling.value,
                    snapshot.available_at,
                    Jsonb(snapshot.to_canonical_dict()),
                    str(artifact_path.resolve()),
                    snapshot.created_at,
                ),
            )

        self._factory.run_transaction(operation)
        return self.get(snapshot.snapshot_id)

    def get(self, snapshot_id: ArtifactId) -> ETFThemeReferenceSnapshot:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json, snapshot_hash, artifact_locator "
                "FROM etf_theme_reference_snapshot WHERE snapshot_id = %s",
                (str(snapshot_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(snapshot_id))
        return self._restore(row)

    def latest_as_of(
        self,
        *,
        effective_at: datetime,
        known_at: datetime,
    ) -> ETFThemeReferenceSnapshot:
        _aware("effective_at", effective_at)
        _aware("known_at", known_at)
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, snapshot_hash, artifact_locator
                FROM etf_theme_reference_snapshot
                WHERE available_at <= %s AND created_at <= %s
                ORDER BY available_at DESC, created_at DESC, snapshot_id DESC
                LIMIT 1
                """,
                (known_at, known_at),
            ).fetchone()
        if row is None:
            raise KeyError("no ETF/Theme Reference Snapshot was known at that time")
        snapshot = self._restore(row)
        records = (
            *snapshot.etfs,
            *snapshot.themes,
            *snapshot.memberships,
            *snapshot.mappings,
        )
        if not any(
            item.validity.effective_from <= effective_at
            and (
                item.validity.effective_to is None
                or effective_at < item.validity.effective_to
            )
            for item in records
        ):
            raise KeyError("Reference Snapshot has no effective facts at that time")
        return snapshot

    def replay(self, snapshot_id: ArtifactId) -> ETFThemeReferenceSnapshot:
        stored = self.get(snapshot_id)
        rebuilt = ETFThemeReferenceSnapshot.create(
            reference_version=stored.reference_version,
            etfs=stored.etfs,
            themes=stored.themes,
            memberships=stored.memberships,
            mappings=stored.mappings,
            data_eligibility=stored.data_eligibility,
            evidence_ceiling=stored.evidence_ceiling,
            created_at=stored.created_at,
            limitations=stored.limitations,
            schema_version=stored.schema_version,
        )
        if rebuilt != stored:
            raise ReferenceDataIntegrityError(
                "Reference Snapshot did not replay deterministically"
            )
        return rebuilt

    @staticmethod
    def _restore(row: Any) -> ETFThemeReferenceSnapshot:
        try:
            snapshot = ETFThemeReferenceSnapshot.from_canonical_dict(
                _json_object(row[0])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReferenceDataIntegrityError(
                "Reference Snapshot failed canonical restoration"
            ) from exc
        if snapshot.content_hash != str(row[1]):
            raise ReferenceDataIntegrityError("Reference owner hash drift")
        if load_reference_snapshot(Path(str(row[2]))) != snapshot:
            raise ReferenceDataIntegrityError("Reference Artifact drift")
        return snapshot


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ReferenceDataIntegrityError("stored Reference payload is not an object")
    return value


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


__all__ = [
    "PostgresETFThemeReferenceRepository",
    "ReferenceDataConflict",
    "ReferenceDataIntegrityError",
]
