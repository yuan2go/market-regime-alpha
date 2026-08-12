from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from market_regime_alpha.application.strategy_shadow.performance import (
    build_portfolio_performance_report,
)
from market_regime_alpha.application.strategy_shadow.postgres_performance import (
    PostgresPortfolioPerformanceRepository,
)
from market_regime_alpha.application.strategy_shadow.performance_operator import (
    PortfolioPerformanceOperator,
)
from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from tests.application.strategy_shadow.test_performance import (
    _performance_policy,
    _states,
)
from tests.application.strategy_shadow.test_portfolio_shadow import NOW


def _persisted_inputs(postgres_factory):
    portfolio_policy, portfolio, states = _states()
    portfolio_repository = PostgresShadowPortfolioRepository(postgres_factory)
    portfolio_repository.save_portfolio(
        policy=portfolio_policy,
        portfolio=portfolio,
    )
    previous = None
    for state in states:
        portfolio_repository.append_state(
            state,
            expected_previous_state_id=previous,
        )
        previous = state.state_id
    performance_policy = _performance_policy()
    report = build_portfolio_performance_report(
        portfolio=portfolio,
        states=states,
        policy=performance_policy,
        generated_at=NOW + timedelta(days=3),
    )
    return performance_policy, report


def test_performance_report_is_idempotent_and_reloadable(postgres_factory) -> None:
    policy, report = _persisted_inputs(postgres_factory)
    repository = PostgresPortfolioPerformanceRepository(postgres_factory)

    assert repository.publish(policy=policy, report=report) == report
    assert repository.publish(policy=policy, report=report) == report
    assert repository.get_policy(policy.policy_id) == policy
    assert repository.get(report.report_id) == report
    assert repository.find(
        portfolio_id=report.portfolio_reference.artifact_id,
        start_date=report.start_date,
        end_date=report.end_date,
        policy_id=policy.policy_id,
    ) == report


def test_performance_report_and_projections_are_append_only(postgres_factory) -> None:
    policy, report = _persisted_inputs(postgres_factory)
    repository = PostgresPortfolioPerformanceRepository(postgres_factory)
    repository.publish(policy=policy, report=report)

    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException,
        match="shadow_performance_report is append-only",
    ):
        connection.execute(
            "UPDATE shadow_performance_report SET payload_json = payload_json "
            "WHERE report_id = %s",
            (str(report.report_id),),
        )


def test_performance_operator_builds_reports_and_replays_from_portfolio_owner(
    postgres_factory,
) -> None:
    policy, expected = _persisted_inputs(postgres_factory)
    operator = PortfolioPerformanceOperator(postgres_factory)

    report = operator.build(
        portfolio_id=expected.portfolio_reference.artifact_id,
        policy=policy,
        generated_at=expected.generated_at,
    )

    assert report == expected
    assert operator.report(report.report_id) == expected
    assert operator.replay(report.report_id) == expected
