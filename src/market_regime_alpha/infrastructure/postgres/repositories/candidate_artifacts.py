"""Candidate-facing exact Foundation Artifact adapter."""

from typing import Any, Literal

import psycopg

from market_regime_alpha.infrastructure.postgres.repositories.artifacts import (
    PostgresArtifactRepository,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
)
from market_regime_alpha.runtime.ports import ArtifactRecord
from market_regime_alpha.selection.domain import CandidateArtifactBinding


class PostgresCandidateArtifactRepository(PostgresArtifactRepository):
    """Require exact immutable Artifact bindings for Candidate commands."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        super().__init__(connection)
        self._candidate_connection = connection

    def require_exact(
        self,
        binding: CandidateArtifactBinding,
        *,
        lock: bool,
    ) -> ArtifactRecord:
        record, verified_integrity = self._exact_identity(
            binding,
            lock_clause=" FOR SHARE" if lock else "",
        )
        if not verified_integrity:
            raise ArtifactIntegrityError(
                "Candidate Artifact identity or Foundation integrity does not match"
            )
        return record

    def require_exact_for_verification(
        self,
        binding: CandidateArtifactBinding,
    ) -> ArtifactRecord:
        record, verified_integrity = self._exact_identity(
            binding,
            lock_clause=" FOR UPDATE",
        )
        if not verified_integrity:
            raise ArtifactIntegrityError(
                "Candidate Artifact identity or Foundation integrity does not match"
            )
        return record

    def lock_exact_identity(
        self,
        binding: CandidateArtifactBinding,
    ) -> ArtifactRecord:
        record, _ = self._exact_identity(binding, lock_clause=" FOR SHARE")
        return record

    def _exact_identity(
        self,
        binding: CandidateArtifactBinding,
        *,
        lock_clause: Literal["", " FOR SHARE", " FOR UPDATE"],
    ) -> tuple[ArtifactRecord, bool]:
        row = self._candidate_connection.execute(
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
            + lock_clause,
            (binding.artifact_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"Artifact {binding.artifact_id} does not exist"
            )
        if (
            str(row[1]) != str(binding.content_sha256)
            or int(row[2]) != binding.size_bytes
        ):
            raise ArtifactIntegrityError(
                "Candidate Artifact identity does not match its binding"
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


__all__ = ["PostgresCandidateArtifactRepository"]
