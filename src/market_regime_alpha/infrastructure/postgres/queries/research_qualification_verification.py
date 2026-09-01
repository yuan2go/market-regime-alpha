"""Read-only relational replay checks for WP-12 Research Authorities."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.domain.assessment import (
    AssessmentEvaluationSummary,
    AssessmentStatus,
    derive_assessment_status,
)
from market_regime_alpha.research_qualification.domain.evidence import (
    EvidenceClass,
    EvidenceDependencyPlan,
    EvidenceDependencyRole,
    EvidenceDirection,
    EvidenceItemPlan,
    EvidenceOriginClass,
    EvidenceRole,
    EvidenceScope,
    ResearchProofClass,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.qualification import (
    FloorMissingnessPolicy,
    FloorResultStatus,
    QualificationOperator,
    QualificationPolicyFloorPlan,
    QualificationPurpose,
    ResearchQualificationPolicyPlan,
    qualification_decision_status,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    CandidateDisposition,
    EvaluationReducer,
    EvaluationRunStatus,
    EvaluationSliceKind,
    MetricDirection,
    PartitionPurpose,
    SourceMetricValueType,
)
from market_regime_alpha.research_qualification.domain.verification import (
    ResearchVerificationMismatch,
    ResearchVerificationMismatchKind,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


Mismatch = ResearchVerificationMismatch
Kind = ResearchVerificationMismatchKind


class PostgresResearchQualificationVerificationProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def inspect_evidence(self, evidence_item_id: UUID) -> tuple[Mismatch, ...]:
        mismatches: list[Mismatch] = []
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT evaluation_run_id, evaluation_metric_id,
                       evidence_code, evidence_scope, evidence_class,
                       origin_class, evidence_role, evidence_direction,
                       proof_ceiling, observed_at,
                       evidence_artifact_id, evidence_content_sha256,
                       evidence_size_bytes, code_artifact_id,
                       code_content_sha256, code_size_bytes,
                       config_artifact_id, config_content_sha256,
                       config_size_bytes, provenance_sha256,
                       dependency_count, dependency_roster_sha256,
                       content_sha256, evaluation_terminal_at,
                       source_generation_max_decision_time, recorded_at
                FROM mra.evidence_item WHERE evidence_item_id = %s
                """,
                (evidence_item_id,),
            ).fetchone()
            if root is None:
                return (_missing("evidence_item", evidence_item_id),)
            dependencies = connection.execute(
                """
                SELECT evidence_dependency_id, parent_evidence_item_id,
                       dependency_ordinal, dependency_role,
                       content_sha256, created_at
                FROM mra.evidence_dependency
                WHERE child_evidence_item_id = %s
                ORDER BY dependency_ordinal
                """,
                (evidence_item_id,),
            ).fetchall()
            plans = tuple(
                EvidenceDependencyPlan(
                    evidence_dependency_id=UUID(str(row[0])),
                    parent_evidence_item_id=UUID(str(row[1])),
                    ordinal=int(row[2]),
                    dependency_role=EvidenceDependencyRole(str(row[3])),
                )
                for row in dependencies
            )
            for dependency_plan, row in zip(plans, dependencies, strict=True):
                _compare(
                    mismatches,
                    "evidence.dependency_content_sha256",
                    str(dependency_plan.content_sha256),
                    str(row[4]),
                )
            try:
                evidence_plan = EvidenceItemPlan(
                    evidence_item_id=evidence_item_id,
                    evaluation_run_id=UUID(str(root[0])),
                    evaluation_metric_id=(
                        UUID(str(root[1])) if root[1] is not None else None
                    ),
                    evidence_code=str(root[2]),
                    scope=EvidenceScope(str(root[3])),
                    evidence_class=EvidenceClass(str(root[4])),
                    origin_class=EvidenceOriginClass(str(root[5])),
                    role=EvidenceRole(str(root[6])),
                    direction=EvidenceDirection(str(root[7])),
                    proof_ceiling=ResearchProofClass(str(root[8])),
                    observed_at=root[9],
                    evidence_artifact=ArtifactBinding(
                        UUID(str(root[10])), str(root[11]), int(root[12])
                    ),
                    code_artifact=ArtifactBinding(
                        UUID(str(root[13])), str(root[14]), int(root[15])
                    ),
                    config_artifact=ArtifactBinding(
                        UUID(str(root[16])), str(root[17]), int(root[18])
                    ),
                    provenance_sha256=str(root[19]),
                    dependencies=plans,
                )
                _compare(
                    mismatches,
                    "evidence.dependency_count",
                    str(evidence_plan.dependency_count),
                    str(root[20]),
                )
                _compare(
                    mismatches,
                    "evidence.dependency_roster_sha256",
                    str(evidence_plan.dependency_roster_sha256),
                    str(root[21]),
                )
                _compare(
                    mismatches,
                    "evidence.content_sha256",
                    str(evidence_plan.content_sha256),
                    str(root[22]),
                )
            except (TypeError, ValueError) as exc:
                mismatches.append(_identity("evidence.domain", "valid", str(exc)))
            evaluation = connection.execute(
                """
                SELECT coalesce(run.completed_at, run.failed_at),
                       max(member.decision_time), run.status
                FROM mra.evaluation_run AS run
                JOIN mra.research_partition_member AS member
                  ON member.research_partition_id = run.research_partition_id
                WHERE run.evaluation_run_id = %s
                GROUP BY run.completed_at, run.failed_at, run.status
                """,
                (root[0],),
            ).fetchone()
            if (
                evaluation is None
                or evaluation[2] not in {"COMPLETED", "FAILED"}
                or evaluation[0] != root[23]
                or evaluation[1] != root[24]
            ):
                mismatches.append(
                    _identity(
                        "evidence.evaluation_binding",
                        "exact terminal Evaluation generation",
                        str(evaluation),
                    )
                )
            chronological = connection.execute(
                """
                SELECT count(*)
                FROM mra.evidence_dependency AS dependency
                JOIN mra.evidence_item AS parent
                  ON parent.evidence_item_id = dependency.parent_evidence_item_id
                WHERE dependency.child_evidence_item_id = %s
                  AND parent.recorded_at >= %s
                """,
                (evidence_item_id, root[25]),
            ).fetchone()
            if chronological is not None and int(chronological[0]):
                mismatches.append(
                    _temporal("evidence.dependency_dag", "strict prior parents", str(chronological[0]))
                )
            _inspect_provenance(
                connection,
                "EVIDENCE_ITEM",
                evidence_item_id,
                "RECORD_RESEARCH_EVIDENCE",
                mismatches,
            )
        return tuple(mismatches)

    def inspect_assessment(
        self, research_assessment_id: UUID
    ) -> tuple[Mismatch, ...]:
        mismatches: list[Mismatch] = []
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT experiment_id, knowledge_cutoff, assessment_status,
                       evaluation_count, evaluation_roster_sha256,
                       evidence_count, evidence_roster_sha256,
                       source_generation_min_decision_time,
                       source_generation_max_decision_time,
                       terminal_evaluation_ceiling, revision,
                       supersedes_assessment_id, assessment_code, recorded_at
                FROM mra.research_assessment
                WHERE research_assessment_id = %s
                """,
                (research_assessment_id,),
            ).fetchone()
            if root is None:
                return (_missing("research_assessment", research_assessment_id),)
            evaluations = connection.execute(
                """
                SELECT research_assessment_evaluation_id,
                       evaluation_ordinal, evaluation_run_id,
                       evaluation_protocol_id, partition_purpose,
                       evaluation_status, terminal_at, metric_count,
                       rejected_metric_count, not_estimable_metric_count,
                       source_generation_min_decision_time,
                       source_generation_max_decision_time, content_sha256
                FROM mra.research_assessment_evaluation
                WHERE research_assessment_id = %s ORDER BY evaluation_ordinal
                """,
                (research_assessment_id,),
            ).fetchall()
            evidence = connection.execute(
                """
                SELECT research_assessment_evidence_id, evidence_ordinal,
                       research_assessment_evaluation_id, evidence_item_id,
                       evaluation_run_id, evidence_class, origin_class,
                       evidence_role, evidence_direction, content_sha256
                FROM mra.research_assessment_evidence
                WHERE research_assessment_id = %s ORDER BY evidence_ordinal
                """,
                (research_assessment_id,),
            ).fetchall()
            evaluation_hash = canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(row[12]),
                        "evaluation_ordinal": int(row[1]),
                        "evaluation_run_id": UUID(str(row[2])),
                        "research_assessment_evaluation_id": UUID(str(row[0])),
                    }
                    for row in evaluations
                )
            )
            evidence_hash = canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(row[9]),
                        "evidence_item_id": UUID(str(row[3])),
                        "evidence_ordinal": int(row[1]),
                        "research_assessment_evidence_id": UUID(str(row[0])),
                    }
                    for row in evidence
                )
            )
            _roster(mismatches, "assessment.evaluation", int(root[3]), str(root[4]), evaluations, evaluation_hash)
            _roster(mismatches, "assessment.evidence", int(root[5]), str(root[6]), evidence, evidence_hash)
            summaries = tuple(
                AssessmentEvaluationSummary(
                    evaluation_run_id=UUID(str(row[2])),
                    status=EvaluationRunStatus(str(row[5])),
                    metric_count=int(row[7]),
                    rejected_metric_count=int(row[8]),
                    not_estimable_metric_count=int(row[9]),
                )
                for row in evaluations
            )
            directions = tuple(EvidenceDirection(str(row[8])) for row in evidence)
            try:
                derived = derive_assessment_status(summaries, directions).value
                _compare(mismatches, "assessment.status", derived, str(root[2]))
            except ValueError as exc:
                mismatches.append(_identity("assessment.domain", "valid", str(exc)))
            expected_evaluations = connection.execute(
                """
                SELECT count(*) FROM (
                    (SELECT evaluation_run_id FROM mra.evaluation_run
                     WHERE experiment_id = %s AND opened_at <= %s)
                    EXCEPT
                    (SELECT evaluation_run_id
                     FROM mra.research_assessment_evaluation
                     WHERE research_assessment_id = %s)
                ) AS missing
                """,
                (root[0], root[1], research_assessment_id),
            ).fetchone()
            missing_evidence = connection.execute(
                """
                SELECT count(*) FROM (
                    (SELECT item.evidence_item_id
                     FROM mra.evidence_item AS item
                     JOIN mra.evaluation_run AS run
                       ON run.evaluation_run_id = item.evaluation_run_id
                     WHERE run.experiment_id = %s AND run.opened_at <= %s
                       AND item.recorded_at <= %s)
                    EXCEPT
                    (SELECT evidence_item_id
                     FROM mra.research_assessment_evidence
                     WHERE research_assessment_id = %s)
                ) AS missing
                """,
                (root[0], root[1], root[1], research_assessment_id),
            ).fetchone()
            if expected_evaluations and int(expected_evaluations[0]):
                mismatches.append(_identity("assessment.complete_evaluations", "0 missing", str(expected_evaluations[0])))
            if missing_evidence and int(missing_evidence[0]):
                mismatches.append(_identity("assessment.complete_evidence", "0 missing", str(missing_evidence[0])))
            _inspect_provenance(
                connection,
                "RESEARCH_ASSESSMENT",
                research_assessment_id,
                "ASSESS_RESEARCH_EXPERIMENT",
                mismatches,
            )
        return tuple(mismatches)

    def inspect_policy(
        self, research_qualification_policy_id: UUID
    ) -> tuple[Mismatch, ...]:
        mismatches: list[Mismatch] = []
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT policy_code, version, supersedes_policy_id,
                       target_definition_id, target_version,
                       target_definition_sha256, qualification_purpose,
                       required_assessment_status, require_preaccess_freeze,
                       floor_count, floor_roster_sha256,
                       code_artifact_id, code_content_sha256,
                       code_size_bytes, config_artifact_id,
                       config_content_sha256, config_size_bytes,
                       provenance_sha256, content_sha256
                FROM mra.research_qualification_policy
                WHERE research_qualification_policy_id = %s
                """,
                (research_qualification_policy_id,),
            ).fetchone()
            if root is None:
                return (_missing("research_qualification_policy", research_qualification_policy_id),)
            rows = connection.execute(
                """
                SELECT research_qualification_policy_floor_id, floor_code,
                       floor_ordinal, evaluation_protocol_id,
                       evaluation_protocol_metric_id,
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
                FROM mra.research_qualification_policy_floor
                WHERE research_qualification_policy_id = %s
                ORDER BY floor_ordinal
                """,
                (research_qualification_policy_id,),
            ).fetchall()
            try:
                floors = tuple(_floor_plan(row) for row in rows)
                plan = ResearchQualificationPolicyPlan(
                    research_qualification_policy_id=research_qualification_policy_id,
                    policy_code=str(root[0]),
                    version=int(root[1]),
                    supersedes_policy_id=(UUID(str(root[2])) if root[2] else None),
                    target_definition_id=UUID(str(root[3])),
                    target_version=int(root[4]),
                    target_definition_sha256=str(root[5]),
                    qualification_purpose=QualificationPurpose(str(root[6])),
                    required_assessment_status=AssessmentStatus(str(root[7])),
                    require_preaccess_freeze=bool(root[8]),
                    floors=floors,
                    code_artifact=ArtifactBinding(UUID(str(root[11])), str(root[12]), int(root[13])),
                    config_artifact=ArtifactBinding(UUID(str(root[14])), str(root[15]), int(root[16])),
                    provenance_sha256=str(root[17]),
                )
                _compare(mismatches, "policy.floor_count", str(plan.floor_count), str(root[9]))
                _compare(mismatches, "policy.floor_roster_sha256", str(plan.floor_roster_sha256), str(root[10]))
                _compare(mismatches, "policy.content_sha256", str(plan.content_sha256), str(root[18]))
                for floor, row in zip(floors, rows, strict=True):
                    _compare(mismatches, "policy.floor_content_sha256", str(floor.content_sha256), str(row[26]))
            except (TypeError, ValueError) as exc:
                mismatches.append(_identity("policy.domain", "valid", str(exc)))
            _inspect_provenance(
                connection,
                "RESEARCH_QUALIFICATION_POLICY",
                research_qualification_policy_id,
                "REGISTER_RESEARCH_QUALIFICATION_POLICY",
                mismatches,
            )
        return tuple(mismatches)

    def inspect_decision(
        self, research_qualification_decision_id: UUID
    ) -> tuple[Mismatch, ...]:
        mismatches: list[Mismatch] = []
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT research_assessment_id,
                       research_qualification_policy_id,
                       assessment_status, decision_status, floor_count,
                       floor_result_roster_sha256,
                       source_generation_max_decision_time,
                       effective_at, known_at, recorded_at
                FROM mra.research_qualification_decision
                WHERE research_qualification_decision_id = %s
                """,
                (research_qualification_decision_id,),
            ).fetchone()
            if root is None:
                return (_missing("research_qualification_decision", research_qualification_decision_id),)
            results = connection.execute(
                """
                SELECT result.research_qualification_floor_result_id,
                       result.research_qualification_policy_floor_id,
                       result.result_ordinal, result.result_status,
                       result.content_sha256, floor.required
                FROM mra.research_qualification_floor_result AS result
                JOIN mra.research_qualification_policy_floor AS floor
                  ON floor.research_qualification_policy_floor_id =
                     result.research_qualification_policy_floor_id
                WHERE result.research_qualification_decision_id = %s
                ORDER BY result.result_ordinal
                """,
                (research_qualification_decision_id,),
            ).fetchall()
            roster_hash = canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(row[4]),
                        "research_qualification_floor_result_id": UUID(str(row[0])),
                        "research_qualification_policy_floor_id": UUID(str(row[1])),
                        "result_ordinal": int(row[2]),
                    }
                    for row in results
                )
            )
            _roster(mismatches, "decision.floor_result", int(root[4]), str(root[5]), results, roster_hash)
            policy_status = connection.execute(
                """
                SELECT required_assessment_status
                FROM mra.research_qualification_policy
                WHERE research_qualification_policy_id = %s
                """,
                (root[1],),
            ).fetchone()
            if policy_status is None:
                mismatches.append(_missing("decision.policy", UUID(str(root[1]))))
            else:
                required = tuple(
                    FloorResultStatus(str(row[3])) for row in results if row[5]
                )
                try:
                    status = qualification_decision_status(
                        assessment_status=AssessmentStatus(str(root[2])),
                        required_assessment_status=AssessmentStatus(str(policy_status[0])),
                        required_floor_statuses=required,
                    ).value
                    _compare(mismatches, "decision.status", status, str(root[3]))
                except ValueError as exc:
                    mismatches.append(_identity("decision.domain", "valid", str(exc)))
            policy_difference = connection.execute(
                """
                SELECT count(*) FROM (
                    (SELECT research_qualification_policy_floor_id
                     FROM mra.research_qualification_policy_floor
                     WHERE research_qualification_policy_id = %s)
                    EXCEPT
                    (SELECT research_qualification_policy_floor_id
                     FROM mra.research_qualification_floor_result
                     WHERE research_qualification_decision_id = %s)
                ) AS missing
                """,
                (root[1], research_qualification_decision_id),
            ).fetchone()
            if policy_difference and int(policy_difference[0]):
                mismatches.append(_identity("decision.complete_floors", "0 missing", str(policy_difference[0])))
            evidence_drift = connection.execute(
                """
                SELECT count(*)
                FROM mra.research_qualification_floor_result AS result
                WHERE result.research_qualification_decision_id = %s
                  AND result.evidence_roster_sha256 <>
                      (SELECT mra.canonical_sha256(
                           replace(coalesce(json_agg(json_build_object(
                               'content_sha256', binding.content_sha256,
                               'evidence_ordinal', binding.evidence_ordinal,
                               'research_assessment_evidence_id',
                                   binding.research_assessment_evidence_id,
                               'research_qualification_floor_evidence_id',
                                   binding.research_qualification_floor_evidence_id
                           ) ORDER BY binding.evidence_ordinal), '[]'::json)::text, ' ', ''))
                       FROM mra.research_qualification_floor_evidence AS binding
                       WHERE binding.research_qualification_floor_result_id =
                             result.research_qualification_floor_result_id)
                """,
                (research_qualification_decision_id,),
            ).fetchone()
            if evidence_drift and int(evidence_drift[0]):
                mismatches.append(_hash("decision.floor_evidence_rosters", "all matched", str(evidence_drift[0])))
            if not (root[6] < root[7] <= root[8] <= root[9]):
                mismatches.append(_temporal("decision.generation_order", "source < effective <= known <= recorded", str(root[6:10])))
            _inspect_provenance(
                connection,
                "RESEARCH_QUALIFICATION_DECISION",
                research_qualification_decision_id,
                "DECIDE_RESEARCH_QUALIFICATION",
                mismatches,
            )
        return tuple(mismatches)


def _floor_plan(row: Any) -> QualificationPolicyFloorPlan:
    return QualificationPolicyFloorPlan(
        research_qualification_policy_floor_id=UUID(str(row[0])),
        floor_code=str(row[1]),
        ordinal=int(row[2]),
        evaluation_protocol_id=UUID(str(row[3])),
        evaluation_protocol_metric_id=UUID(str(row[4])),
        evaluation_protocol_metric_sha256=str(row[5]),
        required_partition_purpose=PartitionPurpose(str(row[6])),
        required_evaluation_status=str(row[7]),
        metric_code=str(row[8]),
        source_value_type=SourceMetricValueType(str(row[9])),
        reducer=EvaluationReducer(str(row[10])),
        slice_kind=EvaluationSliceKind(str(row[11])),
        candidate_disposition=(CandidateDisposition(str(row[12])) if row[12] else None),
        direction=MetricDirection(str(row[13])),
        operator=QualificationOperator(str(row[14])),
        decimal_threshold=row[15],
        boolean_threshold=row[16],
        minimum_member_count=int(row[17]),
        minimum_estimable_count=int(row[18]),
        missingness_policy=FloorMissingnessPolicy(str(row[19])),
        required_evidence_class=EvidenceClass(str(row[20])),
        required_origin_class=EvidenceOriginClass(str(row[21])),
        required_evidence_role=EvidenceRole(str(row[22])),
        minimum_support_evidence_count=int(row[23]),
        maximum_counter_evidence_count=int(row[24]),
        required=bool(row[25]),
    )


def _inspect_provenance(connection: Any, kind: str, authority_id: UUID, command: str, mismatches: list[Mismatch]) -> None:
    row = connection.execute(
        """
        SELECT count(*), count(audit.audit_event_id)
        FROM mra.command_receipt AS receipt
        LEFT JOIN mra.audit_event AS audit
          ON audit.command_receipt_id = receipt.receipt_id
         AND audit.aggregate_kind = receipt.result_aggregate_kind
         AND audit.aggregate_id = receipt.result_aggregate_id
        WHERE receipt.command_kind = %s AND receipt.status = 'SUCCEEDED'
          AND receipt.result_aggregate_kind = %s
          AND receipt.result_aggregate_id = %s
        """,
        (command, kind, str(authority_id)),
    ).fetchone()
    if row is None or int(row[0]) != 1 or int(row[1]) < 1:
        mismatches.append(_provenance(f"{kind.lower()}.receipt_audit", "1 receipt and audit", str(row)))


def _roster(mismatches: list[Mismatch], path: str, expected_count: int, expected_hash: str, rows: list[Any], actual_hash: str) -> None:
    _compare(mismatches, f"{path}_count", str(expected_count), str(len(rows)), kind=Kind.COUNT_MISMATCH)
    _compare(mismatches, f"{path}_roster_sha256", expected_hash, actual_hash, kind=Kind.HASH_MISMATCH)
    ordinals = [int(row[1] if path.startswith("assessment") else row[2]) for row in rows]
    if ordinals != list(range(1, len(rows) + 1)):
        mismatches.append(Mismatch(Kind.ORDER_MISMATCH, f"{path}_ordinals", str(list(range(1, len(rows) + 1))), str(ordinals)))


def _compare(mismatches: list[Mismatch], path: str, expected: str, actual: str, *, kind: Kind = Kind.HASH_MISMATCH) -> None:
    if expected != actual:
        mismatches.append(Mismatch(kind, path, expected, actual))


def _missing(path: str, authority_id: UUID) -> Mismatch:
    return Mismatch(Kind.MISSING_ROW, path, str(authority_id), "missing")


def _identity(path: str, expected: str, actual: str) -> Mismatch:
    return Mismatch(Kind.IDENTITY_MISMATCH, path, expected, actual)


def _hash(path: str, expected: str, actual: str) -> Mismatch:
    return Mismatch(Kind.HASH_MISMATCH, path, expected, actual)


def _temporal(path: str, expected: str, actual: str) -> Mismatch:
    return Mismatch(Kind.TEMPORAL_MISMATCH, path, expected, actual)


def _provenance(path: str, expected: str, actual: str) -> Mismatch:
    return Mismatch(Kind.PROVENANCE_MISMATCH, path, expected, actual)


__all__ = ["PostgresResearchQualificationVerificationProvider"]
