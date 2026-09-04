from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode,
    BacktestMetricSurface,
    EvaluationFormulaDefinition,
    EvaluationFormulaParameter,
    FormulaObservation,
    FormulaParameterType,
    FormulaResultState,
    FormulaSourceState,
    FrozenRankingMembership,
    evaluate_backtest_formula,
)


_METRIC_ID = UUID("f34fd322-dfc3-5f06-b676-f30bb2c06779")


def _parameter(
    ordinal: int,
    code: str,
    value: Decimal | int | bool | str,
) -> EvaluationFormulaParameter:
    kinds = {
        Decimal: FormulaParameterType.DECIMAL,
        int: FormulaParameterType.INTEGER,
        bool: FormulaParameterType.BOOLEAN,
        str: FormulaParameterType.TEXT,
    }
    kind = kinds[type(value)]
    return EvaluationFormulaParameter(
        formula_parameter_id=UUID(int=ordinal),
        ordinal=ordinal,
        parameter_code=code,
        value_type=kind,
        decimal_value=value if kind is FormulaParameterType.DECIMAL else None,
        integer_value=value if kind is FormulaParameterType.INTEGER else None,
        boolean_value=value if kind is FormulaParameterType.BOOLEAN else None,
        text_value=value if kind is FormulaParameterType.TEXT else None,
    )


def _formula(
    code: BacktestFormulaCode,
    *parameters: tuple[str, Decimal | int | bool | str],
) -> EvaluationFormulaDefinition:
    return EvaluationFormulaDefinition(
        evaluation_protocol_metric_id=_METRIC_ID,
        formula_code=code,
        formula_version=1,
        decimal_precision=28,
        rounding_mode="ROUND_HALF_EVEN",
        parameters=tuple(
            _parameter(ordinal, name, value)
            for ordinal, (name, value) in enumerate(parameters, start=1)
        ),
        surface=BacktestMetricSurface.ECONOMICS,
    )


def _observation(
    ordinal: int,
    value: Decimal | None,
    *,
    group: str = "s1",
    secondary: Decimal | None = None,
    state: FormulaSourceState = FormulaSourceState.AVAILABLE,
    membership: FrozenRankingMembership = FrozenRankingMembership.NONE,
    decision_time: datetime | None = None,
    outcome_known_at: datetime | None = None,
    buy_turnover: Decimal | None = None,
    sell_turnover: Decimal | None = None,
) -> FormulaObservation:
    return FormulaObservation(
        observation_id=UUID(int=ordinal),
        ordinal=ordinal,
        group_key=group,
        source_state=state,
        value=value,
        secondary_value=secondary,
        ranking_membership=membership,
        decision_time=decision_time,
        outcome_known_at=outcome_known_at,
        buy_turnover=buy_turnover,
        sell_turnover=sell_turnover,
    )


def test_formula_parameters_are_ordered_typed_scalars_and_hash_stable() -> None:
    formula = _formula(
        BacktestFormulaCode.SHARPE,
        ("annualization_sessions", 252),
        ("risk_free_per_session", Decimal("0")),
    )

    assert formula.parameter_count == 2
    assert len(str(formula.parameter_roster_sha256)) == 64
    assert len(str(formula.content_sha256)) == 64

    with pytest.raises(ValueError, match="exactly one typed scalar"):
        EvaluationFormulaParameter(
            formula_parameter_id=UUID(int=99),
            ordinal=1,
            parameter_code="bad",
            value_type=FormulaParameterType.DECIMAL,
            decimal_value=Decimal("1"),
            integer_value=1,
        )


def test_coverage_uses_complete_expected_roster_and_never_fabricates_zero() -> None:
    formula = _formula(
        BacktestFormulaCode.COVERAGE_RATE,
        ("expected_roster_size", 4),
    )
    result = evaluate_backtest_formula(
        formula,
        (
            _observation(1, Decimal("1")),
            _observation(2, Decimal("2")),
            _observation(3, None, state=FormulaSourceState.SOURCE_GAP),
            _observation(4, None, state=FormulaSourceState.UNAVAILABLE),
        ),
    )

    assert result.state is FormulaResultState.ESTIMABLE
    assert result.decimal_value == Decimal("0.5")

    empty = evaluate_backtest_formula(
        _formula(
            BacktestFormulaCode.COVERAGE_RATE,
            ("expected_roster_size", 0),
        ),
        (),
    )
    assert empty.state is FormulaResultState.NOT_ESTIMABLE
    assert empty.decimal_value is None
    assert empty.reason_code == "EMPTY_EXPECTED_ROSTER"


def test_rank_ic_uses_midranks_per_session_and_icir_uses_sample_std() -> None:
    rank_ic = evaluate_backtest_formula(
        _formula(BacktestFormulaCode.RANK_IC, ("minimum_pairs_per_group", 2)),
        (
            _observation(1, Decimal("1"), secondary=Decimal("1"), group="s1"),
            _observation(2, Decimal("2"), secondary=Decimal("2"), group="s1"),
            _observation(3, Decimal("2"), secondary=Decimal("3"), group="s1"),
            _observation(4, Decimal("4"), secondary=Decimal("4"), group="s1"),
        ),
    )
    assert rank_ic.decimal_value == Decimal("0.9486832980505137995996680633")

    icir = evaluate_backtest_formula(
        _formula(BacktestFormulaCode.ICIR, ("minimum_observations", 2)),
        (
            _observation(1, Decimal("0.1"), group="ic"),
            _observation(2, Decimal("0.3"), group="ic"),
        ),
    )
    assert icir.decimal_value == Decimal("1.414213562373095048801688724")


