"""PostgreSQL writer for immutable Evaluation-bound Research Evidence."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.evidence import EvidenceItemPlan
from market_regime_alpha.research_qualification.ports.evidence_uow import (
    EvidenceItemRecord,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError, RuntimeStateConflictError


class PostgresEvidenceRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_identity(self, evaluation_run_id: UUID, evidence_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"research-evidence:{evaluation_run_id}:{evidence_code}",),
        )

    def record(
        self,
        plan: EvidenceItemPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> EvidenceItemRecord:
        authority = self._connection.execute(
            """
            SELECT run.experiment_id, run.evaluation_protocol_id,
                   run.target_definition_id, run.partition_purpose,
                   coalesce(run.completed_at, run.failed_at),
                   run.research_partition_id
            FROM mra.evaluation_run AS run
            WHERE run.evaluation_run_id = %s
              AND run.status IN ('COMPLETED', 'FAILED')
            FOR SHARE
            """,
            (plan.evaluation_run_id,),
        ).fetchone()
        if authority is None:
            raise RuntimeStateConflictError(
                "Evidence requires an exact terminal EvaluationRun"
            )
        generation = self._connection.execute(
            """
            SELECT max(decision_time)
            FROM mra.research_partition_member
            WHERE research_partition_id = %s
            """,
            (authority[5],),
        ).fetchone()
        if generation is None or generation[0] is None:
            raise RuntimeStateConflictError(
                "Evidence Evaluation source generation is empty"
            )

        evaluation_protocol_metric_id = None
        if plan.evaluation_metric_id is not None:
            metric = self._connection.execute(
                """
                SELECT evaluation_protocol_metric_id
                FROM mra.evaluation_metric
                WHERE evaluation_metric_id = %s AND evaluation_run_id = %s
                FOR SHARE
                """,
                (plan.evaluation_metric_id, plan.evaluation_run_id),
            ).fetchone()
            if metric is None:
                raise RuntimeStateConflictError(
                    "Evidence metric does not belong to the EvaluationRun"
                )
            evaluation_protocol_metric_id = metric[0]

        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.evidence_dependency (
                    evidence_dependency_id, child_evidence_item_id,
                    parent_evidence_item_id, dependency_ordinal,
                    dependency_role, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        dependency.evidence_dependency_id,
                        plan.evidence_item_id,
                        dependency.parent_evidence_item_id,
                        dependency.ordinal,
                        dependency.dependency_role.value,
                        str(dependency.content_sha256),
                    )
                    for dependency in plan.dependencies
                ),
            )

        self._connection.execute(
            """
            INSERT INTO mra.evidence_item (
                evidence_item_id, evidence_code, evaluation_run_id,
                experiment_id, evaluation_protocol_id, target_definition_id,
                partition_purpose, evaluation_metric_id,
                evaluation_protocol_metric_id, evidence_scope,
                evidence_class, origin_class, evidence_role,
                evidence_direction, proof_ceiling, evaluation_terminal_at,
                source_generation_max_decision_time, observed_at,
                evidence_artifact_id, evidence_content_sha256,
                evidence_size_bytes, code_artifact_id, code_content_sha256,
                code_size_bytes, config_artifact_id, config_content_sha256,
                config_size_bytes, provenance_sha256, dependency_count,
                dependency_roster_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s
            )
            """,
            (
                plan.evidence_item_id,
                plan.evidence_code,
                plan.evaluation_run_id,
                authority[0],
                authority[1],
                authority[2],
                authority[3],
                plan.evaluation_metric_id,
                evaluation_protocol_metric_id,
                plan.scope.value,
                plan.evidence_class.value,
                plan.origin_class.value,
                plan.role.value,
                plan.direction.value,
                plan.proof_ceiling.value,
                authority[4],
                generation[0],
                plan.observed_at,
                plan.evidence_artifact.artifact_id,
                str(plan.evidence_artifact.content_sha256),
                plan.evidence_artifact.size_bytes,
                plan.code_artifact.artifact_id,
                str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256),
                plan.config_artifact.size_bytes,
                str(plan.provenance_sha256),
                plan.dependency_count,
                str(plan.dependency_roster_sha256),
                str(plan.content_sha256),
                request_identity,
                request_sha256,
            ),
        )
        return self.item_record(plan.evidence_item_id, lock=False)

    def item_record(
        self, evidence_item_id: UUID, *, lock: bool
    ) -> EvidenceItemRecord:
        row = self._connection.execute(
            """
            SELECT evidence_item_id, evaluation_run_id, dependency_count,
                   dependency_roster_sha256, content_sha256, recorded_at
            FROM mra.evidence_item
            WHERE evidence_item_id = %s
            """
            + (" FOR SHARE" if lock else ""),
            (evidence_item_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"EvidenceItem {evidence_item_id} does not exist"
            )
        return EvidenceItemRecord(
            evidence_item_id=UUID(str(row[0])),
            evaluation_run_id=UUID(str(row[1])),
            dependency_count=int(row[2]),
            dependency_roster_sha256=str(row[3]),
            content_sha256=str(row[4]),
            recorded_at=row[5],
        )


__all__ = ["PostgresEvidenceRepository"]
