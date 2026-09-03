from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationInput,
    ProtocolMetricDefinition,
    evaluate_metric,
    transition_evaluation_run,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    AcceptanceOperator,
    CandidateDisposition,
    EvaluationInputState,
    EvaluationMetricState,
    EvaluationReducer,
    EvaluationSourceKind,
    EvaluationSourceMeasure,
    EvaluationRunStatus,
    EvaluationSliceKind,
    ExploratoryBacktestArmKind,
    MetricDirection,
    SourceMetricValueType,
)


def _metric(**changes: object) -> ProtocolMetricDefinition:
    values: dict[str, object] = {
        "evaluation_protocol_metric_id": uuid4(),
        "metric_code": "mean-return",
        "ordinal": 1,
        "source_target_metric_definition_id": uuid4(),
        "source_metric_code": "simple-return",
        "source_value_type": SourceMetricValueType.DECIMAL,
        "reducer": EvaluationReducer.MEAN_DECIMAL,
        "slice_kind": EvaluationSliceKind.ALL_MEMBERS,
        "candidate_disposition": None,
        "direction": MetricDirection.HIGHER,
        "minimum_estimable_count": 1,
        "acceptance_operator": AcceptanceOperator.AT_LEAST,
        "acceptance_threshold": Decimal("0.01"),
    }
    values.update(changes)
    return ProtocolMetricDefinition(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("reducer", "source_type"),
    [
        (EvaluationReducer.MEAN_DECIMAL, SourceMetricValueType.BOOLEAN),
        (EvaluationReducer.MEDIAN_DECIMAL, SourceMetricValueType.BOOLEAN),
        (EvaluationReducer.TRUE_RATE, SourceMetricValueType.DECIMAL),
    ],
)
def test_reducer_source_type_mismatch_fails(
    reducer: EvaluationReducer,
    source_type: SourceMetricValueType,
) -> None:
    with pytest.raises(ValueError, match="reducer"):
        _metric(reducer=reducer, source_value_type=source_type)


def test_candidate_disposition_slice_freezes_exact_disposition() -> None:
    with pytest.raises(ValueError, match="candidate_disposition"):
        _metric(slice_kind=EvaluationSliceKind.CANDIDATE_DISPOSITION)
    metric = _metric(
        slice_kind=EvaluationSliceKind.CANDIDATE_DISPOSITION,
        candidate_disposition=CandidateDisposition.SELECTED,
    )
    assert metric.candidate_disposition is CandidateDisposition.SELECTED


def test_all_members_slice_forbids_disposition() -> None:
    with pytest.raises(ValueError, match="candidate_disposition"):
        _metric(candidate_disposition=CandidateDisposition.UNRANKABLE)


def test_exploratory_arm_slice_freezes_exact_arm() -> None:
    with pytest.raises(ValueError, match="backtest_arm_kind"):
        _metric(slice_kind=EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM)
    metric = _metric(
        slice_kind=EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM,
        backtest_arm_kind=ExploratoryBacktestArmKind.MODEL_CHALLENGER,
    )
    assert metric.backtest_arm_kind is ExploratoryBacktestArmKind.MODEL_CHALLENGER


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (EvaluationRunStatus.OPEN, EvaluationRunStatus.INPUTS_ACQUIRED),
        (EvaluationRunStatus.OPEN, EvaluationRunStatus.FAILED),
        (EvaluationRunStatus.INPUTS_ACQUIRED, EvaluationRunStatus.COMPLETED),
        (EvaluationRunStatus.INPUTS_ACQUIRED, EvaluationRunStatus.FAILED),
    ],
)
def test_evaluation_lifecycle_accepts_only_forward_transitions(
    current: EvaluationRunStatus,
    target: EvaluationRunStatus,
) -> None:
    assert transition_evaluation_run(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (EvaluationRunStatus.INPUTS_ACQUIRED, EvaluationRunStatus.OPEN),
        (EvaluationRunStatus.COMPLETED, EvaluationRunStatus.OPEN),
        (EvaluationRunStatus.FAILED, EvaluationRunStatus.OPEN),
        (EvaluationRunStatus.OPEN, EvaluationRunStatus.COMPLETED),
    ],
)
def test_evaluation_lifecycle_rejects_reopen_and_skips(
    current: EvaluationRunStatus,
    target: EvaluationRunStatus,
) -> None:
    with pytest.raises(ValueError, match="transition"):
        transition_evaluation_run(current, target)


def test_mean_reducer_preserves_complete_input_roster() -> None:
    metric = _metric()
    inputs = (
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("0.1"), None),
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "UNAVAILABLE", None, None),
        EvaluationInput(uuid4(), CandidateDisposition.UNRANKABLE, "FAILED", None, None),
    )
    result = evaluate_metric(metric, inputs)
    assert result.state is EvaluationMetricState.ESTIMATED
    assert result.decimal_value == Decimal("0.1")
    assert len(result.observations) == len(inputs)
    assert [item.state for item in result.observations] == [
        EvaluationInputState.INCLUDED,
        EvaluationInputState.NOT_ESTIMABLE,
        EvaluationInputState.NOT_ESTIMABLE,
    ]


def test_not_estimable_is_explicit_and_does_not_delete_members() -> None:
    metric = replace(_metric(), minimum_estimable_count=2)
    inputs = (
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("0.1"), None),
        EvaluationInput(uuid4(), CandidateDisposition.UNRANKABLE, "FAILED", None, None),
    )
    result = evaluate_metric(metric, inputs)
    assert result.state is EvaluationMetricState.NOT_ESTIMABLE
    assert result.decimal_value is None
    assert len(result.observations) == 2


