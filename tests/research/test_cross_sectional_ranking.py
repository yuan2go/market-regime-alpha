from __future__ import annotations

from decimal import Decimal, localcontext
from itertools import permutations

import pytest

from market_regime_alpha.research.cross_sectional_ranking import (
    FactorCrossSection,
    RankInformationStatus,
    composite_percentile_scores,
    competition_ranks,
    fractional_boundary_weights,
    fractional_slot_weight_total,
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


def test_large_fractional_boundary_is_process_context_invariant() -> None:
    scores = {f"entity-{index:03d}": Decimal("1") for index in range(300)}

    with localcontext() as context:
        context.prec = 8
        low_precision = fractional_boundary_weights(
            scores,
            slots=10,
            higher_is_better=True,
        )
    with localcontext() as context:
        context.prec = 50
        high_precision = fractional_boundary_weights(
            dict(reversed(tuple(scores.items()))),
            slots=10,
            higher_is_better=True,
        )

    assert low_precision == high_precision
    assert low_precision.boundary_group_size == 300
    assert len(set(low_precision.weights.values())) == 1
    total = fractional_slot_weight_total(low_precision.weights, slots=10)
    assert abs(total - Decimal("10")) <= Decimal("1e-55")


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


def test_exactly_equal_rational_composites_do_not_split_at_decimal_precision() -> None:
    entities = tuple(f"entity-{index:02d}" for index in range(23))
    first_values = {
        entities[0]: Decimal("0"),
        entities[1]: Decimal("1"),
        entities[2]: Decimal("2"),
    }
    occupied = {Decimal("1"), Decimal("12")}
    available = iter(
        Decimal(index) for index in range(23) if Decimal(index) not in occupied
    )
    second_values = {
        entity: (
            Decimal("12")
            if entity == entities[0]
            else Decimal("1")
            if entity == entities[1]
            else next(available)
        )
        for entity in entities
    }

    result = composite_percentile_scores(
        (
            FactorCrossSection("three_observations", first_values, True, 1),
            FactorCrossSection("twenty_three_observations", second_values, True, 1),
        ),
        entities=entities,
    )

    # 0/2 + 12/22 and 1/2 + 1/22 are both exactly 6/11.  Finite
    # intermediate Decimal rounding must not manufacture a winner.
    assert result.scores[entities[0]] == result.scores[entities[1]]


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


def test_expanding_a_symmetric_tie_group_preserves_its_midrank() -> None:
    original = rank_percentiles(
        {
            "low": Decimal("1"),
            "tie-a": Decimal("2"),
            "tie-b": Decimal("2"),
            "high": Decimal("3"),
        },
        higher_is_better=True,
    )
    expanded = rank_percentiles(
        {
            "low": Decimal("1"),
            "tie-a": Decimal("2"),
            "tie-b": Decimal("2"),
            "tie-c": Decimal("2"),
            "tie-d": Decimal("2"),
            "high": Decimal("3"),
        },
        higher_is_better=True,
    )

    assert original.percentiles["tie-a"] == Decimal("0.5")
    expanded_tie_percentiles = {
        expanded.percentiles[key]
        for key in ("tie-a", "tie-b", "tie-c", "tie-d")
    }
    assert len(expanded_tie_percentiles) == 1
    assert expanded.percentiles["tie-a"] == Decimal("0.5")


def test_factor_order_permutation_is_invariant() -> None:
    factors = (
        FactorCrossSection(
            "price",
            {"a": Decimal("3"), "b": Decimal("1"), "c": Decimal("2")},
            True,
            2,
        ),
        FactorCrossSection(
            "volume",
            {"a": Decimal("1"), "b": Decimal("2"), "c": Decimal("3")},
            True,
            1,
        ),
    )

    expected = composite_percentile_scores(factors, entities=("a", "b", "c"))
    permuted = composite_percentile_scores(
        tuple(reversed(factors)),
        entities=("a", "b", "c"),
    )

    assert permuted.scores == expected.scores
    assert permuted.diagnostics == expected.diagnostics


def test_competition_ranks_preserve_ties_without_identity_winners() -> None:
    ranks = competition_ranks(
        {"a": Decimal("1"), "b": Decimal("0"), "c": Decimal("0")},
        higher_is_better=True,
    )
    renamed = competition_ranks(
        {"z": Decimal("1"), "x": Decimal("0"), "y": Decimal("0")},
        higher_is_better=True,
    )

    assert ranks == {"a": 1, "b": 2, "c": 2}
    assert renamed == {"z": 1, "x": 2, "y": 2}
