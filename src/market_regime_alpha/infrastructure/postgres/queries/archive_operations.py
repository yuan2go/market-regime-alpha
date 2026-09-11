"""Read-only PostgreSQL preparation for Market archive operations."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.market import PostgresMarketRepository
from market_regime_alpha.market.domain import ArchiveLane, CaptureStatus
from market_regime_alpha.market.ports.archive_operations import (
    ArchiveCaptureDisposition,
    ArchiveSliceOperatingContract,
    ArchiveTerminalNormalizerFailure,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError


class PostgresArchiveOperationsReadPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def terminal_normalizer_failure(
        self, *, run_id: UUID, step_id: UUID, market_archive_id: UUID,
        market_archive_slice_id: UUID, fence_token: int,
    ) -> ArchiveTerminalNormalizerFailure | None:
        """Reload a single known failed normalization without issuing a command.

        A terminal error code alone is insufficient. The failed receipt must be
        the sole Attempt's result and follow its exact committed Capture and
        verified source read. Frozen request and current bytes are checked by
        the application after this reload; no failure is relabelled here.
        """
        prefix = f"archive:{market_archive_id}:runtime:{market_archive_slice_id}"
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT capture.capture_id, captured.result_hash, failed.request_hash
                FROM mra.runtime_step AS step
                JOIN mra.runtime_attempt AS attempt ON attempt.step_id = step.step_id
                JOIN mra.command_receipt AS failed
                  ON failed.receipt_id = attempt.result_receipt_id
                JOIN mra.command_receipt AS captured
                  ON captured.runtime_attempt_id = attempt.attempt_id
                 AND captured.command_kind = 'CAPTURE_MARKET_DATA'
                JOIN mra.data_capture AS capture
                  ON capture.capture_id::text = captured.result_aggregate_id
                JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
                JOIN mra.market_archive_slice AS slice
                  ON slice.market_archive_slice_id = %s AND slice.market_archive_id = %s
                JOIN mra.market_archive AS root ON root.market_archive_id = slice.market_archive_id
                WHERE step.step_id = %s AND step.run_id = %s
                  AND step.state = 'FAILED' AND step.current_attempt_id IS NULL
                  AND step.current_fence = %s AND attempt.fence_token = step.current_fence
                  AND attempt.attempt_no = 1 AND attempt.state = 'FAILED_TERMINAL'
                  AND attempt.error_class = 'DOMAIN'
                  AND attempt.error_code = 'NORMALIZER_OUTPUT_REJECTED'
                  AND attempt.external_effect_class = 'CONTENT_PUT'
                  AND NOT EXISTS (SELECT 1 FROM mra.runtime_attempt AS other
                                  WHERE other.step_id = step.step_id
                                    AND other.attempt_id <> attempt.attempt_id)
                  AND failed.command_kind = 'NORMALIZE_MARKET_PIT'
                  AND failed.scope_id = capture.capture_id::text
                  AND failed.idempotency_key = %s AND failed.status = 'FAILED'
                  AND failed.error_code = 'NORMALIZER_OUTPUT_REJECTED'
                  AND failed.runtime_step_id = step.step_id
                  AND failed.runtime_attempt_id = attempt.attempt_id
                  AND failed.fence_token = attempt.fence_token
                  AND captured.idempotency_key = %s AND captured.status = 'SUCCEEDED'
                  AND captured.scope_id = capture.provider_product_id::text
                  AND captured.result_aggregate_kind = 'DATA_CAPTURE'
                  AND captured.result_aggregate_version = 1
                  AND captured.runtime_step_id = step.step_id
                  AND captured.fence_token = attempt.fence_token
                  AND captured.request_hash = capture.request_hash
                  AND capture.request_hash = slice.request_sha256
                  AND capture.provider_product_id = root.provider_product_id
                  AND capture.status = 'CAPTURED' AND artifact.integrity_state = 'AVAILABLE'
                  AND capture.capture_started_at >= slice.event_window_start
                  AND capture.capture_started_at <= slice.event_window_end
                  AND capture.known_at <= captured.completed_at
                  AND captured.completed_at <= failed.created_at
                  AND failed.completed_at <= attempt.finished_at
                  AND EXISTS (
                      SELECT 1 FROM mra.artifact_verification AS verified
                      JOIN mra.command_receipt AS verification
                        ON verification.receipt_id = verified.command_receipt_id
                      WHERE verified.artifact_id = artifact.artifact_id
                        AND verified.result = 'VERIFIED' AND verified.observed_exists
                        AND verified.observed_sha256 = artifact.content_sha256
                        AND verified.observed_size_bytes = artifact.size_bytes
                        AND verified.verification_policy = 'MARKET_NORMALIZATION_SOURCE_READ'
                        AND verified.verifier_id = 'market-normalizer:market.baostock_archive:3'
                        AND verification.command_kind = 'VERIFY_MARKET_SOURCE_ARTIFACT'
                        AND verification.scope_id = artifact.artifact_id::text
                        AND verification.status = 'SUCCEEDED'
                        AND verification.result_aggregate_kind = 'ARTIFACT_VERIFICATION'
                        AND verification.result_aggregate_id = verified.verification_id::text
                        AND verification.runtime_step_id = step.step_id
                        AND verification.runtime_attempt_id = attempt.attempt_id
                        AND verification.fence_token = attempt.fence_token
                        AND verification.created_at >= captured.completed_at
                        AND verification.completed_at <= failed.created_at
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM mra.command_receipt AS normalized
                      WHERE normalized.command_kind = 'NORMALIZE_MARKET_PIT'
                        AND normalized.scope_id = capture.capture_id::text
                        AND normalized.receipt_id <> failed.receipt_id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM mra.market_archive_capture_observation AS observation
                      WHERE observation.capture_id = capture.capture_id
                         OR observation.market_archive_slice_id = slice.market_archive_slice_id
                  )
                """,
                (market_archive_slice_id, market_archive_id, step_id, run_id,
                 fence_token, f"{prefix}:normalize", f"{prefix}:capture"),
            ).fetchall()
            if len(rows) != 1:
                return None
            capture_id, result_hash, normalization_hash = rows[0]
            source = PostgresMarketRepository(connection).capture_source(capture_id, lock=False)
            if source.artifact is None:
                return None
            return ArchiveTerminalNormalizerFailure(
                source.capture, source.artifact, str(result_hash), str(normalization_hash),
            )

    def load_slice_contract(
        self,
        market_archive_id: UUID,
        market_archive_slice_id: UUID,
    ) -> ArchiveSliceOperatingContract:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT root.provider_product_id, slice.request_sha256,
                       root.lane, slice.event_window_start,
                       slice.event_window_end,
                       root.reserved_free_bytes, root.maximum_slice_bytes,
                       CASE
                         WHEN terminal.market_archive_slice_id IS NOT NULL THEN terminal.terminal_state
                         WHEN resource.market_archive_resource_stop_id IS NOT NULL THEN 'RESOURCE_LIMIT'
                         WHEN gap.market_archive_slice_gap_id IS NOT NULL THEN gap.terminal_status
                         WHEN root.lane = 'RETROSPECTIVE_BACKFILL' AND EXISTS (
                             SELECT 1 FROM mra.market_archive_capture_observation AS observation
                             WHERE observation.market_archive_slice_id = slice.market_archive_slice_id
                         ) THEN 'CAPTURED'
                         ELSE NULL
                       END AS terminal_status
                FROM mra.market_archive AS root
                JOIN mra.market_archive_slice AS slice
                  ON slice.market_archive_id = root.market_archive_id
                LEFT JOIN mra.market_archive_slice_gap AS gap
                  ON gap.market_archive_slice_id = slice.market_archive_slice_id
                LEFT JOIN mra.market_archive_resource_stop AS resource
                  ON resource.market_archive_slice_id = slice.market_archive_slice_id
                LEFT JOIN mra.prospective_archive_slice_terminal AS terminal
                  ON terminal.market_archive_slice_id = slice.market_archive_slice_id
                WHERE root.market_archive_id = %s
                  AND slice.market_archive_slice_id = %s
                """,
                (market_archive_id, market_archive_slice_id),
            ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("Market archive slice operating contract is missing")
        return ArchiveSliceOperatingContract(
            market_archive_id=market_archive_id,
            market_archive_slice_id=market_archive_slice_id,
            provider_product_id=UUID(str(row[0])),
            request_sha256=str(row[1]),
            lane=ArchiveLane(str(row[2])),
            event_window_start=row[3],
            event_window_end=row[4],
            reserved_free_bytes=int(row[5]),
            maximum_slice_bytes=int(row[6]),
            terminal_status=str(row[7]) if row[7] is not None else None,
        )

    def due_slice_ids(self, market_archive_id: UUID) -> tuple[UUID, ...]:
        """Use PostgreSQL time and immutable terminal facts for due admission."""
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT slice.market_archive_slice_id
                FROM mra.market_archive_slice AS slice
                JOIN mra.prospective_archive_slice_schedule AS schedule
                  ON schedule.market_archive_slice_id = slice.market_archive_slice_id
                WHERE slice.market_archive_id = %s
                  AND slice.event_window_start <= clock_timestamp()
                  AND slice.event_window_end >= clock_timestamp()
                  AND NOT EXISTS (
                      SELECT 1 FROM mra.prospective_archive_slice_terminal AS terminal
                      WHERE terminal.market_archive_slice_id = slice.market_archive_slice_id
                  )
                ORDER BY schedule.ordinal
                """,
                (market_archive_id,),
            ).fetchall()
        return tuple(UUID(str(row[0])) for row in rows)

    def capture_disposition(self, capture_id: UUID) -> ArchiveCaptureDisposition:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT status FROM mra.data_capture WHERE capture_id = %s",
                (capture_id,),
            ).fetchone()
            gaps = connection.execute(
                "SELECT gap_id FROM mra.source_gap WHERE capture_id = %s ORDER BY gap_id",
                (capture_id,),
            ).fetchall()
        if row is None:
            raise RuntimeNotFoundError(f"Capture {capture_id} does not exist")
        return ArchiveCaptureDisposition(
            capture_id=capture_id,
            status=CaptureStatus(str(row[0])),
            source_gap_ids=tuple(UUID(str(item[0])) for item in gaps),
        )


__all__ = ["PostgresArchiveOperationsReadPort"]
