from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.evidence_uow import (
    PostgresEvidenceUnitOfWorkProvider,
)
from market_regime_alpha.research_qualification.application.evidence import (
    EvidenceCommands,
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
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
)
from tests.refoundation.research_qualification import (
    test_evaluation_closure_postgres as _wp11,
)


@pytest.fixture
def wp12_evidence_stack(target_database_url, tmp_path, request):
    return _wp11.wp11_stack.__wrapped__(target_database_url, tmp_path, request)


def _completed_evaluation(stack):
    target, _, _, settled = _wp11._settle_two_visible_revisions(stack)
    commands, _, experiment_run_id, protocol = _wp11._freeze_and_predeclare(stack, target)
    evaluation_run_id, _, _ = _wp11._run_evaluation(
        commands,
        experiment_run_id,
        protocol,
        settled[1][1] + timedelta(microseconds=1),
        "wp12-evidence",
    )
    with psycopg.connect(stack.database_url) as connection:
        row = connection.execute(
            """
            SELECT completed_at FROM mra.evaluation_run
            WHERE evaluation_run_id = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
    assert row is not None
    return target, protocol, evaluation_run_id, row[0]


def _plan(target, evaluation_run_id, observed_at, *, code, dependencies=()):
    return EvidenceItemPlan(
        evidence_item_id=uuid4(),
        evaluation_run_id=evaluation_run_id,
        evaluation_metric_id=None,
        evidence_code=code,
        scope=EvidenceScope.RUN,
        evidence_class=EvidenceClass.RESEARCH_RESULT,
        origin_class=EvidenceOriginClass.DERIVED_CANONICAL,
        role=EvidenceRole.PRIMARY_RESULT,
        direction=EvidenceDirection.SUPPORT,
        proof_ceiling=ResearchProofClass.EXPLORATORY,
        observed_at=observed_at,
        evidence_artifact=target.algorithm.config_artifact,
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="a" * 64,
        dependencies=dependencies,
    )


def test_evidence_is_evaluation_bound_append_only_and_exactly_replayable(
    wp12_evidence_stack,
) -> None:
    stack = wp12_evidence_stack
    target, _, evaluation_run_id, completed_at = _completed_evaluation(stack)
    commands = EvidenceCommands(PostgresEvidenceUnitOfWorkProvider(stack.pool), id_factory=uuid4)
    parent = _plan(
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=1),
        code=f"wp12-parent-{uuid4().hex[:8]}",
    )
    parent_result = commands.record(
        parent,
        _wp11._wp11_context("record-parent-evidence", "RECORD_RESEARCH_EVIDENCE"),
    )
    dependency = EvidenceDependencyPlan(
        evidence_dependency_id=uuid4(),
        parent_evidence_item_id=parent.evidence_item_id,
        ordinal=1,
        dependency_role=EvidenceDependencyRole.DERIVED_FROM,
    )
    child = _plan(
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=2),
        code=f"wp12-child-{uuid4().hex[:8]}",
        dependencies=(dependency,),
    )
    context = _wp11._wp11_context("record-child-evidence", "RECORD_RESEARCH_EVIDENCE")
    result = commands.record(child, context)
    replay = commands.record(child, context)

    assert parent_result.replayed is False
    assert result.replayed is False
    assert replay.replayed is True
    assert replay.result_hash == result.result_hash
    with psycopg.connect(stack.database_url) as connection:
        rows = connection.execute(
            """
            SELECT item.evidence_item_id, item.evaluation_run_id,
                   item.dependency_count, dependency.parent_evidence_item_id
            FROM mra.evidence_item AS item
            LEFT JOIN mra.evidence_dependency AS dependency
              ON dependency.child_evidence_item_id = item.evidence_item_id
            ORDER BY item.recorded_at
            """
        ).fetchall()
        assert rows == [
            (parent.evidence_item_id, evaluation_run_id, 0, None),
            (
                child.evidence_item_id,
                evaluation_run_id,
                1,
                parent.evidence_item_id,
            ),
        ]
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """
                UPDATE mra.evidence_item SET evidence_direction = 'COUNTER'
                WHERE evidence_item_id = %s
                """,
                (child.evidence_item_id,),
            )


def test_evidence_concurrency_has_one_authority_and_changed_request_fails(
    wp12_evidence_stack,
) -> None:
    stack = wp12_evidence_stack
    target, _, evaluation_run_id, completed_at = _completed_evaluation(stack)
    commands = EvidenceCommands(PostgresEvidenceUnitOfWorkProvider(stack.pool), id_factory=uuid4)
    plan = _plan(
        target,
        evaluation_run_id,
        completed_at + timedelta(microseconds=1),
        code=f"wp12-concurrent-{uuid4().hex[:8]}",
    )
    context = _wp11._wp11_context("record-concurrent-evidence", "RECORD_RESEARCH_EVIDENCE")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: commands.record(plan, context), range(2)))
    assert sorted(result.replayed for result in results) == [False, True]
    with pytest.raises(IdempotencyKeyReusedError):
        commands.record(
            replace(plan, evidence_item_id=uuid4(), direction=EvidenceDirection.COUNTER),
            context,
        )


def test_evidence_rejects_nonterminal_evaluation(wp12_evidence_stack) -> None:
    stack = wp12_evidence_stack
    target, _, _, settled = _wp11._settle_two_visible_revisions(stack)
    commands, _, experiment_run_id, protocol = _wp11._freeze_and_predeclare(stack, target)
    evaluation_run_id = uuid4()
    from market_regime_alpha.research_qualification.domain.evaluation import (
        EvaluationRunPlan,
    )

    commands.open_run(
        EvaluationRunPlan(
            evaluation_run_id=evaluation_run_id,
            experiment_run_id=experiment_run_id,
            evaluation_protocol_id=protocol.evaluation_protocol_id,
            requested_knowledge_cutoff=settled[1][1] + timedelta(microseconds=1),
            request_identity="wp12-nonterminal-evaluation",
            code_artifact=protocol.code_artifact,
            config_artifact=protocol.config_artifact,
            provenance_sha256="b" * 64,
        ),
        _wp11._wp11_context("open-nonterminal", "OPEN_EVALUATION_RUN"),
    )
    evidence = EvidenceCommands(PostgresEvidenceUnitOfWorkProvider(stack.pool), id_factory=uuid4)
    plan = _plan(
        target,
        evaluation_run_id,
        settled[1][1] + timedelta(seconds=1),
        code=f"wp12-nonterminal-{uuid4().hex[:8]}",
    )
    with pytest.raises(RuntimeStateConflictError):
        evidence.record(
            plan,
            _wp11._wp11_context("record-nonterminal-evidence", "RECORD_RESEARCH_EVIDENCE"),
        )


def test_evidence_rejects_self_cycle_without_partial_authority(
    wp12_evidence_stack,
) -> None:
    stack = wp12_evidence_stack
    target, _, evaluation_run_id, completed_at = _completed_evaluation(stack)
    evidence_item_id = uuid4()
    dependency = EvidenceDependencyPlan(
        evidence_dependency_id=uuid4(),
        parent_evidence_item_id=evidence_item_id,
        ordinal=1,
        dependency_role=EvidenceDependencyRole.DERIVED_FROM,
    )
    with pytest.raises(ValueError, match="depend on itself"):
        replace(
            _plan(
                target,
                evaluation_run_id,
                completed_at + timedelta(microseconds=1),
                code=f"wp12-self-cycle-{uuid4().hex[:8]}",
                dependencies=(dependency,),
            ),
            evidence_item_id=evidence_item_id,
        )
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.evidence_item
               WHERE evidence_item_id = %s),
              (SELECT count(*) FROM mra.evidence_dependency
               WHERE child_evidence_item_id = %s)
            """,
            (evidence_item_id, evidence_item_id),
        ).fetchone() == (0, 0)
