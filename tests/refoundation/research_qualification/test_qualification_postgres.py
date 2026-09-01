from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.assessment_uow import (
    PostgresAssessmentUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.evaluation_uow import (
    PostgresEvaluationUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.qualification_uow import (
    PostgresQualificationUnitOfWorkProvider,
)
from market_regime_alpha.research_qualification.application.assessment import (
    AssessmentCommands,
)
from market_regime_alpha.research_qualification.application.evaluations import (
    EvaluationCommands,
)
from market_regime_alpha.research_qualification.application.qualification import (
    QualificationCommands,
)
from market_regime_alpha.research_qualification.domain.assessment import (
    AssessmentStatus,
)
from market_regime_alpha.research_qualification.domain.evidence import (
    EvidenceClass,
    EvidenceDirection,
    EvidenceOriginClass,
    EvidenceRole,
)
from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationProtocolPlan,
    ProtocolMetricDefinition,
)
from market_regime_alpha.research_qualification.domain.qualification import (
    FloorMissingnessPolicy,
    QualificationOperator,
    QualificationPolicyFloorPlan,
    QualificationPurpose,
    ResearchQualificationDecisionPlan,
    ResearchQualificationPolicyPlan,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    EvaluationReducer,
    EvaluationSliceKind,
    AcceptanceOperator,
    MetricDirection,
    PartitionPurpose,
    SourceMetricValueType,
)
from market_regime_alpha.runtime.errors import IdempotencyKeyReusedError
from tests.refoundation.research_qualification import (
    test_assessment_postgres as _assessment,
)
from tests.refoundation.research_qualification import (
    test_evaluation_closure_postgres as _wp11,
)


@pytest.fixture
def wp12_qualification_stack(target_database_url, tmp_path, request):
    return _wp11.wp11_stack.__wrapped__(target_database_url, tmp_path, request)


def _assessment_authority(stack, *, counter=False):
    target, experiment_id, evaluation_run_id, completed_at = (
        _assessment._completed_authority(stack)
    )
    _assessment._record_evidence(
        stack,
        target,
        evaluation_run_id,
        completed_at,
        direction=EvidenceDirection.SUPPORT,
        code=f"wp12-qualification-support-{uuid4().hex[:8]}",
    )
    if counter:
        _assessment._record_evidence(
            stack,
            target,
            evaluation_run_id,
            completed_at,
            direction=EvidenceDirection.COUNTER,
            code=f"wp12-qualification-counter-{uuid4().hex[:8]}",
        )
    plan = _assessment._assessment_plan(
        target,
        experiment_id,
        _assessment._cutoff(stack),
        code=f"wp12-qualification-assessment-{uuid4().hex[:8]}",
    )
    result = AssessmentCommands(
        PostgresAssessmentUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    ).assess(
        plan,
        _wp11._wp11_context(
            f"assess-for-qualification-{uuid4().hex[:8]}",
            "ASSESS_RESEARCH_EXPERIMENT",
        ),
    )
    return target, evaluation_run_id, plan, result


def _floor(stack, evaluation_run_id, *, minimum_member_count=1, threshold="0"):
    with psycopg.connect(stack.database_url) as connection:
        row = connection.execute(
            """
            SELECT metric.evaluation_protocol_id,
                   metric.evaluation_protocol_metric_id,
                   metric.content_sha256, metric.metric_code,
                   metric.source_value_type, metric.reducer,
                   metric.slice_kind, metric.candidate_disposition,
                   metric.direction
            FROM mra.evaluation_run AS run
            JOIN mra.evaluation_protocol_metric AS metric
              ON metric.evaluation_protocol_id = run.evaluation_protocol_id
            WHERE run.evaluation_run_id = %s
            ORDER BY metric.ordinal
            """,
            (evaluation_run_id,),
        ).fetchone()
    assert row is not None
    return QualificationPolicyFloorPlan(
        research_qualification_policy_floor_id=uuid4(),
        floor_code=f"primary-{uuid4().hex[:8]}",
        ordinal=1,
        evaluation_protocol_id=row[0],
        evaluation_protocol_metric_id=row[1],
        evaluation_protocol_metric_sha256=row[2],
        required_partition_purpose=PartitionPurpose.VALIDATION,
        required_evaluation_status="COMPLETED",
        metric_code=row[3],
        source_value_type=SourceMetricValueType(row[4]),
        reducer=EvaluationReducer(row[5]),
        slice_kind=EvaluationSliceKind(row[6]),
        candidate_disposition=None,
        direction=MetricDirection(row[8]),
        operator=QualificationOperator.AT_LEAST,
        decimal_threshold=Decimal(threshold),
        boolean_threshold=None,
        minimum_member_count=minimum_member_count,
        minimum_estimable_count=1,
        missingness_policy=FloorMissingnessPolicy.INCONCLUSIVE,
        required_evidence_class=EvidenceClass.RESEARCH_RESULT,
        required_origin_class=EvidenceOriginClass.DERIVED_CANONICAL,
        required_evidence_role=EvidenceRole.PRIMARY_RESULT,
        minimum_support_evidence_count=1,
        maximum_counter_evidence_count=0,
        required=True,
    )


def _policy(target, floor, *, code):
    return ResearchQualificationPolicyPlan(
        research_qualification_policy_id=uuid4(),
        policy_code=code,
        version=1,
        supersedes_policy_id=None,
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        qualification_purpose=QualificationPurpose.VALIDATION,
        required_assessment_status=AssessmentStatus.SUPPORTED,
        require_preaccess_freeze=False,
        floors=(floor,),
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="e" * 64,
    )


def _decision(stack, assessment_id, policy, target, *, code):
    with psycopg.connect(stack.database_url) as connection:
        authority_time = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    return ResearchQualificationDecisionPlan(
        research_qualification_decision_id=uuid4(),
        decision_code=code,
        revision=1,
        supersedes_decision_id=None,
        research_assessment_id=assessment_id,
        research_qualification_policy_id=policy.research_qualification_policy_id,
        effective_at=authority_time,
        known_at=authority_time,
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="f" * 64,
    )


def test_qualification_evaluates_every_floor_and_binds_exact_evidence(
    wp12_qualification_stack,
) -> None:
    stack = wp12_qualification_stack
    target, evaluation_run_id, assessment, assessment_result = _assessment_authority(
        stack
    )
    floor = _floor(stack, evaluation_run_id)
    policy = _policy(
        target, floor, code=f"wp12-policy-{uuid4().hex[:8]}"
    )
    commands = QualificationCommands(
        PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    policy_context = _wp11._wp11_context(
        "register-qualification-policy", "REGISTER_RESEARCH_QUALIFICATION_POLICY"
    )
    policy_result = commands.register_policy(policy, policy_context)
    policy_replay = commands.register_policy(policy, policy_context)
    assert policy_result.replayed is False
    assert policy_replay.replayed is True

    decision = _decision(
        stack,
        assessment.research_assessment_id,
        policy,
        target,
        code=f"wp12-decision-{uuid4().hex[:8]}",
    )
    decision_context = _wp11._wp11_context(
        "decide-qualification", "DECIDE_RESEARCH_QUALIFICATION"
    )
    result = commands.decide(decision, decision_context)
    replay = commands.decide(decision, decision_context)

    assert assessment_result.assessment_status == "SUPPORTED"
    assert result.decision_status == "ADMITTED"
    assert result.floor_count == 1
    assert replay.replayed is True
    with psycopg.connect(stack.database_url) as connection:
        floor_rows = connection.execute(
            """
            SELECT result_status, support_evidence_count,
                   counter_evidence_count
            FROM mra.research_qualification_floor_result
            WHERE research_qualification_decision_id = %s
            """,
            (decision.research_qualification_decision_id,),
        ).fetchall()
        evidence_count = connection.execute(
            """
            SELECT count(*) FROM mra.research_qualification_floor_evidence
            WHERE research_qualification_decision_id = %s
            """,
            (decision.research_qualification_decision_id,),
        ).fetchone()
    assert floor_rows == [("SATISFIED", 1, 0)]
    assert evidence_count == (1,)
    with pytest.raises(IdempotencyKeyReusedError):
        commands.decide(
            replace(decision, research_qualification_decision_id=uuid4()),
            decision_context,
        )


@pytest.mark.parametrize(
    ("counter", "minimum_member_count", "expected_assessment", "expected_floor", "expected_decision"),
    [
        (True, 1, "INCONCLUSIVE", "REJECTED", "REJECTED"),
        (False, 2, "SUPPORTED", "INCONCLUSIVE", "INCONCLUSIVE"),
    ],
)
def test_qualification_preserves_counter_and_insufficient_sample(
    wp12_qualification_stack,
    counter,
    minimum_member_count,
    expected_assessment,
    expected_floor,
    expected_decision,
) -> None:
    stack = wp12_qualification_stack
    target, evaluation_run_id, assessment, assessment_result = _assessment_authority(
        stack, counter=counter
    )
    floor = _floor(
        stack,
        evaluation_run_id,
        minimum_member_count=minimum_member_count,
    )
    policy = _policy(
        target, floor, code=f"wp12-policy-{uuid4().hex[:8]}"
    )
    commands = QualificationCommands(
        PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    commands.register_policy(
        policy,
        _wp11._wp11_context(
            f"register-policy-{uuid4().hex[:8]}",
            "REGISTER_RESEARCH_QUALIFICATION_POLICY",
        ),
    )
    decision = _decision(
        stack,
        assessment.research_assessment_id,
        policy,
        target,
        code=f"wp12-decision-{uuid4().hex[:8]}",
    )
    result = commands.decide(
        decision,
        _wp11._wp11_context(
            f"decide-{uuid4().hex[:8]}", "DECIDE_RESEARCH_QUALIFICATION"
        ),
    )
    with psycopg.connect(stack.database_url) as connection:
        floor_status = connection.execute(
            """
            SELECT result_status FROM mra.research_qualification_floor_result
            WHERE research_qualification_decision_id = %s
            """,
            (decision.research_qualification_decision_id,),
        ).fetchone()[0]
    assert assessment_result.assessment_status == expected_assessment
    assert floor_status == expected_floor
    assert result.decision_status == expected_decision


def test_qualification_concurrent_identical_decision_has_one_root(
    wp12_qualification_stack,
) -> None:
    stack = wp12_qualification_stack
    target, evaluation_run_id, assessment, _ = _assessment_authority(stack)
    policy = _policy(
        target,
        _floor(stack, evaluation_run_id),
        code=f"wp12-race-policy-{uuid4().hex[:8]}",
    )
    commands = QualificationCommands(
        PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    commands.register_policy(
        policy,
        _wp11._wp11_context(
            "register-race-policy", "REGISTER_RESEARCH_QUALIFICATION_POLICY"
        ),
    )
    decision = _decision(
        stack,
        assessment.research_assessment_id,
        policy,
        target,
        code=f"wp12-race-decision-{uuid4().hex[:8]}",
    )
    context = _wp11._wp11_context(
        "decide-race", "DECIDE_RESEARCH_QUALIFICATION"
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: commands.decide(decision, context), range(2)))
    assert sorted(result.replayed for result in results) == [False, True]
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT count(*) FROM mra.research_qualification_decision
            WHERE decision_code = %s
            """,
            (decision.decision_code,),
        ).fetchone() == (1,)


def test_qualification_records_missing_floor_instead_of_skipping_it(
    wp12_qualification_stack,
) -> None:
    stack = wp12_qualification_stack
    target, _, assessment, _ = _assessment_authority(stack)
    source_metric = target.metrics[0]
    protocol = EvaluationProtocolPlan(
        evaluation_protocol_id=uuid4(),
        protocol_code=f"wp12-missing-protocol-{uuid4().hex[:8]}",
        protocol_version=1,
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        applicable_purpose=PartitionPurpose.VALIDATION,
        decision_rule="Declare a metric for which this Assessment has no EvaluationRun.",
        metrics=(
            ProtocolMetricDefinition(
                evaluation_protocol_metric_id=uuid4(),
                metric_code=f"missing-{uuid4().hex[:8]}",
                ordinal=1,
                source_target_metric_definition_id=(
                    source_metric.target_metric_definition_id
                ),
                source_metric_code=source_metric.metric_code,
                source_value_type=SourceMetricValueType.DECIMAL,
                reducer=EvaluationReducer.MEAN_DECIMAL,
                slice_kind=EvaluationSliceKind.ALL_MEMBERS,
                candidate_disposition=None,
                direction=MetricDirection.DESCRIPTIVE,
                minimum_estimable_count=1,
                acceptance_operator=AcceptanceOperator.NONE,
                acceptance_threshold=None,
            ),
        ),
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="1" * 64,
    )
    EvaluationCommands(
        PostgresEvaluationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    ).register_protocol(
        protocol,
        _wp11._wp11_context(
            "register-missing-floor-protocol", "REGISTER_EVALUATION_PROTOCOL"
        ),
    )
    metric = protocol.metrics[0]
    floor = QualificationPolicyFloorPlan(
        research_qualification_policy_floor_id=uuid4(),
        floor_code="missing-declared-floor",
        ordinal=1,
        evaluation_protocol_id=protocol.evaluation_protocol_id,
        evaluation_protocol_metric_id=metric.evaluation_protocol_metric_id,
        evaluation_protocol_metric_sha256=metric.content_sha256,
        required_partition_purpose=PartitionPurpose.VALIDATION,
        required_evaluation_status="COMPLETED",
        metric_code=metric.metric_code,
        source_value_type=metric.source_value_type,
        reducer=metric.reducer,
        slice_kind=metric.slice_kind,
        candidate_disposition=None,
        direction=metric.direction,
        operator=QualificationOperator.AT_LEAST,
        decimal_threshold=Decimal("0"),
        boolean_threshold=None,
        minimum_member_count=1,
        minimum_estimable_count=1,
        missingness_policy=FloorMissingnessPolicy.INCONCLUSIVE,
        required_evidence_class=EvidenceClass.RESEARCH_RESULT,
        required_origin_class=EvidenceOriginClass.DERIVED_CANONICAL,
        required_evidence_role=EvidenceRole.PRIMARY_RESULT,
        minimum_support_evidence_count=1,
        maximum_counter_evidence_count=0,
        required=True,
    )
    policy = _policy(
        target, floor, code=f"wp12-missing-policy-{uuid4().hex[:8]}"
    )
    commands = QualificationCommands(
        PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    commands.register_policy(
        policy,
        _wp11._wp11_context(
            "register-missing-floor-policy",
            "REGISTER_RESEARCH_QUALIFICATION_POLICY",
        ),
    )
    decision = _decision(
        stack,
        assessment.research_assessment_id,
        policy,
        target,
        code=f"wp12-missing-decision-{uuid4().hex[:8]}",
    )
    result = commands.decide(
        decision,
        _wp11._wp11_context(
            "decide-missing-floor", "DECIDE_RESEARCH_QUALIFICATION"
        ),
    )
    with psycopg.connect(stack.database_url) as connection:
        floor_result = connection.execute(
            """
            SELECT result_status, evaluation_run_id, evaluation_metric_id
            FROM mra.research_qualification_floor_result
            WHERE research_qualification_decision_id = %s
            """,
            (decision.research_qualification_decision_id,),
        ).fetchone()
    assert floor_result == ("MISSING", None, None)
    assert result.decision_status == "INCONCLUSIVE"
