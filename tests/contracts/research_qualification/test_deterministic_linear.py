from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
import json

from market_regime_alpha.research_qualification.application.deterministic_linear import (
    fit_deterministic_ridge,
    load_deterministic_ridge_artifact,
    predict_deterministic_ridge,
)
from market_regime_alpha.research_qualification.domain.research_models import (
    LinearTrainingRow,
)


def test_deterministic_ridge_replays_exact_canonical_artifact() -> None:
    rows = (
        LinearTrainingRow(UUID(int=1), (Decimal("0"), Decimal("1")), Decimal("1")),
        LinearTrainingRow(UUID(int=2), (Decimal("1"), Decimal("0")), Decimal("2")),
        LinearTrainingRow(UUID(int=3), (Decimal("2"), Decimal("1")), Decimal("5")),
        LinearTrainingRow(UUID(int=4), (Decimal("3"), Decimal("2")), Decimal("8")),
    )

    first = fit_deterministic_ridge(
        rows,
        feature_definition_ids=(UUID(int=10), UUID(int=11)),
        alpha=Decimal("0.01"),
        seed=23,
    )
    second = fit_deterministic_ridge(
        tuple(reversed(rows)),
        feature_definition_ids=(UUID(int=10), UUID(int=11)),
        alpha=Decimal("0.01"),
        seed=23,
    )

    assert first.content == second.content
    assert first.content_sha256 == second.content_sha256
    assert first.sample_roster_sha256 == second.sample_roster_sha256
    assert len(first.coefficients) == 2
    assert load_deterministic_ridge_artifact(first.content) == first
    assert predict_deterministic_ridge(first, (Decimal("4"), Decimal("3"))).is_finite()


def test_deterministic_ridge_rejects_non_finite_or_incomplete_matrix() -> None:
    with pytest.raises(ValueError, match="at least two"):
        fit_deterministic_ridge(
            (LinearTrainingRow(UUID(int=1), (Decimal("1"),), Decimal("1")),),
            feature_definition_ids=(UUID(int=10),),
            alpha=Decimal("0.1"),
            seed=1,
        )


def test_deterministic_ridge_parser_fails_closed() -> None:
    with pytest.raises(ValueError, match="duplicate field"):
        load_deterministic_ridge_artifact(
            b'{"schema":"mra-deterministic-ridge-model-v1",'
            b'"schema":"mra-deterministic-ridge-model-v1"}'
        )
    with pytest.raises(ValueError, match="exact fields"):
        load_deterministic_ridge_artifact(b'{"schema":"mra-deterministic-ridge-model-v1"}')

    with pytest.raises(ValueError, match="feature width"):
        fit_deterministic_ridge(
            (
                LinearTrainingRow(UUID(int=1), (Decimal("1"),), Decimal("1")),
                LinearTrainingRow(UUID(int=2), (Decimal("1"), Decimal("2")), Decimal("2")),
            ),
            feature_definition_ids=(UUID(int=10),),
            alpha=Decimal("0.1"),
            seed=1,
        )


def test_prediction_reuses_fit_scaling_without_learning_from_unseen_rows() -> None:
    # Hand calculation: x=(1,3), z=(-1,1), mean(x)=2, population std=1.
    # y=(2,6), intercept=4. With alpha=2, beta=4/(2+2)=1.
    # Unseen x=5 must therefore predict 4+(5-2)=7, not a refitted intercept.
    fitted = fit_deterministic_ridge(
        (LinearTrainingRow(UUID(int=1), (Decimal(1),), Decimal(2)),
         LinearTrainingRow(UUID(int=2), (Decimal(3),), Decimal(6))),
        feature_definition_ids=(UUID(int=10),), alpha=Decimal(2), seed=18,
    )
    original = fitted.content
    assert fitted.feature_means == (Decimal(2),)
    assert fitted.feature_scales == (Decimal(1),)
    assert fitted.intercept == Decimal(4)
    assert fitted.coefficients == (Decimal(1),)
    assert predict_deterministic_ridge(fitted, (Decimal(5),)) == Decimal(7)
    assert predict_deterministic_ridge(fitted, (Decimal(-1),)) == Decimal(1)
    assert fitted.content == original


