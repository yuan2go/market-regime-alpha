"""Transaction-bound PIT Outcome resolution and Evaluation input closure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.errors import (
    EvaluationAcquisitionError,
    EvaluationReconciliationError,
)
from market_regime_alpha.research_qualification.ports.evaluation_inputs import OutcomeAcquisitionResult
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class _MemberIdentity:
    member_id: UUID
    partition_id: UUID
    commitment_id: UUID
    target_definition_id: UUID
    candidate_disposition: str
    outcome_due_at: datetime


@dataclass(frozen=True, slots=True)
class _VisibleRevision:
    revision_id: UUID
    outcome_id: UUID
    revision_ordinal: int
    commitment_id: UUID
    target_definition_id: UUID
    observation_cutoff: datetime
    knowledge_cutoff: datetime
    outcome_status: str


class PostgresTransactionalOutcomeAcquisition:
    """Exact-as-of resolver that only returns committed-safe identities/counts."""

    def __init__(self, connection: psycopg.Connection[Any], *, id_factory: Callable[[], UUID]) -> None:
        self._connection = connection
        self._id_factory = id_factory

    def acquire(self, evaluation_run_id: UUID) -> OutcomeAcquisitionResult:
        preliminary = self._connection.execute(
            """
            SELECT research_partition_id, target_definition_id,
                   requested_knowledge_cutoff, expected_member_count,
                   status, input_roster_sha256, access_count,
                   observation_count
            FROM mra.evaluation_run
            WHERE evaluation_run_id = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
        if preliminary is None:
            raise EvaluationAcquisitionError("EvaluationRun does not exist")
        if preliminary[4] in {"INPUTS_ACQUIRED", "COMPLETED"}:
            if preliminary[5] is None:
                raise EvaluationReconciliationError("acquired EvaluationRun has no roster hash")
            return OutcomeAcquisitionResult(
                evaluation_run_id, int(preliminary[6]), int(preliminary[7]), str(preliminary[5])
            )
        if preliminary[4] != "OPEN":
            raise EvaluationAcquisitionError("EvaluationRun is not OPEN")
        partition_id = UUID(str(preliminary[0]))
        target_id = UUID(str(preliminary[1]))
        cutoff = preliminary[2]
        members = self._load_members(partition_id)
        if len(members) != int(preliminary[3]):
            raise EvaluationAcquisitionError("Partition member roster is incomplete")
        if any(member.target_definition_id != target_id for member in members):
            raise EvaluationAcquisitionError("Partition member Target mismatch")
        revisions = tuple(self._resolve_visible(member, cutoff) for member in members)

        # Preserve global lock order: Outcome (#9), Partition (#10), Evaluation (#11).
        outcome_ids = sorted({item.outcome_id for item in revisions}, key=str)
        revision_ids = sorted({item.revision_id for item in revisions}, key=str)
        locked_outcomes = self._connection.execute(
            """
            SELECT market_target_outcome_id FROM mra.market_target_outcome
            WHERE market_target_outcome_id = ANY(%s::uuid[])
            ORDER BY market_target_outcome_id FOR SHARE
            """,
            (outcome_ids,),
        ).fetchall()
        locked_revisions = self._connection.execute(
            """
            SELECT market_target_outcome_revision_id
            FROM mra.market_target_outcome_revision
            WHERE market_target_outcome_revision_id = ANY(%s::uuid[])
            ORDER BY market_target_outcome_revision_id FOR SHARE
            """,
            (revision_ids,),
        ).fetchall()
        if len(locked_outcomes) != len(outcome_ids) or len(locked_revisions) != len(revision_ids):
            raise EvaluationAcquisitionError("exact Outcome revision disappeared before lock")

        self._connection.execute(
            "SELECT research_partition_id FROM mra.research_partition WHERE research_partition_id = %s FOR SHARE",
            (partition_id,),
        ).fetchone()
        locked_members = self._load_members(partition_id, lock=True)
        if locked_members != members:
            raise EvaluationAcquisitionError("Partition roster changed before acquisition")
        run = self._connection.execute(
            """
            SELECT status, requested_knowledge_cutoff, expected_member_count
            FROM mra.evaluation_run
            WHERE evaluation_run_id = %s
            FOR UPDATE
            """,
            (evaluation_run_id,),
        ).fetchone()
        if run is None or run[0] != "OPEN" or run[1] != cutoff or int(run[2]) != len(members):
            raise EvaluationAcquisitionError("Gate B no longer holds")
        existing = self._connection.execute(
            "SELECT count(*) FROM mra.research_partition_outcome_access WHERE evaluation_run_id = %s",
            (evaluation_run_id,),
        ).fetchone()
        assert existing is not None
        if int(existing[0]) != 0:
            raise EvaluationAcquisitionError("Gate B requires zero access for this EvaluationRun")

        for member_id in sorted((item.member_id for item in members), key=str):
            self._connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"research-outcome-access:{member_id}",),
            )

        roster_items: list[tuple[UUID, UUID, UUID, int]] = []
        for member, revision in zip(members, revisions, strict=True):
            ordinal_row = self._connection.execute(
                """
                SELECT coalesce(max(access_ordinal), 0) + 1
                FROM mra.research_partition_outcome_access
                WHERE research_partition_member_id = %s
                """,
                (member.member_id,),
            ).fetchone()
            assert ordinal_row is not None
            access_ordinal = int(ordinal_row[0])
            access_id = self._id_factory()
            access_hash = canonical_json_sha256(
                {
                    "access_ordinal": access_ordinal,
                    "evaluation_run_id": evaluation_run_id,
                    "member_id": member.member_id,
                    "revision_id": revision.revision_id,
                }
            )
            self._connection.execute(
                """
                INSERT INTO mra.research_partition_outcome_access (
                    research_partition_outcome_access_id,
                    evaluation_run_id, research_partition_member_id,
                    research_partition_id, commitment_id,
                    target_definition_id,
                    market_target_outcome_revision_id,
                    market_target_outcome_id, revision_ordinal,
                    observation_cutoff, knowledge_cutoff,
                    outcome_status, access_ordinal, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    access_id, evaluation_run_id, member.member_id,
                    member.partition_id, member.commitment_id,
                    member.target_definition_id, revision.revision_id,
                    revision.outcome_id, revision.revision_ordinal,
                    revision.observation_cutoff, revision.knowledge_cutoff,
                    revision.outcome_status, access_ordinal, access_hash,
                ),
            )
            observation_id = self._id_factory()
            observation_hash = canonical_json_sha256(
                {
                    "access_id": access_id,
                    "candidate_disposition": member.candidate_disposition,
                    "outcome_status": revision.outcome_status,
                }
            )
            self._connection.execute(
                """
                INSERT INTO mra.evaluation_observation (
                    evaluation_observation_id, evaluation_run_id,
                    research_partition_member_id, research_partition_id,
                    outcome_access_id, market_target_outcome_revision_id,
                    candidate_disposition, outcome_status, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    observation_id, evaluation_run_id, member.member_id,
                    member.partition_id, access_id, revision.revision_id,
                    member.candidate_disposition, revision.outcome_status,
                    observation_hash,
                ),
            )
            roster_items.append((member.member_id, access_id, revision.revision_id, access_ordinal))
        counts = self._connection.execute(
            """
            SELECT count(DISTINCT access.research_partition_outcome_access_id),
                   count(DISTINCT observation.evaluation_observation_id)
            FROM mra.research_partition_outcome_access AS access
            FULL JOIN mra.evaluation_observation AS observation
              ON observation.outcome_access_id = access.research_partition_outcome_access_id
            WHERE coalesce(access.evaluation_run_id, observation.evaluation_run_id) = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
        assert counts is not None
        if int(counts[0]) != len(members) or int(counts[1]) != len(members):
            raise EvaluationReconciliationError("Outcome access/Observation roster is incomplete")
        roster_hash = canonical_json_sha256(tuple(roster_items))
        changed = self._connection.execute(
            """
            UPDATE mra.evaluation_run
            SET status = 'INPUTS_ACQUIRED',
                inputs_acquired_at = clock_timestamp(),
                access_count = %s, observation_count = %s,
                input_roster_sha256 = %s, version = version + 1
            WHERE evaluation_run_id = %s AND status = 'OPEN'
            """,
            (len(members), len(members), roster_hash, evaluation_run_id),
        ).rowcount
        if changed != 1:
            raise EvaluationAcquisitionError("EvaluationRun transition lost a concurrent race")
        return OutcomeAcquisitionResult(
            evaluation_run_id, len(members), len(members), roster_hash
        )

    def _load_members(self, partition_id: UUID, *, lock: bool = False) -> tuple[_MemberIdentity, ...]:
        rows = self._connection.execute(
            """
            SELECT research_partition_member_id, research_partition_id,
                   commitment_id, target_definition_id,
                   candidate_disposition, outcome_due_at
            FROM mra.research_partition_member
            WHERE research_partition_id = %s
            ORDER BY member_ordinal
            """ + (" FOR SHARE" if lock else ""),
            (partition_id,),
        ).fetchall()
        return tuple(
            _MemberIdentity(
                UUID(str(row[0])), UUID(str(row[1])), UUID(str(row[2])),
                UUID(str(row[3])), str(row[4]), row[5],
            )
            for row in rows
        )

    def _resolve_visible(self, member: _MemberIdentity, cutoff: datetime) -> _VisibleRevision:
        if member.outcome_due_at > cutoff:
            raise EvaluationAcquisitionError(
                f"NOT_DUE commitment {member.commitment_id} cannot be acquired"
            )
        rows = self._connection.execute(
            """
            WITH eligible AS (
                SELECT revision.*
                FROM mra.market_target_outcome_revision AS revision
                WHERE revision.commitment_id = %s
                  AND revision.target_definition_id = %s
                  AND revision.observation_cutoff <= %s
                  AND revision.knowledge_cutoff <= %s
                  AND revision.settled_at <= %s
            )
            SELECT eligible.market_target_outcome_revision_id,
                   eligible.market_target_outcome_id,
                   eligible.revision_ordinal, eligible.commitment_id,
                   eligible.target_definition_id,
                   eligible.observation_cutoff, eligible.knowledge_cutoff,
                   eligible.outcome_status
            FROM eligible
            WHERE NOT EXISTS (
                SELECT 1 FROM eligible AS successor
                WHERE successor.supersedes_revision_id =
                      eligible.market_target_outcome_revision_id
            )
            """,
            (
                member.commitment_id, member.target_definition_id,
                cutoff, cutoff, cutoff,
            ),
        ).fetchall()
        if len(rows) != 1:
            qualifier = "missing" if not rows else "ambiguous"
            raise EvaluationAcquisitionError(
                f"due Outcome has {qualifier} unique visible revision"
            )
        row = rows[0]
        return _VisibleRevision(
            UUID(str(row[0])), UUID(str(row[1])), int(row[2]),
            UUID(str(row[3])), UUID(str(row[4])), row[5], row[6], str(row[7]),
        )


__all__ = ["PostgresTransactionalOutcomeAcquisition"]