def test_disposition_slice_records_out_of_slice_exclusions() -> None:
    metric = _metric(
        slice_kind=EvaluationSliceKind.CANDIDATE_DISPOSITION,
        candidate_disposition=CandidateDisposition.SELECTED,
    )
    inputs = (
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("0.2"), None),
        EvaluationInput(uuid4(), CandidateDisposition.UNRANKABLE, "COMPLETE", Decimal("0.8"), None),
    )
    result = evaluate_metric(metric, inputs)
    assert [item.state for item in result.observations] == [
        EvaluationInputState.INCLUDED,
        EvaluationInputState.EXCLUDED,
    ]


def test_forecast_outcome_rank_correlation_handles_ties_deterministically() -> None:
    metric = _metric(
        metric_code="rank-ic",
        reducer=EvaluationReducer.SPEARMAN_RANK_CORRELATION,
        source_kind=EvaluationSourceKind.FORECAST_OUTCOME_PAIR,
        source_measure=EvaluationSourceMeasure.FORECAST_POINT_VS_TARGET,
        acceptance_threshold=Decimal("0"),
    )
    inputs = (
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("1"), None, Decimal("1")),
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("2"), None, Decimal("2")),
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("2"), None, Decimal("3")),
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("4"), None, Decimal("4")),
    )

    result = evaluate_metric(metric, inputs)

    assert result.state is EvaluationMetricState.ESTIMATED
    assert result.decimal_value == Decimal("0.9486832980505137995996680633")
    assert len(result.observations) == 4


def test_rank_ic_averages_cross_sectional_session_correlations() -> None:
    metric = _metric(
        metric_code="rank-ic",
        reducer=EvaluationReducer.SPEARMAN_RANK_CORRELATION,
        source_kind=EvaluationSourceKind.FORECAST_OUTCOME_PAIR,
        source_measure=EvaluationSourceMeasure.FORECAST_POINT_VS_TARGET,
        acceptance_threshold=Decimal("0"),
    )
    inputs = (
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("1"), None, Decimal("1"), group_key="s1"),
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("2"), None, Decimal("2"), group_key="s1"),
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("1"), None, Decimal("2"), group_key="s2"),
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("2"), None, Decimal("1"), group_key="s2"),
    )

    result = evaluate_metric(metric, inputs)

    assert result.decimal_value == Decimal("0")


def test_arm_slice_keeps_complete_roster_as_explicit_exclusions() -> None:
    metric = _metric(
        slice_kind=EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM,
        backtest_arm_kind=ExploratoryBacktestArmKind.RULE_BASELINE,
    )
    inputs = (
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("0.1"), None, backtest_arm_kind=ExploratoryBacktestArmKind.RULE_BASELINE),
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", Decimal("0.2"), None, backtest_arm_kind=ExploratoryBacktestArmKind.MODEL_CHALLENGER),
    )

    result = evaluate_metric(metric, inputs)

    assert [item.state for item in result.observations] == [
        EvaluationInputState.INCLUDED,
        EvaluationInputState.EXCLUDED,
    ]


def test_drawdown_reducer_uses_declared_chronological_roster() -> None:
    metric = _metric(
        metric_code="max-drawdown",
        reducer=EvaluationReducer.MAX_DRAWDOWN,
        source_kind=EvaluationSourceKind.PORTFOLIO_OUTCOME,
        source_measure=EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN,
        direction=MetricDirection.LOWER,
        acceptance_operator=AcceptanceOperator.AT_MOST,
        acceptance_threshold=Decimal("0.25"),
    )
    inputs = tuple(
        EvaluationInput(uuid4(), CandidateDisposition.SELECTED, "COMPLETE", value, None)
        for value in (Decimal("0.10"), Decimal("-0.20"), Decimal("0.05"))
    )

    result = evaluate_metric(metric, inputs)

    assert result.decimal_value == Decimal("0.20")


def test_source_kind_and_measure_are_frozen_compatibly() -> None:
    with pytest.raises(ValueError, match="source measure"):
        _metric(
            source_kind=EvaluationSourceKind.SIGNAL_STATUS,
            source_measure=EvaluationSourceMeasure.FORECAST_POINT_VS_TARGET,
        )


@pytest.mark.parametrize(
    ("source_kind", "source_measure", "source_type"),
    [
        (
            EvaluationSourceKind.CANDIDATE_DISPOSITION,
            EvaluationSourceMeasure.CANDIDATE_SELECTED,
            SourceMetricValueType.DECIMAL,
        ),
        (
            EvaluationSourceKind.SIGNAL_STATUS,
            EvaluationSourceMeasure.SIGNAL_PRESENT,
            SourceMetricValueType.DECIMAL,
        ),
        (
            EvaluationSourceKind.PORTFOLIO_LINE,
            EvaluationSourceMeasure.TARGET_WEIGHT,
            SourceMetricValueType.BOOLEAN,
        ),
        (
            EvaluationSourceKind.RISK_DECISION,
            EvaluationSourceMeasure.RISK_REJECTED,
            SourceMetricValueType.DECIMAL,
        ),
    ],
)
def test_source_kind_and_input_value_type_are_frozen_compatibly(
    source_kind: EvaluationSourceKind,
    source_measure: EvaluationSourceMeasure,
    source_type: SourceMetricValueType,
) -> None:
    with pytest.raises(ValueError, match="source kind"):
        _metric(
            source_kind=source_kind,
            source_measure=source_measure,
            source_value_type=source_type,
            reducer=(
                EvaluationReducer.TRUE_RATE
                if source_type is SourceMetricValueType.BOOLEAN
                else EvaluationReducer.MEAN_DECIMAL
            ),
        )
