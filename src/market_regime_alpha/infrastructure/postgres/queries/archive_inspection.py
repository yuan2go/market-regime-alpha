"""Read-only PostgreSQL archive progress and evidence inspection."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.ports.archive_inspection import (
    ArchiveInspection,
    ArchiveSliceInspection,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError


class PostgresArchiveInspectionPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def inspect(self, market_archive_id: UUID) -> ArchiveInspection:
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT root.archive_code, root.lane, root.evidence_class,
                       root.archive_start_at, root.event_window_start,
                       root.event_window_end, root.slice_count,
                       (SELECT count(DISTINCT item.market_archive_slice_id)
                        FROM mra.market_archive_capture_observation AS item
                        WHERE item.market_archive_id = root.market_archive_id),
                       (SELECT count(*) FROM mra.market_archive_slice_gap AS item
                        WHERE item.market_archive_id = root.market_archive_id),
                       (SELECT count(*) FROM mra.market_archive_resource_stop AS item
                        WHERE item.market_archive_id = root.market_archive_id),
                       (SELECT count(*) FROM mra.market_archive_capture_observation AS item
                        WHERE item.market_archive_id = root.market_archive_id),
                       (SELECT count(*) FROM mra.market_archive_capture_observation AS item
                        WHERE item.market_archive_id = root.market_archive_id
                          AND item.relation = 'CHANGED'),
                       (SELECT count(*) FROM mra.market_archive_capture_observation AS item
                        WHERE item.market_archive_id = root.market_archive_id
                          AND item.timeliness = 'ON_TIME'),
                       (SELECT count(*) FROM mra.market_archive_capture_observation AS item
                        WHERE item.market_archive_id = root.market_archive_id
                          AND item.timeliness = 'LATE'),
                       (SELECT count(DISTINCT capture.artifact_id)
                        FROM mra.market_archive_capture_observation AS item
                        JOIN mra.data_capture AS capture ON capture.capture_id = item.capture_id
                        WHERE item.market_archive_id = root.market_archive_id),
                       (SELECT coalesce(sum(item.size_bytes), 0)
                        FROM (
                            SELECT DISTINCT artifact.artifact_id, artifact.size_bytes
                            FROM mra.market_archive_capture_observation AS observation
                            JOIN mra.data_capture AS capture
                              ON capture.capture_id = observation.capture_id
                            JOIN mra.artifact AS artifact
                              ON artifact.artifact_id = capture.artifact_id
                            WHERE observation.market_archive_id = root.market_archive_id
                        ) AS item),
                       (SELECT coalesce(sum(item.normalized_revision_count), 0)
                        FROM mra.market_archive_capture_observation AS item
                        WHERE item.market_archive_id = root.market_archive_id),
                       (SELECT count(*)
                        FROM mra.market_archive_capture_observation AS item
                        JOIN mra.market_bar_revision AS revision
                          ON revision.capture_id = item.capture_id
                        JOIN mra.market_bar_revision AS successor
                          ON successor.supersedes_revision_id = revision.bar_revision_id
                        WHERE item.market_archive_id = root.market_archive_id),
                       seal.market_archive_seal_id, seal.sealed_at,
                       seal.disposition
                FROM mra.market_archive AS root
                LEFT JOIN mra.market_archive_seal AS seal
                  ON seal.market_archive_id = root.market_archive_id
                WHERE root.market_archive_id = %s
                """,
                (market_archive_id,),
            ).fetchone()
            if root is None:
                raise RuntimeNotFoundError(
                    f"Market archive {market_archive_id} does not exist"
                )
            slice_rows = connection.execute(
                """
                SELECT slice.market_archive_slice_id, slice.ordinal,
                       slice.scope_key, slice.expected_fact_kind,
                       slice.event_window_start, slice.event_window_end,
                       CASE
                         WHEN terminal.market_archive_slice_id IS NOT NULL
                           THEN terminal.terminal_state
                         WHEN resource.market_archive_resource_stop_id IS NOT NULL
                           THEN 'RESOURCE_LIMIT'
                         WHEN gap.market_archive_slice_gap_id IS NOT NULL
                           THEN gap.terminal_status
                         WHEN count(observation.market_archive_capture_observation_id) > 0
                           THEN 'CAPTURED'
                         WHEN clock_timestamp() < slice.event_window_start
                           THEN 'NOT_DUE'
                         WHEN clock_timestamp() <= slice.event_window_end
                           THEN 'DUE'
                         ELSE 'OVERDUE'
                       END,
                       count(observation.market_archive_capture_observation_id),
                       (array_agg(observation.relation ORDER BY observation.observation_ordinal DESC)
                          FILTER (WHERE observation.relation IS NOT NULL))[1],
                       (array_agg(observation.timeliness ORDER BY observation.observation_ordinal DESC)
                          FILTER (WHERE observation.timeliness IS NOT NULL))[1],
                       max(observation.known_at), gap.gap_id, source_gap.reason_code
                FROM mra.market_archive_slice AS slice
                LEFT JOIN mra.market_archive_capture_observation AS observation
                  ON observation.market_archive_slice_id = slice.market_archive_slice_id
                LEFT JOIN mra.market_archive_slice_gap AS gap
                  ON gap.market_archive_slice_id = slice.market_archive_slice_id
                LEFT JOIN mra.source_gap
                  ON source_gap.gap_id = gap.gap_id
                LEFT JOIN mra.market_archive_resource_stop AS resource
                  ON resource.market_archive_slice_id = slice.market_archive_slice_id
                LEFT JOIN mra.prospective_archive_slice_terminal AS terminal
                  ON terminal.market_archive_slice_id = slice.market_archive_slice_id
                WHERE slice.market_archive_id = %s
                GROUP BY slice.market_archive_slice_id, gap.gap_id,
                         gap.market_archive_slice_gap_id, gap.terminal_status,
                         source_gap.reason_code,
                         resource.market_archive_resource_stop_id,
                         terminal.market_archive_slice_id, terminal.terminal_state
                ORDER BY slice.ordinal
                """,
                (market_archive_id,),
            ).fetchall()
            generation = connection.execute(
                """
                SELECT generation, predecessor_market_archive_id,
                       (SELECT count(*)
                        FROM mra.prospective_archive_revision_observation AS revision
                        WHERE revision.market_archive_id = root.market_archive_id
                          AND revision.relation = 'IDENTICAL'),
                       (SELECT count(*)
                        FROM mra.prospective_archive_revision_observation AS revision
                        WHERE revision.market_archive_id = root.market_archive_id
                          AND revision.relation = 'CHANGED')
                FROM mra.prospective_archive_generation AS root
                WHERE root.market_archive_id = %s
                """,
                (market_archive_id,),
            ).fetchone()
        slices = tuple(
            ArchiveSliceInspection(
                market_archive_slice_id=UUID(str(row[0])),
                ordinal=int(row[1]),
                scope_key=str(row[2]),
                expected_fact_kind=str(row[3]),
                event_window_start=row[4],
                event_window_end=row[5],
                status=str(row[6]),
                observation_count=int(row[7]),
                latest_relation=str(row[8]) if row[8] is not None else None,
                latest_timeliness=str(row[9]) if row[9] is not None else None,
                latest_known_at=row[10],
                gap_id=UUID(str(row[11])) if row[11] is not None else None,
                gap_reason_code=str(row[12]) if row[12] is not None else None,
            )
            for row in slice_rows
        )
        captured = int(root[7])
        gaps = int(root[8])
        resource_stops = int(root[9])
        statuses = tuple(item.status for item in slices)
        terminal_states = {
            "CAPTURED_ON_TIME",
            "CAPTURED_LATE",
            "MISSED",
            "PROVIDER_GAP",
            "RESOURCE_STOP",
            "FAILED",
        }
        wp18_terminal_count = sum(item in terminal_states for item in statuses)
        return ArchiveInspection(
            market_archive_id=market_archive_id,
            archive_code=str(root[0]),
            lane=str(root[1]),
            evidence_class=str(root[2]),
            archive_start_at=root[3],
            event_window_start=root[4],
            event_window_end=root[5],
            slice_count=int(root[6]),
            captured_slice_count=captured,
            gap_slice_count=gaps,
            resource_stop_count=resource_stops,
            pending_slice_count=(
                int(root[6]) - wp18_terminal_count
                if generation is not None
                else int(root[6]) - captured - gaps - resource_stops
            ),
            observation_count=int(root[10]),
            changed_observation_count=int(root[11]),
            on_time_observation_count=int(root[12]),
            late_observation_count=int(root[13]),
            artifact_count=int(root[14]),
            artifact_bytes=int(root[15]),
            normalized_revision_count=int(root[16]),
            market_revision_successor_count=int(root[17]),
            seal_id=UUID(str(root[18])) if root[18] is not None else None,
            sealed_at=root[19],
            seal_disposition=str(root[20]) if root[20] is not None else None,
            slices=slices,
            prospective_generation=(
                int(generation[0]) if generation is not None else None
            ),
            predecessor_market_archive_id=(
                UUID(str(generation[1]))
                if generation is not None and generation[1] is not None
                else None
            ),
            not_due_slice_count=statuses.count("NOT_DUE"),
            due_slice_count=statuses.count("DUE"),
            overdue_slice_count=statuses.count("OVERDUE"),
            missed_slice_count=statuses.count("MISSED"),
            observed_identical_count=(
                int(generation[2]) if generation is not None else 0
            ),
            observed_changed_count=(
                int(generation[3]) if generation is not None else 0
            ),
        )


__all__ = ["PostgresArchiveInspectionPort"]
