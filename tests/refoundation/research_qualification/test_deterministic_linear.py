from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.application.deterministic_linear import (
    LinearTrainingRow,
    fit_deterministic_ridge,
    predict_deterministic_ridge,
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
    assert predict_deterministic_ridge(first, (Decimal("4"), Decimal("3"))).is_finite()


def test_deterministic_ridge_rejects_non_finite_or_incomplete_matrix() -> None:
    with pytest.raises(ValueError, match="at least two"):
        fit_deterministic_ridge(
            (LinearTrainingRow(UUID(int=1), (Decimal("1"),), Decimal("1")),),
            feature_definition_ids=(UUID(int=10),),
            alpha=Decimal("0.1"),
            seed=1,
        )

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
