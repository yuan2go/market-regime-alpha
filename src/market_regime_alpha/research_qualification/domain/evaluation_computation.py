"""Deterministic Evaluation computation between input-read and result-write UoWs."""
from dataclasses import dataclass
from typing import Any
from decimal import Decimal, localcontext
from market_regime_alpha.research_qualification.domain.evaluation import ProtocolMetricDefinition, EvaluationMetricResult, evaluate_metric
from market_regime_alpha.research_qualification.domain.evaluation_formula import FormulaResultState, evaluate_backtest_formula
from market_regime_alpha.research_qualification.domain.evaluation_sources import _ResolvedMetricInput, resolve_metric_inputs, formula_observations
from market_regime_alpha.research_qualification.domain.research_vocabulary import EvaluationMetricState, AcceptanceState, AcceptanceOperator
from market_regime_alpha.shared.hashing import canonical_json_sha256

@dataclass(frozen=True, slots=True)
class EvaluationMetricInputs:
    metric: ProtocolMetricDefinition
    source_rows: tuple[tuple[Any, ...], ...]
    outcome_guard_sha256: str | None = None

@dataclass(frozen=True, slots=True)
class ComputedEvaluationMetric:
    inputs: EvaluationMetricInputs
    resolved: tuple[_ResolvedMetricInput, ...]
    result: EvaluationMetricResult
    reason_code: str | None
    result_sha256: str


def compute_evaluation(inputs: tuple[EvaluationMetricInputs, ...]) -> tuple[ComputedEvaluationMetric, ...]:
    return tuple(_compute(item) for item in inputs)


def _compute(inputs: EvaluationMetricInputs) -> ComputedEvaluationMetric:
    metric = inputs.metric
    with localcontext() as context:
        # Preserve the historical input transform's 28-digit arithmetic; only
        # V2 moves its complete financial path to the frozen formula precision.
        context.prec = metric.formula.decimal_precision if metric.formula and metric.formula.formula_version == 2 else 28
        resolved = resolve_metric_inputs(metric, list(inputs.source_rows))
        result = evaluate_metric(metric, tuple(item.input for item in resolved))
        reason = None
        if metric.formula is not None:
            formula_result = evaluate_backtest_formula(metric.formula, formula_observations(metric, resolved))
            result = _formula_metric_result(metric, formula_result.state, formula_result.decimal_value,
                                            formula_result.estimable_count, result)
            reason = formula_result.reason_code
            if metric.formula.formula_version == 2 and result.estimable_count < metric.minimum_estimable_count:
                result = _formula_metric_result(metric, FormulaResultState.NOT_ESTIMABLE, None,
                                                result.estimable_count, result)
                reason = "INSUFFICIENT_EPISODE_OBSERVATIONS"
        payload: dict[str, object] = {"metric": metric.content_sha256, "result": result}
        if metric.formula is not None:
            payload["formula_content_sha256"] = str(metric.formula.content_sha256)
            payload["reason_code"] = reason
        if resolved and resolved[0].economic_path_sha256 is not None:
            payload["economic_path_sha256"] = resolved[0].economic_path_sha256
        return ComputedEvaluationMetric(inputs, resolved, result, reason, canonical_json_sha256(payload))


def _formula_metric_result(
    metric: ProtocolMetricDefinition,
    state: FormulaResultState,
    decimal_value: Decimal | None,
    estimable_count: int,
    classified: EvaluationMetricResult,
) -> EvaluationMetricResult:
    if state is FormulaResultState.NOT_ESTIMABLE:
        return EvaluationMetricResult(
            EvaluationMetricState.NOT_ESTIMABLE,
            None,
            None,
            estimable_count,
            AcceptanceState.NOT_ESTIMABLE,
            classified.observations,
        )
    assert decimal_value is not None
    if metric.acceptance_operator is AcceptanceOperator.NONE:
        acceptance = AcceptanceState.NOT_APPLICABLE
    else:
        threshold = metric.acceptance_threshold
        assert threshold is not None
        accepted = decimal_value >= threshold if metric.acceptance_operator is AcceptanceOperator.AT_LEAST else decimal_value <= threshold
        acceptance = AcceptanceState.ACCEPTED if accepted else AcceptanceState.REJECTED
    return EvaluationMetricResult(
        EvaluationMetricState.ESTIMATED,
        decimal_value,
        None,
        estimable_count,
        acceptance,
        classified.observations,
    )
