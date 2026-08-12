from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from market_regime_alpha.application.strategy_shadow.performance import (
    EstimationStatus,
    PerformancePolicy,
    build_portfolio_performance_report,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    build_shadow_portfolio,
    run_shadow_portfolio_day,
)
from tests.application.strategy_shadow.test_portfolio_shadow import (
    NOW,
    _observation,
    _policy,
    _reference,
)


def _states():
    policy = _policy(top_k=1)
    portfolio = build_shadow_portfolio(
        policy=policy,
        research_reference=_reference("RESEARCH_PANEL_V2", "performance-panel"),
        candidate_reference=_reference("CANDIDATE_SET", "performance-candidates"),
        initial_cash=Decimal("100000"),
        created_at=NOW,
    )
    first = run_shadow_portfolio_day(
        portfolio=portfolio,
        policy=policy,
        trading_date=date(2026, 8, 10),
        observations=(_observation("000001.SZ", "0.9", "10"),),
        previous=None,
        recorded_at=NOW,
    )
    second_at = NOW + timedelta(days=1)
    second = run_shadow_portfolio_day(
        portfolio=portfolio,
        policy=policy,
        trading_date=date(2026, 8, 11),
        observations=(
            _observation("000001.SZ", "0.9", "11", observed_at=second_at),
        ),
        previous=first,
        recorded_at=second_at,
    )
    third_at = NOW + timedelta(days=2)
    third = run_shadow_portfolio_day(
        portfolio=portfolio,
        policy=policy,
        trading_date=date(2026, 8, 12),
        observations=(
            replace(
                _observation(
                    "000001.SZ", "0.1", "10.5", observed_at=third_at
                ),
                score=None,
            ),
        ),
        previous=second,
        recorded_at=third_at,
    )
    return policy, portfolio, (first, second, third)


def _performance_policy() -> PerformancePolicy:
    return PerformancePolicy.create(
        policy_version="shadow-performance-v1",
        annual_sessions=252,
        annual_risk_free_rate=Decimal("0"),
        minimum_return_samples=2,
        reconciliation_tolerance=Decimal("0.000001"),
        benchmark_reference=None,
    )


def test_performance_report_computes_requested_metrics_without_hiding_losses() -> None:
    _portfolio_policy, portfolio, states = _states()

    report = build_portfolio_performance_report(
        portfolio=portfolio,
        states=states,
        policy=_performance_policy(),
        generated_at=NOW + timedelta(days=3),
    )

    assert report.metric("cumulative_return").value == (
        states[-1].nav / portfolio.initial_cash - Decimal("1")
    )
    assert report.metric("maximum_drawdown").value is not None
    assert report.metric("turnover").value == sum(
        (item.turnover for item in states), Decimal("0")
    )
    assert report.metric("cost_drag").value == sum(
        (item.total_cost for item in states), Decimal("0")
    ) / portfolio.initial_cash
    assert report.metric("mfe").status is EstimationStatus.NOT_ESTIMABLE
    assert report.metric("mae").status is EstimationStatus.NOT_ESTIMABLE
    assert report.metric("average_holding_period").unit == "SESSIONS"
    assert report.monthly_returns
    assert report.yearly_returns
    assert report.reconciliation_difference.copy_abs() <= Decimal("0.000001")
    assert report.negative_results_preserved is True


def test_performance_report_marks_undefined_ratios_not_est_array_values() -> None:
    _portfolio_policy, portfolio, states = _states()

    report = build_portfolio_performance_report(
        portfolio=portfolio,
        states=states[:1],
        policy=_performance_policy(),
        generated_at=NOW + timedelta(days=1),
    )

    for name in ("annualized_return", "volatility", "sharpe", "sortino", "calmar"):
        metric = report.metric(name)
        assert metric.status is EstimationStatus.NOT_ESTIMABLE
        assert metric.value is None
        assert metric.reason_codes


def test_performance_identity_is_deterministic_and_symbol_attribution_reconciles() -> None:
    _portfolio_policy, portfolio, states = _states()
    policy = _performance_policy()
    generated_at = NOW + timedelta(days=3)

    first = build_portfolio_performance_report(
        portfolio=portfolio,
        states=states,
        policy=policy,
        generated_at=generated_at,
    )
    second = build_portfolio_performance_report(
        portfolio=portfolio,
        states=states,
        policy=policy,
        generated_at=generated_at,
    )

    assert first == second
    assert sum(
        (
            item.contribution
            for item in first.attribution
            if item.dimension == "SYMBOL" and item.contribution is not None
        ),
        Decimal("0"),
    ) == states[-1].nav - portfolio.initial_cash
    assert {
        item.dimension
        for item in first.attribution
        if item.status is EstimationStatus.NOT_ESTIMABLE
    }.issuperset({"REGIME", "THEME", "FACTOR", "SIGNAL", "CANDIDATE_RANK"})


def test_performance_is_invariant_to_input_order_and_rejects_time_travel() -> None:
    _portfolio_policy, portfolio, states = _states()
    generated_at = NOW + timedelta(days=3)

    ordered = build_portfolio_performance_report(
        portfolio=portfolio,
        states=states,
        policy=_performance_policy(),
        generated_at=generated_at,
    )
    shuffled = build_portfolio_performance_report(
        portfolio=portfolio,
        states=(states[2], states[0], states[1]),
        policy=_performance_policy(),
        generated_at=generated_at,
    )

    assert shuffled == ordered
    with pytest.raises(ValueError, match="generated_at predates"):
        build_portfolio_performance_report(
            portfolio=portfolio,
            states=states,
            policy=_performance_policy(),
            generated_at=states[-1].recorded_at - timedelta(seconds=1),
        )
