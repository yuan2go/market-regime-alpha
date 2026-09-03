"""Read-only PostgreSQL preparation for Market archive operations."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.domain import ArchiveLane, CaptureStatus
from market_regime_alpha.market.ports.archive_operations import (
    ArchiveCaptureDisposition,
    ArchiveSliceOperatingContract,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError


class PostgresArchiveOperationsReadPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

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
