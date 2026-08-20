"""Pure cross-sectional rank and boundary-selection correctness kernels."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import Generic, Hashable, Mapping, TypeVar


EntityKey = TypeVar("EntityKey", bound=Hashable)
Numeric = Decimal | int | float
_RANK_DECIMAL_CONTEXT = Context(prec=64, rounding=ROUND_HALF_EVEN)
_SLOT_EXPOSURE_TOLERANCE = Decimal("1e-55")
_MAX_EXACT_SCORE_DECIMAL_PRECISION = 4096


class RankInformationStatus(str, Enum):
    """Whether one cross-section contains observable ranking information."""

    AVAILABLE = "AVAILABLE"
    CONSTANT = "CONSTANT"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class CrossSectionalRankResult(Generic[EntityKey]):
    """Tie-aware percentiles keyed by opaque entity identity."""

    percentiles: Mapping[EntityKey, Decimal]
    status: RankInformationStatus
    observed_count: int
    distinct_count: int

    def __post_init__(self) -> None:
        if self.observed_count != len(self.percentiles):
            raise ValueError("rank observed count must match percentile count")
        if not 0 <= self.distinct_count <= self.observed_count:
            raise ValueError("rank distinct count is outside the observed population")
        if any(not Decimal("0") <= value <= Decimal("1") for value in self.percentiles.values()):
            raise ValueError("rank percentiles must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class BoundarySelection(Generic[EntityKey]):
    """Identity-neutral fractional exposure at one rank boundary."""

    weights: Mapping[EntityKey, Decimal]
    boundary_score: Decimal | None
    strict_count: int
    boundary_group_size: int
    boundary_weight: Decimal

    def __post_init__(self) -> None:
        if self.strict_count < 0 or self.boundary_group_size < 0:
            raise ValueError("boundary counts must be non-negative")
        if not Decimal("0") <= self.boundary_weight <= Decimal("1"):
            raise ValueError("boundary weight must be within [0, 1]")
        if any(not Decimal("0") <= value <= Decimal("1") for value in self.weights.values()):
            raise ValueError("selection weights must be within [0, 1]")
        if (self.boundary_score is None) != (not self.weights):
            raise ValueError("boundary score must exist exactly when weights exist")


@dataclass(frozen=True, slots=True)
class FactorCrossSection(Generic[EntityKey]):
    """One declared Factor cross-section for a fixed-denominator composite."""

    factor_id: str
    values: Mapping[EntityKey, Numeric | None]
    higher_is_better: bool
    weight: Numeric

    def __post_init__(self) -> None:
        if not isinstance(self.factor_id, str) or not self.factor_id.strip() or self.factor_id != self.factor_id.strip():
            raise ValueError("factor identity must be non-empty and trimmed")
        if _finite_numeric(self.weight) <= 0:
            raise ValueError("factor weight must be positive")


@dataclass(frozen=True, slots=True)
class FactorRankDiagnostic:
    """Coverage and information status retained beside a composite score."""

    status: RankInformationStatus
    observed_count: int
    missing_count: int
    distinct_count: int

    def __post_init__(self) -> None:
        if min(self.observed_count, self.missing_count, self.distinct_count) < 0:
            raise ValueError("factor diagnostic counts must be non-negative")
        if self.distinct_count > self.observed_count:
            raise ValueError("factor distinct count exceeds observed count")


@dataclass(frozen=True, slots=True)
class CompositeRankResult(Generic[EntityKey]):
    """Fixed-denominator composite scores plus explicit Factor diagnostics."""

    scores: Mapping[EntityKey, Decimal]
    diagnostics: Mapping[str, FactorRankDiagnostic]

    def __post_init__(self) -> None:
        if any(not Decimal("0") <= value <= Decimal("1") for value in self.scores.values()):
            raise ValueError("composite percentile scores must be within [0, 1]")


def rank_percentiles(
    values: Mapping[EntityKey, Numeric],
    *,
    higher_is_better: bool,
) -> CrossSectionalRankResult[EntityKey]:
    """Return arithmetic-midrank percentiles without identity tie-breaking."""

    normalized = {key: _finite_numeric(value) for key, value in values.items()}
    fractions, status, distinct_count = _rank_fraction_values(
        normalized,
        higher_is_better=higher_is_better,
    )
    observed_count = len(normalized)
    return CrossSectionalRankResult(
        percentiles=MappingProxyType(_fractions_to_decimals(fractions)),
        status=status,
        observed_count=observed_count,
        distinct_count=distinct_count,
    )


def fractional_boundary_weights(
    scores: Mapping[EntityKey, Numeric],
    *,
    slots: int,
    higher_is_better: bool,
) -> BoundarySelection[EntityKey]:
    """Allocate K slots fractionally across every entity tied at the boundary."""

    if isinstance(slots, bool) or not isinstance(slots, int) or slots <= 0:
        raise ValueError("boundary slots must be a positive integer")
    normalized = {key: _finite_numeric(value) for key, value in scores.items()}
    if not normalized:
        return BoundarySelection(
            weights=MappingProxyType({}),
            boundary_score=None,
            strict_count=0,
            boundary_group_size=0,
            boundary_weight=Decimal("0"),
        )
    with localcontext(_RANK_DECIMAL_CONTEXT):
        selected_slots = min(slots, len(normalized))
        ordered_scores = sorted(normalized.values(), reverse=higher_is_better)
        boundary_score = ordered_scores[selected_slots - 1]
        if higher_is_better:
            strict = {key for key, value in normalized.items() if value > boundary_score}
        else:
            strict = {key for key, value in normalized.items() if value < boundary_score}
        boundary = {key for key, value in normalized.items() if value == boundary_score}
        boundary_weight = Decimal(selected_slots - len(strict)) / Decimal(len(boundary))
        weights = {
            key: (
                Decimal("1")
                if key in strict
                else boundary_weight
                if key in boundary
                else Decimal("0")
            )
            for key in normalized
        }
        fractional_slot_weight_total(weights, slots=selected_slots)
    return BoundarySelection(
        weights=MappingProxyType(weights),
        boundary_score=boundary_score,
        strict_count=len(strict),
        boundary_group_size=len(boundary),
        boundary_weight=boundary_weight,
    )


def fractional_slot_weight_total(
    weights: Mapping[EntityKey, Numeric],
    *,
    slots: int,
) -> Decimal:
    """Validate identity-neutral fractional exposure within fixed Decimal error."""

    if isinstance(slots, bool) or not isinstance(slots, int) or slots <= 0:
        raise ValueError("fractional exposure slots must be a positive integer")
    normalized = tuple(_finite_numeric(value) for value in weights.values())
    if any(not Decimal("0") <= value <= Decimal("1") for value in normalized):
        raise ValueError("fractional exposure weights must be within [0, 1]")
    with localcontext(_RANK_DECIMAL_CONTEXT):
        total = sum(normalized, Decimal("0"))
        if abs(total - Decimal(slots)) > _SLOT_EXPOSURE_TOLERANCE:
            raise ValueError(
                "fractional boundary weights do not preserve K-slot exposure"
            )
        return total


def competition_ranks(
    scores: Mapping[EntityKey, Numeric],
    *,
    higher_is_better: bool,
) -> Mapping[EntityKey, int]:
    """Return 1-based competition ranks while preserving equal-score ties."""

    normalized = {key: _finite_numeric(value) for key, value in scores.items()}
    ordered_scores = sorted(set(normalized.values()), reverse=higher_is_better)
    rank_by_score: dict[Decimal, int] = {}
    position = 1
    for score in ordered_scores:
        rank_by_score[score] = position
        position += sum(1 for value in normalized.values() if value == score)
    return MappingProxyType(
        {key: rank_by_score[value] for key, value in normalized.items()}
    )


def composite_percentile_scores(
    factors: tuple[FactorCrossSection[EntityKey], ...],
    *,
    entities: tuple[EntityKey, ...],
) -> CompositeRankResult[EntityKey]:
    """Combine Factors without allowing identity, ties, or missingness to drift."""

    if not factors:
        raise ValueError("composite ranking requires at least one Factor")
    if not entities or len(entities) != len(set(entities)):
        raise ValueError("composite ranking entities must be non-empty and unique")
    factor_ids = tuple(item.factor_id for item in factors)
    if len(factor_ids) != len(set(factor_ids)):
        raise ValueError("composite Factor identities must be unique")
    entity_set = set(entities)
    if any(not set(item.values).issubset(entity_set) for item in factors):
        raise ValueError("composite Factor contains an entity outside its population")

    weights = {
        item.factor_id: Fraction(_finite_numeric(item.weight)) for item in factors
    }
    percentiles: dict[str, Mapping[EntityKey, Fraction]] = {}
    diagnostics: dict[str, FactorRankDiagnostic] = {}
    for factor in factors:
        observed = {
            key: _finite_numeric(value)
            for key, value in factor.values.items()
            if value is not None
        }
        ranked, status, distinct_count = _rank_fraction_values(
            observed,
            higher_is_better=factor.higher_is_better,
        )
        percentiles[factor.factor_id] = ranked
        diagnostics[factor.factor_id] = FactorRankDiagnostic(
            status=status,
            observed_count=len(observed),
            missing_count=len(entities) - len(observed),
            distinct_count=distinct_count,
        )

    denominator = sum(weights.values(), Fraction(0))
    exact_scores = {
        entity: sum(
            (
                weights[factor.factor_id]
                * percentiles[factor.factor_id].get(entity, Fraction(1, 2))
                for factor in factors
            ),
            Fraction(0),
        )
        / denominator
        for entity in entities
    }
    return CompositeRankResult(
        scores=MappingProxyType(_fractions_to_decimals(exact_scores)),
        diagnostics=MappingProxyType(diagnostics),
    )


def _rank_fraction_values(
    values: Mapping[EntityKey, Decimal],
    *,
    higher_is_better: bool,
) -> tuple[dict[EntityKey, Fraction], RankInformationStatus, int]:
    """Build exact arithmetic midranks before any Decimal projection."""

    ordered = sorted(values.items(), key=lambda item: item[1])
    observed_count = len(ordered)
    distinct_count = len(set(values.values()))
    if not ordered:
        return {}, RankInformationStatus.NOT_ESTIMABLE, 0
    if observed_count == 1 or distinct_count == 1:
        return (
            {key: Fraction(1, 2) for key, _value in ordered},
            RankInformationStatus.CONSTANT,
            distinct_count,
        )
    denominator = 2 * (observed_count - 1)
    percentiles: dict[EntityKey, Fraction] = {}
    position = 0
    while position < observed_count:
        end = position + 1
        while end < observed_count and ordered[end][1] == ordered[position][1]:
            end += 1
        ascending = Fraction(position + end - 1, denominator)
        percentile = ascending if higher_is_better else Fraction(1) - ascending
        for index in range(position, end):
            percentiles[ordered[index][0]] = percentile
        position = end
    return percentiles, RankInformationStatus.AVAILABLE, distinct_count


def _fractions_to_decimals(
    values: Mapping[EntityKey, Fraction],
) -> dict[EntityKey, Decimal]:
    """Project exact scores without merging or splitting mathematical ties."""

    precision = _RANK_DECIMAL_CONTEXT.prec
    ordered = sorted(set(values.values()))
    while precision <= _MAX_EXACT_SCORE_DECIMAL_PRECISION:
        with localcontext(Context(prec=precision, rounding=ROUND_HALF_EVEN)):
            projected_by_value = {
                value: Decimal(value.numerator) / Decimal(value.denominator)
                for value in ordered
            }
        projected = [projected_by_value[value] for value in ordered]
        if all(first < second for first, second in zip(projected, projected[1:])):
            return {key: projected_by_value[value] for key, value in values.items()}
        precision *= 2
    raise ValueError("exact rank scores exceed the declared Decimal projection ceiling")


def _finite_numeric(value: Numeric) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float)):
        raise TypeError("cross-sectional rank requires finite numeric values")
    normalized = value if isinstance(value, Decimal) else Decimal(str(value))
    if not normalized.is_finite():
        raise ValueError("cross-sectional rank requires finite numeric values")
    return normalized


__all__ = [
    "BoundarySelection",
    "CompositeRankResult",
    "CrossSectionalRankResult",
    "FactorCrossSection",
    "FactorRankDiagnostic",
    "RankInformationStatus",
    "composite_percentile_scores",
    "competition_ranks",
    "fractional_boundary_weights",
    "fractional_slot_weight_total",
    "rank_percentiles",
]
