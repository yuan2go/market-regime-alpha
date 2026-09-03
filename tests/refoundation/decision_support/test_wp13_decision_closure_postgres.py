from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import UUID

import psycopg
import pytest

from market_regime_alpha.decision_support.application import (
    InferenceCommands,
    OpportunityCommands,
    PortfolioCommands,
    RiskCommands,
)
from market_regime_alpha.decision_support.errors import (
    DecisionAuthorityIntegrityError,
    DecisionCommitOutcomeUnknownError,
)
from market_regime_alpha.decision_support.domain import (
    ThesisConditionKind,
    ThesisConditionOperator,
    ThesisConditionPlan,
    ThesisConditionSource,
    ThesisMissingAction,
    ThesisPlan,
)
from market_regime_alpha.infrastructure.postgres.inference_uow import PostgresInferenceUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.opportunity_uow import PostgresOpportunityUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.portfolio_uow import PostgresPortfolioUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.queries.decision_inference_inputs import (
    PostgresInferenceInputPreparationProvider,
    PostgresInferenceQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_opportunity_inputs import (
    PostgresOpportunityInputPreparationProvider,
    PostgresOpportunityQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_portfolio_inputs import (
    PostgresPortfolioInputPreparationProvider,
    PostgresPortfolioQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_risk_inputs import (
    PostgresRiskInputPreparationProvider,
    PostgresRiskQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_verification import PostgresDecisionRunVerificationProvider
from market_regime_alpha.infrastructure.postgres.risk_uow import PostgresRiskUnitOfWorkProvider
from market_regime_alpha.runtime.errors import StaleFenceError
from tests.refoundation.decision_support.test_decision_domain import _uuid
from tests.refoundation.decision_support.test_wp13_decision_closure_domain import _portfolio_policy, _risk_policy
from tests.refoundation.decision_support import test_wp13_strategy_inference_postgres as _inference
from tests.refoundation.decision_support.test_wp13_strategy_inference_postgres import (
    _binding,
    _context_policy,
    _open_decision,
    _registered_strategy,
)
from tests.refoundation.research_qualification import test_research_postgres as _research
from tests.refoundation.selection import test_candidate_vertical_slice_postgres as _candidate


def _published_policy_artifacts(stack, plan, prefix):
    code = stack.artifacts.publish(
        f"def {prefix}(inputs): return inputs\n".encode(),
        media_type="text/plain",
        context=_research._context(f"{prefix}-code", "PUBLISH_ARTIFACT"),
    )
    config = stack.artifacts.publish(
        f'{{"policy":"{prefix}"}}\n'.encode(),
        media_type="application/json",
        context=_research._context(f"{prefix}-config", "PUBLISH_ARTIFACT"),
    )
    return replace(plan, code_artifact=_binding(code), config_artifact=_binding(config))


def _index_names(node: dict) -> set[str]:
    names = {str(node["Index Name"])} if "Index Name" in node else set()
    for child in node.get("Plans", ()):
        names.update(_index_names(child))
    return names


class _BarrierPreparation:
    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self._barrier = Barrier(2)

    def prepare(self, *args):
        prepared = self._delegate.prepare(*args)
        self._barrier.wait(timeout=10)
        return prepared


def _ready_for_decide(stack, *, key_prefix: str):
    runtime, decision = _open_decision(stack)
    context_policy = _context_policy(stack, decision.decision_run_id, runtime)
    strategy = _registered_strategy(stack, decision.decision_run_id, context_policy)
    InferenceCommands(
        PostgresInferenceInputPreparationProvider(stack.pool),
        PostgresInferenceUnitOfWorkProvider(stack.pool),
        PostgresInferenceQueryProvider(stack.pool),
    ).produce(
        decision.decision_run_id,
        strategy.strategy_version_id,
        _research._context(f"{key_prefix}-inference", "SIGNAL_AND_FORECAST"),
        runtime_claim=_candidate._claim(runtime, step_key="signal-and-forecast"),
    )
    return (
        runtime,
        decision,
        strategy,
        _candidate._claim(runtime, step_key="decide-and-risk"),
    )


def _create_opportunities(stack, decision, strategy, claim, *, key_prefix: str):
    commands = OpportunityCommands(
        PostgresOpportunityInputPreparationProvider(stack.pool),
        PostgresOpportunityUnitOfWorkProvider(stack.pool),
        PostgresOpportunityQueryProvider(stack.pool),
    )
    result = commands.create_opportunities(
        decision.decision_run_id,
        strategy.strategy_version_id,
        _research._context(f"{key_prefix}-opportunity", "CREATE_OPPORTUNITIES"),
        runtime_claim=claim,
    )
    return commands, result


def _create_portfolio(stack, opportunity_set_id, claim, *, key_prefix: str):
    policy = _published_policy_artifacts(stack, _portfolio_policy(), f"{key_prefix}_portfolio_policy")
    commands = PortfolioCommands(
        PostgresPortfolioInputPreparationProvider(stack.pool),
        PostgresPortfolioUnitOfWorkProvider(stack.pool),
        PostgresPortfolioQueryProvider(stack.pool),
    )
    commands.register_policy(
        policy,
        _research._context(f"{key_prefix}-portfolio-policy", "REGISTER_PORTFOLIO_POLICY"),
    )
    result = commands.propose(
        opportunity_set_id,
        policy.portfolio_policy_id,
        _research._context(f"{key_prefix}-portfolio", "PROPOSE_PORTFOLIO"),
        runtime_claim=claim,
    )
    return commands, policy, result


def _install_ordinal_failure(stack, *, table: str, ordinal: int, prefix: str) -> None:
    function_name = f"fail_{prefix}_ordinal"
    trigger_name = f"{prefix}_ordinal_failure"
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            f"""
            CREATE FUNCTION mra.{function_name}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.ordinal = {ordinal} THEN
                    RAISE EXCEPTION 'injected {table} failure'
                      USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        connection.execute(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON mra.{table}
            FOR EACH ROW EXECUTE FUNCTION mra.{function_name}()
            """
        )


@pytest.fixture
def wp13_closure_stack(target_database_url, tmp_path, request):
    return _inference.wp13_inference_stack.__wrapped__(target_database_url, tmp_path, request)


def test_postgres_closes_opportunity_thesis_portfolio_and_risk(wp13_closure_stack) -> None:
    stack = wp13_closure_stack
    runtime, decision = _open_decision(stack)
    context_policy = _context_policy(stack, decision.decision_run_id, runtime)
    strategy = _registered_strategy(stack, decision.decision_run_id, context_policy)
    InferenceCommands(
        PostgresInferenceInputPreparationProvider(stack.pool),
        PostgresInferenceUnitOfWorkProvider(stack.pool),
        PostgresInferenceQueryProvider(stack.pool),
    ).produce(
        decision.decision_run_id,
        strategy.strategy_version_id,
        _research._context("wp13-closure-inference", "SIGNAL_AND_FORECAST"),
        runtime_claim=_candidate._claim(runtime, step_key="signal-and-forecast"),
    )
    claim = _candidate._claim(runtime, step_key="decide-and-risk")
    opportunities = OpportunityCommands(
        _BarrierPreparation(PostgresOpportunityInputPreparationProvider(stack.pool)),
        PostgresOpportunityUnitOfWorkProvider(stack.pool),
        PostgresOpportunityQueryProvider(stack.pool),
    )
    opportunity_context = _research._context("wp13-closure-opportunity", "CREATE_OPPORTUNITIES")
    with ThreadPoolExecutor(max_workers=2) as executor:
        opportunity_results = tuple(
            executor.map(
                lambda _: opportunities.create_opportunities(
                    decision.decision_run_id,
                    strategy.strategy_version_id,
                    opportunity_context,
                    runtime_claim=claim,
                ),
                range(2),
            )
        )
    assert {item.aggregate_id for item in opportunity_results} == {opportunity_results[0].aggregate_id}
    assert sum(item.replayed for item in opportunity_results) == 1
    opportunity = opportunity_results[0]
    with stack.pool.connection(read_only=True) as connection:
        exact = connection.execute(
            "SELECT opportunity_id, content_sha256 FROM mra.opportunity WHERE opportunity_set_id = %s ORDER BY ordinal LIMIT 1",
            (opportunity.aggregate_id,),
        ).fetchone()
    assert exact is not None
    thesis_code = stack.artifacts.publish(
        b"thesis-v1\n", media_type="text/plain", context=_research._context("wp13-thesis-code", "PUBLISH_ARTIFACT")
    )
    thesis_config = stack.artifacts.publish(
        b'{"thesis":1}\n', media_type="application/json", context=_research._context("wp13-thesis-config", "PUBLISH_ARTIFACT")
    )
    thesis_id = _uuid(9810)
    thesis = ThesisPlan(
        thesis_id=thesis_id,
        opportunity_id=UUID(str(exact[0])),
        opportunity_content_sha256=str(exact[1]),
        revision=1,
        supersedes_thesis_id=None,
        claim="The exact setup is falsified by a negative regime.",
        conditions=(
            ThesisConditionPlan(
                thesis_condition_id=_uuid(9811),
                thesis_id=thesis_id,
                ordinal=1,
                condition_code="negative_regime",
                kind=ThesisConditionKind.INVALIDATE,
                source=ThesisConditionSource.CONTEXT,
                operator=ThesisConditionOperator.EQUALS,
                decimal_threshold=None,
                text_threshold="NEGATIVE",
                value_unit="CONTEXT_STATE",
                missing_action=ThesisMissingAction.INVALIDATE,
                invalidates=True,
            ),
        ),
        code_artifact=_binding(thesis_code),
        config_artifact=_binding(thesis_config),
        provenance_sha256="a" * 64,
    )
    opportunities.create_thesis(thesis, _research._context("wp13-closure-thesis", "CREATE_THESIS"))

    portfolio_policy = _published_policy_artifacts(stack, _portfolio_policy(), "portfolio_policy")
    portfolios = PortfolioCommands(
        _BarrierPreparation(PostgresPortfolioInputPreparationProvider(stack.pool)),
        PostgresPortfolioUnitOfWorkProvider(stack.pool),
        PostgresPortfolioQueryProvider(stack.pool),
    )
    portfolios.register_policy(portfolio_policy, _research._context("wp13-portfolio-policy", "REGISTER_PORTFOLIO_POLICY"))
    portfolio_context = _research._context("wp13-portfolio-propose", "PROPOSE_PORTFOLIO")
    with ThreadPoolExecutor(max_workers=2) as executor:
        proposal_results = tuple(
            executor.map(
                lambda _: portfolios.propose(
                    opportunity.aggregate_id,
                    portfolio_policy.portfolio_policy_id,
                    portfolio_context,
                    runtime_claim=claim,
                ),
                range(2),
            )
        )
    assert {item.aggregate_id for item in proposal_results} == {proposal_results[0].aggregate_id}
    assert sum(item.replayed for item in proposal_results) == 1
    proposal = proposal_results[0]
    risk_policy = _published_policy_artifacts(stack, _risk_policy(), "risk_policy")
    risks = RiskCommands(
        _BarrierPreparation(PostgresRiskInputPreparationProvider(stack.pool)),
        PostgresRiskUnitOfWorkProvider(stack.pool),
        PostgresRiskQueryProvider(stack.pool),
    )
    risks.register_policy(risk_policy, _research._context("wp13-risk-policy", "REGISTER_RISK_POLICY"))
    risk_context = _research._context("wp13-risk-assess", "ASSESS_RISK")
    with ThreadPoolExecutor(max_workers=2) as executor:
        risk_results = tuple(
            executor.map(
                lambda _: risks.assess(
                    proposal.aggregate_id,
                    risk_policy.risk_policy_id,
                    risk_context,
                    runtime_claim=claim,
                ),
                range(2),
            )
        )
    assert {item.aggregate_id for item in risk_results} == {risk_results[0].aggregate_id}
    assert sum(item.replayed for item in risk_results) == 1
    assessed = risk_results[0]
    assert assessed.status == "REJECTED"
    verification = PostgresDecisionRunVerificationProvider(stack.pool).verify(decision.decision_run_id)
    assert verification.matched is True
    assert verification.mismatch_count == 0
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """SELECT
                (SELECT count(*) FROM mra.opportunity WHERE opportunity_set_id = %s),
                (SELECT count(*) FROM mra.opportunity_context WHERE opportunity_set_id = %s),
                (SELECT count(*) FROM mra.thesis WHERE opportunity_id = %s),
                (SELECT count(*) FROM mra.portfolio_line WHERE portfolio_proposal_id = %s),
                (SELECT count(*) FROM mra.risk_reason WHERE risk_decision_id = %s)
            """,
            (opportunity.aggregate_id, opportunity.aggregate_id, exact[0], proposal.aggregate_id, assessed.aggregate_id),
        ).fetchone() == (1, 2, 1, 1, 2)
        assert connection.execute(
            "SELECT state FROM mra.runtime_step WHERE run_id = %s AND step_key = 'decide-and-risk'",
            (claim.run_id,),
        ).fetchone() == ("SUCCEEDED",)

        connection.execute(
            """
            ANALYZE mra.context_assessment, mra.signal_context_binding,
                    mra.forecast_estimate, mra.opportunity_context,
                    mra.portfolio_line, mra.risk_reason
            """
        )
        connection.execute("SET LOCAL enable_seqscan = off")
        plans = (
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT assessment_group_id
                FROM mra.context_assessment
                WHERE decision_run_id = %s
                """,
                (decision.decision_run_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT signal_context_binding_id
                FROM mra.signal_context_binding
                WHERE signal_id = (
                    SELECT signal_id FROM mra.opportunity
                    WHERE opportunity_set_id = %s ORDER BY ordinal LIMIT 1
                )
                """,
                (opportunity.aggregate_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT forecast_estimate_id
                FROM mra.forecast_estimate
                WHERE forecast_id = (
                    SELECT forecast_id FROM mra.opportunity
                    WHERE opportunity_set_id = %s ORDER BY ordinal LIMIT 1
                )
                """,
                (opportunity.aggregate_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT opportunity_context_id
                FROM mra.opportunity_context
                WHERE opportunity_id = %s
                ORDER BY ordinal
                """,
                (exact[0],),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT portfolio_line_id
                FROM mra.portfolio_line
                WHERE portfolio_proposal_id = %s
                ORDER BY ordinal
                """,
                (proposal.aggregate_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT risk_reason_id
                FROM mra.risk_reason
                WHERE risk_decision_id = %s
                ORDER BY ordinal
                """,
                (assessed.aggregate_id,),
            ).fetchone()[0][0]["Plan"],
        )
    plan_indexes = tuple(_index_names(plan) for plan in plans)
    assert plan_indexes[0] & {
        "context_assessment_run_fk_idx",
        "context_assessment_identity_uk",
        "context_assessment_request_uk",
        "context_assessment_signal_authority_uk",
    }
    assert plan_indexes[1] & {
        "signal_context_binding_signal_fk_idx",
        "signal_context_binding_ordinal_uk",
        "signal_context_binding_requirement_uk",
        "signal_context_binding_opportunity_authority_uk",
    }
    assert plan_indexes[2] & {
        "forecast_estimate_forecast_fk_idx",
        "forecast_estimate_model_output_uk",
    }
    assert "opportunity_context_ordinal_uk" in plan_indexes[3]
    assert "portfolio_line_ordinal_uk" in plan_indexes[4]
    assert "risk_reason_ordinal_uk" in plan_indexes[5]


def test_unknown_commit_requires_exact_authority_probe_before_replay() -> None:
    expected = object()

    def unknown_commit():
        raise DecisionCommitOutcomeUnknownError("acknowledgement lost")

    for retry in (
        OpportunityCommands._retry,
        PortfolioCommands._retry,
        RiskCommands._retry,
    ):
        assert retry(unknown_commit, lambda: expected) is expected


def test_stale_fence_writes_no_opportunity_or_failure_authority(wp13_closure_stack) -> None:
    stack = wp13_closure_stack
    runtime, decision, strategy, claim = _ready_for_decide(stack, key_prefix="wp13-stale")
    stale_claim = replace(claim, fence_token=claim.fence_token + 1)
    commands = OpportunityCommands(
        PostgresOpportunityInputPreparationProvider(stack.pool),
        PostgresOpportunityUnitOfWorkProvider(stack.pool),
        PostgresOpportunityQueryProvider(stack.pool),
    )

    with pytest.raises(StaleFenceError):
        commands.create_opportunities(
            decision.decision_run_id,
            strategy.strategy_version_id,
            _research._context("wp13-stale-opportunity", "CREATE_OPPORTUNITIES"),
            runtime_claim=stale_claim,
        )

    assert runtime.inspect_run(claim.run_id).steps[-1].state == "RUNNING"
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.opportunity_set),
              (SELECT count(*) FROM mra.opportunity),
              (SELECT count(*) FROM mra.opportunity_context),
              (SELECT count(*) FROM mra.command_receipt
                 WHERE command_kind LIKE 'CREATE_OPPORTUNITIES%'),
              (SELECT count(*) FROM mra.audit_event
                 WHERE action LIKE 'OPPORTUNITIES_%')
            """
        ).fetchone() == (0, 0, 0, 0, 0)


def test_changed_opportunity_requests_race_to_one_truth(wp13_closure_stack) -> None:
    stack = wp13_closure_stack
    _, decision, strategy, claim = _ready_for_decide(stack, key_prefix="wp13-changed-race")
    commands = OpportunityCommands(
        _BarrierPreparation(PostgresOpportunityInputPreparationProvider(stack.pool)),
        PostgresOpportunityUnitOfWorkProvider(stack.pool),
        PostgresOpportunityQueryProvider(stack.pool),
    )
    contexts = (
        _research._context("wp13-changed-race-a", "CREATE_OPPORTUNITIES"),
        _research._context("wp13-changed-race-b", "CREATE_OPPORTUNITIES"),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(
            executor.submit(
                commands.create_opportunities,
                decision.decision_run_id,
                strategy.strategy_version_id,
                context,
                runtime_claim=claim,
            )
            for context in contexts
        )
        outcomes: list[object] = []
        errors: list[BaseException] = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except BaseException as exc:
                errors.append(exc)

    assert len(outcomes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], DecisionAuthorityIntegrityError)
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.opportunity_set),
              (SELECT count(*) FROM mra.opportunity),
              (SELECT count(*) FROM mra.opportunity_context)
            """
        ).fetchone() == (1, 1, 2)


