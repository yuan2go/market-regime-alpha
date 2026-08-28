"""PostgreSQL metadata, verification, dependency, and GC owner for Artifacts."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeNotFoundError
from market_regime_alpha.runtime.ports import (
    ArtifactGcStatus,
    ArtifactRecord,
    ArtifactVerificationRecord,
    ByteVerification,
    PublishedArtifact,
)


class PostgresArtifactRepository:
    """Aggregate operations for artifact metadata; never reads or writes bytes."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def register(
        self,
        *,
        artifact_id: UUID,
        published: PublishedArtifact,
        retention_until: datetime | None,
        pin_reason_code: str | None,
    ) -> ArtifactRecord:
        self._lock_artifact_identity(published.content_sha256)
        candidate = self._connection.execute(
            """
            SELECT state
            FROM mra.artifact_gc_candidate
            WHERE content_sha256 = %s
            FOR UPDATE
            """,
            (published.content_sha256,),
        ).fetchone()
        if candidate is not None and candidate[0] not in {"OBSERVED", "CLEARED"}:
            raise ArtifactIntegrityError(
                "artifact identity is already under quarantine or deletion"
            )
        self._connection.execute(
            """
            INSERT INTO mra.artifact (
                artifact_id, content_sha256, size_bytes, media_type, locator,
                integrity_state, retention_until, pin_reason_code, last_verified_at
            )
            VALUES (%s, %s, %s, %s, %s, 'AVAILABLE', %s, %s, clock_timestamp())
            ON CONFLICT (content_sha256) DO NOTHING
            """,
            (
                artifact_id,
                published.content_sha256,
                published.size_bytes,
                published.media_type,
                published.locator,
                retention_until,
                pin_reason_code,
            ),
        )
        record = self.get_by_hash(published.content_sha256, lock=True)
        if record is None:
            raise ArtifactIntegrityError("artifact row disappeared during registration")
        expected = (
            published.content_sha256,
            published.size_bytes,
            published.media_type,
            published.locator,
            retention_until,
            pin_reason_code,
        )
        actual = (
            record.content_sha256,
            record.size_bytes,
            record.media_type,
            record.locator,
            record.retention_until,
            record.pin_reason_code,
        )
        if actual != expected:
            raise ArtifactIntegrityError(
                "same content hash is registered with conflicting metadata"
            )
        if candidate is not None and candidate[0] == "OBSERVED":
            self._connection.execute(
                """
                UPDATE mra.artifact_gc_candidate
                SET artifact_id = %s, state = 'CLEARED',
                    last_seen_at = clock_timestamp(),
                    cleared_at = clock_timestamp(),
                    operator_id = 'artifact-registration',
                    disposition_reason_code = 'ARTIFACT_REGISTERED'
                WHERE content_sha256 = %s AND state = 'OBSERVED'
                """,
                (record.artifact_id, published.content_sha256),
            )
        return record

    def get(self, artifact_id: UUID) -> ArtifactRecord:
        row = self._connection.execute(
            """
            SELECT artifact_id, content_sha256, size_bytes, media_type, locator,
                   integrity_state, retention_until, pin_reason_code
            FROM mra.artifact
            WHERE artifact_id = %s
            """,
            (artifact_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Artifact {artifact_id} does not exist")
        return _artifact_record(row)

    def get_by_hash(
        self,
        content_sha256: str,
        *,
        lock: bool = False,
    ) -> ArtifactRecord | None:
        suffix = " FOR UPDATE" if lock else ""
        row = self._connection.execute(
            """
            SELECT artifact_id, content_sha256, size_bytes, media_type, locator,
                   integrity_state, retention_until, pin_reason_code
            FROM mra.artifact
            WHERE content_sha256 = %s
            """
            + suffix,
            (content_sha256,),
        ).fetchone()
        return _artifact_record(row) if row is not None else None

    def record_verification(
        self,
        *,
        verification_id: UUID,
        receipt_id: UUID,
        artifact: ArtifactRecord,
        verifier_id: str,
        policy: str,
        verification: ByteVerification,
    ) -> ArtifactVerificationRecord:
        state = {
            "VERIFIED": "AVAILABLE",
            "MISSING": "MISSING",
            "SIZE_MISMATCH": "CORRUPT",
            "HASH_MISMATCH": "CORRUPT",
            "INTEGRITY_ERROR": "CORRUPT",
        }[verification.result]
        updated = self._connection.execute(
            """
            UPDATE mra.artifact
            SET integrity_state = %s, last_verified_at = clock_timestamp()
            WHERE artifact_id = %s
              AND content_sha256 = %s
              AND size_bytes = %s
              AND integrity_state IN ('AVAILABLE', 'MISSING', 'CORRUPT')
            RETURNING artifact_id
            """,
            (
                state,
                artifact.artifact_id,
                artifact.content_sha256,
                artifact.size_bytes,
            ),
        ).fetchone()
        if updated is None:
            raise ArtifactIntegrityError(
                f"Artifact {artifact.artifact_id} changed or entered GC during verification"
            )
        self._connection.execute(
            """
            INSERT INTO mra.artifact_verification (
                verification_id, artifact_id, command_receipt_id, verifier_id,
                verification_policy, result, observed_exists,
                observed_size_bytes, observed_sha256
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                verification_id,
                artifact.artifact_id,
                receipt_id,
                verifier_id,
                policy,
                verification.result,
                verification.observed_exists,
                verification.observed_size_bytes,
                verification.observed_sha256,
            ),
        )
        return ArtifactVerificationRecord(
            verification_id=verification_id,
            artifact_id=artifact.artifact_id,
            result=verification.result,
            observed_exists=verification.observed_exists,
            observed_size_bytes=verification.observed_size_bytes,
            observed_sha256=verification.observed_sha256,
        )

    def verification_for_receipt(
        self, receipt_id: UUID
    ) -> ArtifactVerificationRecord:
        row = self._connection.execute(
            """
            SELECT verification_id, artifact_id, result, observed_exists,
                   observed_size_bytes, observed_sha256
            FROM mra.artifact_verification
            WHERE command_receipt_id = %s
            """,
            (receipt_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"Artifact verification for receipt {receipt_id} does not exist"
            )
        return ArtifactVerificationRecord(
            verification_id=UUID(str(row[0])),
            artifact_id=UUID(str(row[1])),
            result=str(row[2]),
            observed_exists=bool(row[3]),
            observed_size_bytes=int(row[4]) if row[4] is not None else None,
            observed_sha256=str(row[5]) if row[5] is not None else None,
        )

    def gc_status(self, content_sha256: str) -> ArtifactGcStatus:
        row = self._connection.execute(
            """
            SELECT
                artifact.artifact_id,
                candidate.state,
                COALESCE(candidate.grace_until <= clock_timestamp(), false) AS due,
                COALESCE(
                    EXISTS (
                        SELECT 1 FROM mra.runtime_run AS run
                        WHERE run.config_artifact_id = artifact.artifact_id
                    ) OR EXISTS (
                        SELECT 1 FROM mra.command_receipt AS receipt
                        WHERE receipt.result_artifact_id = artifact.artifact_id
                    ) OR EXISTS (
                        SELECT 1 FROM mra.data_capture AS capture
                        WHERE capture.artifact_id = artifact.artifact_id
                    ) OR EXISTS (
                        SELECT 1 FROM mra.artifact_dependency AS dependency
                        WHERE dependency.child_artifact_id = artifact.artifact_id
                           OR dependency.parent_artifact_id = artifact.artifact_id
                    ),
                    false
                ) AS referenced,
                COALESCE(
                    artifact.pin_reason_code IS NOT NULL
                    OR artifact.retention_until > clock_timestamp()
                    OR artifact.integrity_state IN ('MISSING', 'CORRUPT'),
                    false
                ) AS pinned
                , candidate.operation_token
            FROM (SELECT %s::text AS content_sha256) AS identity
            LEFT JOIN mra.artifact AS artifact
              ON artifact.content_sha256 = identity.content_sha256
            LEFT JOIN mra.artifact_gc_candidate AS candidate
              ON candidate.content_sha256 = identity.content_sha256
            """,
            (content_sha256,),
        ).fetchone()
        if row is None:
            raise AssertionError("artifact GC identity query must return one row")
        return ArtifactGcStatus(
            content_sha256=content_sha256,
            artifact_id=UUID(str(row[0])) if row[0] is not None else None,
            state=str(row[1]) if row[1] is not None else None,
            due=bool(row[2]),
            referenced=bool(row[3]),
            pinned=bool(row[4]),
            operation_token=UUID(str(row[5])) if row[5] is not None else None,
        )

    def observe_gc_candidate(
        self,
        *,
        content_sha256: str,
        grace: timedelta,
    ) -> bool:
        self._lock_artifact_identity(content_sha256)
        status = self.gc_status(content_sha256)
        if status.referenced or status.pinned:
            return False
        if status.state not in {None, "OBSERVED", "CLEARED"}:
            raise ArtifactIntegrityError(
                "artifact identity entered GC after orphan observation began"
            )
        grace_ms = max(0, int(grace.total_seconds() * 1_000))
        self._connection.execute(
            """
            INSERT INTO mra.artifact_gc_candidate (
                content_sha256, artifact_id, state, first_seen_at,
                last_seen_at, grace_until
            )
            VALUES (
                %s, %s, 'OBSERVED', clock_timestamp(), clock_timestamp(),
                clock_timestamp() + (%s * interval '1 millisecond')
            )
            ON CONFLICT (content_sha256) DO UPDATE
            SET artifact_id = COALESCE(
                    mra.artifact_gc_candidate.artifact_id,
                    EXCLUDED.artifact_id
                ),
                state = 'OBSERVED',
                first_seen_at = CASE
                    WHEN mra.artifact_gc_candidate.state = 'CLEARED'
                    THEN clock_timestamp()
                    ELSE mra.artifact_gc_candidate.first_seen_at
                END,
                last_seen_at = clock_timestamp(),
                grace_until = CASE
                    WHEN mra.artifact_gc_candidate.state = 'CLEARED'
                    THEN clock_timestamp() + (%s * interval '1 millisecond')
                    ELSE mra.artifact_gc_candidate.grace_until
                END,
                second_seen_at = CASE
                    WHEN mra.artifact_gc_candidate.state = 'CLEARED' THEN NULL
                    ELSE mra.artifact_gc_candidate.second_seen_at
                END,
                operation_token = CASE
                    WHEN mra.artifact_gc_candidate.state = 'CLEARED' THEN NULL
                    ELSE mra.artifact_gc_candidate.operation_token
                END,
                quarantined_at = CASE
                    WHEN mra.artifact_gc_candidate.state = 'CLEARED' THEN NULL
                    ELSE mra.artifact_gc_candidate.quarantined_at
                END,
                deleted_at = CASE
                    WHEN mra.artifact_gc_candidate.state = 'CLEARED' THEN NULL
                    ELSE mra.artifact_gc_candidate.deleted_at
                END,
                cleared_at = CASE
                    WHEN mra.artifact_gc_candidate.state = 'CLEARED' THEN NULL
                    ELSE mra.artifact_gc_candidate.cleared_at
                END,
                operator_id = CASE
                    WHEN mra.artifact_gc_candidate.state = 'CLEARED' THEN NULL
                    ELSE mra.artifact_gc_candidate.operator_id
                END,
                disposition_reason_code = CASE
                    WHEN mra.artifact_gc_candidate.state = 'CLEARED' THEN NULL
                    ELSE mra.artifact_gc_candidate.disposition_reason_code
                END
            WHERE mra.artifact_gc_candidate.state IN ('OBSERVED', 'CLEARED')
            """,
            (content_sha256, status.artifact_id, grace_ms, grace_ms),
        )
        return True

    def clear_gc_candidate(
        self,
        *,
        content_sha256: str,
        operator_id: str,
        reason_code: str,
    ) -> None:
        row = self._connection.execute(
            """
            UPDATE mra.artifact_gc_candidate
            SET state = 'CLEARED', last_seen_at = clock_timestamp(),
                cleared_at = clock_timestamp(), operator_id = %s,
                disposition_reason_code = %s, operation_token = NULL
            WHERE content_sha256 = %s AND state = 'OBSERVED'
            RETURNING content_sha256
            """,
            (operator_id, reason_code, content_sha256),
        ).fetchone()
        if row is None:
            raise ArtifactIntegrityError("artifact GC candidate cannot be cleared")

    def begin_quarantine(self, content_sha256: str, operation_token: UUID) -> None:
        self._lock_artifact_identity(content_sha256)
        artifact_row = self._connection.execute(
            """
            SELECT artifact_id, integrity_state
            FROM mra.artifact
            WHERE content_sha256 = %s
            FOR UPDATE
            """,
            (content_sha256,),
        ).fetchone()
        status = self.gc_status(content_sha256)
        if status.referenced or status.pinned or status.state != "OBSERVED" or not status.due:
            raise ArtifactIntegrityError("artifact is not eligible for second-pass quarantine")
        row = self._connection.execute(
            """
            UPDATE mra.artifact_gc_candidate
            SET state = 'QUARANTINE_PENDING', second_seen_at = clock_timestamp(),
                last_seen_at = clock_timestamp(), operation_token = %s
            WHERE content_sha256 = %s AND state = 'OBSERVED'
              AND grace_until <= clock_timestamp()
            RETURNING content_sha256
            """,
            (operation_token, content_sha256),
        ).fetchone()
        if row is None:
            raise ArtifactIntegrityError("artifact quarantine eligibility changed")
        if artifact_row is not None:
            if artifact_row[1] != "AVAILABLE":
                raise ArtifactIntegrityError(
                    "registered Artifact must be AVAILABLE before quarantine"
                )
            updated = self._connection.execute(
                """
                UPDATE mra.artifact
                SET integrity_state = 'QUARANTINED'
                WHERE artifact_id = %s AND integrity_state = 'AVAILABLE'
                RETURNING artifact_id
                """,
                (artifact_row[0],),
            ).fetchone()
            if updated is None:
                raise ArtifactIntegrityError("Artifact quarantine state changed")

    def finish_quarantine(self, content_sha256: str, operation_token: UUID) -> None:
        row = self._connection.execute(
            """
            UPDATE mra.artifact_gc_candidate
            SET state = 'QUARANTINED', quarantined_at = clock_timestamp()
            WHERE content_sha256 = %s AND state = 'QUARANTINE_PENDING'
              AND operation_token = %s
            RETURNING artifact_id
            """,
            (content_sha256, operation_token),
        ).fetchone()
        if row is None:
            raise ArtifactIntegrityError("artifact quarantine operation token is stale")
        if row[0] is not None:
            state = self._connection.execute(
                "SELECT integrity_state FROM mra.artifact WHERE artifact_id = %s",
                (row[0],),
            ).fetchone()
            if state != ("QUARANTINED",):
                raise ArtifactIntegrityError("Artifact quarantine binding is inconsistent")

    def begin_delete(self, content_sha256: str, operation_token: UUID) -> None:
        self._lock_artifact_identity(content_sha256)
        status = self.gc_status(content_sha256)
        if status.referenced or status.pinned or status.state != "QUARANTINED":
            raise ArtifactIntegrityError("artifact is not eligible for explicit deletion")
        row = self._connection.execute(
            """
            UPDATE mra.artifact_gc_candidate
            SET state = 'DELETE_PENDING', operation_token = %s
            WHERE content_sha256 = %s AND state = 'QUARANTINED'
            RETURNING content_sha256
            """,
            (operation_token, content_sha256),
        ).fetchone()
        if row is None:
            raise ArtifactIntegrityError("artifact is not quarantined for deletion")

    def finish_delete(
        self,
        content_sha256: str,
        operation_token: UUID,
        *,
        verification_id: UUID,
        receipt_id: UUID,
        verifier_id: str,
    ) -> None:
        row = self._connection.execute(
            """
            UPDATE mra.artifact_gc_candidate
            SET state = 'DELETED', deleted_at = clock_timestamp(),
                operator_id = %s, disposition_reason_code = 'EXPLICIT_GC_DELETE'
            WHERE content_sha256 = %s AND state = 'DELETE_PENDING'
              AND operation_token = %s
            RETURNING artifact_id
            """,
            (verifier_id, content_sha256, operation_token),
        ).fetchone()
        if row is None:
            raise ArtifactIntegrityError("artifact delete operation token is stale")
        if row[0] is not None:
            artifact_id = UUID(str(row[0]))
            self._connection.execute(
                """
                UPDATE mra.artifact
                SET integrity_state = 'DELETED', last_verified_at = clock_timestamp()
                WHERE artifact_id = %s
                """,
                (artifact_id,),
            )
            self._connection.execute(
                """
                INSERT INTO mra.artifact_verification (
                    verification_id, artifact_id, command_receipt_id,
                    verifier_id, verification_policy, result,
                    observed_exists, observed_size_bytes, observed_sha256
                )
                VALUES (%s, %s, %s, %s, 'GC_DELETE', 'MISSING', false, NULL, NULL)
                """,
                (verification_id, artifact_id, receipt_id, verifier_id),
            )

    def _lock_artifact_identity(self, content_sha256: str) -> None:
        """Serialize registration/binding against two-phase GC by content identity."""

        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (content_sha256,),
        )


def _artifact_record(row: tuple[Any, ...]) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=UUID(str(row[0])),
        content_sha256=str(row[1]),
        size_bytes=int(row[2]),
        media_type=str(row[3]),
        locator=str(row[4]),
        integrity_state=str(row[5]),
        retention_until=row[6],
        pin_reason_code=str(row[7]) if row[7] is not None else None,
    )


__all__ = ["PostgresArtifactRepository"]
