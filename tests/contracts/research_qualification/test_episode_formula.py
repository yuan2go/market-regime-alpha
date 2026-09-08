from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from uuid import UUID, uuid4

import pytest

from market_regime_alpha.outcome.domain.economic_prices import OutcomeEpisodePrices
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode as Code,
    BacktestMetricSurface,
    EvaluationFormulaDefinition,
    EvaluationFormulaParameter,
    FormulaParameterType,
)
from market_regime_alpha.research_qualification.domain.evaluation_computation import EvaluationMetricInputs, compute_evaluation
from market_regime_alpha.research_qualification.errors import EvaluationReconciliationError
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    EvaluationSourceKind,
    EvaluationSourceMeasure,
    EvaluationSliceKind,
)
from tests.contracts.research_qualification.test_evaluation_source_repository import _metric, _source


ENTRY, EXIT = UUID(int=800), UUID(int=801)


def formula(metric_id, code=Code.NET_RETURN_ASSUMED_COST, *, entry=ENTRY, exit=EXIT):
    values = {
        "economic_model": "INDEPENDENT_EPISODES",
        "execution_assumption": "ASSUMED_CHECKPOINT_CLOSE_FRACTIONAL",
        "price_basis": "RAW_UNADJUSTED",
        "initial_capital": D(1000),
        "buy_fee_bps": D(10),
        "sell_fee_bps": D(20),
        "minimum_fee": D(0),
        "slippage_bps": D(0),
        "final_liquidation": True,
        "carry_forward": "NONE",
        "entry_checkpoint_id": str(entry),
        "exit_checkpoint_id": str(exit),
    }
    parameters = []
    for ordinal, (key, value) in enumerate(values.items(), 1):
        if isinstance(value, D):
            parameter = EvaluationFormulaParameter(uuid4(), ordinal, key, FormulaParameterType.DECIMAL, decimal_value=value)
        elif isinstance(value, bool):
            parameter = EvaluationFormulaParameter(uuid4(), ordinal, key, FormulaParameterType.BOOLEAN, boolean_value=value)
        else:
            parameter = EvaluationFormulaParameter(uuid4(), ordinal, key, FormulaParameterType.TEXT, text_value=value)
        parameters.append(parameter)
    return EvaluationFormulaDefinition(metric_id, code, 2, 34, "ROUND_HALF_EVEN", tuple(parameters), BacktestMetricSurface.ECONOMICS)


def inputs(code=Code.NET_RETURN_ASSUMED_COST):
    metric = _metric(EvaluationSourceKind.PORTFOLIO_OUTCOME, EvaluationSourceMeasure.NET_PORTFOLIO_RETURN_ASSUMED_COST)
    metric = replace(
        metric,
        formula=formula(metric.evaluation_protocol_metric_id, code),
        slice_kind=EvaluationSliceKind.ALL_MEMBERS,
        backtest_arm_kind=None,
    )
    t, instrument, arm = datetime(2026, 1, 5, tzinfo=UTC), uuid4(), uuid4()
    rows = []
    for i, risk in enumerate(("REJECTED", "AUTHORIZED")):
        decision = t + timedelta(days=i)
        row = _source(decision_time=decision, risk_status=risk, instrument_id=instrument, arm_id=arm)
        prices = OutcomeEpisodePrices(
            row[2],
            "a" * 64,
            ENTRY,
            EXIT,
            uuid4(),
            uuid4(),
            "b" * 64,
            "c" * 64,
            decision + timedelta(hours=1),
            decision + timedelta(hours=2),
            D(10),
            D(11),
            decision + timedelta(days=1),
            decision + timedelta(days=2),
            "RAW_UNADJUSTED",
        )
        rows.append((*row, prices.knowledge_cutoff, D(10), D(20), False, False, prices))
    return EvaluationMetricInputs(metric, tuple(rows))


def test_evaluation_v2_rejected_then_approved_hand_oracle_and_result_identity():
    batch = inputs()
    (computed,) = compute_evaluation((batch,))
    assert [item.net_return for item in computed.resolved] == [D(0), D(".03872")]
    assert [item.turnover for item in computed.resolved] == [D(0), D(".84")]
    assert computed.result.decimal_value == D(".01936")  # equal independent episode capital
    assert computed.reason_code == "INDEPENDENT_EPISODES_V2"
    assert computed == compute_evaluation((batch,))[0]
    assert len(computed.resolved[0].economic_path_sha256) == 64


@pytest.mark.parametrize("code", [Code.CUMULATIVE_RETURN, Code.SHARPE, Code.MAX_DRAWDOWN, Code.ANNUALIZED_RETURN])
def test_episode_protocol_cannot_claim_continuous_nav_statistics(code):
    with pytest.raises(ValueError, match="independent episode"):
        formula(uuid4(), code)


def test_partial_roster_slicing_is_rejected_at_protocol_freeze():
    batch = inputs()
    with pytest.raises(ValueError, match="whole-episode"):
        replace(
            batch.metric,
            slice_kind=EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM,
            backtest_arm_kind=_metric(
                EvaluationSourceKind.PORTFOLIO_OUTCOME, EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN
            ).backtest_arm_kind,
        )


def test_formula_cost_roster_mismatch_cannot_reinterpret_existing_result():
    batch = inputs()
    row = list(batch.source_rows[0])
    row[41] = D(11)
    with pytest.raises(EvaluationReconciliationError, match="directional cost"):
        compute_evaluation((replace(batch, source_rows=(tuple(row), *batch.source_rows[1:])),))


def test_v2_gross_notional_turnover_uses_actual_sale_value():
    (computed,) = compute_evaluation((inputs(Code.TURNOVER),))
    assert computed.result.decimal_value == D(".42")


