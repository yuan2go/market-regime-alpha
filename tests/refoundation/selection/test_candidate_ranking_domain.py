"""Candidate V1 ranks complete cross-sections with exact, identity-neutral math."""

from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
from uuid import UUID

import pytest

from market_regime_alpha.selection.domain.candidate_policy import (
    CandidateFeatureValueType,
    CandidatePolicy,
    CandidatePolicyComponent,
    DesirabilityDirection,
)
from market_regime_alpha.selection.domain.candidate_ranking import (
    CandidateCellStatus,
    CandidateDatasetPopulation,
    CandidateDisposition,
    CandidateRankingStatus,
    CandidatePopulationCell,
    CandidatePopulationRow,
    arithmetic_midrank_percentiles,
    build_candidate_set,
    project_exact_values,
)
from market_regime_alpha.selection.domain.candidate_inputs import (
    CandidateArtifactBinding,
)
from market_regime_alpha.shared.time import DecisionTime


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _component(
    ordinal: int,
    *,
    weight: str = "1",
    direction: DesirabilityDirection = DesirabilityDirection.HIGHER_IS_BETTER,
) -> CandidatePolicyComponent:
    return CandidatePolicyComponent(
        candidate_policy_component_id=_uuid(100 + ordinal),
        candidate_policy_id=_uuid(10),
        component_code=f"feature_{ordinal}",
        ordinal=ordinal,
        feature_definition_id=_uuid(200 + ordinal),
        feature_content_sha256=f"{ordinal:064x}",
        feature_value_type=CandidateFeatureValueType.DECIMAL,
        direction=direction,
        declared_weight=Decimal(weight),
    )


def _policy(
    *components: CandidatePolicyComponent,
    requested_top_k: int = 1,
) -> CandidatePolicy:
    return CandidatePolicy(
        candidate_policy_id=_uuid(10),
        policy_code="candidate_v1",
        version=1,
        code_artifact=CandidateArtifactBinding(
            artifact_id=_uuid(301),
            content_sha256="a" * 64,
            size_bytes=1,
        ),
        config_artifact=CandidateArtifactBinding(
            artifact_id=_uuid(302),
            content_sha256="b" * 64,
            size_bytes=1,
        ),
        requested_top_k=requested_top_k,
        components=components,
    )


def _cell(
    feature: int,
    value: str | None,
    *,
    status: CandidateCellStatus = CandidateCellStatus.AVAILABLE,
) -> CandidatePopulationCell:
    return CandidatePopulationCell(
        feature_definition_id=_uuid(200 + feature),
        status=status,
        value=None if value is None else Decimal(value),
        reason_code="OBSERVED" if status is CandidateCellStatus.AVAILABLE else status.value,
        cell_source_lineage_hash=f"{feature:064x}",
    )


def _row(instrument: int, *cells: CandidatePopulationCell) -> CandidatePopulationRow:
    return CandidatePopulationRow(
        instrument_id=_uuid(1_000 + instrument),
        dataset_population_source_id=_uuid(2_000 + instrument),
        cells=cells,
    )


def _population(*rows: CandidatePopulationRow) -> CandidateDatasetPopulation:
    return CandidateDatasetPopulation(
        dataset_id=_uuid(20),
        dataset_content_sha256="f" * 64,
        decision_time=DecisionTime(datetime(2026, 8, 30, tzinfo=timezone.utc)),
        universe_revision_id=_uuid(21),
        eligibility_policy_id=_uuid(22),
        rows=rows,
    )


def test_arithmetic_midrank_is_tie_aware_and_directional() -> None:
    observations = {
        _uuid(1): Decimal("10"),
        _uuid(2): Decimal("20"),
        _uuid(3): Decimal("20"),
        _uuid(4): Decimal("40"),
    }

    assert arithmetic_midrank_percentiles(
        observations,
        direction=DesirabilityDirection.HIGHER_IS_BETTER,
    ) == {
        _uuid(1): Fraction(0),
        _uuid(2): Fraction(1, 2),
        _uuid(3): Fraction(1, 2),
        _uuid(4): Fraction(1),
    }
    assert arithmetic_midrank_percentiles(
        observations,
        direction=DesirabilityDirection.LOWER_IS_BETTER,
    ) == {
        _uuid(1): Fraction(1),
        _uuid(2): Fraction(1, 2),
        _uuid(3): Fraction(1, 2),
        _uuid(4): Fraction(0),
    }


