from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.assessment_uow import (
    PostgresAssessmentUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.evidence_uow import (
    PostgresEvidenceUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.qualification_uow import (
    PostgresQualificationUnitOfWorkProvider,
)
from market_regime_alpha.research_qualification.application.assessment import (
    AssessmentCommands,
)
from market_regime_alpha.research_qualification.application.evidence import (
    EvidenceCommands,
)
from market_regime_alpha.research_qualification.application.qualification import (
    QualificationCommands,
)
from market_regime_alpha.research_qualification.domain.evidence import (
    EvidenceDependencyPlan,
    EvidenceDependencyRole,
    EvidenceDirection,
)
from market_regime_alpha.research_qualification.errors import (
    ResearchRetryableTransactionError,
)
from market_regime_alpha.runtime.errors import StaleFenceError
from tests.refoundation.outcome import test_outcome_postgres as _outcome
from tests.refoundation.research_qualification import (
    test_assessment_postgres as _assessment,
)
from tests.refoundation.research_qualification import (
    test_evaluation_closure_postgres as _wp11,
)
from tests.refoundation.research_qualification import (
    test_evidence_postgres as _evidence,
)
from tests.refoundation.research_qualification import (
    test_qualification_postgres as _qualification,
)


@pytest.fixture
def wp12_engineering_stack(target_database_url, tmp_path, request):
    return _wp11.wp11_stack.__wrapped__(target_database_url, tmp_path, request)


def _execute_ddl(stack, sql: str) -> None:
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(sql)
        connection.commit()


def test_mid_roster_serialization_failures_roll_back_and_recover_exactly(
    wp12_engineering_stack,
) -> None:
    stack = wp12_engineering_stack
    target, experiment_id, evaluation_run_id, completed_at = _assessment._completed_authority(stack)
    parent = _assessment._record_evidence(
        stack,
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=1),
        direction=EvidenceDirection.SUPPORT,
        code=f"wp12-recovery-parent-{uuid4().hex[:8]}",
    )
    child = _evidence._plan(
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=2),
        code=f"wp12-recovery-child-{uuid4().hex[:8]}",
        dependencies=(
            EvidenceDependencyPlan(
                evidence_dependency_id=uuid4(),
                parent_evidence_item_id=parent.evidence_item_id,
                ordinal=1,
                dependency_role=EvidenceDependencyRole.DERIVED_FROM,
            ),
        ),
    )
    evidence_context = _wp11._wp11_context("mid-evidence-dependency", "RECORD_RESEARCH_EVIDENCE")
    evidence_commands = EvidenceCommands(PostgresEvidenceUnitOfWorkProvider(stack.pool), id_factory=uuid4)
    _execute_ddl(
        stack,
        """
        CREATE FUNCTION mra.wp12_fail_evidence_dependency()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'injected mid-Evidence serialization'
                USING ERRCODE = '40001';
        END;
        $$;
        CREATE TRIGGER wp12_fail_evidence_dependency
        BEFORE INSERT ON mra.evidence_dependency
        FOR EACH ROW EXECUTE FUNCTION mra.wp12_fail_evidence_dependency();
        """,
    )
    try:
        with pytest.raises(ResearchRetryableTransactionError):
            evidence_commands.record(child, evidence_context)
        with psycopg.connect(stack.database_url) as connection:
            assert connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM mra.evidence_item
                   WHERE evidence_item_id = %s),
                  (SELECT count(*) FROM mra.evidence_dependency
                   WHERE child_evidence_item_id = %s),
                  (SELECT count(*) FROM mra.command_receipt
                   WHERE idempotency_key = %s)
                """,
                (
                    child.evidence_item_id,
                    child.evidence_item_id,
                    evidence_context.idempotency_key,
                ),
            ).fetchone() == (0, 0, 0)
    finally:
        _execute_ddl(
            stack,
            """
            DROP TRIGGER wp12_fail_evidence_dependency ON mra.evidence_dependency;
            DROP FUNCTION mra.wp12_fail_evidence_dependency();
            """,
        )
    assert evidence_commands.record(child, evidence_context).replayed is False

    assessment = _assessment._assessment_plan(
        target,
        experiment_id,
        _assessment._cutoff(stack),
        code=f"wp12-recovery-assessment-{uuid4().hex[:8]}",
    )
    assessment_context = _wp11._wp11_context("mid-assessment-evidence", "ASSESS_RESEARCH_EXPERIMENT")
    assessment_commands = AssessmentCommands(
        PostgresAssessmentUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    _execute_ddl(
        stack,
        """
        CREATE FUNCTION mra.wp12_fail_assessment_evidence()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.evidence_ordinal = 2 THEN
                RAISE EXCEPTION 'injected mid-Assessment serialization'
                    USING ERRCODE = '40001';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER wp12_fail_assessment_evidence
        BEFORE INSERT ON mra.research_assessment_evidence
        FOR EACH ROW EXECUTE FUNCTION mra.wp12_fail_assessment_evidence();
        """,
    )
    try:
        with pytest.raises(ResearchRetryableTransactionError):
            assessment_commands.assess(assessment, assessment_context)
        with psycopg.connect(stack.database_url) as connection:
            assert connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM mra.research_assessment
                   WHERE research_assessment_id = %s),
                  (SELECT count(*) FROM mra.research_assessment_evaluation
                   WHERE research_assessment_id = %s),
                  (SELECT count(*) FROM mra.research_assessment_evidence
                   WHERE research_assessment_id = %s),
                  (SELECT count(*) FROM mra.command_receipt
                   WHERE idempotency_key = %s)
                """,
                (
                    assessment.research_assessment_id,
                    assessment.research_assessment_id,
                    assessment.research_assessment_id,
                    assessment_context.idempotency_key,
                ),
            ).fetchone() == (0, 0, 0, 0)
    finally:
        _execute_ddl(
            stack,
            """
            DROP TRIGGER wp12_fail_assessment_evidence
              ON mra.research_assessment_evidence;
            DROP FUNCTION mra.wp12_fail_assessment_evidence();
            """,
        )
    assessment_result = assessment_commands.assess(assessment, assessment_context)
    assert assessment_result.evaluation_count == 1
    assert assessment_result.evidence_count == 2

    floor = _qualification._floor(stack, evaluation_run_id)
    policy = _qualification._policy(
        target,
        floor,
        code=f"wp12-recovery-policy-{uuid4().hex[:8]}",
    )
    qualification_commands = QualificationCommands(
        PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    qualification_commands.register_policy(
        policy,
        _wp11._wp11_context("register-recovery-policy", "REGISTER_RESEARCH_QUALIFICATION_POLICY"),
    )
    decision = _qualification._decision(
        stack,
        assessment.research_assessment_id,
        policy,
        target,
        code=f"wp12-recovery-decision-{uuid4().hex[:8]}",
    )
    decision_context = _wp11._wp11_context("mid-floor-evidence", "DECIDE_RESEARCH_QUALIFICATION")
    _execute_ddl(
        stack,
        """
        CREATE FUNCTION mra.wp12_fail_floor_evidence()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.evidence_ordinal = 2 THEN
                RAISE EXCEPTION 'injected mid-Qualification serialization'
                    USING ERRCODE = '40001';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER wp12_fail_floor_evidence
        BEFORE INSERT ON mra.research_qualification_floor_evidence
        FOR EACH ROW EXECUTE FUNCTION mra.wp12_fail_floor_evidence();
        """,
    )
    try:
        with pytest.raises(ResearchRetryableTransactionError):
            qualification_commands.decide(decision, decision_context)
        with psycopg.connect(stack.database_url) as connection:
            assert connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM mra.research_qualification_decision
                   WHERE research_qualification_decision_id = %s),
                  (SELECT count(*) FROM mra.research_qualification_floor_result
                   WHERE research_qualification_decision_id = %s),
                  (SELECT count(*) FROM mra.research_qualification_floor_evidence
                   WHERE research_qualification_decision_id = %s),
                  (SELECT count(*) FROM mra.command_receipt
                   WHERE idempotency_key = %s)
                """,
                (
                    decision.research_qualification_decision_id,
                    decision.research_qualification_decision_id,
                    decision.research_qualification_decision_id,
                    decision_context.idempotency_key,
                ),
            ).fetchone() == (0, 0, 0, 0)
    finally:
        _execute_ddl(
            stack,
            """
            DROP TRIGGER wp12_fail_floor_evidence
              ON mra.research_qualification_floor_evidence;
            DROP FUNCTION mra.wp12_fail_floor_evidence();
            """,
        )
    recovered = qualification_commands.decide(decision, decision_context)
    assert recovered.floor_count == 1
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT count(*) FROM mra.research_qualification_floor_evidence
            WHERE research_qualification_decision_id = %s
            """,
            (decision.research_qualification_decision_id,),
        ).fetchone() == (2,)


