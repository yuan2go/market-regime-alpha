"""PostgreSQL derivation of complete Experiment-bound ResearchAssessment."""

from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.assessment import (
    AssessmentEvaluationSummary,
    ResearchAssessmentPlan,
    derive_assessment_status,
)
from market_regime_alpha.research_qualification.domain.evidence import EvidenceDirection
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    EvaluationRunStatus,
)
from market_regime_alpha.research_qualification.ports.assessment_uow import (
    ResearchAssessmentRecord,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError, RuntimeStateConflictError
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresAssessmentRepository:
    def __init__(
        self,
        connection: psycopg.Connection[Any],
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._connection = connection
        self._id_factory = id_factory

    def lock_identity(self, assessment_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"research-assessment:{assessment_code}",),
        )

    def assess(
        self,
        plan: ResearchAssessmentPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ResearchAssessmentRecord:
        experiment = self._connection.execute(
            """
            SELECT target_definition_id, target_version,
                   target_definition_sha256
            FROM mra.experiment
            WHERE experiment_id = %s AND status = 'REGISTERED'
            FOR SHARE
            """,
            (plan.experiment_id,),
        ).fetchone()
        if experiment is None:
            raise RuntimeNotFoundError(
                f"Experiment {plan.experiment_id} does not exist"
            )

        # These short SHARE locks make the cutoff-derived rosters stable until
        # the deferred root closure has committed.
        self._connection.execute("LOCK TABLE mra.evaluation_run IN SHARE MODE")
        self._connection.execute("LOCK TABLE mra.evidence_item IN SHARE MODE")

        evaluation_rows = self._connection.execute(
            """
            SELECT run.evaluation_run_id, run.evaluation_protocol_id,
                   run.partition_purpose, run.status,
                   coalesce(run.completed_at, run.failed_at) AS terminal_at,
                   count(metric.evaluation_metric_id) AS metric_count,
                   count(metric.evaluation_metric_id) FILTER (
                       WHERE metric.acceptance_state = 'REJECTED'
                   ) AS rejected_metric_count,
                   count(metric.evaluation_metric_id) FILTER (
                       WHERE metric.metric_state = 'NOT_ESTIMABLE'
                   ) AS not_estimable_metric_count,
                   min(member.decision_time) AS generation_min,
                   max(member.decision_time) AS generation_max
            FROM mra.evaluation_run AS run
            JOIN mra.research_partition_member AS member
              ON member.research_partition_id = run.research_partition_id
            LEFT JOIN mra.evaluation_metric AS metric
              ON metric.evaluation_run_id = run.evaluation_run_id
            WHERE run.experiment_id = %s AND run.opened_at <= %s
            GROUP BY run.evaluation_run_id, run.evaluation_protocol_id,
                     run.partition_purpose, run.status,
                     run.completed_at, run.failed_at, run.opened_at
            ORDER BY run.opened_at, run.evaluation_run_id
            """,
            (plan.experiment_id, plan.knowledge_cutoff),
        ).fetchall()
        if not evaluation_rows:
            raise RuntimeStateConflictError(
                "ResearchAssessment requires a non-empty Evaluation roster"
            )
        if any(row[3] not in {"COMPLETED", "FAILED"} for row in evaluation_rows):
            raise RuntimeStateConflictError(
                "ResearchAssessment requires every EvaluationRun terminal"
            )

        evaluation_ids = [row[0] for row in evaluation_rows]
        evidence_rows = self._connection.execute(
            """
            SELECT evidence_item_id, evaluation_run_id, evidence_class,
                   origin_class, evidence_role, evidence_direction,
                   content_sha256, recorded_at
            FROM mra.evidence_item
            WHERE evaluation_run_id = ANY(%s::uuid[])
              AND recorded_at <= %s
            ORDER BY evaluation_run_id, recorded_at, evidence_item_id
            """,
            (evaluation_ids, plan.knowledge_cutoff),
        ).fetchall()
        evidence_by_run: dict[UUID, list[Any]] = {
            UUID(str(evaluation_run_id)): [] for evaluation_run_id in evaluation_ids
        }
        for row in evidence_rows:
            evidence_by_run[UUID(str(row[1]))].append(row)
        if any(not rows for rows in evidence_by_run.values()):
            raise RuntimeStateConflictError(
                "ResearchAssessment requires Evidence for every EvaluationRun"
            )

        summaries = tuple(
            AssessmentEvaluationSummary(
                evaluation_run_id=UUID(str(row[0])),
                status=EvaluationRunStatus(str(row[3])),
                metric_count=int(row[5]),
                rejected_metric_count=int(row[6]),
                not_estimable_metric_count=int(row[7]),
            )
            for row in evaluation_rows
        )
        directions = tuple(
            EvidenceDirection(str(row[5])) for row in evidence_rows
        )
        status = derive_assessment_status(summaries, directions)

        evaluation_children: list[dict[str, Any]] = []
        evaluation_child_ids: dict[UUID, UUID] = {}
        for ordinal, row in enumerate(evaluation_rows, start=1):
            evaluation_run_id = UUID(str(row[0]))
            child_id = self._id_factory()
            evaluation_child_ids[evaluation_run_id] = child_id
            content_hash = canonical_json_sha256(
                {
                    "evaluation_protocol_id": UUID(str(row[1])),
                    "evaluation_run_id": evaluation_run_id,
                    "evaluation_status": str(row[3]),
                    "metric_count": int(row[5]),
                    "not_estimable_metric_count": int(row[7]),
                    "partition_purpose": str(row[2]),
                    "rejected_metric_count": int(row[6]),
                    "source_generation_max_decision_time": row[9],
                    "source_generation_min_decision_time": row[8],
                    "terminal_at": row[4],
                }
            )
            evaluation_children.append(
                {
                    "id": child_id,
                    "ordinal": ordinal,
                    "row": row,
                    "content_sha256": content_hash,
                }
            )

        evidence_children: list[dict[str, Any]] = []
        global_ordinal = 0
        for evaluation in evaluation_children:
            evaluation_run_id = UUID(str(evaluation["row"][0]))
            for row in evidence_by_run[evaluation_run_id]:
                global_ordinal += 1
                child_id = self._id_factory()
                content_hash = canonical_json_sha256(
                    {
                        "evidence_class": str(row[2]),
                        "evidence_direction": str(row[5]),
                        "evidence_item_id": UUID(str(row[0])),
                        "evidence_role": str(row[4]),
                        "evaluation_run_id": evaluation_run_id,
                        "origin_class": str(row[3]),
                        "research_assessment_evaluation_id": evaluation["id"],
                    }
                )
                evidence_children.append(
                    {
                        "id": child_id,
                        "ordinal": global_ordinal,
                        "evaluation_id": evaluation["id"],
                        "row": row,
                        "content_sha256": content_hash,
                    }
                )

        evaluation_roster_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": child["content_sha256"],
                    "evaluation_ordinal": child["ordinal"],
                    "evaluation_run_id": UUID(str(child["row"][0])),
                    "research_assessment_evaluation_id": child["id"],
                }
                for child in evaluation_children
            )
        )
        evidence_roster_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": child["content_sha256"],
                    "evidence_item_id": UUID(str(child["row"][0])),
                    "evidence_ordinal": child["ordinal"],
                    "research_assessment_evidence_id": child["id"],
                }
                for child in evidence_children
            )
        )

        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.research_assessment_evaluation (
                    research_assessment_evaluation_id,
                    research_assessment_id, evaluation_ordinal,
                    evaluation_run_id, experiment_id,
                    evaluation_protocol_id, target_definition_id,
                    partition_purpose, evaluation_status, terminal_at,
                    metric_count, rejected_metric_count,
                    not_estimable_metric_count,
                    source_generation_min_decision_time,
                    source_generation_max_decision_time, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        child["id"],
                        plan.research_assessment_id,
                        child["ordinal"],
                        child["row"][0],
                        plan.experiment_id,
                        child["row"][1],
                        experiment[0],
                        child["row"][2],
                        child["row"][3],
                        child["row"][4],
                        child["row"][5],
                        child["row"][6],
                        child["row"][7],
                        child["row"][8],
                        child["row"][9],
                        child["content_sha256"],
                    )
                    for child in evaluation_children
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.research_assessment_evidence (
                    research_assessment_evidence_id, research_assessment_id,
                    research_assessment_evaluation_id, evidence_ordinal,
                    evidence_item_id, evaluation_run_id, evidence_class,
                    origin_class, evidence_role, evidence_direction,
                    content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        child["id"],
                        plan.research_assessment_id,
                        child["evaluation_id"],
                        child["ordinal"],
                        child["row"][0],
                        child["row"][1],
                        child["row"][2],
                        child["row"][3],
                        child["row"][4],
                        child["row"][5],
                        child["content_sha256"],
                    )
                    for child in evidence_children
                ),
            )

        generation_min = min(row[8] for row in evaluation_rows)
        generation_max = max(row[9] for row in evaluation_rows)
        terminal_ceiling = max(row[4] for row in evaluation_rows)
        root_content_hash = canonical_json_sha256(
            {
                "assessment_definition_sha256": str(plan.content_sha256),
                "assessment_status": status,
                "evaluation_count": len(evaluation_children),
                "evaluation_roster_sha256": evaluation_roster_hash,
                "evidence_count": len(evidence_children),
                "evidence_roster_sha256": evidence_roster_hash,
                "source_generation_max_decision_time": generation_max,
                "source_generation_min_decision_time": generation_min,
                "terminal_evaluation_ceiling": terminal_ceiling,
            }
        )
        self._connection.execute(
            """
            INSERT INTO mra.research_assessment (
                research_assessment_id, assessment_code, revision,
                supersedes_assessment_id, experiment_id,
                target_definition_id, target_version,
                target_definition_sha256, knowledge_cutoff,
                assessment_status, reason_code, evaluation_count,
                evaluation_roster_sha256, evidence_count,
                evidence_roster_sha256,
                source_generation_min_decision_time,
                source_generation_max_decision_time,
                terminal_evaluation_ceiling, code_artifact_id,
                code_content_sha256, code_size_bytes, config_artifact_id,
                config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                plan.research_assessment_id,
                plan.assessment_code,
                plan.revision,
                plan.supersedes_assessment_id,
                plan.experiment_id,
                experiment[0],
                experiment[1],
                experiment[2],
                plan.knowledge_cutoff,
                status.value,
                f"ASSESSMENT_{status.value}",
                len(evaluation_children),
                evaluation_roster_hash,
                len(evidence_children),
                evidence_roster_hash,
                generation_min,
                generation_max,
                terminal_ceiling,
                plan.code_artifact.artifact_id,
                str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256),
                plan.config_artifact.size_bytes,
                str(plan.provenance_sha256),
                root_content_hash,
                request_identity,
                request_sha256,
            ),
        )
        return self.record(plan.research_assessment_id, lock=False)

    def record(
        self, research_assessment_id: UUID, *, lock: bool
    ) -> ResearchAssessmentRecord:
        row = self._connection.execute(
            """
            SELECT research_assessment_id, experiment_id, revision,
                   assessment_status, evaluation_count,
                   evaluation_roster_sha256, evidence_count,
                   evidence_roster_sha256, content_sha256, recorded_at
            FROM mra.research_assessment
            WHERE research_assessment_id = %s
            """
            + (" FOR SHARE" if lock else ""),
            (research_assessment_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"ResearchAssessment {research_assessment_id} does not exist"
            )
        return ResearchAssessmentRecord(
            research_assessment_id=UUID(str(row[0])),
            experiment_id=UUID(str(row[1])),
            revision=int(row[2]),
            assessment_status=str(row[3]),
            evaluation_count=int(row[4]),
            evaluation_roster_sha256=str(row[5]),
            evidence_count=int(row[6]),
            evidence_roster_sha256=str(row[7]),
            content_sha256=str(row[8]),
            recorded_at=row[9],
        )


__all__ = ["PostgresAssessmentRepository"]