def test_top_k_membership_is_frozen_before_future_outcome_is_read() -> None:
    decision = datetime(2026, 1, 5, 6, 55, tzinfo=UTC)
    known = decision + timedelta(days=1)
    observations = (
        _observation(
            1,
            Decimal("-0.10"),
            membership=FrozenRankingMembership.TOP,
            decision_time=decision,
            outcome_known_at=known,
        ),
        _observation(
            2,
            Decimal("0.40"),
            membership=FrozenRankingMembership.BOTTOM,
            decision_time=decision,
            outcome_known_at=known,
        ),
    )

    top = evaluate_backtest_formula(
        _formula(BacktestFormulaCode.TOP_K_RETURN, ("top_k", 1)),
        observations,
    )
    spread = evaluate_backtest_formula(
        _formula(BacktestFormulaCode.TOP_BOTTOM_SPREAD, ("top_k", 1)),
        observations,
    )

    assert top.decimal_value == Decimal("-0.10")
    assert spread.decimal_value == Decimal("-0.50")

    leaked = (
        _observation(
            1,
            Decimal("0.1"),
            membership=FrozenRankingMembership.TOP,
            decision_time=known,
            outcome_known_at=decision,
        ),
    )
    result = evaluate_backtest_formula(
        _formula(BacktestFormulaCode.TOP_K_RETURN, ("top_k", 1)), leaked
    )
    assert result.state is FormulaResultState.NOT_ESTIMABLE
    assert result.reason_code == "RANKING_NOT_FROZEN_BEFORE_OUTCOME"


def test_exposure_and_turnover_follow_frozen_cash_and_terminal_conventions() -> None:
    weights = (
        _observation(1, Decimal("0.6"), secondary=Decimal("0")),
        _observation(2, Decimal("-0.2"), secondary=Decimal("0")),
    )
    gross = evaluate_backtest_formula(
        _formula(BacktestFormulaCode.GROSS_EXPOSURE), weights
    )
    net = evaluate_backtest_formula(
        _formula(BacktestFormulaCode.NET_EXPOSURE), weights
    )
    turnover = evaluate_backtest_formula(
        _formula(
            BacktestFormulaCode.TURNOVER,
            ("initial_cash", True),
            ("final_liquidation", False),
            ("carry_forward", "LAST_TARGET_WEIGHT"),
            ("corporate_action_convention", "PRE_ADJUSTED_WEIGHTS"),
        ),
        weights,
    )

    assert gross.decimal_value == Decimal("0.8")
    assert net.decimal_value == Decimal("0.4")
    assert turnover.decimal_value == Decimal("0.4")


def test_assumed_cost_and_economic_formulae_are_exact_decimal() -> None:
    net = evaluate_backtest_formula(
        _formula(
            BacktestFormulaCode.NET_RETURN_ASSUMED_COST,
            ("commission_bps", Decimal("3")),
            ("slippage_bps", Decimal("2")),
            ("stamp_duty_bps", Decimal("5")),
        ),
        (
            _observation(
                1,
                Decimal("0.02"),
                buy_turnover=Decimal("0.4"),
                sell_turnover=Decimal("0.3"),
            ),
        ),
    )
    assert net.decimal_value == Decimal("0.0195")

    returns = (
        _observation(1, Decimal("0.01"), group="d1"),
        _observation(2, Decimal("-0.02"), group="d2"),
        _observation(3, Decimal("0.03"), group="d3"),
    )
    cumulative = evaluate_backtest_formula(
        _formula(BacktestFormulaCode.CUMULATIVE_RETURN), returns
    )
    drawdown = evaluate_backtest_formula(
        _formula(BacktestFormulaCode.MAX_DRAWDOWN), returns
    )
    sortino = evaluate_backtest_formula(
        _formula(
            BacktestFormulaCode.SORTINO,
            ("annualization_sessions", 252),
            ("mar_per_session", Decimal("0")),
        ),
        returns,
    )

    assert cumulative.decimal_value == Decimal("0.019494")
    assert drawdown.decimal_value == Decimal("0.02")
    assert sortino.decimal_value == Decimal("9.165151389911680013176094386")


def test_zero_variance_no_downside_and_non_positive_wealth_are_not_estimable() -> None:
    constant = (
        _observation(1, Decimal("0.01"), group="d1"),
        _observation(2, Decimal("0.01"), group="d2"),
    )
    sharpe = evaluate_backtest_formula(
        _formula(
            BacktestFormulaCode.SHARPE,
            ("annualization_sessions", 252),
            ("risk_free_per_session", Decimal("0")),
        ),
        constant,
    )
    sortino = evaluate_backtest_formula(
        _formula(
            BacktestFormulaCode.SORTINO,
            ("annualization_sessions", 252),
            ("mar_per_session", Decimal("0")),
        ),
        constant,
    )
    annualized = evaluate_backtest_formula(
        _formula(
            BacktestFormulaCode.ANNUALIZED_RETURN,
            ("annualization_sessions", 252),
        ),
        (_observation(1, Decimal("-1")),),
    )

    assert (sharpe.state, sharpe.reason_code) == (
        FormulaResultState.NOT_ESTIMABLE,
        "ZERO_VARIANCE",
    )
    assert (sortino.state, sortino.reason_code) == (
        FormulaResultState.NOT_ESTIMABLE,
        "NO_DOWNSIDE_DEVIATION",
    )
    assert (annualized.state, annualized.reason_code) == (
        FormulaResultState.NOT_ESTIMABLE,
        "NON_POSITIVE_WEALTH",
    )
