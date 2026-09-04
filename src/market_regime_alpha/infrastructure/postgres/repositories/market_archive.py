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
    ProspectiveArchiveGenerationPlan,
    ProspectiveArchivePlanningGap,
)
from market_regime_alpha.market.ports.archive import (
    ArchiveResourceStopRecord,
    ArchiveSliceGapRecord,
)
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

    def insert_prospective_generation(
        self,
        plan: ProspectiveArchiveGenerationPlan,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.prospective_archive_generation (
                market_archive_id, series_code, generation,
                predecessor_market_archive_id, exchange_code,
                target_definition_id, target_version,
                target_definition_sha256, reference_checkpoint_id,
                outcome_checkpoint_id, decision_session_id,
                outcome_session_id, later_verification_session_id,
                member_count, member_roster_sha256,
                schedule_count, schedule_roster_sha256,
                provenance_sha256, content_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                plan.market_archive_id,
                plan.series_code,
                plan.generation,
                plan.predecessor_market_archive_id,
                plan.exchange,
                plan.target_definition_id,
                plan.target_version,
                str(plan.target_definition_sha256),
                plan.reference_checkpoint_id,
                plan.outcome_checkpoint_id,
                plan.decision_session_id,
                plan.outcome_session_id,
                plan.later_verification_session_id,
                len(plan.members),
                str(plan.member_roster_sha256),
                len(plan.schedules),
                str(plan.schedule_roster_sha256),
                str(plan.provenance_sha256),
                str(plan.content_sha256),
            ),
        )
        member_ordinals = {
            item.instrument_id: item.ordinal for item in plan.members
        }
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.prospective_archive_generation_member (
                    market_archive_id, ordinal, instrument_id,
                    instrument_identifier_id, content_sha256
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    (
                        plan.market_archive_id,
                        item.ordinal,
                        item.instrument_id,
                        item.instrument_identifier_id,
                        str(item.content_sha256),
                    )
                    for item in plan.members
                ),
            )

            cursor.executemany(
                """
                INSERT INTO mra.prospective_archive_slice_schedule (
                    market_archive_slice_id, market_archive_id, ordinal,
                    instrument_id, member_ordinal, schedule_slot,
                    trading_session_id, target_checkpoint_id,
                    comparison_ordinal, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        item.market_archive_slice_id,
                        plan.market_archive_id,
                        item.ordinal,
                        item.instrument_id,
                        member_ordinals[item.instrument_id],
                        item.slot.value,
                        item.trading_session_id,
                        item.target_checkpoint_id,
                        item.comparison_ordinal,
                        str(item.content_sha256),
                    )
                    for item in plan.schedules
                ),
            )

    def insert_prospective_planning_gap(
        self,
        gap: ProspectiveArchivePlanningGap,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.prospective_archive_planning_gap (
                prospective_archive_planning_gap_id, series_code,
                expected_generation, predecessor_market_archive_id,
                target_definition_id, target_version,
                target_definition_sha256, expected_decision_session_id,
                detected_at, reason_code, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                gap.prospective_archive_planning_gap_id,
                gap.series_code,
                gap.expected_generation,
                gap.predecessor_market_archive_id,
                gap.target_definition_id,
                gap.target_version,
                str(gap.target_definition_sha256),
                gap.expected_decision_session_id,
                gap.detected_at,
                gap.reason_code,
                str(gap.content_sha256),
            ),
        )

    def get_prospective_planning_gap(
        self,
        planning_gap_id: UUID,
    ) -> ProspectiveArchivePlanningGap:
        row = self._connection.execute(
            """
            SELECT series_code, expected_generation,
                   predecessor_market_archive_id, target_definition_id,
                   target_version, target_definition_sha256,
                   expected_decision_session_id, detected_at,
                   reason_code, content_sha256
            FROM mra.prospective_archive_planning_gap
            WHERE prospective_archive_planning_gap_id = %s
            """,
            (planning_gap_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"Prospective planning gap {planning_gap_id} does not exist"
            )
        gap = ProspectiveArchivePlanningGap(
            prospective_archive_planning_gap_id=planning_gap_id,
            series_code=str(row[0]),
            expected_generation=int(row[1]),
            predecessor_market_archive_id=(
                UUID(str(row[2])) if row[2] is not None else None
            ),
            target_definition_id=UUID(str(row[3])),
            target_version=int(row[4]),
            target_definition_sha256=str(row[5]),
            expected_decision_session_id=UUID(str(row[6])),
            detected_at=row[7],
            reason_code=str(row[8]),
        )
        if str(gap.content_sha256) != str(row[9]):
            raise RuntimeStateConflictError(
                "persisted prospective planning gap does not reconcile"
            )
        return gap

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
                     WHEN terminal.market_archive_slice_id IS NOT NULL THEN terminal.terminal_state
                     WHEN resource_stop.market_archive_resource_stop_id IS NOT NULL THEN 'RESOURCE_LIMIT'
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
            LEFT JOIN mra.market_archive_resource_stop AS resource_stop
              ON resource_stop.market_archive_slice_id = slice.market_archive_slice_id
            LEFT JOIN mra.prospective_archive_slice_terminal AS terminal
              ON terminal.market_archive_slice_id = slice.market_archive_slice_id
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
        if (
            str(root[0]) == ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS.value
            and (requested_at < slice_row[0] or capture[3] < slice_row[0])
        ):
            raise RuntimeStateConflictError(
                "Prospective archive observation cannot precede its frozen window"
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
        self._record_prospective_observation_closure(observation)
        return observation

    def _record_prospective_observation_closure(
        self,
        observation: ArchiveCaptureObservation,
    ) -> None:
        schedule = self._connection.execute(
            """
            SELECT instrument_id, comparison_ordinal, target_checkpoint_id
            FROM mra.prospective_archive_slice_schedule
            WHERE market_archive_slice_id = %s
            FOR UPDATE
            """,
            (observation.market_archive_slice_id,),
        ).fetchone()
        if schedule is None:
            return
        prior = self._connection.execute(
            """
            SELECT market_archive_capture_observation_id,
                   comparison_ordinal, artifact_sha256,
                   normalized_revision_roster_sha256
            FROM mra.prospective_archive_revision_observation
            WHERE market_archive_id = %s AND instrument_id = %s
              AND target_checkpoint_id = %s
            ORDER BY comparison_ordinal DESC LIMIT 1 FOR UPDATE
            """,
            (observation.market_archive_id, schedule[0], schedule[2]),
        ).fetchone()
        relation = (
            "FIRST"
            if prior is None
            else "IDENTICAL"
            if str(prior[2]) == str(observation.artifact_sha256)
            and str(prior[3])
            == str(observation.normalized_revision_roster_sha256)
            else "CHANGED"
        )
        revision_payload = {
            "artifact_sha256": str(observation.artifact_sha256),
            "comparison_ordinal": int(schedule[1]),
            "instrument_id": UUID(str(schedule[0])),
            "market_archive_capture_observation_id": (
                observation.market_archive_capture_observation_id
            ),
            "market_archive_id": observation.market_archive_id,
            "market_archive_slice_id": observation.market_archive_slice_id,
            "target_checkpoint_id": UUID(str(schedule[2])),
            "normalized_revision_roster_sha256": str(
                observation.normalized_revision_roster_sha256
            ),
            "predecessor_observation_id": (
                None if prior is None else UUID(str(prior[0]))
            ),
            "relation": relation,
        }
        self._connection.execute(
            """
            INSERT INTO mra.prospective_archive_revision_observation (
                market_archive_capture_observation_id, market_archive_id,
                market_archive_slice_id, instrument_id,
                target_checkpoint_id, comparison_ordinal,
                predecessor_observation_id, relation,
                artifact_sha256, normalized_revision_roster_sha256,
                content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                observation.market_archive_capture_observation_id,
                observation.market_archive_id,
                observation.market_archive_slice_id,
                schedule[0],
                schedule[2],
                schedule[1],
                revision_payload["predecessor_observation_id"],
                relation,
                str(observation.artifact_sha256),
                str(observation.normalized_revision_roster_sha256),
                canonical_json_sha256(revision_payload),
            ),
        )
        state = (
            "CAPTURED_ON_TIME"
            if observation.timeliness is ArchiveObservationTimeliness.ON_TIME
            else "CAPTURED_LATE"
        )
        self._insert_terminal(
            observation.market_archive_id,
            observation.market_archive_slice_id,
            state,
            f"ARCHIVE_{state}",
        )

    def _insert_terminal(
        self,
        market_archive_id: UUID,
        market_archive_slice_id: UUID,
        terminal_state: str,
        reason_code: str,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.prospective_archive_slice_terminal (
                market_archive_slice_id, market_archive_id,
                terminal_state, reason_code, content_sha256
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                market_archive_slice_id,
                market_archive_id,
                terminal_state,
                reason_code,
                "0" * 64,
            ),
        )

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
        if self._connection.execute(
            "SELECT 1 FROM mra.prospective_archive_slice_schedule WHERE market_archive_slice_id = %s",
            (market_archive_slice_id,),
        ).fetchone() is not None:
            self._insert_terminal(
                market_archive_id,
                market_archive_slice_id,
                "PROVIDER_GAP",
                "PROVIDER_CAPTURE_GAP",
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

    def record_resource_stop(
        self,
        *,
        resource_stop_id: UUID,
        market_archive_id: UUID,
        market_archive_slice_id: UUID,
        observed_free_bytes: int,
    ) -> ArchiveResourceStopRecord:
        root = self._connection.execute(
            """
            SELECT reserved_free_bytes + maximum_slice_bytes
            FROM mra.market_archive WHERE market_archive_id = %s FOR UPDATE
            """,
            (market_archive_id,),
        ).fetchone()
        if root is None:
            raise RuntimeNotFoundError("Market archive resource-stop root is missing")
        required_free_bytes = int(root[0])
        reason_code = "DISK_RESERVED_FLOOR"
        content_hash = canonical_json_sha256(
            {
                "market_archive_id": market_archive_id,
                "market_archive_resource_stop_id": resource_stop_id,
                "market_archive_slice_id": market_archive_slice_id,
                "observed_free_bytes": observed_free_bytes,
                "reason_code": reason_code,
                "required_free_bytes": required_free_bytes,
            }
        )
        self._connection.execute(
            """
            INSERT INTO mra.market_archive_resource_stop (
                market_archive_resource_stop_id, market_archive_id,
                market_archive_slice_id, observed_free_bytes,
                required_free_bytes, reason_code, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resource_stop_id,
                market_archive_id,
                market_archive_slice_id,
                observed_free_bytes,
                required_free_bytes,
                reason_code,
                content_hash,
            ),
        )
        if self._connection.execute(
            "SELECT 1 FROM mra.prospective_archive_slice_schedule WHERE market_archive_slice_id = %s",
            (market_archive_slice_id,),
        ).fetchone() is not None:
            self._insert_terminal(
                market_archive_id,
                market_archive_slice_id,
                "RESOURCE_STOP",
                "DISK_RESERVED_FLOOR",
            )
        return ArchiveResourceStopRecord(
            market_archive_resource_stop_id=resource_stop_id,
            market_archive_id=market_archive_id,
            market_archive_slice_id=market_archive_slice_id,
            observed_free_bytes=observed_free_bytes,
            required_free_bytes=required_free_bytes,
            reason_code=reason_code,
            content_sha256=content_hash,
        )

    def finalize_overdue(
        self,
        market_archive_id: UUID,
    ) -> tuple[UUID, ...]:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"prospective-overdue:{market_archive_id}",),
        )
        rows = self._connection.execute(
            """
            SELECT schedule.market_archive_slice_id
            FROM mra.prospective_archive_slice_schedule AS schedule
            JOIN mra.market_archive_slice AS slice
              ON slice.market_archive_slice_id = schedule.market_archive_slice_id
            LEFT JOIN mra.prospective_archive_slice_terminal AS terminal
              ON terminal.market_archive_slice_id = schedule.market_archive_slice_id
            WHERE schedule.market_archive_id = %s
              AND terminal.market_archive_slice_id IS NULL
              AND slice.event_window_end < clock_timestamp()
            ORDER BY schedule.ordinal
            FOR UPDATE OF slice
            """,
            (market_archive_id,),
        ).fetchall()
        for row in rows:
            self._insert_terminal(
                market_archive_id,
                UUID(str(row[0])),
                "MISSED",
                "CAPTURE_WINDOW_ELAPSED",
            )
        all_missed = self._connection.execute(
            """
            SELECT terminal.market_archive_slice_id
            FROM mra.prospective_archive_slice_terminal AS terminal
            JOIN mra.prospective_archive_slice_schedule AS schedule
              ON schedule.market_archive_slice_id = terminal.market_archive_slice_id
            WHERE terminal.market_archive_id = %s
              AND terminal.terminal_state = 'MISSED'
            ORDER BY schedule.ordinal
            """,
            (market_archive_id,),
        ).fetchall()
        return tuple(UUID(str(row[0])) for row in all_missed)

    def get_resource_stop(self, resource_stop_id: UUID) -> ArchiveResourceStopRecord:
        row = self._connection.execute(
            """
            SELECT market_archive_id, market_archive_slice_id,
                   observed_free_bytes, required_free_bytes, reason_code,
                   content_sha256
            FROM mra.market_archive_resource_stop
            WHERE market_archive_resource_stop_id = %s
            """,
            (resource_stop_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Archive resource stop {resource_stop_id} does not exist")
        return ArchiveResourceStopRecord(
            market_archive_resource_stop_id=resource_stop_id,
            market_archive_id=UUID(str(row[0])),
            market_archive_slice_id=UUID(str(row[1])),
            observed_free_bytes=int(row[2]),
            required_free_bytes=int(row[3]),
            reason_code=str(row[4]),
            content_sha256=str(row[5]),
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
            SELECT market_archive_slice_id, binding_id, gap_identity,
                   terminal_status, gap_kind
            FROM (
                SELECT market_archive_slice_id,
                       market_archive_slice_gap_id AS binding_id,
                       gap_id AS gap_identity,
                       terminal_status,
                       'SOURCE_GAP'::text AS gap_kind
                FROM mra.market_archive_slice_gap
                WHERE market_archive_id = %s
                UNION ALL
                SELECT market_archive_slice_id,
                       market_archive_resource_stop_id AS binding_id,
                       market_archive_resource_stop_id AS gap_identity,
                       'RESOURCE_LIMIT'::text AS terminal_status,
                       'RESOURCE_STOP'::text AS gap_kind
                FROM mra.market_archive_resource_stop
                WHERE market_archive_id = %s
            ) AS terminal_gap
            ORDER BY market_archive_slice_id
            """,
            (market_archive_id, market_archive_id),
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
                "binding_id": UUID(str(item[1])),
                "gap_id": UUID(str(item[2])),
                "gap_kind": str(item[4]),
                "terminal_status": str(item[3]),
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
