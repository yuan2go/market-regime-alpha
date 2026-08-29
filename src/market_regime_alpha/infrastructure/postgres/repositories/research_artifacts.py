"""Research-facing exact Artifact metadata and verification adapter."""

from typing import Any

import psycopg

from market_regime_alpha.infrastructure.postgres.repositories.artifacts import (
    PostgresArtifactRepository,
)
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
)
from market_regime_alpha.runtime.ports import ArtifactRecord


class PostgresResearchArtifactRepository(PostgresArtifactRepository):
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        super().__init__(connection)
        self._research_connection = connection

    def require_exact(
        self,
        binding: ArtifactBinding,
        *,
        lock: bool,
    ) -> ArtifactRecord:
        record, verified_integrity = self._exact_identity(binding, lock=lock)
        if not verified_integrity:
            raise ArtifactIntegrityError(
                "Research Artifact identity or Foundation integrity does not match"
            )
        return record

    def lock_exact_identity(self, binding: ArtifactBinding) -> ArtifactRecord:
        record, _ = self._exact_identity(binding, lock=True)
        return record

    def _exact_identity(
        self,
        binding: ArtifactBinding,
        *,
        lock: bool,
    ) -> tuple[ArtifactRecord, bool]:
        suffix = " FOR SHARE" if lock else ""
        row = self._research_connection.execute(
            """
            SELECT artifact_id, content_sha256, size_bytes, media_type,
                   locator, integrity_state, retention_until,
                   pin_reason_code,
                   mra.artifact_has_verified_integrity(
                       integrity_state, last_verified_at
                   )
            FROM mra.artifact
            WHERE artifact_id = %s
            """
            + suffix,
            (binding.artifact_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"Artifact {binding.artifact_id} does not exist"
            )
        if str(row[1]) != str(binding.content_sha256) or int(row[2]) != binding.size_bytes:
            raise ArtifactIntegrityError(
                "Research Artifact identity does not match its binding"
            )
        return ArtifactRecord(
            artifact_id=binding.artifact_id,
            content_sha256=str(row[1]),
            size_bytes=int(row[2]),
            media_type=str(row[3]),
            locator=str(row[4]),
            integrity_state=str(row[5]),
            retention_until=row[6],
            pin_reason_code=str(row[7]) if row[7] is not None else None,
        ), row[8] is True


__all__ = ["PostgresResearchArtifactRepository"]