def test_strict_complete_case_keeps_every_row_and_never_partially_scores() -> None:
    result = build_candidate_set(
        policy=_policy(_component(1), _component(2)),
        dataset=_population(
            _row(1, _cell(1, "1"), _cell(2, "10")),
            _row(
                2,
                _cell(1, "2"),
                _cell(2, None, status=CandidateCellStatus.MISSING),
            ),
            _row(3, _cell(1, "3"), _cell(2, "30")),
        ),
    )

    assert (
        result.candidate_set.population_count,
        result.candidate_set.rankable_count,
        result.candidate_set.unrankable_count,
        result.candidate_set.selected_count,
        result.candidate_set.ranked_not_selected_count,
        result.candidate_set.score_component_count,
    ) == (3, 2, 1, 1, 1, 6)
    candidates = {item.instrument_id: item for item in result.candidates}
    assert candidates[_uuid(1_002)].disposition is CandidateDisposition.UNRANKABLE
    assert candidates[_uuid(1_002)].composite_score is None
    assert candidates[_uuid(1_002)].competition_rank is None
    incomplete_scores = [
        item
        for item in result.score_components
        if item.instrument_id == _uuid(1_002)
    ]
    assert len(incomplete_scores) == 2
    assert all(item.normalized_weight is not None for item in incomplete_scores)
    assert all(item.percentile is None for item in incomplete_scores)
    assert all(item.contribution is None for item in incomplete_scores)
    diagnostics = {
        item.feature_definition_id: item for item in result.component_diagnostics
    }
    assert (
        diagnostics[_uuid(201)].raw_available_count,
        diagnostics[_uuid(201)].observed_count,
        diagnostics[_uuid(201)].distinct_count,
    ) == (3, 2, 2)
    assert diagnostics[_uuid(202)].missing_count == 1


def test_singleton_uses_constant_half_without_claiming_discrimination() -> None:
    result = build_candidate_set(
        policy=_policy(_component(1), requested_top_k=1),
        dataset=_population(_row(1, _cell(1, "7"))),
    )

    assert result.candidate_set.ranking_status is CandidateRankingStatus.CONSTANT
    assert result.candidate_set.composite_distinct_count == 1
    assert result.candidate_set.boundary_contains_tie is False
    assert result.candidates[0].disposition is CandidateDisposition.SELECTED
    assert result.candidates[0].composite_score == Decimal("0.5")
    assert result.candidates[0].competition_rank == 1
    assert result.score_components[0].percentile == Decimal("0.5")
    assert result.score_components[0].contribution == Decimal("0.5")


def test_constant_singleton_does_not_require_explanatory_weight_order_projection() -> None:
    beyond_projection_cap = "1." + ("0" * 4096) + "1"

    result = build_candidate_set(
        policy=_policy(
            _component(1, weight="1"),
            _component(2, weight=beyond_projection_cap),
            requested_top_k=1,
        ),
        dataset=_population(
            _row(1, _cell(1, "7"), _cell(2, "11")),
        ),
    )

    assert result.candidate_set.decimal_projection_precision == 64
    assert result.candidate_set.ranking_status is CandidateRankingStatus.CONSTANT
    assert result.candidate_set.composite_distinct_count == 1
    assert result.candidates[0].composite_score == Decimal("0.5")
    assert result.candidates[0].competition_rank == 1
    assert {item.percentile for item in result.score_components} == {
        Decimal("0.5")
    }
    assert {item.normalized_weight for item in result.score_components} == {
        Decimal("0.5")
    }
    assert {item.contribution for item in result.score_components} == {
        Decimal("0.25")
    }
    assert all(
        item.normalized_weight.is_finite()
        and item.contribution is not None
        and item.contribution.is_finite()
        and item.contribution <= item.normalized_weight
        for item in result.score_components
    )


