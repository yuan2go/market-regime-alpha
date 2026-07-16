from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates.baselines import rank_candidates_by_feature
from market_regime_alpha.candidates.dataset import (
    CandidateDatasetRow,
    CandidateFeatureValue,
    CandidateResearchDataset,
    CandidateTargetValue,
    TargetObservationStatus,
)
from market_regime_alpha.candidates.directional_accuracy import (
    R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
    CandidateDirectionalAccuracySpec,
    DirectionalOutcomeCounts,
    evaluate_candidate_directional_accuracy_panel,
    evaluate_candidate_directional_accuracy_slice,
)
from market_regime_alpha.candidates.panel import assemble_candidate_research_panel
from market_regime_alpha.candidates.rehearsal_targets import (
    R5_NEXT_SESSION_RETURN_TARGET_ID,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data import DataEligibility


TZ = ZoneInfo("Asia/Shanghai")
FEATURE_ID = FeatureDefinitionId("feature-directional-accuracy-test-v1")
MODEL_ID = ModelId("model-directional-accuracy-test-v1")
SYMBOLS = tuple(f"00000{index}.SZ" for index in range(1, 7))


def _dataset(
    day: int,
    values: tuple[float | None, ...],
    *,
    target_id: TargetId = R5_NEXT_SESSION_RETURN_TARGET_ID,
) -> CandidateResearchDataset:
    decision_time = DecisionTime(datetime(2026, 7, 10 + day, 14, 55, tzinfo=TZ))
    observed_at = AvailabilityTime(decision_time.value + timedelta(days=1, hours=1))
    rows = tuple(
        CandidateDatasetRow(
            symbol=symbol,
            feature_values=(
                CandidateFeatureValue(
                    feature_id=FEATURE_ID,
                    status=InputAvailabilityStatus.AVAILABLE,
                    value=float(len(SYMBOLS) - index),
                ),
            ),
            target=CandidateTargetValue(
                target_id=target_id,
                status=(
                    TargetObservationStatus.AVAILABLE
                    if value is not None
                    else TargetObservationStatus.MISSING
                ),
                value=value,
                observed_at=observed_at,
            ),
        )
        for index, (symbol, value) in enumerate(zip(SYMBOLS, values, strict=True))
    )
    return CandidateResearchDataset(
        dataset_id=DatasetId(f"candidate-directional-{day}-{target_id}"),
        source_dataset_ids=(DatasetId(f"source-directional-{day}"),),
        data_eligibility=DataEligibility.REHEARSAL,
        universe_id=UniverseId(f"universe-directional-{day}"),
        decision_time=decision_time,
        population_symbols=SYMBOLS,
        target_id=target_id,
        target_materialization_artifact_id=ArtifactId(f"target-directional-{day}"),
        feature_definition_ids=(FEATURE_ID,),
        feature_materialization_ids=(
            FeatureMaterializationId(f"feature-materialization-directional-{day}"),
        ),
        rows=rows,
    )


def _ranking(dataset: CandidateResearchDataset, *, model_id: ModelId = MODEL_ID):
    return rank_candidates_by_feature(
        dataset,
        feature_id=FEATURE_ID,
        model_id=model_id,
        code_revision="abc123",
        config_hash="directional-accuracy-test-v1",
    )


def test_slice_classifies_sign_and_does_not_backfill_unavailable_top_k_target() -> None:
    dataset = _dataset(0, (0.10, -0.10, 0.0, None, 0.20, -0.20))

    result = evaluate_candidate_directional_accuracy_slice(
        dataset,
        _ranking(dataset),
        spec=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
    )

    assert result.candidate_population == DirectionalOutcomeCounts(
        observed_count=5,
        positive_count=2,
        negative_count=2,
        neutral_count=1,
    )
    assert result.ranked_population == result.candidate_population
    assert result.top_k == DirectionalOutcomeCounts(
        observed_count=4,
        positive_count=2,
        negative_count=1,
        neutral_count=1,
    )
    assert result.target_coverage == 5 / 6
    assert result.top_k_observed_coverage == 4 / 5
    assert result.top_k_positive_rate_lift == pytest.approx(0.1)
    assert result.top_k_negative_rate_reduction == pytest.approx(0.15)


def test_zero_observation_rates_and_lifts_remain_unknown() -> None:
    dataset = _dataset(0, (None, None, None, None, None, None))

    result = evaluate_candidate_directional_accuracy_slice(
        dataset,
        _ranking(dataset),
        spec=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
    )

    assert result.candidate_population.positive_rate is None
    assert result.ranked_population.negative_rate is None
    assert result.top_k.neutral_rate is None
    assert result.target_coverage == 0.0
    assert result.top_k_observed_coverage == 0.0
    assert result.top_k_positive_rate_lift is None
    assert result.top_k_negative_rate_reduction is None


def test_panel_preserves_chronology_and_reports_micro_macro_stability() -> None:
    later = _dataset(1, (0.10, -0.20, -0.10, None, None, 0.20))
    earlier = _dataset(0, (0.10, 0.20, -0.10, None, None, -0.20))
    panel = assemble_candidate_research_panel((later, earlier))

    result = evaluate_candidate_directional_accuracy_panel(
        panel,
        (_ranking(later), _ranking(earlier)),
        spec=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
    )

    assert (
        result.slice_evaluations[0].decision_time.value
        < result.slice_evaluations[1].decision_time.value
    )
    assert result.micro_top_k.positive_rate == 3 / 6
    assert result.macro_top_k_positive_rate == pytest.approx(0.5)
    assert result.comparable_slice_count == 2
    assert result.improved_slice_count == 1
    assert result.improved_slice_fraction == 0.5


def test_panel_skips_undefined_slice_rates_in_macro_metrics() -> None:
    observed = _dataset(0, (0.10, -0.10, 0.0, None, None, None))
    unavailable = _dataset(1, (None, None, None, None, None, None))
    panel = assemble_candidate_research_panel((observed, unavailable))

    result = evaluate_candidate_directional_accuracy_panel(
        panel,
        (_ranking(observed), _ranking(unavailable)),
        spec=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
    )

    assert result.macro_top_k_positive_rate == pytest.approx(1 / 3)
    assert result.comparable_slice_count == 1
    assert result.improved_slice_fraction == 0.0


def test_evaluation_rejects_target_and_panel_alignment_mismatches() -> None:
    first = _dataset(0, (0.10, -0.10, 0.0, None, None, None))
    second = _dataset(1, (-0.10, 0.10, 0.0, None, None, None))
    first_ranking = _ranking(first)
    second_ranking = _ranking(second)
    panel = assemble_candidate_research_panel((first, second))
    other_spec = CandidateDirectionalAccuracySpec(
        spec_id="OTHER_POSITIVE_RETURN_V1",
        target_id=TargetId("target-other-v1"),
        top_k=5,
    )

    with pytest.raises(ValueError, match="spec Target"):
        evaluate_candidate_directional_accuracy_slice(
            first,
            first_ranking,
            spec=other_spec,
        )
    with pytest.raises(ValueError, match="cover every Candidate panel slice"):
        evaluate_candidate_directional_accuracy_panel(
            panel,
            (first_ranking,),
            spec=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
        )
    with pytest.raises(ValueError, match="unique Candidate dataset identities"):
        evaluate_candidate_directional_accuracy_panel(
            panel,
            (first_ranking, first_ranking),
            spec=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
        )
    with pytest.raises(ValueError, match="one Model Identity"):
        evaluate_candidate_directional_accuracy_panel(
            panel,
            (
                first_ranking,
                replace(second_ranking, model_id=ModelId("model-other-v1")),
            ),
            spec=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
        )