def test_mid_opportunity_failure_leaves_no_partial_roster(wp13_closure_stack) -> None:
    stack = wp13_closure_stack
    runtime, decision, strategy, claim = _ready_for_decide(stack, key_prefix="wp13-mid-opportunity")
    _install_ordinal_failure(stack, table="opportunity_context", ordinal=2, prefix="wp13_opportunity_context")
    commands = OpportunityCommands(
        PostgresOpportunityInputPreparationProvider(stack.pool),
        PostgresOpportunityUnitOfWorkProvider(stack.pool),
        PostgresOpportunityQueryProvider(stack.pool),
    )

    with pytest.raises(DecisionAuthorityIntegrityError):
        commands.create_opportunities(
            decision.decision_run_id,
            strategy.strategy_version_id,
            _research._context("wp13-mid-opportunity-create", "CREATE_OPPORTUNITIES"),
            runtime_claim=claim,
        )

    assert runtime.inspect_run(claim.run_id).run_state == "FAILED"
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.opportunity_set),
              (SELECT count(*) FROM mra.opportunity),
              (SELECT count(*) FROM mra.opportunity_context),
              (SELECT count(*) FROM mra.command_receipt
                 WHERE command_kind = 'CREATE_OPPORTUNITIES' AND status = 'FAILED'),
              (SELECT count(*) FROM mra.audit_event
                 WHERE action = 'CREATE_OPPORTUNITIES_FAILED')
            """
        ).fetchone() == (0, 0, 0, 1, 1)


def test_mid_portfolio_failure_leaves_no_partial_roster(wp13_closure_stack) -> None:
    stack = wp13_closure_stack
    runtime, decision, strategy, claim = _ready_for_decide(stack, key_prefix="wp13-mid-portfolio")
    _, opportunity = _create_opportunities(
        stack,
        decision,
        strategy,
        claim,
        key_prefix="wp13-mid-portfolio",
    )
    policy = _published_policy_artifacts(stack, _portfolio_policy(), "wp13_mid_portfolio_policy")
    commands = PortfolioCommands(
        PostgresPortfolioInputPreparationProvider(stack.pool),
        PostgresPortfolioUnitOfWorkProvider(stack.pool),
        PostgresPortfolioQueryProvider(stack.pool),
    )
    commands.register_policy(
        policy,
        _research._context("wp13-mid-portfolio-policy", "REGISTER_PORTFOLIO_POLICY"),
    )
    _install_ordinal_failure(stack, table="portfolio_line", ordinal=1, prefix="wp13_portfolio_line")

    with pytest.raises(DecisionAuthorityIntegrityError):
        commands.propose(
            opportunity.aggregate_id,
            policy.portfolio_policy_id,
            _research._context("wp13-mid-portfolio-propose", "PROPOSE_PORTFOLIO"),
            runtime_claim=claim,
        )

    assert runtime.inspect_run(claim.run_id).run_state == "FAILED"
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.portfolio_proposal),
              (SELECT count(*) FROM mra.portfolio_line),
              (SELECT count(*) FROM mra.command_receipt
                 WHERE command_kind = 'PROPOSE_PORTFOLIO' AND status = 'FAILED'),
              (SELECT count(*) FROM mra.audit_event
                 WHERE action = 'PROPOSE_PORTFOLIO_FAILED')
            """
        ).fetchone() == (0, 0, 1, 1)


