from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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
from market_regime_alpha.research_qualification.application.assessment import (
    AssessmentCommands,
)
from market_regime_alpha.research_qualification.application.evidence import (
    EvidenceCommands,
)
from market_regime_alpha.research_qualification.domain.assessment import (
    ResearchAssessmentPlan,
)
from market_regime_alpha.research_qualification.domain.evidence import (
    EvidenceClass,
    EvidenceDirection,
    EvidenceItemPlan,
    EvidenceOriginClass,
    EvidenceRole,
    EvidenceScope,
    ResearchProofClass,
)
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
)
from tests.refoundation.research_qualification import (
    test_evaluation_closure_postgres as _wp11,
)


@pytest.fixture
def wp12_assessment_stack(target_database_url, tmp_path, request):
    return _wp11.wp11_stack.__wrapped__(target_database_url, tmp_path, request)


def _completed_authority(stack):
    target, _, _, settled = _wp11._settle_two_visible_revisions(stack)
    commands, _, experiment_run_id, protocol = _wp11._freeze_and_predeclare(
        stack, target
    )
    evaluation_run_id, _, _ = _wp11._run_evaluation(
        commands,
        experiment_run_id,
        protocol,
        settled[1][1] + timedelta(microseconds=1),
        "wp12-assessment",
    )
    with psycopg.connect(stack.database_url) as connection:
        row = connection.execute(
            """
            SELECT experiment_id, completed_at FROM mra.evaluation_run
            WHERE evaluation_run_id = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
    assert row is not None
    return target, row[0], evaluation_run_id, row[1]


def _record_evidence(
    stack,
    target,
    evaluation_run_id,
    observed_at,
    *,
    direction: EvidenceDirection,
    code: str,
):
    plan = EvidenceItemPlan(
        evidence_item_id=uuid4(),
        evaluation_run_id=evaluation_run_id,
        evaluation_metric_id=None,
        evidence_code=code,
        scope=EvidenceScope.RUN,
        evidence_class=EvidenceClass.RESEARCH_RESULT,
        origin_class=EvidenceOriginClass.DERIVED_CANONICAL,
        role=EvidenceRole.PRIMARY_RESULT,
        direction=direction,
        proof_ceiling=ResearchProofClass.EXPLORATORY,
        observed_at=observed_at,
        evidence_artifact=target.algorithm.config_artifact,
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="c" * 64,
        dependencies=(),
    )
    EvidenceCommands(
        PostgresEvidenceUnitOfWorkProvider(stack.pool), id_factory=uuid4
    ).record(
        plan,
        _wp11._wp11_context(f"record-{code}", "RECORD_RESEARCH_EVIDENCE"),
    )
    return plan


def _cutoff(stack):
    with psycopg.connect(stack.database_url) as connection:
        return connection.execute("SELECT clock_timestamp()").fetchone()[0]


def _assessment_plan(target, experiment_id, cutoff, *, code, revision=1, supersedes=None):
    return ResearchAssessmentPlan(
        research_assessment_id=uuid4(),
        assessment_code=code,
        revision=revision,
        supersedes_assessment_id=supersedes,
        experiment_id=experiment_id,
        knowledge_cutoff=cutoff,
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="d" * 64,
    )


def test_assessment_derives_complete_evaluation_and_evidence_rosters(
    wp12_assessment_stack,
) -> None:
    stack = wp12_assessment_stack
    target, experiment_id, evaluation_run_id, completed_at = _completed_authority(stack)
    support = _record_evidence(
        stack,
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=1),
        direction=EvidenceDirection.SUPPORT,
        code=f"wp12-support-{uuid4().hex[:8]}",
    )
    counter = _record_evidence(
        stack,
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=2),
        direction=EvidenceDirection.COUNTER,
        code=f"wp12-counter-{uuid4().hex[:8]}",
    )
    plan = _assessment_plan(
        target,
        experiment_id,
        _cutoff(stack),
        code=f"wp12-assessment-{uuid4().hex[:8]}",
    )
    commands = AssessmentCommands(
        PostgresAssessmentUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    context = _wp11._wp11_context(
        "assess-complete-roster", "ASSESS_RESEARCH_EXPERIMENT"
    )
    result = commands.assess(plan, context)
    replay = commands.assess(plan, context)

    assert result.assessment_status == "INCONCLUSIVE"
    assert result.evaluation_count == 1
    assert result.evidence_count == 2
    assert replay.replayed is True
    with pytest.raises(IdempotencyKeyReusedError):
        commands.assess(
            replace(plan, research_assessment_id=uuid4()),
            context,
        )
    with psycopg.connect(stack.database_url) as connection:
        evaluations = connection.execute(
            """
            SELECT evaluation_run_id FROM mra.research_assessment_evaluation
            WHERE research_assessment_id = %s
            """,
            (plan.research_assessment_id,),
        ).fetchall()
        evidence = connection.execute(
            """
            SELECT evidence_item_id, evidence_direction
            FROM mra.research_assessment_evidence
            WHERE research_assessment_id = %s ORDER BY evidence_ordinal
            """,
            (plan.research_assessment_id,),
        ).fetchall()
    assert evaluations == [(evaluation_run_id,)]
    assert evidence == [
        (support.evidence_item_id, "SUPPORT"),
        (counter.evidence_item_id, "COUNTER"),
    ]


def test_assessment_rejects_incomplete_evidence(
    wp12_assessment_stack,
) -> None:
    stack = wp12_assessment_stack
    target, experiment_id, _, _ = _completed_authority(stack)
    plan = _assessment_plan(
        target,
        experiment_id,
        _cutoff(stack),
        code=f"wp12-incomplete-{uuid4().hex[:8]}",
    )
    commands = AssessmentCommands(
        PostgresAssessmentUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    context = _wp11._wp11_context(
        "assess-incomplete", "ASSESS_RESEARCH_EXPERIMENT"
    )
    with pytest.raises(RuntimeStateConflictError):
        commands.assess(plan, context)


def test_assessment_supersession_is_append_only(wp12_assessment_stack) -> None:
    stack = wp12_assessment_stack
    target, experiment_id, evaluation_run_id, completed_at = _completed_authority(stack)
    _record_evidence(
        stack,
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=1),
        direction=EvidenceDirection.SUPPORT,
        code=f"wp12-supersession-{uuid4().hex[:8]}",
    )
    commands = AssessmentCommands(
        PostgresAssessmentUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    code = f"wp12-series-{uuid4().hex[:8]}"
    first = _assessment_plan(target, experiment_id, _cutoff(stack), code=code)
    commands.assess(
        first,
        _wp11._wp11_context("assess-revision-1", "ASSESS_RESEARCH_EXPERIMENT"),
    )
    second = _assessment_plan(
        target,
        experiment_id,
        _cutoff(stack),
        code=code,
        revision=2,
        supersedes=first.research_assessment_id,
    )
    result = commands.assess(
        second,
        _wp11._wp11_context("assess-revision-2", "ASSESS_RESEARCH_EXPERIMENT"),
    )
    assert result.revision == 2
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT revision, supersedes_assessment_id
            FROM mra.research_assessment WHERE assessment_code = %s
            ORDER BY revision
            """,
            (code,),
        ).fetchall() == [(1, None), (2, first.research_assessment_id)]


def test_assessment_concurrent_identical_request_has_one_root(
    wp12_assessment_stack,
) -> None:
    stack = wp12_assessment_stack
    target, experiment_id, evaluation_run_id, completed_at = _completed_authority(stack)
    _record_evidence(
        stack,
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=1),
        direction=EvidenceDirection.SUPPORT,
        code=f"wp12-race-evidence-{uuid4().hex[:8]}",
    )
    plan = _assessment_plan(
        target,
        experiment_id,
        _cutoff(stack),
        code=f"wp12-race-{uuid4().hex[:8]}",
    )
    commands = AssessmentCommands(
        PostgresAssessmentUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    context = _wp11._wp11_context("assess-race", "ASSESS_RESEARCH_EXPERIMENT")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: commands.assess(plan, context), range(2)))
    assert sorted(item.replayed for item in results) == [False, True]
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.research_assessment WHERE assessment_code = %s",
            (plan.assessment_code,),
        ).fetchone() == (1,)
