from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

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
