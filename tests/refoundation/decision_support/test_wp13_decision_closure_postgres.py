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


class _BarrierPreparation:
    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self._barrier = Barrier(2)

    def prepare(self, *args):
        prepared = self._delegate.prepare(*args)
        self._barrier.wait(timeout=10)
        return prepared


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
