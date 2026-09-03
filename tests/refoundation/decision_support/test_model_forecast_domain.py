from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.decision_support.domain.model_forecast import (
    ForecastModelBindingPlan,
    ModelForecastPrediction,
    ModelPredictionState,
)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _prediction() -> ModelForecastPrediction:
    return ModelForecastPrediction(
        candidate_id=_id(1),
        commitment_id=_id(2),
        dataset_id=_id(3),
        feature_vector_sha256="a" * 64,
        state=ModelPredictionState.AVAILABLE,
        reason_code="MODEL_ESTIMATE_AVAILABLE",
        point_estimate=Decimal("0.012345678901"),
    )


def _binding(**changes: object) -> ForecastModelBindingPlan:
    now = datetime(2026, 9, 3, 8, tzinfo=UTC)
    values: dict[str, object] = {
        "forecast_model_binding_id": _id(10),
        "forecast_id": _id(11),
        "forecast_group_id": _id(12),
        "forecast_estimate_id": _id(13),
        "decision_run_id": _id(14),
        "strategy_version_id": _id(15),
        "commitment_id": _id(2),
        "target_metric_definition_id": _id(25),
        "forecast_estimate_content_sha256": "d" * 64,
        "dataset_id": _id(3),
        "exploratory_backtest_run_id": _id(16),
        "exploratory_backtest_arm_id": _id(17),
        "exploratory_backtest_fold_id": _id(18),
        "exploratory_backtest_fold_session_id": _id(19),
        "inference_fold_ordinal": 2,
        "model_version_id": _id(20),
        "model_id": _id(21),
        "model_training_run_id": _id(22),
        "training_fold_id": _id(23),
        "training_fold_ordinal": 1,
        "model_version_sha256": "b" * 64,
        "fitted_model_artifact_id": _id(24),
        "fitted_model_content_sha256": "c" * 64,
        "fitted_model_size_bytes": 123,
        "feature_vector_sha256": "a" * 64,
        "prediction_state": ModelPredictionState.AVAILABLE,
        "reason_code": "MODEL_ESTIMATE_AVAILABLE",
        "point_estimate": Decimal("0.012345678901"),
        "model_registered_at": now,
        "forecast_recorded_at": now + timedelta(seconds=1),
    }
    values.update(changes)
    return ForecastModelBindingPlan(**values)  # type: ignore[arg-type]


def test_model_forecast_binding_freezes_exact_input_and_output() -> None:
    prediction = _prediction()
    binding = _binding()

    assert str(prediction.input_sha256) == "667ece5f63c6861adc73c192f15bd154977e20df4e28493941e4dbf3df1e1b18"
    assert len(str(binding.inference_input_sha256)) == 64
    assert len(str(binding.inference_output_sha256)) == 64
    assert len(str(binding.content_sha256)) == 64


def test_not_estimable_model_forecast_is_explicit() -> None:
    prediction = ModelForecastPrediction(
        candidate_id=_id(1),
        commitment_id=_id(2),
        dataset_id=_id(3),
        feature_vector_sha256="a" * 64,
        state=ModelPredictionState.NOT_ESTIMABLE,
        reason_code="FEATURE_MISSING",
        point_estimate=None,
    )
    binding = _binding(
        prediction_state=ModelPredictionState.NOT_ESTIMABLE,
        reason_code="FEATURE_MISSING",
        point_estimate=None,
    )
    assert prediction.point_estimate is None
    assert binding.point_estimate is None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"inference_fold_ordinal": 1}, "later fold"),
        ({"inference_fold_ordinal": 0}, "positive"),
        ({"forecast_recorded_at": datetime(2026, 9, 3, 8, tzinfo=UTC)}, "registered before"),
        ({"point_estimate": Decimal("NaN")}, "finite"),
    ],
)
def test_model_forecast_binding_rejects_leakage_or_invalid_output(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _binding(**changes)
