from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import psycopg
import pytest

from market_regime_alpha.decision_support.application import ContextCommands
from market_regime_alpha.decision_support.domain import DecisionArtifactBinding
from market_regime_alpha.decision_support.errors import ContextAuthorityIntegrityError
from market_regime_alpha.infrastructure.postgres.context_uow import (
    PostgresContextUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_context_inputs import (
    PostgresContextInputPreparationProvider,
    PostgresContextQueryProvider,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError
from tests.refoundation.decision_support import test_decision_postgres as _decision
from tests.refoundation.decision_support.test_wp13_context_domain import _policy
from tests.refoundation.research_qualification import test_research_postgres as _research
from tests.refoundation.selection import (
    test_candidate_vertical_slice_postgres as _candidate,
)


@pytest.fixture
def wp13_context_stack(target_database_url, tmp_path, request):
    return _decision.candidate_vertical_stack.__wrapped__(
        target_database_url,
        tmp_path,
        request,
    )


def _binding(record) -> DecisionArtifactBinding:
    return DecisionArtifactBinding(
        artifact_id=record.artifact_id,
        content_sha256=record.content_sha256,
        size_bytes=record.size_bytes,
    )


def _registered_policy(stack, commands: ContextCommands):
    code = stack.artifacts.publish(
        b"def assess_context(exact_references): return exact_references\n",
        media_type="text/plain",
        context=_research._context("context-code", "REGISTER_CONTEXT_CODE"),
    )
    config = stack.artifacts.publish(
        b'{"source_role":"PRIMARY_DECISION_REFERENCE"}\n',
        media_type="application/json",
        context=_research._context("context-config", "REGISTER_CONTEXT_CONFIG"),
    )
    plan = replace(
        _policy(),
        code_artifact=_binding(code),
        config_artifact=_binding(config),
    )
    result = commands.register_policy(
        plan,
        _research._context("context-policy", "REGISTER_CONTEXT_POLICY"),
    )
    assert result.child_count == 4
    return plan


def test_context_postgres_closes_exact_primary_reference_roster_and_replays(
    wp13_context_stack,
) -> None:
    stack = wp13_context_stack
    runtime, _, decision = _decision._open_default_decision(
        stack,
        key_prefix="wp13-context",
    )
    commands = ContextCommands(
        PostgresContextInputPreparationProvider(stack.pool),
        PostgresContextUnitOfWorkProvider(stack.pool),
        PostgresContextQueryProvider(stack.pool),
    )
    policy = _registered_policy(stack, commands)
    context = _research._context("context-assess", "ASSESS_CONTEXT")
    claim = _candidate._claim(runtime, step_key="assess-context")

    first = commands.assess_context(
        decision.decision_run_id,
        policy.context_policy_id,
        context,
        runtime_claim=claim,
    )
    replay = commands.assess_context(
        decision.decision_run_id,
        policy.context_policy_id,
        context,
        runtime_claim=claim,
    )

    assert replay == first.as_replay()
    assert (first.child_count, first.source_count) == (4, 4)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.context_assessment
               WHERE assessment_group_id = %s),
              (SELECT count(*) FROM mra.context_metric
               WHERE assessment_group_id = %s),
              (SELECT count(*) FROM mra.context_metric_source AS source
               JOIN mra.decision_reference_observation AS reference
                 ON reference.decision_reference_observation_id =
                    source.decision_reference_observation_id
               JOIN mra.decision_run_target AS target
                 ON target.decision_run_target_id =
                    reference.decision_run_target_id
               WHERE source.context_metric_id IN (
                   SELECT context_metric_id FROM mra.context_metric
                   WHERE assessment_group_id = %s
               ) AND target.ordinal = 1)
            """,
            (first.aggregate_id, first.aggregate_id, first.aggregate_id),
        ).fetchone()
        assert counts == (4, 4, 4)
        with pytest.raises(psycopg.Error):
            connection.execute(
                "UPDATE mra.context_metric SET metric_state = 'NEGATIVE'"
            )


def test_context_policy_requires_exact_artifacts_and_partial_root_rolls_back(
    wp13_context_stack,
) -> None:
    stack = wp13_context_stack
    commands = ContextCommands(
        PostgresContextInputPreparationProvider(stack.pool),
        PostgresContextUnitOfWorkProvider(stack.pool),
        PostgresContextQueryProvider(stack.pool),
    )
    with pytest.raises(RuntimeNotFoundError):
        commands.register_policy(
            _policy(),
            _research._context(
                "context-policy-missing-artifact",
                "REGISTER_CONTEXT_POLICY",
            ),
        )
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.context_policy"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM mra.context_policy_metric"
        ).fetchone() == (0,)


def test_context_preparation_rejects_cross_run_identity(wp13_context_stack) -> None:
    stack = wp13_context_stack
    commands = ContextCommands(
        PostgresContextInputPreparationProvider(stack.pool),
        PostgresContextUnitOfWorkProvider(stack.pool),
        PostgresContextQueryProvider(stack.pool),
    )
    policy = _registered_policy(stack, commands)
    with pytest.raises(ContextAuthorityIntegrityError, match="DecisionRun is absent"):
        PostgresContextInputPreparationProvider(stack.pool).prepare(
            UUID("00000000-0000-4000-8000-000000009999"),
            policy.context_policy_id,
        )
