from __future__ import annotations

from decimal import Decimal

import pytest

from market_regime_alpha.forecasting.regularized_linear import (
    TrainingMatrix,
    fit_regularized_continuous_statistics,
    fit_regularized_multi_target,
)


def _matrix() -> TrainingMatrix:
    return TrainingMatrix.create(
        feature_names=("value", "momentum"),
        rows=(
            {"momentum": Decimal("-2"), "value": Decimal("1")},
            {"momentum": Decimal("-1"), "value": Decimal("2")},
            {"momentum": None, "value": Decimal("3")},
            {"momentum": Decimal("1"), "value": Decimal("4")},
            {"momentum": Decimal("2"), "value": Decimal("5")},
            {"momentum": Decimal("3"), "value": Decimal("6")},
        ),
        continuous_targets={
            "expected_return": tuple(
                Decimal(str(value)) for value in (1, 2, 3, 4, 5, 6)
            )
        },
        barrier_targets={
            "up_barrier": (False, False, False, True, True, True)
        },
    )


def test_regularized_multi_target_fit_is_deterministic_and_order_stable() -> None:
    matrix = _matrix()

    first = fit_regularized_multi_target(matrix, penalty=Decimal("0.1"))
    second = fit_regularized_multi_target(matrix, penalty=Decimal("0.1"))

    assert first == second
    assert first.feature_names == ("momentum", "value")
    assert first.transformed_feature_names == (
        "momentum",
        "value",
        "missing::momentum",
        "missing::value",
    )
    estimate = first.predict({"value": Decimal("7"), "momentum": None})
    assert tuple(estimate.continuous) == ("expected_return",)
    assert tuple(estimate.raw_barrier_logits) == ("up_barrier",)
    assert estimate.barrier_scores_are_probabilities is False


def test_missing_values_use_frozen_median_and_explicit_indicator() -> None:
    fitted = fit_regularized_multi_target(
        _matrix(), penalty=Decimal("0.1")
    )

    transformed = fitted.preprocessing.transform(
        {"momentum": None, "value": Decimal("3")}
    )

    assert transformed[0] == Decimal("0")
    assert transformed[2] == Decimal("1")
    assert fitted.preprocessing.medians[0] == Decimal("1")
    assert fitted.preprocessing.scales[0] == Decimal("3")


def test_constant_or_single_class_targets_are_rejected() -> None:
    matrix = TrainingMatrix.create(
        feature_names=("x",),
        rows=({"x": Decimal("1")}, {"x": Decimal("2")}),
        continuous_targets={"return": (Decimal("1"), Decimal("1"))},
        barrier_targets={"barrier": (True, True)},
    )

    with pytest.raises(ValueError, match="degenerate continuous target"):
        fit_regularized_multi_target(matrix, penalty=Decimal("1"))


def test_incremental_continuous_statistics_match_canonical_ridge_head() -> None:
    matrix = _matrix()
    full = fit_regularized_multi_target(matrix, penalty=Decimal("0.1"))
    design = tuple(
        (Decimal("1"), *full.preprocessing.transform(row)) for row in matrix.rows
    )
    targets = matrix.continuous_targets["expected_return"]
    width = len(design[0])
    normal = tuple(
        tuple(
            sum(
                (row[left] * row[right] for row in design),
                Decimal("0"),
            )
            for right in range(width)
        )
        for left in range(width)
    )
    rhs = tuple(
        sum(
            (row[index] * target for row, target in zip(design, targets, strict=True)),
            Decimal("0"),
        )
        for index in range(width)
    )

    streamed = fit_regularized_continuous_statistics(
        preprocessing=full.preprocessing,
        target_name="expected_return",
        normal_matrix=normal,
        rhs=rhs,
        distinct_target_count=len(set(targets)),
        penalty=Decimal("0.1"),
    )

    assert streamed.continuous_heads == full.continuous_heads
    assert streamed.preprocessing == full.preprocessing