def test_mid_risk_failure_leaves_no_partial_cartesian_roster(wp13_closure_stack) -> None:
    stack = wp13_closure_stack
    runtime, decision, strategy, claim = _ready_for_decide(stack, key_prefix="wp13-mid-risk")
    _, opportunity = _create_opportunities(
        stack,
        decision,
        strategy,
        claim,
        key_prefix="wp13-mid-risk",
    )
    _, _, portfolio = _create_portfolio(
        stack,
        opportunity.aggregate_id,
        claim,
        key_prefix="wp13-mid-risk",
    )
    policy = _published_policy_artifacts(stack, _risk_policy(), "wp13_mid_risk_policy")
    commands = RiskCommands(
        PostgresRiskInputPreparationProvider(stack.pool),
        PostgresRiskUnitOfWorkProvider(stack.pool),
        PostgresRiskQueryProvider(stack.pool),
    )
    commands.register_policy(
        policy,
        _research._context("wp13-mid-risk-policy", "REGISTER_RISK_POLICY"),
    )
    _install_ordinal_failure(stack, table="risk_reason", ordinal=2, prefix="wp13_risk_reason")

    with pytest.raises(DecisionAuthorityIntegrityError):
        commands.assess(
            portfolio.aggregate_id,
            policy.risk_policy_id,
            _research._context("wp13-mid-risk-assess", "ASSESS_RISK"),
            runtime_claim=claim,
        )

    assert runtime.inspect_run(claim.run_id).run_state == "FAILED"
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.risk_decision),
              (SELECT count(*) FROM mra.risk_reason),
              (SELECT count(*) FROM mra.command_receipt
                 WHERE command_kind = 'ASSESS_RISK' AND status = 'FAILED'),
              (SELECT count(*) FROM mra.audit_event
                 WHERE action = 'ASSESS_RISK_FAILED')
            """
        ).fetchone() == (0, 0, 1, 1)