def test_mixed_constant_and_variable_components_keep_fixed_weights() -> None:
    result = build_candidate_set(
        policy=_policy(
            _component(1, weight="3"),
            _component(2, weight="1"),
            requested_top_k=1,
        ),
        dataset=_population(
            _row(1, _cell(1, "9"), _cell(2, "0")),
            _row(2, _cell(1, "9"), _cell(2, "1")),
            _row(3, _cell(1, "9"), _cell(2, "2")),
        ),
    )

    diagnostics = {
        item.feature_definition_id: item for item in result.component_diagnostics
    }
    assert diagnostics[_uuid(201)].ranking_status is CandidateRankingStatus.CONSTANT
    assert diagnostics[_uuid(202)].ranking_status is CandidateRankingStatus.AVAILABLE
    assert result.candidate_set.ranking_status is CandidateRankingStatus.AVAILABLE
    middle_components = {
        item.feature_definition_id: item
        for item in result.score_components
        if item.instrument_id == _uuid(1_002)
    }
    assert middle_components[_uuid(201)].normalized_weight == Decimal("0.75")
    assert middle_components[_uuid(201)].percentile == Decimal("0.5")
    assert middle_components[_uuid(201)].contribution == Decimal("0.375")
    assert middle_components[_uuid(202)].normalized_weight == Decimal("0.25")
    assert middle_components[_uuid(202)].percentile == Decimal("0.5")
    assert middle_components[_uuid(202)].contribution == Decimal("0.125")
    assert {
        item.instrument_id: item.composite_score for item in result.candidates
    } == {
        _uuid(1_001): Decimal("0.375"),
        _uuid(1_002): Decimal("0.5"),
        _uuid(1_003): Decimal("0.625"),
    }


def test_all_constant_components_include_every_boundary_tie() -> None:
    result = build_candidate_set(
        policy=_policy(_component(1), _component(2), requested_top_k=1),
        dataset=_population(
            _row(1, _cell(1, "7"), _cell(2, "11")),
            _row(2, _cell(1, "7"), _cell(2, "11")),
            _row(3, _cell(1, "7"), _cell(2, "11")),
        ),
    )

    assert result.candidate_set.ranking_status is CandidateRankingStatus.CONSTANT
    assert result.candidate_set.selected_count == 3
    assert result.candidate_set.ranked_not_selected_count == 0
    assert result.candidate_set.selected_overflow_count == 2
    assert result.candidate_set.boundary_group_count == 3
    assert result.candidate_set.boundary_contains_tie is True
    assert result.candidate_set.boundary_tie_expanded is True
    assert {item.composite_score for item in result.candidates} == {Decimal("0.5")}
    assert {item.competition_rank for item in result.candidates} == {1}
    assert {item.disposition for item in result.candidates} == {
        CandidateDisposition.SELECTED
    }


def test_zero_rankable_and_empty_populations_are_not_estimable() -> None:
    statuses = (
        CandidateCellStatus.MISSING,
        CandidateCellStatus.UNKNOWN,
        CandidateCellStatus.STALE,
        CandidateCellStatus.CONFLICT,
    )
    unavailable = build_candidate_set(
        policy=_policy(_component(1)),
        dataset=_population(
            *(
                _row(index, _cell(1, None, status=status))
                for index, status in enumerate(statuses, start=1)
            )
        ),
    )

    assert unavailable.candidate_set.ranking_status is CandidateRankingStatus.NOT_ESTIMABLE
    assert unavailable.candidate_set.selected_count == 0
    assert unavailable.candidate_set.boundary_score is None
    assert unavailable.candidate_set.boundary_rank is None
    assert unavailable.candidate_set.score_component_count == 4
    assert all(item.percentile is None for item in unavailable.score_components)
    diagnostic = unavailable.component_diagnostics[0]
    assert (
        diagnostic.observed_count,
        diagnostic.distinct_count,
        diagnostic.missing_count,
        diagnostic.unknown_count,
        diagnostic.stale_count,
        diagnostic.conflict_count,
    ) == (0, 0, 1, 1, 1, 1)

    empty = build_candidate_set(
        policy=_policy(_component(1)),
        dataset=_population(),
    )
    assert empty.candidate_set.population_count == 0
    assert empty.candidate_set.ranking_status is CandidateRankingStatus.NOT_ESTIMABLE
    assert empty.candidates == ()
    assert empty.score_components == ()
    assert len(empty.component_diagnostics) == 1
    assert (
        empty.component_diagnostics[0].rank_information_status
        is CandidateRankingStatus.NOT_ESTIMABLE
    )


