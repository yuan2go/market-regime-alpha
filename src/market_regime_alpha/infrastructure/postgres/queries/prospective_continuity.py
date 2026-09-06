"""Reload immutable generation and Runtime Artifact bindings from PostgreSQL."""
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.ports.prospective_continuity import ProspectiveGenerationRuntimeReference
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


class PostgresProspectiveContinuityReadPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def generations(self, series_code: str) -> tuple[ProspectiveGenerationRuntimeReference, ...]:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT generation.market_archive_id, generation.generation,
                       generation.predecessor_market_archive_id,
                       artifact.artifact_id, artifact.content_sha256, artifact.size_bytes, run.code_sha,
                       run.config_hash, schedule.revision
                FROM mra.prospective_archive_generation AS generation
                LEFT JOIN mra.runtime_run AS run
                  ON run.fire_key = 'archive:' || generation.market_archive_id::text || ':predeclare'
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = run.config_artifact_id
                LEFT JOIN mra.runtime_schedule AS schedule
                  ON schedule.schedule_id = run.schedule_id
                WHERE generation.series_code = %s
                ORDER BY generation.generation
                """,
                (series_code,),
            ).fetchall()
        result = []
        predecessor = None
        for ordinal, row in enumerate(rows, 1):
            if row[1] != ordinal or row[2] != predecessor or row[3] is None or row[4] != row[7]:
                raise ArtifactIntegrityError("Prospective series lacks an exact generation/Runtime chain")
            result.append(ProspectiveGenerationRuntimeReference(
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[8],
            ))
            predecessor = row[0]
        return tuple(result)

    def overdue_slice_ids(self, market_archive_id: UUID) -> tuple[UUID, ...]:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT slice.market_archive_slice_id
                FROM mra.market_archive_slice AS slice
                JOIN mra.prospective_archive_slice_schedule AS schedule
                  ON schedule.market_archive_slice_id = slice.market_archive_slice_id
                WHERE slice.market_archive_id = %s
                  AND slice.event_window_end < clock_timestamp()
                  AND NOT EXISTS (
                      SELECT 1 FROM mra.prospective_archive_slice_terminal AS terminal
                      WHERE terminal.market_archive_slice_id = slice.market_archive_slice_id
                  )
                ORDER BY schedule.ordinal
                """, (market_archive_id,),
            ).fetchall()
        return tuple(row[0] for row in rows)
