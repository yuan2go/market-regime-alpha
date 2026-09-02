from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.qualification_uow import (
    PostgresQualificationUnitOfWorkProvider,
)
from market_regime_alpha.research_qualification.application.qualification import (
    QualificationCommands,
)
from tests.refoundation.research_qualification import (
    test_evaluation_closure_postgres as _wp11,
)
from tests.refoundation.research_qualification import (
    test_qualification_postgres as _qualification,
)


@pytest.fixture
def wp12_plan_stack(target_database_url, tmp_path, request):
    return _wp11.wp11_stack.__wrapped__(target_database_url, tmp_path, request)


def test_wp12_representative_queries_use_bounded_index_led_plans(
    wp12_plan_stack,
) -> None:
    stack = wp12_plan_stack
    target, evaluation_run_id, assessment, _ = _qualification._assessment_authority(stack)
    policy = _qualification._policy(
        target,
        _qualification._floor(stack, evaluation_run_id),
        code=f"wp12-plan-policy-{uuid4().hex[:8]}",
    )
    commands = QualificationCommands(
        PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    commands.register_policy(
        policy,
        _wp11._wp11_context("register-plan-policy", "REGISTER_RESEARCH_QUALIFICATION_POLICY"),
    )
    decision = _qualification._decision(
        stack,
        assessment.research_assessment_id,
        policy,
        target,
        code=f"wp12-plan-decision-{uuid4().hex[:8]}",
    )
    commands.decide(
        decision,
        _wp11._wp11_context("decide-query-plan", "DECIDE_RESEARCH_QUALIFICATION"),
    )
    with psycopg.connect(stack.database_url) as connection:
        evidence_item_id = connection.execute(
            """
            SELECT evidence_item_id FROM mra.research_assessment_evidence
            WHERE research_assessment_id = %s ORDER BY evidence_ordinal LIMIT 1
            """,
            (assessment.research_assessment_id,),
        ).fetchone()[0]
        connection.execute("SET LOCAL enable_seqscan = off")
        plans = {
            "evidence_evaluation": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT item.evidence_item_id, run.status
                FROM mra.evidence_item AS item
                JOIN mra.evaluation_run AS run
                  ON run.evaluation_run_id = item.evaluation_run_id
                 AND run.experiment_id = item.experiment_id
                 AND run.evaluation_protocol_id = item.evaluation_protocol_id
                 AND run.target_definition_id = item.target_definition_id
                 AND run.partition_purpose = item.partition_purpose
                WHERE item.evidence_item_id = %s
                """,
                (evidence_item_id,),
            ).fetchone()[0][0],
            "evidence_dependency_dag": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT dependency.parent_evidence_item_id, parent.recorded_at
                FROM mra.evidence_dependency AS dependency
                JOIN mra.evidence_item AS parent
                  ON parent.evidence_item_id = dependency.parent_evidence_item_id
                WHERE dependency.child_evidence_item_id = %s
                ORDER BY dependency.dependency_ordinal
                """,
                (evidence_item_id,),
            ).fetchone()[0][0],
            "assessment_terminal_evaluations": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT item.evaluation_run_id, run.status
                FROM mra.research_assessment_evaluation AS item
                JOIN mra.evaluation_run AS run
                  ON run.evaluation_run_id = item.evaluation_run_id
                 AND run.experiment_id = item.experiment_id
                WHERE item.research_assessment_id = %s
                ORDER BY item.evaluation_ordinal
                """,
                (assessment.research_assessment_id,),
            ).fetchone()[0][0],
            "assessment_evidence_roster": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT binding.evidence_item_id, evidence.evidence_direction
                FROM mra.research_assessment_evidence AS binding
                JOIN mra.evidence_item AS evidence
                  ON evidence.evidence_item_id = binding.evidence_item_id
                 AND evidence.evaluation_run_id = binding.evaluation_run_id
                WHERE binding.research_assessment_id = %s
                ORDER BY binding.evidence_ordinal
                """,
                (assessment.research_assessment_id,),
            ).fetchone()[0][0],
            "policy_floor_metric": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT floor.research_qualification_policy_floor_id,
                       metric.evaluation_protocol_metric_id
                FROM mra.research_qualification_policy_floor AS floor
                JOIN mra.evaluation_protocol_metric AS metric
                  ON metric.evaluation_protocol_metric_id =
                     floor.evaluation_protocol_metric_id
                 AND metric.evaluation_protocol_id = floor.evaluation_protocol_id
                WHERE floor.research_qualification_policy_id = %s
                ORDER BY floor.floor_ordinal
                """,
                (policy.research_qualification_policy_id,),
            ).fetchone()[0][0],
            "decision_floor_reconciliation": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT result.research_qualification_floor_result_id,
                       binding.research_qualification_floor_evidence_id
                FROM mra.research_qualification_floor_result AS result
                LEFT JOIN mra.research_qualification_floor_evidence AS binding
                  ON binding.research_qualification_floor_result_id =
                     result.research_qualification_floor_result_id
                 AND binding.research_qualification_decision_id =
                     result.research_qualification_decision_id
                WHERE result.research_qualification_decision_id = %s
                ORDER BY result.result_ordinal, binding.evidence_ordinal
                """,
                (decision.research_qualification_decision_id,),
            ).fetchone()[0][0],
            "generation_safe_admission": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT research_qualification_decision_id
                FROM mra.research_qualification_decision
                WHERE research_qualification_decision_id = %s
                  AND decision_status = 'ADMITTED'
                  AND effective_at <= %s AND known_at <= %s
                  AND source_generation_max_decision_time < %s
                """,
                (
                    decision.research_qualification_decision_id,
                    decision.known_at,
                    decision.known_at,
                    decision.effective_at,
                ),
            ).fetchone()[0][0],
        }

    expected_indexes = {
        "evidence_evaluation": {
            "evidence_item_pkey",
            "evidence_item_run_authority_uk",
            "evaluation_run_pkey",
            "evaluation_run_evidence_authority_uk",
        },
        "evidence_dependency_dag": {
            "evidence_dependency_child_ordinal_uk",
            "evidence_dependency_child_fk_idx",
        },
        "assessment_terminal_evaluations": {
            "research_assessment_evaluation_ordinal_uk",
            "research_assessment_evaluation_assessment_fk_idx",
        },
        "assessment_evidence_roster": {
            "research_assessment_evidence_ordinal_uk",
            "research_assessment_evidence_assessment_fk_idx",
        },
        "policy_floor_metric": {
            "research_qualification_policy_floor_ordinal_uk",
            "research_qualification_policy_floor_policy_fk_idx",
        },
        "decision_floor_reconciliation": {
            "research_qualification_floor_result_decision_fk_idx",
            "research_qualification_floor_evidence_result_fk_idx",
        },
        "generation_safe_admission": {
            "research_qualification_decision_pkey",
            "research_qualification_decision_admission_uk",
        },
    }
    for label, explanation in plans.items():
        plan = explanation["Plan"]
        names = _wp11._plan_index_names(plan)
        assert expected_indexes[label] & names, (label, names, plan)
        assert int(plan["Actual Rows"]) <= 2, (label, plan)
        assert float(explanation["Execution Time"]) < 100.0, (
            label,
            explanation,
        )
