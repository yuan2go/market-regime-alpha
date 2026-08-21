from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from market_regime_alpha.forecasting.conditional import (
    ConditionalForecastConfig,
    ConditionalForecastSample,
    fit_conditional_forecast,
)


def _config(minimum: int = 6) -> ConditionalForecastConfig:
    return ConditionalForecastConfig.create(
        feature_names=("alpha_score", "signal_score", "liquidity"),
        continuous_targets=("mae", "mfe", "t_plus_1_return"),
        barrier_targets=("lower_barrier", "upper_barrier"),
        train_validation_policy="CHRONOLOGICAL_75_25",
        penalties=(Decimal("0.1"), Decimal("1")),
        hyperparameter_search_budget=2,
        random_seed=20260819,
        minimum_training_samples=minimum,
        cost_assumption=Decimal("0.001"),
    )


def _samples(count: int, *, future_last: bool = False) -> tuple[ConditionalForecastSample, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        ConditionalForecastSample(
            sample_id=f"sample-{index}",
            sample_decision_time=start + timedelta(days=index),
            target_available_at=(
                start + timedelta(days=100)
                if future_last and index == count - 1
                else start + timedelta(days=index + 1)
            ),
            features={
                "alpha_score": Decimal(index),
                "signal_score": Decimal(index % 3),
                "liquidity": Decimal("1000") + Decimal(index),
            },
            continuous_targets={
                "mae": -Decimal(index + 1) / Decimal("100"),
                "mfe": Decimal(index + 1) / Decimal("100"),
                "t_plus_1_return": Decimal(index - 2) / Decimal("100"),
            },
            barrier_targets={
                "lower_barrier": index % 2 == 0,
                "upper_barrier": index % 2 == 1,
            },
        )
        for index in range(count)
    )


def test_minimum_sample_behavior_is_fail_closed() -> None:
    result = fit_conditional_forecast(
        _config(minimum=8),
        samples=_samples(5),
        prediction_time=datetime(2026, 3, 1, tzinfo=UTC),
        inference_features={
            "alpha_score": Decimal("5"),
            "signal_score": Decimal("1"),
            "liquidity": Decimal("1005"),
        },
    )

    assert result.status == "DATA_INSUFFICIENT"
    assert result.regularized_prediction is None
    assert result.calibration_status == "NOT_CALIBRATED"


def test_future_available_sample_is_excluded_from_training() -> None:
    result = fit_conditional_forecast(
        _config(minimum=6),
        samples=_samples(10, future_last=True),
        prediction_time=datetime(2026, 2, 1, tzinfo=UTC),
        inference_features={
            "alpha_score": Decimal("5"),
            "signal_score": Decimal("1"),
            "liquidity": Decimal("1005"),
        },
    )

    assert result.status == "AVAILABLE_FOR_RESEARCH"
    assert result.admitted_sample_count == 9
    assert result.future_excluded_sample_count == 1


def test_baseline_and_regularized_model_are_compared_without_probability_claim() -> None:
    result = fit_conditional_forecast(
        _config(minimum=6),
        samples=_samples(12),
        prediction_time=datetime(2026, 3, 1, tzinfo=UTC),
        inference_features={
            "alpha_score": Decimal("5"),
            "signal_score": Decimal("1"),
            "liquidity": Decimal("1005"),
        },
    )

    assert result.baseline_prediction is not None
    assert result.regularized_prediction is not None
    assert result.model_comparison is not None
    assert result.regularized_prediction.barrier_scores_are_probabilities is False
    assert result.calibration_status == "NOT_CALIBRATED"
    assert result.prediction_uncertainty is not None
    assert result.model_reference is not None