@pytest.mark.parametrize("scale", ["1", "1e-14", "1e-150", "1e-300"])
def test_v2_tiny_scale_round_trip_uses_the_training_transform(scale: str) -> None:
    unit = Decimal(scale)
    fitted = fit_deterministic_ridge(
        tuple(LinearTrainingRow(UUID(int=i), (unit * i,), Decimal(2 * i)) for i in (1, 3)),
        feature_definition_ids=(UUID(int=10),), alpha=Decimal(2), seed=18,
    )
    restored = load_deterministic_ridge_artifact(fitted.content)
    assert json.loads(fitted.content)["schema"] == "mra-deterministic-ridge-model-v2"
    assert restored == fitted
    assert fitted.feature_scales[0] > 0
    # x=(u,3u), z=(-1,1), y=(2,6), alpha=2: intercept=4, beta=1.
    assert predict_deterministic_ridge(restored, (5 * unit,)) == Decimal(7)
    assert predict_deterministic_ridge(fitted, (-unit,)) == Decimal(1)


def test_constant_feature_has_explicit_unit_scale() -> None:
    fitted = fit_deterministic_ridge(
        tuple(LinearTrainingRow(UUID(int=i), (Decimal("1e-30"),), Decimal(i)) for i in (1, 3)),
        feature_definition_ids=(UUID(int=10),), alpha=Decimal(2), seed=18,
    )
    assert fitted.feature_scales == (Decimal(1),)
    assert predict_deterministic_ridge(load_deterministic_ridge_artifact(fitted.content), (Decimal(99),)) == Decimal(2)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e400", "1e-400"])
def test_training_rejects_values_outside_finite_binary64(value: str) -> None:
    with pytest.raises(ValueError, match="finite|binary64"):
        fit_deterministic_ridge(
            tuple(LinearTrainingRow(UUID(int=i), (Decimal(value),), Decimal(i)) for i in (1, 3)),
            feature_definition_ids=(UUID(int=10),), alpha=Decimal(2), seed=18,
        )


def test_v1_bytes_and_prediction_remain_unchanged() -> None:
    content = b'{"algorithm":"deterministic_ridge_v1","alpha":"2","coefficients":["1.000000000000"],"feature_definition_ids":["00000000-0000-0000-0000-00000000000a"],"feature_means":["2.000000000000"],"feature_scales":["1.000000000000"],"intercept":"4.000000000000","sample_roster_sha256":"0e51b24a61f8e6ff17b4bbc41870418edd6933bb790f0fd7c83e5afb24452eb6","schema":"mra-deterministic-ridge-model-v1","seed":18}'
    fitted = fit_deterministic_ridge(
        tuple(LinearTrainingRow(UUID(int=i), (Decimal(i),), Decimal(2 * i)) for i in (1, 3)),
        feature_definition_ids=(UUID(int=10),), alpha=Decimal(2), seed=18, format_version=1,
    )
    assert fitted.content == content
    assert predict_deterministic_ridge(load_deterministic_ridge_artifact(content), (Decimal(5),)) == Decimal(7)


def test_v1_refuses_to_publish_an_unloadable_fit() -> None:
    with pytest.raises(ValueError, match="scales must be positive"):
        fit_deterministic_ridge(
            tuple(LinearTrainingRow(UUID(int=i), (Decimal(i) * Decimal("1e-14"),), Decimal(i)) for i in (1, 3)),
            feature_definition_ids=(UUID(int=10),), alpha=Decimal(2), seed=18, format_version=1,
        )


def test_nonconstant_subnormal_scale_cannot_be_published_as_a_constant():
    # Its nonzero population std is below binary64's minimum. Unit scaling
    # would silently change the model to a constant prediction of 1.
    with pytest.raises(ValueError, match="nonconstant feature scale underflows"):
        fit_deterministic_ridge(tuple(
            LinearTrainingRow(UUID(int=i+1), (Decimal("5e-324") if i == 5 else Decimal(0),), Decimal(6 if i == 5 else 0))
            for i in range(6)), feature_definition_ids=(UUID(int=10),), alpha=Decimal(2), seed=18)
