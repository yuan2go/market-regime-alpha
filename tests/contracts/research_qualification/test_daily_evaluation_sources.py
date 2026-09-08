from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from market_regime_alpha.research_qualification.domain.evaluation_sources import resolve_metric_inputs
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode,
    BacktestMetricSurface,
    EvaluationFormulaDefinition,
    EvaluationFormulaParameter,
    FormulaParameterType,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    EvaluationSliceKind,
    EvaluationSourceKind,
    EvaluationSourceMeasure,
)
from market_regime_alpha.research_qualification.errors import EvaluationReconciliationError
from tests.contracts.research_qualification.test_evaluation_source_repository import _metric, _source


def test_actual_prediction_evaluation_requires_explicit_use_instead_of_a_fake_backtest_arm():
    use = uuid4()
    prior = _metric(EvaluationSourceKind.FORECAST_OUTCOME_PAIR, EvaluationSourceMeasure.FORECAST_POINT_VS_TARGET)
    formula = EvaluationFormulaDefinition(
        prior.evaluation_protocol_metric_id,
        BacktestFormulaCode.PREDICTIVE_MAE,
        1,
        38,
        "ROUND_HALF_EVEN",
        (EvaluationFormulaParameter(uuid4(), 1, "experimental_model_use_id", FormulaParameterType.TEXT, text_value=str(use)),),
        BacktestMetricSurface.SIGNAL_FORECAST,
    )
    metric = replace(
        prior,
        source_kind=EvaluationSourceKind("EXPERIMENTAL_FORECAST_OUTCOME_PAIR"),
        slice_kind=EvaluationSliceKind.ALL_MEMBERS,
        backtest_arm_kind=None,
        formula=formula,
    )
    row = list(_source(decision_time=datetime(2026, 9, 8, tzinfo=UTC), forecast=Decimal("0.03"), outcome=Decimal("0.01")))
    row[13:18] = [None] * 5
    row.extend([None, None, None, False, False, use])
    result = resolve_metric_inputs(metric, [tuple(row)])[0]
    assert result.input.decimal_value == Decimal("0.03")
    assert result.input.secondary_decimal_value == Decimal("0.01")
    row[45] = uuid4()
    with pytest.raises(EvaluationReconciliationError, match="experimental"):
        resolve_metric_inputs(metric, [tuple(row)])
    with pytest.raises(EvaluationReconciliationError, match="Backtest"):
        resolve_metric_inputs(prior, [tuple(row)])


def test_daily_metrics_freeze_both_roles_on_identical_complete_population():
    from market_regime_alpha.research_qualification.domain.daily_protocol import daily_target_definition, daily_evaluation_protocol
    from market_regime_alpha.research_qualification.domain.model import ArtifactBinding

    artifact = ArtifactBinding(uuid4(), "a" * 64, 1)
    target = daily_target_definition(uuid4(), artifact, artifact)
    protocol = daily_evaluation_protocol(uuid4(), target, uuid4(), 32, artifact, artifact)
    assert len(protocol.metrics) == 10
    assert {metric.experimental_forecast_role for metric in protocol.metrics} == {"MODEL", "RULE_BASELINE"}
    assert all(metric.slice_kind is EvaluationSliceKind.ALL_MEMBERS for metric in protocol.metrics)
    coverage = [metric for metric in protocol.metrics if metric.formula.formula_code is BacktestFormulaCode.COVERAGE_RATE]
    assert len(coverage) == 2
    assert all(
        next(p.integer_value for p in metric.formula.parameters if p.parameter_code == "expected_roster_size") == 32 for metric in coverage
    )
