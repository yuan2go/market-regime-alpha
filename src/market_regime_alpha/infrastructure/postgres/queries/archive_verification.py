"""Read-only replay and reconciliation for Market archive Authority."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.market_archive import (
    PostgresArchiveRepository,
)
from market_regime_alpha.market.domain import (
    ArchiveLane,
    ArchiveObservationRelation,
    ArchiveObservationTimeliness,
    MarketArchiveSeal,
)
from market_regime_alpha.market.ports import ArchiveVerification
from market_regime_alpha.runtime.errors import RuntimeNotFoundError
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresArchiveVerificationPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def verify(self, market_archive_id: UUID) -> ArchiveVerification:
        mismatches: list[str] = []
        with self._pool.connection(read_only=True) as connection:
            repository = PostgresArchiveRepository(connection)
            try:
                archive = repository.get_archive(market_archive_id)
            except RuntimeNotFoundError:
                raise
            except RuntimeError:
                return ArchiveVerification(market_archive_id, False, ("ARCHIVE_ROOT",))
            slices_by_id = {
                item.market_archive_slice_id: item for item in archive.slices
            }
            observation_rows = connection.execute(
                """
                SELECT market_archive_capture_observation_id,
                       market_archive_slice_id, capture_id,
                       observation_ordinal, previous_observation_id,
                       artifact_sha256, normalized_revision_count,
                       normalized_revision_roster_sha256, relation,
                       timeliness, known_at, event_window_end
                FROM mra.market_archive_capture_observation
                WHERE market_archive_id = %s
                ORDER BY market_archive_slice_id, observation_ordinal
                """,
                (market_archive_id,),
            ).fetchall()
            prior_by_slice: dict[UUID, tuple[UUID, int, str]] = {}
            for row in observation_rows:
                observation_id = UUID(str(row[0]))
                slice_id = UUID(str(row[1]))
                try:
                    repository.get_capture_observation(observation_id)
                except RuntimeError:
                    mismatches.append(f"OBSERVATION_CONTENT:{observation_id}")
                prior = prior_by_slice.get(slice_id)
                slice_contract = slices_by_id[slice_id]
                expected_ordinal = 1 if prior is None else prior[1] + 1
                expected_previous = None if prior is None else prior[0]
                expected_relation = (
                    ArchiveObservationRelation.FIRST.value
                    if prior is None
                    else ArchiveObservationRelation.IDENTICAL.value
                    if prior[2] == str(row[5])
                    else ArchiveObservationRelation.CHANGED.value
                )
                expected_timeliness = (
                    ArchiveObservationTimeliness.NOT_APPLICABLE.value
                    if archive.lane is ArchiveLane.RETROSPECTIVE_BACKFILL
                    else ArchiveObservationTimeliness.ON_TIME.value
                    if row[10] >= slice_contract.event_window_start
                    and row[10] <= row[11]
                    else ArchiveObservationTimeliness.LATE.value
                )
                if (
                    archive.lane is ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS
                    and row[10] < slice_contract.event_window_start
                ):
                    mismatches.append(f"EARLY_OBSERVATION:{observation_id}")
                if (
                    int(row[3]) != (1 if prior is None else expected_ordinal)
                    or (UUID(str(row[4])) if row[4] is not None else None)
                    != expected_previous
                    or str(row[8]) != expected_relation
                    or str(row[9]) != expected_timeliness
                ):
                    mismatches.append(f"OBSERVATION_CHAIN:{observation_id}")
                normalized = connection.execute(
                    """
                    SELECT normalized_revision_count,
                           normalized_revision_roster_sha256
                    FROM mra.market_capture_normalized_roster(%s)
                    """,
                    (row[2],),
                ).fetchone()
                if normalized is None or (
                    int(normalized[0]), str(normalized[1])
                ) != (int(row[6]), str(row[7])):
                    mismatches.append(f"NORMALIZED_ROSTER:{observation_id}")
                prior_by_slice[slice_id] = (
                    observation_id,
                    int(row[3]),
                    str(row[5]),
                )
            if any(
                ordinal != index
                for rows in _group_observations(observation_rows).values()
                for index, ordinal in enumerate(
                    (int(item[3]) for item in rows), start=1
                )
            ):
                mismatches.append("OBSERVATION_ORDINALS")
            if connection.execute(
                """
                SELECT count(*)
                FROM mra.market_archive_capture_observation AS observation
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = observation.capture_id
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE observation.market_archive_id = %s
                  AND NOT mra.market_artifact_is_readable(
                      artifact.integrity_state, artifact.last_verified_at
                  )
                """,
                (market_archive_id,),
            ).fetchone() != (0,):
                mismatches.append("ARTIFACT_INTEGRITY")
            seal_row = connection.execute(
                """
                SELECT market_archive_seal_id
                FROM mra.market_archive_seal
                WHERE market_archive_id = %s
                """,
                (market_archive_id,),
            ).fetchone()
            if seal_row is not None:
                stored = repository.get_seal(UUID(str(seal_row[0])))
                gaps = connection.execute(
                    """
                    SELECT market_archive_slice_id, binding_id, gap_identity,
                           terminal_status, gap_kind
                    FROM (
                        SELECT market_archive_slice_id,
                               market_archive_slice_gap_id AS binding_id,
                               gap_id AS gap_identity, terminal_status,
                               'SOURCE_GAP'::text AS gap_kind
                        FROM mra.market_archive_slice_gap
                        WHERE market_archive_id = %s
                        UNION ALL
                        SELECT market_archive_slice_id,
                               market_archive_resource_stop_id,
                               market_archive_resource_stop_id,
                               'RESOURCE_LIMIT', 'RESOURCE_STOP'
                        FROM mra.market_archive_resource_stop
                        WHERE market_archive_id = %s
                    ) AS terminal_gap
                    ORDER BY market_archive_slice_id
                    """,
                    (market_archive_id, market_archive_id),
                ).fetchall()
                capture_roster = [
                    {"capture_id": UUID(str(row[2])), "observation_id": UUID(str(row[0]))}
                    for row in observation_rows
                ]
                artifact_roster = [
                    {
                        "content_sha256": str(row[5]),
                        "size_bytes": repository.get_capture_observation(
                            UUID(str(row[0]))
                        ).artifact_size_bytes,
                    }
                    for row in observation_rows
                ]
                normalized_roster = [
                    {"observation_id": UUID(str(row[0])), "roster_sha256": str(row[7])}
                    for row in observation_rows
                ]
                gap_roster = [
                    {
                        "binding_id": UUID(str(row[1])),
                        "gap_id": UUID(str(row[2])),
                        "gap_kind": str(row[4]),
                        "terminal_status": str(row[3]),
                    }
                    for row in gaps
                ]
                expected = MarketArchiveSeal.create(
                    market_archive_seal_id=stored.market_archive_seal_id,
                    archive=archive,
                    terminal_slices=archive.slices,
                    sealed_at=stored.sealed_at,
                    disposition=stored.disposition,
                    capture_count=len(observation_rows),
                    capture_roster_sha256=canonical_json_sha256(capture_roster),
                    artifact_count=len(observation_rows),
                    artifact_roster_sha256=canonical_json_sha256(artifact_roster),
                    normalized_revision_count=sum(int(row[6]) for row in observation_rows),
                    normalized_revision_roster_sha256=canonical_json_sha256(normalized_roster),
                    gap_count=len(gaps),
                    gap_roster_sha256=canonical_json_sha256(gap_roster),
                )
                if expected != stored:
                    mismatches.append("ARCHIVE_SEAL")
            receipt_ok = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM mra.command_receipt AS receipt
                    JOIN mra.audit_event AS audit
                      ON audit.command_receipt_id = receipt.receipt_id
                    WHERE receipt.command_kind = 'START_MARKET_ARCHIVE'
                      AND receipt.status = 'SUCCEEDED'
                      AND receipt.result_aggregate_id = %s
                      AND audit.aggregate_kind = 'MARKET_ARCHIVE'
                      AND audit.aggregate_id = %s
                )
                """,
                (str(market_archive_id), str(market_archive_id)),
            ).fetchone()
            if receipt_ok != (True,):
                mismatches.append("RECEIPT_AUDIT")
        return ArchiveVerification(
            market_archive_id,
            not mismatches,
            tuple(dict.fromkeys(mismatches)),
        )


def _group_observations(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(UUID(str(row[1])), []).append(row)
    return grouped


__all__ = ["PostgresArchiveVerificationPort"]
