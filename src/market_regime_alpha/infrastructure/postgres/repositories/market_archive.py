"""PostgreSQL adapter for immutable Market archive roots and slice rosters."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.market.domain import (
    ArchiveCaptureObservation,
    ArchiveLane,
    ArchiveObservationRelation,
    ArchiveObservationTimeliness,
    ArchiveSealDisposition,
    ArchiveSliceStatus,
    BarTimeframe,
    MarketArchive,
    MarketArchiveSlice,
    MarketArchiveSeal,
    PriceBasis,
)
from market_regime_alpha.market.ports.archive import ArchiveSliceGapRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.runtime.errors import (
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)


class PostgresArchiveRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def database_now(self) -> datetime:
        row = self._connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise AssertionError("PostgreSQL clock query must return one row")
        return row[0].astimezone(timezone.utc)

    def insert_archive(
        self,
        archive: MarketArchive,
        *,
        archive_code: str,
        request_identity: str,
        request_sha256: str,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.market_archive (
                market_archive_id, archive_code, request_identity, request_sha256,
                lane, evidence_class, provider_product_id, exchange_code,
                timeframe, price_basis, instrument_scope,
                instrument_scope_sha256, event_window_start, event_window_end,
                archive_start_at, reserved_free_bytes, maximum_archive_bytes,
                maximum_slice_bytes, code_artifact_id, config_artifact_id,
                provenance_sha256, slice_count, slice_roster_sha256,
                content_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                archive.market_archive_id,
                archive_code,
                request_identity,
                request_sha256,
                archive.lane.value,
                archive.evidence_class.value,
                archive.provider_product_id,
                archive.exchange_code,
                archive.timeframe.value,
                archive.price_basis.value,
                archive.instrument_scope,
                str(archive.instrument_scope_sha256),
                archive.event_window_start,
                archive.event_window_end,
                archive.archive_start_at,
                archive.reserved_free_bytes,
                archive.maximum_archive_bytes,
                archive.maximum_slice_bytes,
                archive.code_artifact_id,
                archive.config_artifact_id,
                str(archive.provenance_sha256),
                archive.slice_count,
                str(archive.slice_roster_sha256),
                str(archive.content_sha256),
            ),
        )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.market_archive_slice (
                    market_archive_slice_id, market_archive_id, ordinal,
                    scope_key, event_window_start, event_window_end,
                    request_sha256, expected_fact_kind, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        item.market_archive_slice_id,
                        item.market_archive_id,
                        item.ordinal,
                        item.scope_key,
                        item.event_window_start,
                        item.event_window_end,
                        str(item.request_sha256),
                        item.expected_fact_kind,
                        str(item.content_sha256),
                    )
                    for item in archive.slices
                ],
            )

    def get_archive(self, market_archive_id: UUID, *, lock: bool = False) -> MarketArchive:
        suffix = " FOR UPDATE" if lock else ""
        row = self._connection.execute(
            """
            SELECT lane, provider_product_id, exchange_code, timeframe,
                   price_basis, instrument_scope, instrument_scope_sha256,
                   event_window_start, event_window_end, archive_start_at,
                   reserved_free_bytes, maximum_archive_bytes,
                   maximum_slice_bytes, code_artifact_id, config_artifact_id,
                   provenance_sha256, slice_count, slice_roster_sha256,
                   content_sha256
            FROM mra.market_archive WHERE market_archive_id = %s
            """
            + suffix,
            (market_archive_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Market archive {market_archive_id} does not exist")
        slice_rows = self._connection.execute(
            """
            SELECT slice.market_archive_slice_id, slice.ordinal, slice.scope_key,
                   slice.event_window_start, slice.event_window_end,
                   slice.request_sha256, slice.expected_fact_kind,
                   CASE
                     WHEN gap.market_archive_slice_gap_id IS NOT NULL THEN gap.terminal_status
                     WHEN EXISTS (
                        SELECT 1 FROM mra.market_archive_capture_observation AS observation
                        WHERE observation.market_archive_slice_id = slice.market_archive_slice_id
                     ) THEN 'CAPTURED'
                     ELSE 'PLANNED'
                   END AS status
            FROM mra.market_archive_slice AS slice
            LEFT JOIN mra.market_archive_slice_gap AS gap
              ON gap.market_archive_slice_id = slice.market_archive_slice_id
            WHERE slice.market_archive_id = %s
            ORDER BY slice.ordinal
            """,
            (market_archive_id,),
        ).fetchall()
        archive = MarketArchive(
            market_archive_id=market_archive_id,
            lane=ArchiveLane(str(row[0])),
            provider_product_id=UUID(str(row[1])),
            exchange_code=str(row[2]),
            timeframe=BarTimeframe(str(row[3])),
            price_basis=PriceBasis(str(row[4])),
            instrument_scope=str(row[5]),
            instrument_scope_sha256=str(row[6]),
            event_window_start=row[7],
            event_window_end=row[8],
            archive_start_at=row[9],
            reserved_free_bytes=int(row[10]),
            maximum_archive_bytes=int(row[11]),
            maximum_slice_bytes=int(row[12]),
            code_artifact_id=UUID(str(row[13])),
            config_artifact_id=UUID(str(row[14])),
            provenance_sha256=str(row[15]),
            slices=tuple(
                MarketArchiveSlice(
                    market_archive_slice_id=UUID(str(item[0])),
                    market_archive_id=market_archive_id,
                    ordinal=int(item[1]),
                    scope_key=str(item[2]),
                    event_window_start=item[3],
                    event_window_end=item[4],
                    request_sha256=str(item[5]),
                    expected_fact_kind=str(item[6]),
                    status=ArchiveSliceStatus(str(item[7])),
                )
                for item in slice_rows
            ),
        )
        if (
            archive.slice_count != int(row[16])
            or str(archive.slice_roster_sha256) != str(row[17])
            or str(archive.content_sha256) != str(row[18])
        ):
            raise RuntimeError("persisted Market archive does not reconcile")
        return archive

    def record_capture_observation(
        self,
        *,
        observation_id: UUID,
        market_archive_id: UUID,
        market_archive_slice_id: UUID,
        capture_id: UUID,
        schedule_slot: str,
        requested_at: datetime,
    ) -> ArchiveCaptureObservation:
        root = self._connection.execute(
            """
            SELECT lane FROM mra.market_archive
            WHERE market_archive_id = %s FOR UPDATE
            """,
            (market_archive_id,),
        ).fetchone()
        slice_row = self._connection.execute(
            """
            SELECT event_window_start, event_window_end
            FROM mra.market_archive_slice
            WHERE market_archive_id = %s AND market_archive_slice_id = %s
            FOR UPDATE
            """,
            (market_archive_id, market_archive_slice_id),
        ).fetchone()
        capture = self._connection.execute(
            """
            SELECT capture.capture_started_at, capture.capture_completed_at,
                   capture.recorded_at, capture.known_at,
                   artifact.content_sha256, artifact.size_bytes
            FROM mra.data_capture AS capture
            JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
            WHERE capture.capture_id = %s FOR SHARE OF capture, artifact
            """,
            (capture_id,),
        ).fetchone()
        if root is None or slice_row is None or capture is None:
            raise RuntimeNotFoundError("Market archive observation source is missing")
        normalized = self._connection.execute(
            "SELECT normalized_revision_count, normalized_revision_roster_sha256 FROM mra.market_capture_normalized_roster(%s)",
            (capture_id,),
        ).fetchone()
        if normalized is None or int(normalized[0]) < 1:
            raise RuntimeStateConflictError("Archive Capture has no canonical normalization disposition")
        prior = self._connection.execute(
            """
            SELECT market_archive_capture_observation_id, observation_ordinal,
                   artifact_sha256
            FROM mra.market_archive_capture_observation
            WHERE market_archive_slice_id = %s
            ORDER BY observation_ordinal DESC LIMIT 1 FOR UPDATE
            """,
            (market_archive_slice_id,),
        ).fetchone()
        ordinal = 1 if prior is None else int(prior[1]) + 1
        previous_id = None if prior is None else UUID(str(prior[0]))
        relation = (
            ArchiveObservationRelation.FIRST
            if prior is None
            else ArchiveObservationRelation.IDENTICAL
            if str(prior[2]) == str(capture[4])
            else ArchiveObservationRelation.CHANGED
        )
        timeliness = (
            ArchiveObservationTimeliness.NOT_APPLICABLE
            if str(root[0]) == ArchiveLane.RETROSPECTIVE_BACKFILL.value
            else ArchiveObservationTimeliness.ON_TIME
            if capture[3] <= slice_row[1]
            else ArchiveObservationTimeliness.LATE
        )
        observation = ArchiveCaptureObservation(
            market_archive_capture_observation_id=observation_id,
            market_archive_id=market_archive_id,
            market_archive_slice_id=market_archive_slice_id,
            capture_id=capture_id,
            observation_ordinal=ordinal,
            previous_observation_id=previous_id,
            schedule_slot=schedule_slot,
            requested_at=requested_at,
            capture_started_at=capture[0],
            capture_completed_at=capture[1],
            recorded_at=capture[2],
            known_at=capture[3],
            event_window_start=slice_row[0],
            event_window_end=slice_row[1],
            artifact_sha256=str(capture[4]),
            artifact_size_bytes=int(capture[5]),
            normalized_revision_count=int(normalized[0]),
            normalized_revision_roster_sha256=str(normalized[1]),
            relation=relation,
            timeliness=timeliness,
        )
        self._connection.execute(
            """
            INSERT INTO mra.market_archive_capture_observation (
                market_archive_capture_observation_id, market_archive_id,
                market_archive_slice_id, capture_id, observation_ordinal,
                previous_observation_id, schedule_slot, requested_at,
                capture_started_at, capture_completed_at, recorded_at, known_at,
                event_window_start, event_window_end, artifact_sha256,
                artifact_size_bytes, normalized_revision_count,
                normalized_revision_roster_sha256, relation, timeliness,
                content_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                observation.market_archive_capture_observation_id,
                observation.market_archive_id,
                observation.market_archive_slice_id,
                observation.capture_id,
                observation.observation_ordinal,
                observation.previous_observation_id,
                observation.schedule_slot,
                observation.requested_at,
                observation.capture_started_at,
                observation.capture_completed_at,
                observation.recorded_at,
                observation.known_at,
                observation.event_window_start,
                observation.event_window_end,
                str(observation.artifact_sha256),
                observation.artifact_size_bytes,
                observation.normalized_revision_count,
                str(observation.normalized_revision_roster_sha256),
                observation.relation.value,
                observation.timeliness.value,
                str(observation.content_sha256),
            ),
        )
        return observation

    def get_capture_observation(
        self, observation_id: UUID
    ) -> ArchiveCaptureObservation:
        row = self._connection.execute(
            """
            SELECT market_archive_id, market_archive_slice_id, capture_id,
                   observation_ordinal, previous_observation_id, schedule_slot,
                   requested_at, capture_started_at, capture_completed_at,
                   recorded_at, known_at, event_window_start, event_window_end,
                   artifact_sha256, artifact_size_bytes,
                   normalized_revision_count, normalized_revision_roster_sha256,
                   relation, timeliness, content_sha256
            FROM mra.market_archive_capture_observation
            WHERE market_archive_capture_observation_id = %s
            """,
            (observation_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Archive observation {observation_id} does not exist")
        observation = ArchiveCaptureObservation(
            market_archive_capture_observation_id=observation_id,
            market_archive_id=UUID(str(row[0])),
            market_archive_slice_id=UUID(str(row[1])),
            capture_id=UUID(str(row[2])),
            observation_ordinal=int(row[3]),
            previous_observation_id=UUID(str(row[4])) if row[4] is not None else None,
            schedule_slot=str(row[5]),
            requested_at=row[6],
            capture_started_at=row[7],
            capture_completed_at=row[8],
            recorded_at=row[9],
            known_at=row[10],
            event_window_start=row[11],
            event_window_end=row[12],
            artifact_sha256=str(row[13]),
            artifact_size_bytes=int(row[14]),
            normalized_revision_count=int(row[15]),
            normalized_revision_roster_sha256=str(row[16]),
            relation=ArchiveObservationRelation(str(row[17])),
            timeliness=ArchiveObservationTimeliness(str(row[18])),
        )
        if str(observation.content_sha256) != str(row[19]):
            raise RuntimeError("persisted archive observation does not reconcile")
        return observation

    def record_slice_gap(
        self,
        *,
        binding_id: UUID,
        market_archive_id: UUID,
        market_archive_slice_id: UUID,
        gap_id: UUID,
        terminal_status: str,
    ) -> ArchiveSliceGapRecord:
        content_hash = canonical_json_sha256(
            {
                "gap_id": gap_id,
                "market_archive_id": market_archive_id,
                "market_archive_slice_gap_id": binding_id,
                "market_archive_slice_id": market_archive_slice_id,
                "terminal_status": terminal_status,
            }
        )
        self._connection.execute(
            """
            INSERT INTO mra.market_archive_slice_gap (
                market_archive_slice_gap_id, market_archive_id,
                market_archive_slice_id, gap_id, terminal_status,
                content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                binding_id,
                market_archive_id,
                market_archive_slice_id,
                gap_id,
                terminal_status,
                content_hash,
            ),
        )
        return ArchiveSliceGapRecord(
            market_archive_slice_gap_id=binding_id,
            market_archive_id=market_archive_id,
            market_archive_slice_id=market_archive_slice_id,
            gap_id=gap_id,
            terminal_status=terminal_status,
            content_sha256=content_hash,
        )

    def get_slice_gap(self, binding_id: UUID) -> ArchiveSliceGapRecord:
        row = self._connection.execute(
            """
            SELECT market_archive_id, market_archive_slice_id, gap_id,
                   terminal_status, content_sha256
            FROM mra.market_archive_slice_gap
            WHERE market_archive_slice_gap_id = %s
            """,
            (binding_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Archive gap binding {binding_id} does not exist")
        return ArchiveSliceGapRecord(
            market_archive_slice_gap_id=binding_id,
            market_archive_id=UUID(str(row[0])),
            market_archive_slice_id=UUID(str(row[1])),
            gap_id=UUID(str(row[2])),
            terminal_status=str(row[3]),
            content_sha256=str(row[4]),
        )

    def seal_retrospective(
        self,
        *,
        seal_id: UUID,
        market_archive_id: UUID,
        disposition: ArchiveSealDisposition,
    ) -> MarketArchiveSeal:
        archive = self.get_archive(market_archive_id, lock=True)
        observations = self._connection.execute(
            """
            SELECT market_archive_capture_observation_id, capture_id,
                   artifact_sha256, artifact_size_bytes,
                   normalized_revision_count, normalized_revision_roster_sha256
            FROM mra.market_archive_capture_observation
            WHERE market_archive_id = %s ORDER BY market_archive_slice_id, observation_ordinal
            """,
            (market_archive_id,),
        ).fetchall()
        gaps = self._connection.execute(
            """
            SELECT market_archive_slice_gap_id, gap_id, terminal_status
            FROM mra.market_archive_slice_gap
            WHERE market_archive_id = %s ORDER BY market_archive_slice_id
            """,
            (market_archive_id,),
        ).fetchall()
        capture_roster = [
            {"capture_id": UUID(str(item[1])), "observation_id": UUID(str(item[0]))}
            for item in observations
        ]
        artifact_roster = [
            {"content_sha256": str(item[2]), "size_bytes": int(item[3])}
            for item in observations
        ]
        normalized_roster = [
            {
                "observation_id": UUID(str(item[0])),
                "roster_sha256": str(item[5]),
            }
            for item in observations
        ]
        gap_roster = [
            {
                "binding_id": UUID(str(item[0])),
                "gap_id": UUID(str(item[1])),
                "terminal_status": str(item[2]),
            }
            for item in gaps
        ]
        sealed_at = self.database_now()
        seal = MarketArchiveSeal.create(
            market_archive_seal_id=seal_id,
            archive=archive,
            terminal_slices=archive.slices,
            sealed_at=sealed_at,
            disposition=disposition,
            capture_count=len(observations),
            capture_roster_sha256=canonical_json_sha256(capture_roster),
            artifact_count=len(observations),
            artifact_roster_sha256=canonical_json_sha256(artifact_roster),
            normalized_revision_count=sum(int(item[4]) for item in observations),
            normalized_revision_roster_sha256=canonical_json_sha256(normalized_roster),
            gap_count=len(gaps),
            gap_roster_sha256=canonical_json_sha256(gap_roster),
        )
        self._connection.execute(
            """
            INSERT INTO mra.market_archive_seal (
                market_archive_seal_id, market_archive_id, sealed_at,
                knowledge_cutoff, disposition, slice_count,
                slice_roster_sha256, capture_count, capture_roster_sha256,
                artifact_count, artifact_roster_sha256,
                normalized_revision_count, normalized_revision_roster_sha256,
                gap_count, gap_roster_sha256, content_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                seal.market_archive_seal_id,
                seal.market_archive_id,
                seal.sealed_at,
                seal.knowledge_cutoff,
                seal.disposition.value,
                seal.slice_count,
                str(seal.slice_roster_sha256),
                seal.capture_count,
                str(seal.capture_roster_sha256),
                seal.artifact_count,
                str(seal.artifact_roster_sha256),
                seal.normalized_revision_count,
                str(seal.normalized_revision_roster_sha256),
                seal.gap_count,
                str(seal.gap_roster_sha256),
                str(seal.content_sha256),
            ),
        )
        return seal

    def get_seal(self, seal_id: UUID) -> MarketArchiveSeal:
        row = self._connection.execute(
            """
            SELECT market_archive_id, sealed_at, knowledge_cutoff, disposition,
                   slice_count, slice_roster_sha256, capture_count,
                   capture_roster_sha256, artifact_count, artifact_roster_sha256,
                   normalized_revision_count, normalized_revision_roster_sha256,
                   gap_count, gap_roster_sha256, content_sha256
            FROM mra.market_archive_seal WHERE market_archive_seal_id = %s
            """,
            (seal_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Market archive seal {seal_id} does not exist")
        return MarketArchiveSeal(
            market_archive_seal_id=seal_id,
            market_archive_id=UUID(str(row[0])),
            sealed_at=row[1],
            knowledge_cutoff=row[2],
            disposition=ArchiveSealDisposition(str(row[3])),
            slice_count=int(row[4]),
            slice_roster_sha256=ContentHash(str(row[5])),
            capture_count=int(row[6]),
            capture_roster_sha256=ContentHash(str(row[7])),
            artifact_count=int(row[8]),
            artifact_roster_sha256=ContentHash(str(row[9])),
            normalized_revision_count=int(row[10]),
            normalized_revision_roster_sha256=ContentHash(str(row[11])),
            gap_count=int(row[12]),
            gap_roster_sha256=ContentHash(str(row[13])),
            content_sha256=ContentHash(str(row[14])),
        )


__all__ = ["PostgresArchiveRepository"]
