"""PostgreSQL writer for immutable ResearchPartition rosters."""

from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.partition import ResearchPartitionPlan
from market_regime_alpha.research_qualification.ports.partition_inputs import (
    DerivedPartitionMember,
    PartitionCalendarBounds,
)
from market_regime_alpha.research_qualification.ports.partition_uow import (
    ResearchPartitionRecord,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeNotFoundError
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresResearchPartitionRepository:
    def __init__(
        self,
        connection: psycopg.Connection[Any],
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._connection = connection
        self._id_factory = id_factory

    def lock_identity(self, partition_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"research-partition:{partition_code}",),
        )

    def insert(
        self,
        plan: ResearchPartitionPlan,
        bounds: PartitionCalendarBounds,
        members: tuple[DerivedPartitionMember, ...],
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ResearchPartitionRecord:
        source_values: tuple[object | None, ...] = (
            None,
            None,
            None,
            None,
            None,
            None,
        )
        if plan.backtest_source is not None:
            source = plan.backtest_source
            row = self._connection.execute(
                """
                SELECT current_specification_sha256
                FROM mra.exploratory_backtest_run
                WHERE exploratory_backtest_run_id = %s
                  AND current_specification_sha256 IS NOT NULL
                """,
                (source.exploratory_backtest_run_id,),
            ).fetchone()
            if row is None:
                raise ArtifactIntegrityError(
                    "Backtest Partition source lacks current specification"
                )
            source_values = (
                source.exploratory_backtest_run_id,
                source.exploratory_backtest_arm_id,
                source.exploratory_backtest_fold_id,
                str(row[0]),
                None if source.context_kind is None else source.context_kind.value,
                None if source.context_state is None else source.context_state.value,
            )
        member_rows = tuple(
            (
                self._id_factory(),
                ordinal,
                member,
                canonical_json_sha256(
                    {
                        "candidate_disposition": member.candidate_disposition,
                        "commitment_id": member.commitment_id,
                        "commitment_recorded_at": member.commitment_recorded_at,
                        "decision_reference_observation_id": member.decision_reference_observation_id,
                        "decision_session_id": member.decision_session_id,
                        "decision_session_date": member.decision_session_date,
                        "decision_time": member.decision_time,
                        "earliest_outcome_event_at": member.earliest_outcome_event_at,
                        "outcome_due_at": member.outcome_due_at,
                        "runtime_mode": member.runtime_mode,
                        "exchange_code": member.exchange_code,
                        "target_definition_id": member.target_definition_id,
                        "timezone_name": member.timezone_name,
                    }
                ),
            )
            for ordinal, member in enumerate(members, start=1)
        )
        roster_hash = canonical_json_sha256(
            tuple(
                {
                    "commitment_id": member.commitment_id,
                    "content_sha256": digest,
                    "member_ordinal": ordinal,
                }
                for _, ordinal, member, digest in member_rows
            )
        )
        content_hash = canonical_json_sha256(
            {
                "bounds": bounds,
                "member_count": len(members),
                "member_roster_sha256": roster_hash,
                "plan_sha256": plan.content_sha256,
            }
        )
        self._connection.execute(
            """
            INSERT INTO mra.research_partition (
                research_partition_id, partition_code, status,
                target_definition_id, target_version,
                target_definition_sha256, purpose, population_scope,
                overlap_policy, exchange_code, timezone_name,
                calendar_session_count, calendar_roster_sha256,
                decision_start_session_id,
                decision_end_session_id, decision_start_date,
                decision_end_date, outcome_horizon_sessions,
                purge_before_sessions, purge_after_sessions,
                embargo_sessions, protected_start_session_id,
                protected_end_session_id, protected_start_date,
                protected_end_date, series_code, fold_ordinal,
                member_count, member_roster_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256,
                source_backtest_run_id, source_backtest_arm_id,
                source_backtest_fold_id, source_backtest_sha256,
                source_context_kind, source_context_state
            ) VALUES (
                %s, %s, 'FROZEN', %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                plan.research_partition_id,
                plan.partition_code,
                plan.target_definition_id,
                plan.target_version,
                str(plan.target_definition_sha256),
                plan.purpose.value,
                plan.population_scope.value,
                plan.overlap_policy.value,
                bounds.exchange_code,
                bounds.timezone_name,
                bounds.calendar_session_count,
                bounds.calendar_roster_sha256,
                plan.decision_start_session_id,
                plan.decision_end_session_id,
                bounds.decision_start_date,
                bounds.decision_end_date,
                bounds.outcome_horizon_sessions,
                plan.purge_before_sessions,
                plan.purge_after_sessions,
                plan.embargo_sessions,
                bounds.protected_start_session_id,
                bounds.protected_end_session_id,
                bounds.protected_start_date,
                bounds.protected_end_date,
                plan.series_code,
                plan.fold_ordinal,
                len(members),
                roster_hash,
                plan.code_artifact.artifact_id,
                str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256),
                plan.config_artifact.size_bytes,
                str(plan.provenance_sha256),
                content_hash,
                request_identity,
                request_sha256,
                *source_values,
            ),
        )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.research_partition_member (
                    research_partition_member_id, research_partition_id,
                    member_ordinal, commitment_id,
                    decision_reference_observation_id,
                    target_definition_id,
                    decision_time, candidate_disposition,
                    commitment_recorded_at, runtime_mode,
                    decision_session_id, decision_session_date,
                    exchange_code, timezone_name, earliest_outcome_event_at,
                    outcome_due_at, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    (
                        member_id,
                        plan.research_partition_id,
                        ordinal,
                        member.commitment_id,
                        member.decision_reference_observation_id,
                        member.target_definition_id,
                        member.decision_time,
                        member.candidate_disposition,
                        member.commitment_recorded_at,
                        member.runtime_mode,
                        member.decision_session_id,
                        member.decision_session_date,
                        member.exchange_code,
                        member.timezone_name,
                        member.earliest_outcome_event_at,
                        member.outcome_due_at,
                        digest,
                    )
                    for member_id, ordinal, member, digest in member_rows
                ),
            )
        return self.record(plan.research_partition_id, lock=False)

    def record(
        self, research_partition_id: UUID, *, lock: bool
    ) -> ResearchPartitionRecord:
        row = self._connection.execute(
            """
            SELECT research_partition_id, exchange_code, timezone_name,
                   target_definition_id,
                   target_version, target_definition_sha256, purpose,
                   calendar_session_count, calendar_roster_sha256,
                   member_count, member_roster_sha256, content_sha256,
                   frozen_at
            FROM mra.research_partition
            WHERE research_partition_id = %s
            """ + (" FOR SHARE" if lock else ""),
            (research_partition_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"ResearchPartition {research_partition_id} does not exist"
            )
        return ResearchPartitionRecord(
            research_partition_id=UUID(str(row[0])),
            exchange_code=str(row[1]),
            timezone_name=str(row[2]),
            target_definition_id=UUID(str(row[3])),
            target_version=int(row[4]),
            target_definition_sha256=str(row[5]),
            purpose=str(row[6]),
            calendar_session_count=int(row[7]),
            calendar_roster_sha256=str(row[8]),
            member_count=int(row[9]),
            member_roster_sha256=str(row[10]),
            content_sha256=str(row[11]),
            frozen_at=row[12],
        )

    def reconcile(self, research_partition_id: UUID) -> bool:
        record = self.record(research_partition_id, lock=True)
        rows = self._connection.execute(
            """
            SELECT member_ordinal, commitment_id, content_sha256
            FROM mra.research_partition_member
            WHERE research_partition_id = %s
            ORDER BY member_ordinal
            FOR SHARE
            """,
            (research_partition_id,),
        ).fetchall()
        actual_hash = canonical_json_sha256(
            tuple(
                {
                    "commitment_id": UUID(str(row[1])),
                    "content_sha256": str(row[2]),
                    "member_ordinal": int(row[0]),
                }
                for row in rows
            )
        )
        matched = (
            len(rows) == record.member_count
            and tuple(int(row[0]) for row in rows)
            == tuple(range(1, record.member_count + 1))
            and actual_hash == record.member_roster_sha256
        )
        if not matched:
            raise ArtifactIntegrityError("ResearchPartition roster does not reconcile")
        return True


__all__ = ["PostgresResearchPartitionRepository"]
