"""Exact Candidate V1 ranking calculations."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Context, Decimal, MAX_EMAX, MIN_EMIN, ROUND_HALF_EVEN
from fractions import Fraction
from typing import Hashable, TypeVar, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from market_regime_alpha.selection.domain.candidate_inputs import (
    CandidateCellStatus,
    CandidateDatasetPopulation,
    CandidatePopulationCell,
    CandidatePopulationRow,
)
from market_regime_alpha.selection.domain.candidate_policy import (
    CandidateFeatureValueType,
    CandidatePolicy,
    CandidatePolicyComponent,
    DesirabilityDirection,
)
from market_regime_alpha.selection.domain.candidate_results import (
    CandidateBuildResult,
    CandidateComponentDiagnostic,
    CandidateDisposition,
    CandidateRankingPlan,
    CandidateRankingStatus,
    CandidateRecord,
    CandidateScoreComponentRecord,
    CandidateSetResult,
    candidate_result_content_sha256,
)
from market_regime_alpha.shared.identity import ContentHash


_ProjectionKey = TypeVar("_ProjectionKey", bound=Hashable)
_DEFAULT_PROJECTION_PRECISION = 64
_MAXIMUM_PROJECTION_PRECISION = 4096
_ALLOWED_PROJECTION_PRECISIONS = frozenset(
    (64, 128, 256, 512, 1024, 2048, 4096)
)
_POSTGRES_NUMERIC_MAX_INTEGER_DIGITS = 131_072
_POSTGRES_NUMERIC_MAX_FRACTIONAL_DIGITS = 16_383


def normalize_declared_weights(
    components: tuple[CandidatePolicyComponent, ...],
) -> dict[UUID, Fraction]:
    """Normalize canonical Decimal weights without binary floating point."""

    exact = {
        item.candidate_policy_component_id: Fraction(item.declared_weight)
        for item in components
    }
    total = sum(exact.values(), start=Fraction())
    return {identity: value / total for identity, value in exact.items()}


def arithmetic_midrank_percentiles(
    observations: Mapping[UUID, Decimal | int | Fraction],
    *,
    direction: DesirabilityDirection,
) -> dict[UUID, Fraction]:
    """Return exact tie-aware percentiles without an identity tie-break."""

    if not isinstance(direction, DesirabilityDirection):
        raise TypeError("direction must be DesirabilityDirection")
    exact: dict[UUID, Fraction] = {}
    for identity, value in observations.items():
        if isinstance(value, bool) or not isinstance(value, (Decimal, int, Fraction)):
            raise TypeError("Candidate observations must be exact numeric values")
        exact[identity] = Fraction(value)
    count = len(exact)
    if count == 0:
        return {}
    if len(set(exact.values())) == 1:
        return {identity: Fraction(1, 2) for identity in exact}
    oriented = {
        identity: value
        if direction is DesirabilityDirection.HIGHER_IS_BETTER
        else -value
        for identity, value in exact.items()
    }
    result: dict[UUID, Fraction] = {}
    for identity, value in oriented.items():
        worse_count = sum(other < value for other in oriented.values())
        tied_count = sum(other == value for other in oriented.values())
        result[identity] = (
            Fraction(worse_count) + Fraction(tied_count - 1, 2)
        ) / Fraction(count - 1)
    return result


def project_exact_values(
    values: Mapping[_ProjectionKey, Fraction],
    *,
    minimum_precision: int = _DEFAULT_PROJECTION_PRECISION,
    maximum_precision: int = _MAXIMUM_PROJECTION_PRECISION,
) -> tuple[int, dict[_ProjectionKey, Decimal]]:
    """Project exact values while preserving every equality/order class."""

    if (
        isinstance(minimum_precision, bool)
        or isinstance(maximum_precision, bool)
        or minimum_precision not in _ALLOWED_PROJECTION_PRECISIONS
        or maximum_precision not in _ALLOWED_PROJECTION_PRECISIONS
        or maximum_precision < minimum_precision
    ):
        raise ValueError("invalid Candidate Decimal projection precision bounds")
    if any(not isinstance(item, Fraction) for item in values.values()):
        raise TypeError("Candidate projection inputs must be Fractions")
    precision = minimum_precision
    while True:
        projected = {
            key: _project_fraction(value, precision=precision)
            for key, value in values.items()
        }
        exact_order = sorted(set(values.values()))
        projected_order = [
            _project_fraction(value, precision=precision) for value in exact_order
        ]
        if all(
            left < right
            for left, right in zip(projected_order, projected_order[1:], strict=False)
        ):
            return precision, projected
        if precision == maximum_precision:
            raise ValueError(
                "Candidate Decimal projection cannot preserve exact order "
                f"at closed precision cap {maximum_precision}"
            )
        precision = min(precision * 2, maximum_precision)


def build_candidate_set(
    *,
    policy: CandidatePolicy,
    dataset: CandidateDatasetPopulation,
    minimum_projection_precision: int = _DEFAULT_PROJECTION_PRECISION,
    maximum_projection_precision: int = _MAXIMUM_PROJECTION_PRECISION,
) -> CandidateRankingPlan:
    """Build a complete immutable Candidate ranking plan from one Dataset."""

    if not isinstance(policy, CandidatePolicy):
        raise TypeError("policy must be CandidatePolicy")
    if not isinstance(dataset, CandidateDatasetPopulation):
        raise TypeError("dataset must be CandidateDatasetPopulation")
    components = policy.components
    components_by_feature = {
        item.feature_definition_id: item for item in components
    }
    row_cells: dict[UUID, dict[UUID, CandidatePopulationCell]] = {}
    for row in dataset.rows:
        cells = {item.feature_definition_id: item for item in row.cells}
        absent = set(components_by_feature).difference(cells)
        if absent:
            raise ValueError(
                "Candidate Dataset row is missing required Feature cells: "
                + ",".join(sorted((str(item) for item in absent)))
            )
        for feature_id, component in components_by_feature.items():
            _validate_cell_value_type(cells[feature_id], component)
        row_cells[row.instrument_id] = cells

    rankable_rows = tuple(
        row
        for row in dataset.rows
        if all(
            row_cells[row.instrument_id][component.feature_definition_id].status
            is CandidateCellStatus.AVAILABLE
            for component in components
        )
    )
    rankable_ids = {item.instrument_id for item in rankable_rows}
    exact_weights = normalize_declared_weights(components)
    exact_percentiles: dict[tuple[UUID, UUID], Fraction] = {}
    diagnostics: list[CandidateComponentDiagnostic] = []
    for component in components:
        observations = {
            row.instrument_id: _exact_cell_value(
                row_cells[row.instrument_id][component.feature_definition_id]
            )
            for row in rankable_rows
        }
        component_percentiles = arithmetic_midrank_percentiles(
            observations,
            direction=component.direction,
        )
        exact_percentiles.update(
            {
                (instrument_id, component.candidate_policy_component_id): value
                for instrument_id, value in component_percentiles.items()
            }
        )
        all_cells = [
            row_cells[row.instrument_id][component.feature_definition_id]
            for row in dataset.rows
        ]
        raw_available_count = sum(
            item.status is CandidateCellStatus.AVAILABLE for item in all_cells
        )
        distinct_count = len(set(observations.values()))
        component_status = _component_status(
            rankable_count=len(rankable_rows),
            distinct_count=distinct_count,
        )
        diagnostics.append(
            CandidateComponentDiagnostic(
                candidate_policy_component_id=(
                    component.candidate_policy_component_id
                ),
                feature_definition_id=component.feature_definition_id,
                observed_count=len(rankable_rows),
                distinct_count=distinct_count,
                raw_available_count=raw_available_count,
                available_but_not_observed_count=(
                    raw_available_count - len(rankable_rows)
                ),
                missing_count=_status_count(all_cells, CandidateCellStatus.MISSING),
                unknown_count=_status_count(all_cells, CandidateCellStatus.UNKNOWN),
                stale_count=_status_count(all_cells, CandidateCellStatus.STALE),
                conflict_count=_status_count(all_cells, CandidateCellStatus.CONFLICT),
                rank_information_status=component_status,
            )
        )

    exact_contributions: dict[tuple[UUID, UUID], Fraction] = {}
    exact_scores: dict[UUID, Fraction] = {}
    for row in rankable_rows:
        score = Fraction()
        for component in components:
            key = (row.instrument_id, component.candidate_policy_component_id)
            contribution = (
                exact_weights[component.candidate_policy_component_id]
                * exact_percentiles[key]
            )
            exact_contributions[key] = contribution
            score += contribution
        exact_scores[row.instrument_id] = score

    exact_ranks = {
        instrument_id: 1
        + sum(other_score > score for other_score in exact_scores.values())
        for instrument_id, score in exact_scores.items()
    }
    boundary_score_exact = _boundary_score(
        exact_scores,
        requested_top_k=policy.requested_top_k,
    )
    selected_ids = {
        instrument_id
        for instrument_id, score in exact_scores.items()
        if boundary_score_exact is not None and score >= boundary_score_exact
    }
    strictly_above_boundary_count = (
        0
        if boundary_score_exact is None
        else sum(score > boundary_score_exact for score in exact_scores.values())
    )
    boundary_group_count = (
        0
        if boundary_score_exact is None
        else sum(score == boundary_score_exact for score in exact_scores.values())
    )

    ranking_projection_inputs = {
        ("score", str(instrument_id), ""): exact_score
        for instrument_id, exact_score in exact_scores.items()
    }
    if boundary_score_exact is not None:
        ranking_projection_inputs[("boundary", "", "")] = boundary_score_exact
    projection_precision, projected = project_exact_values(
        ranking_projection_inputs,
        minimum_precision=minimum_projection_precision,
        maximum_precision=maximum_projection_precision,
    )
    if dataset.rows:
        for component in components:
            component_id = component.candidate_policy_component_id
            projected[("weight", str(component_id), "")] = _project_fraction(
                exact_weights[component_id],
                precision=projection_precision,
            )
    for (instrument_id, component_id), percentile in exact_percentiles.items():
        key_suffix = (str(instrument_id), str(component_id))
        projected[("percentile", *key_suffix)] = _project_fraction(
            percentile,
            precision=projection_precision,
        )
        projected[("contribution", *key_suffix)] = _project_fraction(
            exact_contributions[(instrument_id, component_id)],
            precision=projection_precision,
        )

    candidate_set_id = uuid5(
        NAMESPACE_URL,
        "market-regime-alpha:candidate-set:v1:"
        f"{policy.candidate_policy_id}:{dataset.dataset_id}",
    )
    candidate_records: list[CandidateRecord] = []
    score_records: list[CandidateScoreComponentRecord] = []
    for row in sorted(dataset.rows, key=lambda item: str(item.instrument_id)):
        candidate_id = uuid5(
            NAMESPACE_URL,
            f"market-regime-alpha:candidate:v1:{candidate_set_id}:{row.instrument_id}",
        )
        projected_score: Decimal | None
        rank: int | None
        if row.instrument_id not in rankable_ids:
            disposition = CandidateDisposition.UNRANKABLE
            projected_score = None
            rank = None
            disposition_reason = (
                "STRICT_COMPLETE_CASE_REQUIRED_FEATURE_UNAVAILABLE"
            )
        elif row.instrument_id in selected_ids:
            disposition = CandidateDisposition.SELECTED
            projected_score = projected[("score", str(row.instrument_id), "")]
            rank = exact_ranks[row.instrument_id]
            disposition_reason = _selected_reason(
                exact_scores[row.instrument_id],
                boundary_score_exact=boundary_score_exact,
                all_rankable_selected=(
                    len(selected_ids) == len(rankable_rows)
                    and policy.requested_top_k >= len(rankable_rows)
                ),
                boundary_tie_expanded=(
                    len(selected_ids) > policy.requested_top_k
                ),
            )
        else:
            disposition = CandidateDisposition.RANKED_NOT_SELECTED
            projected_score = projected[("score", str(row.instrument_id), "")]
            rank = exact_ranks[row.instrument_id]
            disposition_reason = "BELOW_BOUNDARY"
        candidate_records.append(
            CandidateRecord(
                candidate_id=candidate_id,
                candidate_set_id=candidate_set_id,
                candidate_policy_id=policy.candidate_policy_id,
                dataset_id=dataset.dataset_id,
                instrument_id=row.instrument_id,
                dataset_population_source_id=row.population_source_id,
                dataset_source_role="POPULATION",
                disposition=disposition,
                composite_score=projected_score,
                competition_rank=rank,
                reason_code=disposition_reason,
            )
        )
        for component in components:
            component_id = component.candidate_policy_component_id
            cell = row_cells[row.instrument_id][component.feature_definition_id]
            score_records.append(
                CandidateScoreComponentRecord(
                    candidate_score_component_id=uuid5(
                        NAMESPACE_URL,
                        "market-regime-alpha:candidate-score-component:v1:"
                        f"{candidate_id}:{component_id}",
                    ),
                    candidate_id=candidate_id,
                    candidate_set_id=candidate_set_id,
                    candidate_policy_id=policy.candidate_policy_id,
                    candidate_policy_component_id=component_id,
                    feature_definition_id=component.feature_definition_id,
                    feature_content_sha256=cast(
                        ContentHash,
                        component.feature_content_sha256,
                    ),
                    feature_value_type=component.feature_value_type,
                    dataset_id=dataset.dataset_id,
                    instrument_id=row.instrument_id,
                    raw_status=cell.status,
                    raw_decimal_value=(
                        cell.value
                        if component.feature_value_type
                        is CandidateFeatureValueType.DECIMAL
                        and isinstance(cell.value, Decimal)
                        else None
                    ),
                    raw_integer_value=(
                        cell.value
                        if component.feature_value_type
                        is CandidateFeatureValueType.INTEGER
                        and isinstance(cell.value, int)
                        and not isinstance(cell.value, bool)
                        else None
                    ),
                    raw_reason_code=cell.reason_code,
                    cell_source_lineage_hash=cast(
                        ContentHash,
                        cell.cell_source_lineage_hash,
                    ),
                    normalized_weight=projected[
                        ("weight", str(component_id), "")
                    ],
                    percentile=(
                        projected[("percentile", str(row.instrument_id), str(component_id))]
                        if row.instrument_id in rankable_ids
                        else None
                    ),
                    contribution=(
                        projected[("contribution", str(row.instrument_id), str(component_id))]
                        if row.instrument_id in rankable_ids
                        else None
                    ),
                    candidate_disposition=disposition,
                )
            )

    ranking_status = _candidate_set_status(diagnostics)
    selected_count = len(selected_ids)
    rankable_count = len(rankable_rows)
    boundary_rank = (
        None
        if boundary_score_exact is None
        else 1
        + sum(score > boundary_score_exact for score in exact_scores.values())
    )
    boundary_tie_expanded = selected_count > policy.requested_top_k
    result_hash = candidate_result_content_sha256(
        policy=policy,
        candidate_set_id=candidate_set_id,
        dataset_id=dataset.dataset_id,
        dataset_content_sha256=cast(
            ContentHash,
            dataset.dataset_content_sha256,
        ),
        dependency_sha256=cast(ContentHash, dataset.dependency_sha256),
        projection_precision=projection_precision,
        candidates=candidate_records,
        score_components=score_records,
        component_diagnostics=diagnostics,
    )
    candidate_set = CandidateSetResult(
        candidate_set_id=candidate_set_id,
        candidate_policy_id=policy.candidate_policy_id,
        candidate_policy_content_sha256=policy.content_sha256,
        dataset_id=dataset.dataset_id,
        dataset_content_sha256=cast(
            ContentHash,
            dataset.dataset_content_sha256,
        ),
        universe_revision_id=dataset.universe_revision_id,
        eligibility_policy_id=dataset.eligibility_policy_id,
        decision_time=dataset.decision_time,
        decimal_projection_precision=projection_precision,
        requested_top_k=policy.requested_top_k,
        component_count=len(components),
        population_count=len(dataset.rows),
        rankable_count=rankable_count,
        unrankable_count=len(dataset.rows) - rankable_count,
        selected_count=selected_count,
        ranked_not_selected_count=rankable_count - selected_count,
        score_component_count=len(score_records),
        available_component_count=sum(
            item.ranking_status is CandidateRankingStatus.AVAILABLE
            for item in diagnostics
        ),
        constant_component_count=sum(
            item.ranking_status is CandidateRankingStatus.CONSTANT
            for item in diagnostics
        ),
        not_estimable_component_count=sum(
            item.ranking_status is CandidateRankingStatus.NOT_ESTIMABLE
            for item in diagnostics
        ),
        ranking_status=ranking_status,
        composite_distinct_count=len(set(exact_scores.values())),
        boundary_score=(
            None if boundary_score_exact is None else projected[("boundary", "", "")]
        ),
        boundary_rank=boundary_rank,
        strictly_above_boundary_count=strictly_above_boundary_count,
        boundary_group_count=boundary_group_count,
        selected_overflow_count=max(0, selected_count - policy.requested_top_k),
        boundary_has_tie=boundary_group_count > 1,
        boundary_tie_expanded=boundary_tie_expanded,
        dependency_sha256=cast(ContentHash, dataset.dependency_sha256),
        content_sha256=result_hash,
    )
    return CandidateBuildResult(
        candidate_set=candidate_set,
        candidates=tuple(candidate_records),
        score_components=tuple(score_records),
        component_diagnostics=tuple(diagnostics),
    )


def _validate_cell_value_type(
    cell: CandidatePopulationCell,
    component: CandidatePolicyComponent,
) -> None:
    if cell.status is not CandidateCellStatus.AVAILABLE:
        return
    if component.feature_value_type is CandidateFeatureValueType.DECIMAL:
        if not isinstance(cell.value, Decimal):
            raise TypeError("DECIMAL Candidate Features require Decimal values")
        return
    if isinstance(cell.value, bool) or not isinstance(cell.value, int):
        raise TypeError("INTEGER Candidate Features require integer values")


def _exact_cell_value(cell: CandidatePopulationCell) -> Fraction:
    if cell.status is not CandidateCellStatus.AVAILABLE or cell.value is None:
        raise ValueError("only AVAILABLE Candidate cells have exact values")
    return Fraction(cell.value)


def _component_status(
    *,
    rankable_count: int,
    distinct_count: int,
) -> CandidateRankingStatus:
    if rankable_count == 0:
        return CandidateRankingStatus.NOT_ESTIMABLE
    if distinct_count == 1:
        return CandidateRankingStatus.CONSTANT
    return CandidateRankingStatus.AVAILABLE


def _candidate_set_status(
    diagnostics: list[CandidateComponentDiagnostic],
) -> CandidateRankingStatus:
    if all(
        item.rank_information_status is CandidateRankingStatus.NOT_ESTIMABLE
        for item in diagnostics
    ):
        return CandidateRankingStatus.NOT_ESTIMABLE
    if any(
        item.rank_information_status is CandidateRankingStatus.AVAILABLE
        for item in diagnostics
    ):
        return CandidateRankingStatus.AVAILABLE
    return CandidateRankingStatus.CONSTANT


def _status_count(
    cells: list[CandidatePopulationCell],
    status: CandidateCellStatus,
) -> int:
    return sum(item.status is status for item in cells)


def _boundary_score(
    exact_scores: Mapping[UUID, Fraction],
    *,
    requested_top_k: int,
) -> Fraction | None:
    if not exact_scores:
        return None
    scores_descending = sorted(exact_scores.values(), reverse=True)
    return scores_descending[min(requested_top_k, len(scores_descending)) - 1]


def _selected_reason(
    score: Fraction,
    *,
    boundary_score_exact: Fraction | None,
    all_rankable_selected: bool,
    boundary_tie_expanded: bool,
) -> str:
    if boundary_score_exact is None:
        raise ValueError("selected Candidate requires a boundary")
    if all_rankable_selected:
        return "ALL_RANKABLE_SELECTED"
    if score > boundary_score_exact:
        return "ABOVE_BOUNDARY"
    if boundary_tie_expanded:
        return "BOUNDARY_TIE_INCLUDED"
    return "AT_BOUNDARY"


def _project_fraction(value: Fraction, *, precision: int) -> Decimal:
    context = Context(
        prec=precision,
        rounding=ROUND_HALF_EVEN,
        Emin=MIN_EMIN,
        Emax=MAX_EMAX,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[],
    )
    projected = context.divide(
        Decimal(value.numerator),
        Decimal(value.denominator),
    )
    _, digits, exponent = projected.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError("Candidate Decimal projection must be finite")
    integer_digits = max(len(digits) + exponent, 0)
    fractional_digits = max(-exponent, 0)
    if (
        integer_digits > _POSTGRES_NUMERIC_MAX_INTEGER_DIGITS
        or fractional_digits > _POSTGRES_NUMERIC_MAX_FRACTIONAL_DIGITS
    ):
        raise ValueError(
            "Candidate Decimal projection exceeds PostgreSQL numeric physical limits"
        )
    return projected


__all__ = [
    "CandidateBuildResult",
    "CandidateCellStatus",
    "CandidateDatasetPopulation",
    "CandidateDisposition",
    "CandidatePopulationCell",
    "CandidatePopulationRow",
    "CandidateRankingPlan",
    "CandidateRankingStatus",
    "arithmetic_midrank_percentiles",
    "build_candidate_set",
    "normalize_declared_weights",
    "project_exact_values",
]
