"""PostgreSQL Research Qualification Policy and complete floor Decision writer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.assessment import AssessmentStatus
from market_regime_alpha.research_qualification.domain.qualification import (
    FloorMissingnessPolicy,
    FloorResultStatus,
    QualificationOperator,
    ResearchQualificationDecisionPlan,
    ResearchQualificationPolicyPlan,
    qualification_decision_status,
)
from market_regime_alpha.research_qualification.ports.qualification_uow import (
    ResearchQualificationDecisionRecord,
    ResearchQualificationPolicyRecord,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError, RuntimeStateConflictError
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresQualificationRepository:
    def __init__(
        self,
        connection: psycopg.Connection[Any],
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._connection = connection
        self._id_factory = id_factory

    def lock_policy_identity(self, policy_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"research-qualification-policy:{policy_code}",),
        )

    def register_policy(
        self,
        plan: ResearchQualificationPolicyPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ResearchQualificationPolicyRecord:
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.research_qualification_policy_floor (
                    research_qualification_policy_floor_id,
                    research_qualification_policy_id, floor_code,
                    floor_ordinal, evaluation_protocol_id,
                    evaluation_protocol_metric_id,
                    source_target_metric_definition_id,
                    evaluation_protocol_metric_sha256,
                    required_partition_purpose,
                    required_evaluation_status, metric_code,
                    source_value_type, reducer, slice_kind,
                    candidate_disposition, direction,
                    qualification_operator, decimal_threshold,
                    boolean_threshold, minimum_member_count,
                    minimum_estimable_count, missingness_policy,
                    required_evidence_class, required_origin_class,
                    required_evidence_role,
                    minimum_support_evidence_count,
                    maximum_counter_evidence_count, required,
                    content_sha256
                )
                SELECT %s, %s, %s, %s, %s, %s,
                       metric.source_target_metric_definition_id,
                       %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s
                FROM mra.evaluation_protocol_metric AS metric
                WHERE metric.evaluation_protocol_metric_id = %s
                  AND metric.evaluation_protocol_id = %s
                """,
                (
                    (
                        floor.research_qualification_policy_floor_id,
                        plan.research_qualification_policy_id,
                        floor.floor_code,
                        floor.ordinal,
                        floor.evaluation_protocol_id,
                        floor.evaluation_protocol_metric_id,
                        str(floor.evaluation_protocol_metric_sha256),
                        floor.required_partition_purpose.value,
                        floor.required_evaluation_status,
                        floor.metric_code,
                        floor.source_value_type.value,
                        floor.reducer.value,
                        floor.slice_kind.value,
                        (
                            floor.candidate_disposition.value
                            if floor.candidate_disposition is not None
                            else None
                        ),
                        floor.direction.value,
                        floor.operator.value,
                        floor.decimal_threshold,
                        floor.boolean_threshold,
                        floor.minimum_member_count,
                        floor.minimum_estimable_count,
                        floor.missingness_policy.value,
                        floor.required_evidence_class.value,
                        floor.required_origin_class.value,
                        floor.required_evidence_role.value,
                        floor.minimum_support_evidence_count,
                        floor.maximum_counter_evidence_count,
                        floor.required,
                        str(floor.content_sha256),
                        floor.evaluation_protocol_metric_id,
                        floor.evaluation_protocol_id,
                    )
                    for floor in plan.floors
                ),
            )
        inserted = self._connection.execute(
            """
            SELECT count(*) FROM mra.research_qualification_policy_floor
            WHERE research_qualification_policy_id = %s
            """,
            (plan.research_qualification_policy_id,),
        ).fetchone()
        if inserted is None or int(inserted[0]) != plan.floor_count:
            raise RuntimeStateConflictError(
                "Qualification Policy metric roster is incomplete"
            )
        self._connection.execute(
            """
            INSERT INTO mra.research_qualification_policy (
                research_qualification_policy_id, policy_code, version,
                supersedes_policy_id, target_definition_id, target_version,
                target_definition_sha256, qualification_purpose,
                required_assessment_status, require_preaccess_freeze,
                floor_count, floor_roster_sha256, code_artifact_id,
                code_content_sha256, code_size_bytes, config_artifact_id,
                config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s
            )
            """,
            (
                plan.research_qualification_policy_id,
                plan.policy_code,
                plan.version,
                plan.supersedes_policy_id,
                plan.target_definition_id,
                plan.target_version,
                str(plan.target_definition_sha256),
                plan.qualification_purpose.value,
                plan.required_assessment_status.value,
                plan.require_preaccess_freeze,
                plan.floor_count,
                str(plan.floor_roster_sha256),
                plan.code_artifact.artifact_id,
                str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256),
                plan.config_artifact.size_bytes,
                str(plan.provenance_sha256),
                str(plan.content_sha256),
                request_identity,
                request_sha256,
            ),
        )
        return self.policy_record(plan.research_qualification_policy_id, lock=False)

    def policy_record(
        self, research_qualification_policy_id: UUID, *, lock: bool
    ) -> ResearchQualificationPolicyRecord:
        row = self._connection.execute(
            """
            SELECT research_qualification_policy_id, version,
                   target_definition_id, qualification_purpose,
                   floor_count, floor_roster_sha256,
                   content_sha256, frozen_at
            FROM mra.research_qualification_policy
            WHERE research_qualification_policy_id = %s
            """
            + (" FOR SHARE" if lock else ""),
            (research_qualification_policy_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"ResearchQualificationPolicy {research_qualification_policy_id} does not exist"
            )
        return ResearchQualificationPolicyRecord(
            research_qualification_policy_id=UUID(str(row[0])),
            version=int(row[1]),
            target_definition_id=UUID(str(row[2])),
            qualification_purpose=str(row[3]),
            floor_count=int(row[4]),
            floor_roster_sha256=str(row[5]),
            content_sha256=str(row[6]),
            frozen_at=row[7],
        )

    def lock_decision_identity(self, decision_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"research-qualification-decision:{decision_code}",),
        )

    def decide(
        self,
        plan: ResearchQualificationDecisionPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ResearchQualificationDecisionRecord:
        authority = self._connection.execute(
            """
            SELECT assessment.experiment_id, assessment.target_definition_id,
                   assessment.assessment_status,
                   assessment.source_generation_max_decision_time,
                   policy.qualification_purpose,
                   policy.required_assessment_status,
                   policy.floor_count
            FROM mra.research_assessment AS assessment
            JOIN mra.research_qualification_policy AS policy
              ON policy.research_qualification_policy_id = %s
             AND policy.target_definition_id = assessment.target_definition_id
            WHERE assessment.research_assessment_id = %s
            FOR SHARE OF assessment, policy
            """,
            (
                plan.research_qualification_policy_id,
                plan.research_assessment_id,
            ),
        ).fetchone()
        if authority is None:
            raise RuntimeStateConflictError(
                "Qualification requires exact Assessment/Policy Target binding"
            )
        floor_rows = self._connection.execute(
            """
            SELECT research_qualification_policy_floor_id, floor_ordinal,
                   evaluation_protocol_id, evaluation_protocol_metric_id,
                   required_partition_purpose, required_evaluation_status,
                   source_value_type, qualification_operator,
                   decimal_threshold, boolean_threshold,
                   minimum_member_count, minimum_estimable_count,
                   missingness_policy, required_evidence_class,
                   required_origin_class, required_evidence_role,
                   minimum_support_evidence_count,
                   maximum_counter_evidence_count, required
            FROM mra.research_qualification_policy_floor
            WHERE research_qualification_policy_id = %s
            ORDER BY floor_ordinal
            FOR SHARE
            """,
            (plan.research_qualification_policy_id,),
        ).fetchall()
        if len(floor_rows) != int(authority[6]):
            raise RuntimeStateConflictError("Qualification Policy floor roster drifted")

        results: list[dict[str, Any]] = []
        all_floor_evidence: list[dict[str, Any]] = []
        required_statuses: list[FloorResultStatus] = []
        for floor in floor_rows:
            matches = self._connection.execute(
                """
                SELECT item.research_assessment_evaluation_id,
                       item.evaluation_run_id, metric.evaluation_metric_id,
                       metric.metric_state, metric.decimal_value,
                       metric.boolean_value, metric.estimable_count,
                       count(input.evaluation_metric_observation_id) FILTER (
                           WHERE input.input_state <> 'EXCLUDED'
                       ) AS member_count,
                       count(input.evaluation_metric_observation_id) FILTER (
                           WHERE input.input_state = 'NOT_ESTIMABLE'
                       ) AS not_estimable_count
                FROM mra.research_assessment_evaluation AS item
                JOIN mra.evaluation_metric AS metric
                  ON metric.evaluation_run_id = item.evaluation_run_id
                 AND metric.evaluation_protocol_metric_id = %s
                LEFT JOIN mra.evaluation_metric_observation AS input
                  ON input.evaluation_metric_id = metric.evaluation_metric_id
                WHERE item.research_assessment_id = %s
                  AND item.evaluation_protocol_id = %s
                  AND item.partition_purpose = %s
                  AND item.evaluation_status = %s
                GROUP BY item.research_assessment_evaluation_id,
                         item.evaluation_run_id, metric.evaluation_metric_id,
                         metric.metric_state, metric.decimal_value,
                         metric.boolean_value, metric.estimable_count
                """,
                (
                    floor[3],
                    plan.research_assessment_id,
                    floor[2],
                    floor[4],
                    floor[5],
                ),
            ).fetchall()
            if len(matches) > 1:
                raise RuntimeStateConflictError(
                    "Qualification floor has ambiguous Evaluation inputs"
                )
            match = matches[0] if matches else None
            evidence_rows: list[Any] = []
            if match is not None:
                evidence_rows = self._connection.execute(
                    """
                    SELECT research_assessment_evidence_id, evidence_item_id,
                           evidence_direction
                    FROM mra.research_assessment_evidence
                    WHERE research_assessment_id = %s
                      AND research_assessment_evaluation_id = %s
                      AND evidence_class = %s
                      AND origin_class = %s
                      AND evidence_role = %s
                    ORDER BY evidence_ordinal
                    """,
                    (
                        plan.research_assessment_id,
                        match[0],
                        floor[13],
                        floor[14],
                        floor[15],
                    ),
                ).fetchall()
            support_count = sum(row[2] == "SUPPORT" for row in evidence_rows)
            counter_count = sum(row[2] == "COUNTER" for row in evidence_rows)
            result_status = self._floor_status(
                floor,
                match,
                support_count=support_count,
                counter_count=counter_count,
            )
            result_id = self._id_factory()
            floor_evidence: list[dict[str, Any]] = []
            for evidence_ordinal, evidence in enumerate(evidence_rows, start=1):
                evidence_id = self._id_factory()
                content_hash = canonical_json_sha256(
                    {
                        "evidence_direction": str(evidence[2]),
                        "evidence_item_id": UUID(str(evidence[1])),
                        "research_assessment_evidence_id": UUID(str(evidence[0])),
                        "research_qualification_floor_result_id": result_id,
                    }
                )
                floor_evidence.append(
                    {
                        "id": evidence_id,
                        "ordinal": evidence_ordinal,
                        "row": evidence,
                        "content_sha256": content_hash,
                    }
                )
            evidence_roster_hash = canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": item["content_sha256"],
                        "evidence_ordinal": item["ordinal"],
                        "research_assessment_evidence_id": UUID(
                            str(item["row"][0])
                        ),
                        "research_qualification_floor_evidence_id": item["id"],
                    }
                    for item in floor_evidence
                )
            )
            reason_code = self._floor_reason(result_status)
            result_content_hash = canonical_json_sha256(
                {
                    "counter_evidence_count": counter_count,
                    "estimable_count": int(match[6]) if match else 0,
                    "evidence_roster_sha256": evidence_roster_hash,
                    "evaluation_metric_id": UUID(str(match[2])) if match else None,
                    "evaluation_run_id": UUID(str(match[1])) if match else None,
                    "member_count": int(match[7]) if match else 0,
                    "not_estimable_count": int(match[8]) if match else 0,
                    "observed_boolean_value": match[5] if match else None,
                    "observed_decimal_value": (
                        Decimal(match[4]) if match and match[4] is not None else None
                    ),
                    "reason_code": reason_code,
                    "research_qualification_policy_floor_id": UUID(str(floor[0])),
                    "result_status": result_status,
                    "support_evidence_count": support_count,
                }
            )
            result = {
                "id": result_id,
                "floor": floor,
                "match": match,
                "status": result_status,
                "support_count": support_count,
                "counter_count": counter_count,
                "evidence": floor_evidence,
                "evidence_roster_sha256": evidence_roster_hash,
                "reason_code": reason_code,
                "content_sha256": result_content_hash,
            }
            results.append(result)
            all_floor_evidence.extend(
                {"result": result, **item} for item in floor_evidence
            )
            if bool(floor[18]):
                required_statuses.append(result_status)

        assessment_status = AssessmentStatus(str(authority[2]))
        decision_status = qualification_decision_status(
            assessment_status=assessment_status,
            required_assessment_status=AssessmentStatus(str(authority[5])),
            required_floor_statuses=tuple(required_statuses),
        )
        floor_result_roster_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": result["content_sha256"],
                    "research_qualification_floor_result_id": result["id"],
                    "research_qualification_policy_floor_id": UUID(
                        str(result["floor"][0])
                    ),
                    "result_ordinal": int(result["floor"][1]),
                }
                for result in results
            )
        )

        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.research_qualification_floor_result (
                    research_qualification_floor_result_id,
                    research_qualification_decision_id,
                    research_qualification_policy_floor_id,
                    research_qualification_policy_id, result_ordinal,
                    research_assessment_evaluation_id,
                    research_assessment_id, evaluation_run_id,
                    evaluation_metric_id, result_status,
                    observed_decimal_value, observed_boolean_value,
                    member_count, estimable_count, not_estimable_count,
                    support_evidence_count, counter_evidence_count,
                    evidence_roster_sha256, reason_code, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        result["id"],
                        plan.research_qualification_decision_id,
                        result["floor"][0],
                        plan.research_qualification_policy_id,
                        result["floor"][1],
                        result["match"][0] if result["match"] else None,
                        plan.research_assessment_id,
                        result["match"][1] if result["match"] else None,
                        result["match"][2] if result["match"] else None,
                        result["status"].value,
                        result["match"][4] if result["match"] else None,
                        result["match"][5] if result["match"] else None,
                        int(result["match"][7]) if result["match"] else 0,
                        int(result["match"][6]) if result["match"] else 0,
                        int(result["match"][8]) if result["match"] else 0,
                        result["support_count"],
                        result["counter_count"],
                        result["evidence_roster_sha256"],
                        result["reason_code"],
                        result["content_sha256"],
                    )
                    for result in results
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.research_qualification_floor_evidence (
                    research_qualification_floor_evidence_id,
                    research_qualification_decision_id,
                    research_qualification_floor_result_id,
                    research_assessment_id,
                    research_assessment_evidence_id, evidence_item_id,
                    evidence_ordinal, evidence_direction, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        item["id"],
                        plan.research_qualification_decision_id,
                        item["result"]["id"],
                        plan.research_assessment_id,
                        item["row"][0],
                        item["row"][1],
                        item["ordinal"],
                        item["row"][2],
                        item["content_sha256"],
                    )
                    for item in all_floor_evidence
                ),
            )

        root_content_hash = canonical_json_sha256(
            {
                "decision_definition_sha256": str(plan.content_sha256),
                "decision_status": decision_status,
                "floor_count": len(results),
                "floor_result_roster_sha256": floor_result_roster_hash,
                "source_generation_max_decision_time": authority[3],
            }
        )
        self._connection.execute(
            """
            INSERT INTO mra.research_qualification_decision (
                research_qualification_decision_id, decision_code,
                revision, supersedes_decision_id, research_assessment_id,
                research_qualification_policy_id, experiment_id,
                target_definition_id, assessment_status,
                qualification_purpose, decision_status, reason_code,
                floor_count, floor_result_roster_sha256,
                source_generation_max_decision_time, effective_at, known_at,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256,
                config_size_bytes, provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                plan.research_qualification_decision_id,
                plan.decision_code,
                plan.revision,
                plan.supersedes_decision_id,
                plan.research_assessment_id,
                plan.research_qualification_policy_id,
                authority[0],
                authority[1],
                authority[2],
                authority[4],
                decision_status.value,
                f"QUALIFICATION_{decision_status.value}",
                len(results),
                floor_result_roster_hash,
                authority[3],
                plan.effective_at,
                plan.known_at,
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
        return self.decision_record(
            plan.research_qualification_decision_id, lock=False
        )

    @staticmethod
    def _floor_status(
        floor: Any,
        match: Any | None,
        *,
        support_count: int,
        counter_count: int,
    ) -> FloorResultStatus:
        if match is None:
            return FloorResultStatus.MISSING
        if str(match[3]) == "NOT_ESTIMABLE":
            return FloorResultStatus.NOT_ESTIMABLE
        if int(match[7]) < int(floor[10]) or int(match[6]) < int(floor[11]):
            return (
                FloorResultStatus.REJECTED
                if FloorMissingnessPolicy(str(floor[12]))
                is FloorMissingnessPolicy.REJECT
                else FloorResultStatus.INCONCLUSIVE
            )
        if support_count < int(floor[16]) or counter_count > int(floor[17]):
            return FloorResultStatus.REJECTED
        operator = QualificationOperator(str(floor[7]))
        if str(floor[6]) == "DECIMAL":
            observed = Decimal(match[4])
            threshold = Decimal(floor[8])
            satisfied = (
                (operator is QualificationOperator.AT_LEAST and observed >= threshold)
                or (operator is QualificationOperator.AT_MOST and observed <= threshold)
            )
        else:
            satisfied = bool(match[5]) is bool(floor[9])
        return (
            FloorResultStatus.SATISFIED
            if satisfied
            else FloorResultStatus.REJECTED
        )

    @staticmethod
    def _floor_reason(status: FloorResultStatus) -> str:
        return {
            FloorResultStatus.SATISFIED: "FLOOR_SATISFIED",
            FloorResultStatus.REJECTED: "FLOOR_REJECTED",
            FloorResultStatus.MISSING: "FLOOR_INPUT_MISSING",
            FloorResultStatus.NOT_ESTIMABLE: "FLOOR_NOT_ESTIMABLE",
            FloorResultStatus.INCONCLUSIVE: "FLOOR_INCONCLUSIVE",
            FloorResultStatus.BLOCKED: "FLOOR_BLOCKED",
        }[status]

    def decision_record(
        self, research_qualification_decision_id: UUID, *, lock: bool
    ) -> ResearchQualificationDecisionRecord:
        row = self._connection.execute(
            """
            SELECT research_qualification_decision_id, revision,
                   research_assessment_id,
                   research_qualification_policy_id, decision_status,
                   floor_count, floor_result_roster_sha256,
                   content_sha256, effective_at, known_at, recorded_at
            FROM mra.research_qualification_decision
            WHERE research_qualification_decision_id = %s
            """
            + (" FOR SHARE" if lock else ""),
            (research_qualification_decision_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"ResearchQualificationDecision {research_qualification_decision_id} does not exist"
            )
        return ResearchQualificationDecisionRecord(
            research_qualification_decision_id=UUID(str(row[0])),
            revision=int(row[1]),
            research_assessment_id=UUID(str(row[2])),
            research_qualification_policy_id=UUID(str(row[3])),
            decision_status=str(row[4]),
            floor_count=int(row[5]),
            floor_result_roster_sha256=str(row[6]),
            content_sha256=str(row[7]),
            effective_at=row[8],
            known_at=row[9],
            recorded_at=row[10],
        )


__all__ = ["PostgresQualificationRepository"]
