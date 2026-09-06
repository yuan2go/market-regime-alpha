from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from uuid import UUID, uuid4

import pytest

from market_regime_alpha.outcome.domain.economic_prices import OutcomeEpisodePrices
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode as Code, BacktestMetricSurface, EvaluationFormulaDefinition,
    EvaluationFormulaParameter, FormulaParameterType,
)
from market_regime_alpha.research_qualification.domain.evaluation_computation import EvaluationMetricInputs, compute_evaluation
from market_regime_alpha.research_qualification.errors import EvaluationReconciliationError
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    EvaluationSourceKind, EvaluationSourceMeasure, EvaluationSliceKind,
)
from tests.refoundation.research_qualification.test_wp17p_evaluation_source_repository import _metric, _source


ENTRY, EXIT = UUID(int=800), UUID(int=801)


def formula(metric_id, code=Code.NET_RETURN_ASSUMED_COST, *, entry=ENTRY, exit=EXIT):
    values = {
        "economic_model": "INDEPENDENT_EPISODES",
        "execution_assumption": "ASSUMED_CHECKPOINT_CLOSE_FRACTIONAL",
        "price_basis": "RAW_UNADJUSTED", "initial_capital": D(1000),
        "buy_fee_bps": D(10), "sell_fee_bps": D(20), "minimum_fee": D(0), "slippage_bps": D(0),
        "final_liquidation": True, "carry_forward": "NONE",
        "entry_checkpoint_id": str(entry), "exit_checkpoint_id": str(exit),
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
    metric = replace(metric, formula=formula(metric.evaluation_protocol_metric_id, code),
                     slice_kind=EvaluationSliceKind.ALL_MEMBERS, backtest_arm_kind=None)
    t, instrument, arm = datetime(2026, 1, 5, tzinfo=UTC), uuid4(), uuid4()
    rows = []
    for i, risk in enumerate(("REJECTED", "AUTHORIZED")):
        decision = t + timedelta(days=i)
        row = _source(decision_time=decision, risk_status=risk, instrument_id=instrument, arm_id=arm)
        prices = OutcomeEpisodePrices(row[2], "a" * 64, ENTRY, EXIT, uuid4(), uuid4(), "b" * 64, "c" * 64,
                                      decision + timedelta(hours=1), decision + timedelta(hours=2), D(10), D(11),
                                      decision + timedelta(days=1), decision + timedelta(days=2), "RAW_UNADJUSTED")
        rows.append((*row, prices.knowledge_cutoff, D(10), D(20), False, False, prices))
    return EvaluationMetricInputs(metric, tuple(rows))


def test_evaluation_v2_rejected_then_approved_hand_oracle_and_result_identity():
    batch = inputs()
    computed, = compute_evaluation((batch,))
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
        replace(batch.metric, slice_kind=EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM,
                backtest_arm_kind=_metric(EvaluationSourceKind.PORTFOLIO_OUTCOME,
                                         EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN).backtest_arm_kind)


def test_formula_cost_roster_mismatch_cannot_reinterpret_existing_result():
    batch = inputs()
    row = list(batch.source_rows[0])
    row[41] = D(11)
    with pytest.raises(EvaluationReconciliationError, match="directional cost"):
        compute_evaluation((replace(batch, source_rows=(tuple(row), *batch.source_rows[1:])),))


def test_v2_gross_notional_turnover_uses_actual_sale_value():
    computed, = compute_evaluation((inputs(Code.TURNOVER),))
    assert computed.result.decimal_value == D(".42")