def test_net_formula_cannot_consume_gross_profit_under_a_net_label():
    with pytest.raises(ValueError, match="net source"):
        replace(inputs().metric, source_measure=EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN)


def test_v2_full_transform_freezes_rounding_independent_of_callers_context():
    from decimal import localcontext, ROUND_DOWN, ROUND_UP, ROUND_HALF_EVEN

    batch = inputs()
    f = replace(
        batch.metric.formula,
        parameters=tuple(
            replace(p, decimal_value=D(1003)) if p.parameter_code == "initial_capital" else p for p in batch.metric.formula.parameters
        ),
    )
    batch = replace(batch, metric=replace(batch.metric, formula=f))
    results = []
    for rounding in (ROUND_DOWN, ROUND_UP, ROUND_HALF_EVEN):
        with localcontext() as context:
            context.rounding = rounding
            context.prec = 9
            results.append(compute_evaluation((batch,))[0])
    # 40.12 units: 401.20 buy, 441.32 sell, .40 + .88 fee = 38.84 PnL.
    with localcontext() as context:
        context.prec = 34
        context.rounding = ROUND_HALF_EVEN
        expected = D("19.42") / D(1003)
    assert all(result.result.decimal_value == expected for result in results)
    assert len({result.result_sha256 for result in results}) == 1


def test_one_multi_instrument_episode_is_one_economic_sample():
    batch = inputs()
    first = batch.source_rows[1]
    companion = list(first)
    companion[0], companion[2], companion[11] = uuid4(), uuid4(), uuid4()
    companion[45] = replace(first[45], revision_id=companion[2])
    batch = replace(batch, source_rows=(first, tuple(companion)), metric=replace(batch.metric, minimum_estimable_count=2))
    (computed,) = compute_evaluation((batch,))
    assert computed.result.decimal_value is None
    assert computed.result.estimable_count == 1
    assert computed.reason_code == "INSUFFICIENT_EPISODE_OBSERVATIONS"


def selected(batch, kind, key=None):
    parameters = list(batch.metric.formula.parameters)
    parameters.append(
        EvaluationFormulaParameter(uuid4(), len(parameters) + 1, "episode_slice_kind", FormulaParameterType.TEXT, text_value=kind)
    )
    if key is not None:
        parameters.append(
            EvaluationFormulaParameter(uuid4(), len(parameters) + 1, "episode_slice_key", FormulaParameterType.TEXT, text_value=key)
        )
    return replace(batch, metric=replace(batch.metric, formula=replace(batch.metric.formula, parameters=tuple(parameters))))


def test_fold_projection_uses_complete_parent_path_then_selects():
    batch = inputs()
    second = list(batch.source_rows[1])
    second[15] = uuid4()
    batch = replace(batch, source_rows=(batch.source_rows[0], tuple(second)))
    (whole,) = compute_evaluation((batch,))
    (sliced,) = compute_evaluation((selected(batch, "FOLD", str(second[15])),))
    assert sliced.result.decimal_value == D(".03872")
    assert sliced.result.estimable_count == 1
    assert sliced.resolved[0].economic_path_sha256 == whole.resolved[0].economic_path_sha256
    assert [item.state.value for item in sliced.result.observations] == ["EXCLUDED", "INCLUDED"]
    broken = list(batch.source_rows[0])
    broken[33] = D(1)
    broken[35] = "AUTHORIZED"
    with pytest.raises(EvaluationReconciliationError, match="INSUFFICIENT_CASH"):
        compute_evaluation((selected(replace(batch, source_rows=(tuple(broken), tuple(second))), "FOLD", str(second[15])),))


@pytest.mark.parametrize("kind,key", [("FOLD", None), ("ALL", "x"), ("CONTEXT", "UP"), ("TIME_MONTH", "2026-13")])
def test_unsupported_or_ambiguous_episode_selector_is_rejected(kind, key):
    with pytest.raises(ValueError, match="episode slice"):
        selected(inputs(), kind, key)


def test_time_projection_uses_exact_session_dates_and_empty_slice_is_typed():
    from datetime import date

    batch = inputs()
    second = list(batch.source_rows[1])
    second[16] = uuid4()
    batch = replace(
        batch,
        source_rows=(batch.source_rows[0], tuple(second)),
        session_dates=((batch.source_rows[0][16], date(2026, 1, 31)), (second[16], date(2026, 2, 2))),
    )
    (projected,) = compute_evaluation((selected(batch, "TIME_MONTH", "2026-02"),))
    assert projected.result.decimal_value == D(".03872")
    (empty,) = compute_evaluation((selected(batch, "TIME_MONTH", "2026-03"),))
    assert empty.result.decimal_value is None
    assert empty.reason_code == "INSUFFICIENT_EPISODE_OBSERVATIONS"
    with pytest.raises(EvaluationReconciliationError, match="canonical Decision TradingSession"):
        compute_evaluation((replace(selected(batch, "TIME_MONTH", "2026-02"), session_dates=()),))


def test_owner_price_port_deduplicates_exact_revision_and_window():
    from market_regime_alpha.research_qualification.application.evaluation_economics import acquire_episode_prices

    batch = inputs()
    raw = replace(batch, source_rows=tuple(row[:-1] for row in batch.source_rows))

    class Owner:
        def __init__(self):
            self.requests = []

        def episode_prices(self, identities, entry, exit):
            self.requests.append((identities, entry, exit))
            return tuple(row[-1] for row in batch.source_rows)

    owner = Owner()
    assert acquire_episode_prices((raw, raw, raw), owner) == (batch, batch, batch)
    assert len(owner.requests) == 1
    with pytest.raises(EvaluationReconciliationError, match="canonical Outcome price owner"):
        acquire_episode_prices((raw,), None)