def test_unknown_commit_results_probe_exact_receipts_without_rewrite(
    wp12_engineering_stack,
) -> None:
    stack = wp12_engineering_stack
    target, experiment_id, evaluation_run_id, completed_at = _assessment._completed_authority(stack)
    evidence = _evidence._plan(
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=1),
        code=f"wp12-unknown-evidence-{uuid4().hex[:8]}",
    )
    evidence_provider = _wp11._CommitAckLostOnce(PostgresEvidenceUnitOfWorkProvider(stack.pool))
    evidence_result = EvidenceCommands(evidence_provider, id_factory=uuid4).record(
        evidence,
        _wp11._wp11_context("unknown-evidence", "RECORD_RESEARCH_EVIDENCE"),
    )
    assert evidence_provider.lost and evidence_result.replayed

    assessment = _assessment._assessment_plan(
        target,
        experiment_id,
        _assessment._cutoff(stack),
        code=f"wp12-unknown-assessment-{uuid4().hex[:8]}",
    )
    assessment_provider = _wp11._CommitAckLostOnce(PostgresAssessmentUnitOfWorkProvider(stack.pool, id_factory=uuid4))
    assessment_result = AssessmentCommands(assessment_provider, id_factory=uuid4).assess(
        assessment,
        _wp11._wp11_context("unknown-assessment", "ASSESS_RESEARCH_EXPERIMENT"),
    )
    assert assessment_provider.lost and assessment_result.replayed

    policy = _qualification._policy(
        target,
        _qualification._floor(stack, evaluation_run_id),
        code=f"wp12-unknown-policy-{uuid4().hex[:8]}",
    )
    policy_provider = _wp11._CommitAckLostOnce(PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4))
    policy_commands = QualificationCommands(policy_provider, id_factory=uuid4)
    policy_result = policy_commands.register_policy(
        policy,
        _wp11._wp11_context("unknown-policy", "REGISTER_RESEARCH_QUALIFICATION_POLICY"),
    )
    assert policy_provider.lost and policy_result.replayed

    decision = _qualification._decision(
        stack,
        assessment.research_assessment_id,
        policy,
        target,
        code=f"wp12-unknown-decision-{uuid4().hex[:8]}",
    )
    decision_provider = _wp11._CommitAckLostOnce(PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4))
    decision_result = QualificationCommands(decision_provider, id_factory=uuid4).decide(
        decision,
        _wp11._wp11_context("unknown-decision", "DECIDE_RESEARCH_QUALIFICATION"),
    )
    assert decision_provider.lost and decision_result.replayed

    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.evidence_item
               WHERE evidence_item_id = %s),
              (SELECT count(*) FROM mra.research_assessment
               WHERE research_assessment_id = %s),
              (SELECT count(*) FROM mra.research_qualification_policy
               WHERE research_qualification_policy_id = %s),
              (SELECT count(*) FROM mra.research_qualification_decision
               WHERE research_qualification_decision_id = %s)
            """,
            (
                evidence.evidence_item_id,
                assessment.research_assessment_id,
                policy.research_qualification_policy_id,
                decision.research_qualification_decision_id,
            ),
        ).fetchone() == (1, 1, 1, 1)


def test_stale_fence_precedes_all_wp12_business_and_failure_writes(
    wp12_engineering_stack,
) -> None:
    stack = wp12_engineering_stack
    target, experiment_id, evaluation_run_id, completed_at = _assessment._completed_authority(stack)
    claim = _outcome._outcome_claim(stack)
    stale = replace(claim, fence_token=claim.fence_token + 1)

    evidence = _evidence._plan(
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=1),
        code=f"wp12-stale-evidence-{uuid4().hex[:8]}",
    )
    evidence_context = _wp11._wp11_context("stale-evidence", "RECORD_RESEARCH_EVIDENCE")
    with pytest.raises(StaleFenceError):
        EvidenceCommands(PostgresEvidenceUnitOfWorkProvider(stack.pool), id_factory=uuid4).record(
            evidence, evidence_context, runtime_claim=stale
        )

    assessment = _assessment._assessment_plan(
        target,
        experiment_id,
        _assessment._cutoff(stack),
        code=f"wp12-stale-assessment-{uuid4().hex[:8]}",
    )
    assessment_context = _wp11._wp11_context("stale-assessment", "ASSESS_RESEARCH_EXPERIMENT")
    with pytest.raises(StaleFenceError):
        AssessmentCommands(
            PostgresAssessmentUnitOfWorkProvider(stack.pool, id_factory=uuid4),
            id_factory=uuid4,
        ).assess(assessment, assessment_context, runtime_claim=stale)

    policy = _qualification._policy(
        target,
        _qualification._floor(stack, evaluation_run_id),
        code=f"wp12-stale-policy-{uuid4().hex[:8]}",
    )
    policy_context = _wp11._wp11_context("stale-policy", "REGISTER_RESEARCH_QUALIFICATION_POLICY")
    with pytest.raises(StaleFenceError):
        QualificationCommands(
            PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
            id_factory=uuid4,
        ).register_policy(policy, policy_context, runtime_claim=stale)

    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.evidence_item
               WHERE evidence_item_id = %s),
              (SELECT count(*) FROM mra.research_assessment
               WHERE research_assessment_id = %s),
              (SELECT count(*) FROM mra.research_qualification_policy
               WHERE research_qualification_policy_id = %s),
              (SELECT count(*) FROM mra.command_receipt
               WHERE idempotency_key = ANY(%s))
            """,
            (
                evidence.evidence_item_id,
                assessment.research_assessment_id,
                policy.research_qualification_policy_id,
                [
                    evidence_context.idempotency_key,
                    assessment_context.idempotency_key,
                    policy_context.idempotency_key,
                ],
            ),
        ).fetchone() == (0, 0, 0, 0)
