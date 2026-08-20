from __future__ import annotations

from decimal import Decimal
from itertools import permutations

import pytest

from market_regime_alpha.research.cross_sectional_ranking import (
    FactorCrossSection,
    RankInformationStatus,
    composite_percentile_scores,
    fractional_boundary_weights,
    rank_percentiles,
)


def test_equal_values_share_midrank_and_constant_is_neutral() -> None:
    tied = rank_percentiles(
        {"a": Decimal("2"), "b": Decimal("2"), "c": Decimal("1")},
        higher_is_better=True,
    )

    assert tied.percentiles == {
        "a": Decimal("0.75"),
        "b": Decimal("0.75"),
        "c": Decimal("0"),
    }
    assert tied.status is RankInformationStatus.AVAILABLE
    assert tied.observed_count == 3
    assert tied.distinct_count == 2

    constant = rank_percentiles(
        {"a": Decimal("7"), "b": Decimal("7")},
        higher_is_better=True,
    )

    assert constant.percentiles == {"a": Decimal("0.5"), "b": Decimal("0.5")}
    assert constant.status is RankInformationStatus.CONSTANT


def test_permutation_and_symbol_renaming_are_equivariant() -> None:
    items = (
        ("000001.SZ", Decimal("3")),
        ("600000.SH", Decimal("1")),
        ("688001.SH", Decimal("1")),
    )
    expected = rank_percentiles(dict(items), higher_is_better=True)

    for permuted in permutations(items):
        assert (
            rank_percentiles(dict(permuted), higher_is_better=True).percentiles
            == expected.percentiles
        )

    renamed = rank_percentiles(
        {"x": Decimal("3"), "y": Decimal("1"), "z": Decimal("1")},
        higher_is_better=True,
    )
    assert expected.percentiles["000001.SZ"] == renamed.percentiles["x"]
    assert expected.percentiles["600000.SH"] == renamed.percentiles["y"]
    assert expected.percentiles["688001.SH"] == renamed.percentiles["z"]


def test_fractional_boundary_never_uses_entity_identity() -> None:
    selected = fractional_boundary_weights(
        {"a": Decimal("1"), "b": Decimal("0"), "c": Decimal("0")},
        slots=2,
        higher_is_better=True,
    )

    assert selected.weights == {
        "a": Decimal("1"),
        "b": Decimal("0.5"),
        "c": Decimal("0.5"),
    }
    assert selected.strict_count == 1
    assert selected.boundary_score == Decimal("0")
    assert selected.boundary_group_size == 2
    assert selected.boundary_weight == Decimal("0.5")

    renamed = fractional_boundary_weights(
        {"z": Decimal("1"), "x": Decimal("0"), "y": Decimal("0")},
        slots=2,
        higher_is_better=True,
    )
    assert renamed.weights == {
        "z": Decimal("1"),
        "x": Decimal("0.5"),
        "y": Decimal("0.5"),
    }


@pytest.mark.parametrize(
    "values",
    (
        {"a": Decimal("NaN")},
        {"a": Decimal("Infinity")},
        {"a": True},
    ),
)
def test_ranking_rejects_non_finite_and_boolean_values(values: object) -> None:
    with pytest.raises((TypeError, ValueError), match="finite numeric"):
        rank_percentiles(values, higher_is_better=True)  # type: ignore[arg-type]


def test_constant_factor_is_neutral_for_composite_order_and_boundary() -> None:
    price = FactorCrossSection(
        factor_id="price",
        values={"a": Decimal("3"), "b": Decimal("2"), "c": Decimal("1")},
        higher_is_better=True,
        weight=Decimal("1"),
    )
    baseline = composite_percentile_scores((price,), entities=("a", "b", "c"))
    augmented = composite_percentile_scores(
        (
            price,
            FactorCrossSection(
                factor_id="theme",
                values={"a": Decimal("7"), "b": Decimal("7"), "c": Decimal("7")},
                higher_is_better=True,
                weight=Decimal("1"),
            ),
        ),
        entities=("a", "b", "c"),
    )

    assert augmented.diagnostics["theme"].status is RankInformationStatus.CONSTANT
    assert fractional_boundary_weights(
        baseline.scores,
        slots=2,
        higher_is_better=True,
    ).weights == fractional_boundary_weights(
        augmented.scores,
        slots=2,
        higher_is_better=True,
    ).weights


def test_missing_and_unobserved_factors_are_neutral_but_diagnosed() -> None:
    result = composite_percentile_scores(
        (
            FactorCrossSection(
                factor_id="partially_missing",
                values={"a": Decimal("3"), "b": None, "c": Decimal("1")},
                higher_is_better=True,
                weight=Decimal("1"),
            ),
            FactorCrossSection(
                factor_id="unobserved",
                values={"a": None, "b": None, "c": None},
                higher_is_better=True,
                weight=Decimal("1"),
            ),
        ),
        entities=("a", "b", "c"),
    )

    assert result.scores == {
        "a": Decimal("0.75"),
        "b": Decimal("0.5"),
        "c": Decimal("0.25"),
    }
    assert result.diagnostics["partially_missing"].missing_count == 1
    assert result.diagnostics["unobserved"].status is RankInformationStatus.NOT_ESTIMABLE
    assert result.diagnostics["unobserved"].missing_count == 3


def test_positive_affine_transform_preserves_percentiles() -> None:
    original = rank_percentiles(
        {"a": Decimal("1"), "b": Decimal("2"), "c": Decimal("2")},
        higher_is_better=True,
    )
    transformed = rank_percentiles(
        {"a": Decimal("12"), "b": Decimal("14"), "c": Decimal("14")},
        higher_is_better=True,
    )

    assert transformed.percentiles == original.percentiles
