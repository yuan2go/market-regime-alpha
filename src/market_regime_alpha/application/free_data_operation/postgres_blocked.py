"""PostgreSQL terminal projection for immutable free-data blocked evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from market_regime_alpha.application.free_data_operation.blocked import (
    FreeDataBlockedArtifact,
    load_free_data_blocked,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    verify_postgres_authority_schema,
)


@dataclass(frozen=True, slots=True)
class FreeDataBlockedProjection:
    artifact: FreeDataBlockedArtifact
    locator: Path


class PostgresFreeDataBlockedRepository:
    """Append one terminal Artifact reference under its operation binding."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        PostgresMigrator().verify_current(factory)
        with factory.connection(read_only=True) as connection:
            verify_postgres_authority_schema(connection)

    def record(
        self,
        *,
        artifact: FreeDataBlockedArtifact,
        locator: Path,
    ) -> FreeDataBlockedProjection:
        resolved = locator.resolve()
        if load_free_data_blocked(resolved) != artifact:
            raise ValueError("blocked projection locator does not bind Artifact")

        def operation(connection: Any) -> FreeDataBlockedProjection:
            connection.execute(
                """
                INSERT INTO free_data_operation_blocked (
                    scope_type, command_hash, artifact_id, content_hash,
                    source_archive_id, source_manifest_id,
                    source_manifest_hash, provider_result_hash, locator,
                    reason_code, error_type, code_revision, created_at
                ) VALUES (
                    'FREE_DATA_OPERATION', %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (scope_type, command_hash) DO NOTHING
                """,
                (
                    artifact.command_hash,
                    str(artifact.artifact_id),
                    artifact.content_hash,
                    str(artifact.source_archive_id),
                    str(artifact.source_manifest_id),
                    artifact.source_manifest_hash,
                    artifact.provider_result_hash,
                    str(resolved),
                    artifact.reason_code,
                    artifact.error_type,
                    artifact.code_revision,
                    artifact.created_at,
                ),
            )
            row = connection.execute(
                """
                SELECT artifact_id, content_hash, source_archive_id,
                       source_manifest_id, source_manifest_hash,
                       provider_result_hash, locator, reason_code, error_type,
                       code_revision, created_at
                FROM free_data_operation_blocked
                WHERE scope_type = 'FREE_DATA_OPERATION' AND command_hash = %s
                """,
                (artifact.command_hash,),
            ).fetchone()
            if row is None:
                raise RuntimeError("free-data blocked projection write failed")
            stored = _projection(artifact.command_hash, row)
            if stored != FreeDataBlockedProjection(artifact, resolved):
                raise ValueError("free-data blocked projection identity conflict")
            return stored

        return self._factory.run_transaction(operation)

    def get(self, command_hash: str) -> FreeDataBlockedProjection | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT artifact_id, content_hash, source_archive_id,
                       source_manifest_id, source_manifest_hash,
                       provider_result_hash, locator, reason_code, error_type,
                       code_revision, created_at
                FROM free_data_operation_blocked
                WHERE scope_type = 'FREE_DATA_OPERATION' AND command_hash = %s
                """,
                (command_hash,),
            ).fetchone()
        return _projection(command_hash, row) if row is not None else None


def _projection(command_hash: str, row: Any) -> FreeDataBlockedProjection:
    artifact = FreeDataBlockedArtifact(
        artifact_id=ArtifactId(str(row[0])),
        content_hash=str(row[1]),
        command_hash=command_hash,
        source_archive_id=ArtifactId(str(row[2])),
        source_manifest_id=ArtifactId(str(row[3])),
        source_manifest_hash=str(row[4]),
        provider_result_hash=str(row[5]),
        reason_code=str(row[7]),
        error_type=str(row[8]),
        created_at=row[10] if isinstance(row[10], datetime) else datetime.fromisoformat(str(row[10])),
        code_revision=str(row[9]),
        limitations=(
            "BROKER_NOT_INVOKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_FILL_CREATED",
            "NO_ORDER_CREATED",
            "NO_POSITION_MUTATION",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
    )
    locator = Path(str(row[6])).resolve()
    if load_free_data_blocked(locator) != artifact:
        raise ValueError("stored blocked projection locator is invalid")
    return FreeDataBlockedProjection(artifact=artifact, locator=locator)


__all__ = [
    "FreeDataBlockedProjection",
    "PostgresFreeDataBlockedRepository",
]
