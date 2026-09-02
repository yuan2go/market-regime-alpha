from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import psycopg
import pytest

from market_regime_alpha.decision_support.application import (
    ContextCommands,
    InferenceCommands,
    StrategyCommands,
)
from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    OpenDecisionRunRequest,
    RequestedDecisionTarget,
    ResearchPurpose,
)
from market_regime_alpha.infrastructure.postgres.context_uow import (
    PostgresContextUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.inference_uow import (
    PostgresInferenceUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_context_inputs import (
    PostgresContextInputPreparationProvider,
    PostgresContextQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_inference_inputs import (
    PostgresInferenceInputPreparationProvider,
    PostgresInferenceQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_strategy import (
    PostgresStrategyQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.strategy_uow import (
    PostgresStrategyUnitOfWorkProvider,
)
from tests.refoundation.decision_support import test_decision_postgres as _decision
from tests.refoundation.decision_support.test_wp13_context_domain import _policy
from tests.refoundation.decision_support.test_wp13_strategy_inference_domain import (
    _strategy,
)
from tests.refoundation.research_qualification import test_research_postgres as _research
from tests.refoundation.selection import (
    test_candidate_vertical_slice_postgres as _candidate,
)


@pytest.fixture
def wp13_inference_stack(target_database_url, tmp_path, request):
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


def _open_decision(stack):
    ready = _candidate._ready_candidate(stack, key_prefix="wp13-inference")
    target = _decision._register_target(stack)
    steps = (
        _candidate._step(
            key="build-candidate-set",
            kind="BUILD_CANDIDATE_SET",
            ordinal=1,
            request_character="1",
        ),
        _candidate._step(
            key="open-decision-run",
            kind="OPEN_DECISION_RUN",
            ordinal=2,
            request_character="2",
        ),
        _candidate._step(
            key="assess-context",
            kind="ASSESS_CONTEXT",
            ordinal=3,
            request_character="3",
        ),
        _candidate._step(
            key="signal-and-forecast",
            kind="SIGNAL_AND_FORECAST",
            ordinal=4,
            request_character="4",
        ),
    )
    runtime, _ = _candidate._schedule_run(
        stack,
        steps=steps,
        canonical_decision_time=stack.decision_time,
    )
    built = ready.application.build_candidate_set(
        ready.policy.candidate_policy_id,
        ready.dataset.dataset_id,
        _research._context("wp13-inference-build", "BUILD_CANDIDATE_SET"),
        runtime_claim=_candidate._claim(runtime, step_key="build-candidate-set"),
    )
    result = _decision._application(stack).open_decision_run(
        OpenDecisionRunRequest(
            candidate_set_id=UUID(built.aggregate_id),
            targets=(
                RequestedDecisionTarget(
                    target_definition_id=target.target_definition_id,
                    reference_provider_product_id=stack.product.provider_product_id,
                ),
            ),
            research_purpose=ResearchPurpose.DISCOVERY,
            research_qualifications=(),
        ),
        _research._context("wp13-inference-open", "OPEN_DECISION_RUN"),
        runtime_claim=_candidate._claim(runtime, step_key="open-decision-run"),
    )
    return runtime, result


def _context_policy(stack, decision_run_id, runtime):
    commands = ContextCommands(
        PostgresContextInputPreparationProvider(stack.pool),
        PostgresContextUnitOfWorkProvider(stack.pool),
        PostgresContextQueryProvider(stack.pool),
    )
    code = stack.artifacts.publish(
        b"def assess_context(inputs): return inputs\n",
        media_type="text/plain",
        context=_research._context("wp13-inference-context-code", "PUBLISH_ARTIFACT"),
    )
    config = stack.artifacts.publish(
        b'{"policy":"wp13-inference-context"}\n',
        media_type="application/json",
        context=_research._context("wp13-inference-context-config", "PUBLISH_ARTIFACT"),
    )
    plan = replace(
        _policy(),
        code_artifact=_binding(code),
        config_artifact=_binding(config),
    )
    commands.register_policy(
        plan,
        _research._context("wp13-inference-context-policy", "REGISTER_CONTEXT_POLICY"),
    )
    commands.assess_context(
        decision_run_id,
        plan.context_policy_id,
        _research._context("wp13-inference-context", "ASSESS_CONTEXT"),
        runtime_claim=_candidate._claim(runtime, step_key="assess-context"),
    )
    return plan


def _registered_strategy(stack, decision_run_id, policy):
    with stack.pool.connection(read_only=True) as connection:
        target = connection.execute(
            """
            SELECT target.target_definition_id,
                   target.target_definition_sha256,
                   target.target_checkpoint_id,
                   target.target_checkpoint_sha256,
                   metric.target_metric_definition_id,
                   metric.content_sha256
            FROM mra.decision_run_target AS target
            JOIN mra.target_metric_definition AS metric
              ON metric.target_definition_id = target.target_definition_id
            WHERE target.decision_run_id = %s
            ORDER BY metric.ordinal LIMIT 1
            """,
            (decision_run_id,),
        ).fetchone()
    assert target is not None
    code = stack.artifacts.publish(
        b"def forecast(score): return score\n",
        media_type="text/plain",
        context=_research._context("wp13-strategy-code", "PUBLISH_ARTIFACT"),
    )
    config = stack.artifacts.publish(
        b'{"baseline":"transparent"}\n',
        media_type="application/json",
        context=_research._context("wp13-strategy-config", "PUBLISH_ARTIFACT"),
    )
    plan = _strategy()
    plan = replace(
        plan,
        context_requirements=tuple(
            replace(
                item,
                context_policy_id=policy.context_policy_id,
                context_policy_content_sha256=policy.content_sha256,
            )
            for item in plan.context_requirements
        ),
        forecast_rules=(
            replace(
                plan.forecast_rules[0],
                target_definition_id=UUID(str(target[0])),
                target_definition_sha256=str(target[1]),
                target_checkpoint_id=UUID(str(target[2])),
                target_checkpoint_sha256=str(target[3]),
                target_metric_definition_id=UUID(str(target[4])),
                target_metric_definition_sha256=str(target[5]),
            ),
        ),
        code_artifact=_binding(code),
        config_artifact=_binding(config),
    )
    commands = StrategyCommands(
        PostgresStrategyUnitOfWorkProvider(stack.pool),
        PostgresStrategyQueryProvider(stack.pool),
    )
    result = commands.register(
        plan,
        _research._context("wp13-strategy-register", "REGISTER_STRATEGY_VERSION"),
    )
    assert result.context_requirement_count == 2
    return plan


def test_postgres_signal_forecast_closes_exact_rosters_and_replays(
    wp13_inference_stack,
) -> None:
    stack = wp13_inference_stack
    runtime, decision = _open_decision(stack)
    policy = _context_policy(stack, decision.decision_run_id, runtime)
    strategy = _registered_strategy(stack, decision.decision_run_id, policy)
    commands = InferenceCommands(
        PostgresInferenceInputPreparationProvider(stack.pool),
        PostgresInferenceUnitOfWorkProvider(stack.pool),
        PostgresInferenceQueryProvider(stack.pool),
    )
    context = _research._context("wp13-inference-produce", "SIGNAL_AND_FORECAST")
    claim = _candidate._claim(runtime, step_key="signal-and-forecast")

    first = commands.produce(
        decision.decision_run_id,
        strategy.strategy_version_id,
        context,
        runtime_claim=claim,
    )
    replay = commands.produce(
        decision.decision_run_id,
        strategy.strategy_version_id,
        context,
        runtime_claim=claim,
    )

    assert replay == first.as_replay()
    assert (first.signal_count, first.forecast_count) == (1, 1)
    assert (first.context_binding_count, first.estimate_count) == (2, 1)
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.signal_run WHERE signal_group_id = %s),
              (SELECT count(*) FROM mra.signal WHERE signal_group_id = %s),
              (SELECT count(*) FROM mra.signal_context_binding
               WHERE signal_group_id = %s),
              (SELECT count(*) FROM mra.forecast_run WHERE forecast_group_id = %s),
              (SELECT count(*) FROM mra.forecast WHERE forecast_group_id = %s),
              (SELECT count(*) FROM mra.forecast_estimate
               WHERE forecast_group_id = %s)
            """,
            (
                first.signal_group_id,
                first.signal_group_id,
                first.signal_group_id,
                first.forecast_group_id,
                first.forecast_group_id,
                first.forecast_group_id,
            ),
        ).fetchone() == (1, 1, 2, 1, 1, 1)
        assert connection.execute(
            "SELECT calibration_status FROM mra.forecast"
        ).fetchone() == ("UNCALIBRATED",)
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute("UPDATE mra.signal SET status = 'NO_SIGNAL'")
