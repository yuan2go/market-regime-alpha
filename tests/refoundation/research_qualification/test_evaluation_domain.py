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
    EvaluationRunStatus,
    EvaluationSliceKind,
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