def test_competition_rank_and_boundary_do_not_break_equal_scores_by_identity() -> None:
    result = build_candidate_set(
        policy=_policy(_component(1), requested_top_k=1),
        dataset=_population(
            _row(3, _cell(1, "0")),
            _row(2, _cell(1, "10")),
            _row(1, _cell(1, "10")),
        ),
    )

    assert {
        item.instrument_id: item.competition_rank for item in result.candidates
    } == {_uuid(1_001): 1, _uuid(1_002): 1, _uuid(1_003): 3}
    assert {
        item.instrument_id
        for item in result.candidates
        if item.disposition is CandidateDisposition.SELECTED
    } == {_uuid(1_001), _uuid(1_002)}
    assert result.candidate_set.selected_overflow_count == 1


def test_available_components_can_cancel_without_misreporting_constant_inputs() -> None:
    result = build_candidate_set(
        policy=_policy(_component(1), _component(2), requested_top_k=1),
        dataset=_population(
            _row(1, _cell(1, "0"), _cell(2, "1")),
            _row(2, _cell(1, "1"), _cell(2, "0")),
        ),
    )

    assert {
        item.rank_information_status for item in result.component_diagnostics
    } == {CandidateRankingStatus.AVAILABLE}
    assert result.candidate_set.ranking_status is CandidateRankingStatus.AVAILABLE
    assert result.candidate_set.composite_distinct_count == 1
    assert {item.composite_score for item in result.candidates} == {Decimal("0.5")}
    assert {item.competition_rank for item in result.candidates} == {1}
    assert result.candidate_set.selected_count == 2


def test_decimal_projection_adapts_and_fails_at_its_closed_cap() -> None:
    almost_one = Fraction(10**70 + 1, 10**70)
    precision, projected = project_exact_values(
        {"one": Fraction(1), "almost_one": almost_one},
        minimum_precision=64,
        maximum_precision=128,
    )

    assert precision == 128
    assert projected["one"] < projected["almost_one"]
    with pytest.raises(ValueError, match="closed precision cap 64"):
        project_exact_values(
            {"one": Fraction(1), "almost_one": almost_one},
            minimum_precision=64,
            maximum_precision=64,
        )


def test_candidate_set_projection_adapts_for_close_composite_score_classes() -> None:
    policy = _policy(
        _component(1, weight="1"),
        _component(2, weight="1E-70"),
        requested_top_k=1,
    )
    dataset = _population(
        _row(1, _cell(1, "9"), _cell(2, "0")),
        _row(2, _cell(1, "9"), _cell(2, "1")),
    )

    result = build_candidate_set(
        policy=policy,
        dataset=dataset,
        minimum_projection_precision=64,
        maximum_projection_precision=128,
    )

    candidates = {item.instrument_id: item for item in result.candidates}
    assert result.candidate_set.decimal_projection_precision == 128
    lower_score = candidates[_uuid(1_001)].composite_score
    higher_score = candidates[_uuid(1_002)].composite_score
    assert lower_score is not None
    assert higher_score is not None
    assert lower_score < higher_score
    assert candidates[_uuid(1_001)].competition_rank == 2
    assert candidates[_uuid(1_002)].competition_rank == 1
    with pytest.raises(ValueError, match="closed precision cap 64"):
        build_candidate_set(
            policy=policy,
            dataset=dataset,
            minimum_projection_precision=64,
            maximum_projection_precision=64,
        )


def test_row_order_and_ambient_decimal_context_cannot_change_ranking() -> None:
    policy = _policy(
        _component(1, weight="1"),
        _component(2, weight="2"),
        requested_top_k=2,
    )
    rows = (
        _row(1, _cell(1, "1"), _cell(2, "30")),
        _row(2, _cell(1, "2"), _cell(2, "20")),
        _row(3, _cell(1, "3"), _cell(2, "10")),
    )
    with localcontext() as context:
        context.prec = 6
        first = build_candidate_set(policy=policy, dataset=_population(*rows))
    with localcontext() as context:
        context.prec = 50
        second = build_candidate_set(
            policy=policy,
            dataset=_population(*reversed(rows)),
        )

    assert first.candidate_set.content_sha256 == second.candidate_set.content_sha256
    assert first.candidates == second.candidates
    assert first.score_components == second.score_components
