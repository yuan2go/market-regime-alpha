from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.decision_support.domain import (
    DecisionRunResearchQualificationMemberPlan,
    QualificationInputRole,
    ResearchPurpose,
    RequestedResearchQualification,
)
from market_regime_alpha.decision_support.errors import (
    DecisionQualificationResolutionError,
)
from market_regime_alpha.infrastructure.postgres.qualification_uow import (
    PostgresQualificationUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_inputs import (
    PostgresDecisionResearchQualificationInputProvider,
)
from market_regime_alpha.research_qualification.application.qualification import (
    QualificationCommands,
)
from tests.refoundation.decision_support.test_wp13_qualification_roster_domain import (
    _uuid,
)
from tests.refoundation.research_qualification import (
    test_evaluation_closure_postgres as _wp11,
)
from tests.refoundation.research_qualification import (
    test_qualification_postgres as _qualification,
)


@pytest.fixture
def wp13_qualification_stack(target_database_url, tmp_path, request):
    return _qualification.wp12_qualification_stack.__wrapped__(
        target_database_url,
        tmp_path,
        request,
    )


def _admitted(stack):
    target, evaluation_run_id, assessment, _ = (
        _qualification._assessment_authority(stack)
    )
    policy = _qualification._policy(
        target,
        _qualification._floor(stack, evaluation_run_id),
        code=f"wp13-policy-{uuid4().hex[:8]}",
    )
    commands = QualificationCommands(
        PostgresQualificationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    commands.register_policy(
        policy,
        _wp11._wp11_context(
            f"wp13-register-policy-{uuid4().hex[:8]}",
            "REGISTER_RESEARCH_QUALIFICATION_POLICY",
        ),
    )
    decision = _qualification._decision(
        stack,
        assessment.research_assessment_id,
        policy,
        target,
        code=f"wp13-decision-{uuid4().hex[:8]}",
    )
    result = commands.decide(
        decision,
        _wp11._wp11_context(
            f"wp13-decide-{uuid4().hex[:8]}",
            "DECIDE_RESEARCH_QUALIFICATION",
        ),
    )
    assert result.decision_status == "ADMITTED"
    return target, commands, decision


def test_exact_cutoff_resolver_rejects_wrong_purpose_and_superseded_revision(
    wp13_qualification_stack,
) -> None:
    stack = wp13_qualification_stack
    target, commands, first = _admitted(stack)
    requested = (
        RequestedResearchQualification(
            research_qualification_decision_id=(
                first.research_qualification_decision_id
            ),
            role=QualificationInputRole.PRIMARY,
        ),
    )
    resolver = PostgresDecisionResearchQualificationInputProvider(stack.pool)
    consumer_time = first.known_at + timedelta(microseconds=1)

    resolved = resolver.resolve_exact(
        requested,
        research_purpose=ResearchPurpose.VALIDATION,
        decision_time=consumer_time,
    )

    assert len(resolved) == 1
    assert resolved[0].research_qualification_decision_id == (
        first.research_qualification_decision_id
    )
    assert resolved[0].target_definition_id == target.target_definition_id
    assert resolved[0].source_generation_max_decision_time < consumer_time
    with pytest.raises(DecisionQualificationResolutionError):
        resolver.resolve_exact(
            requested,
            research_purpose=ResearchPurpose.DISCOVERY,
            decision_time=consumer_time,
        )

    with psycopg.connect(stack.database_url) as connection:
        second_time = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    second = replace(
        first,
        research_qualification_decision_id=uuid4(),
        revision=2,
        supersedes_decision_id=first.research_qualification_decision_id,
        effective_at=second_time,
        known_at=second_time,
    )
    commands.decide(
        second,
        _wp11._wp11_context(
            f"wp13-decide-superseding-{uuid4().hex[:8]}",
            "DECIDE_RESEARCH_QUALIFICATION",
        ),
    )

    with pytest.raises(DecisionQualificationResolutionError):
        resolver.resolve_exact(
            requested,
            research_purpose=ResearchPurpose.VALIDATION,
            decision_time=second.known_at,
        )
    successor = resolver.resolve_exact(
        (
            replace(
                requested[0],
                research_qualification_decision_id=(
                    second.research_qualification_decision_id
                ),
            ),
        ),
        research_purpose=ResearchPurpose.VALIDATION,
        decision_time=second.known_at,
    )
    assert successor[0].revision == 2
    assert successor[0].supersedes_decision_id == (
        first.research_qualification_decision_id
    )


def test_postgres_member_hash_matches_domain_for_nullable_first_revision(
    wp13_qualification_stack,
) -> None:
    stack = wp13_qualification_stack
    _, _, first = _admitted(stack)
    prepared = PostgresDecisionResearchQualificationInputProvider(
        stack.pool
    ).resolve_exact(
        (
            RequestedResearchQualification(
                research_qualification_decision_id=(
                    first.research_qualification_decision_id
                ),
                role=QualificationInputRole.PRIMARY,
            ),
        ),
        research_purpose=ResearchPurpose.VALIDATION,
        decision_time=first.known_at + timedelta(microseconds=1),
    )[0]
    member = DecisionRunResearchQualificationMemberPlan(
        member_id=_uuid(991),
        roster_id=_uuid(992),
        decision_run_id=_uuid(993),
        ordinal=1,
        source=prepared,
    )
    with psycopg.connect(stack.database_url) as connection:
        database_hash = connection.execute(
            """
            SELECT mra.decision_qualification_member_content_sha256(
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                prepared.decision_code,
                prepared.experiment_id,
                prepared.content_sha256,
                prepared.qualification_purpose.value,
                prepared.revision,
                prepared.research_assessment_id,
                prepared.research_qualification_decision_id,
                prepared.research_qualification_policy_id,
                prepared.role.value,
                prepared.source_generation_max_decision_time,
                prepared.supersedes_decision_id,
                prepared.target_definition_id,
            ),
        ).fetchone()[0]
    assert database_hash == member.content_sha256
