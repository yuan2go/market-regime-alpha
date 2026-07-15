from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates import (
    CompositeCandidateRankingRun,
    CompositeFeatureComponent,
    CompositeFeatureDirection,
    CompositeFeatureRole,
    TransparentCompositeSpec,
    rank_candidates_by_transparent_composite,
)
from market_regime_alpha.candidates.dataset import (
    CandidateDatasetRow,
    CandidateFeatureValue,
    CandidateResearchDataset,
    CandidateTargetValue,
    TargetObservationStatus,
)
from market_regime_alpha.candidates.evaluation import (
    evaluate_candidate_ranking_panel,
    evaluate_candidate_ranking_slice,
)
from market_regime_alpha.candidates.panel import assemble_candidate_research_panel
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
from market_regime_alpha.data.contracts import DataEligibility


TZ = ZoneInfo("Asia/Shanghai")
DECISION_TIME = DecisionTime(datetime(2026, 7, 15, 14, 55, tzinfo=TZ))
OBSERVED_AT = AvailabilityTime(datetime(2026, 7, 16, 15, 0, tzinfo=TZ))
MOMENTUM = FeatureDefinitionId("feature-momentum")
LIQUIDITY = FeatureDefinitionId("feature-liquidity")
VOLATILITY = FeatureDefinitionId("feature-volatility")
TARGET = TargetId("target-next-session-close-return-v1")


def _dataset(
    *,
    dataset_id: str,
    feature_ids: tuple[FeatureDefinitionId, ...],
    values: dict[str, tuple[float | None, ...]],
    target_values: dict[str, float] | None = None,
) -> CandidateResearchDataset:
    symbols = tuple(sorted(values))
    target_values = target_values or {}
    rows = []
    for symbol in symbols:
        feature_values = tuple(
            CandidateFeatureValue(
                feature_id=feature_id,
                status=InputAvailabilityStatus.AVAILABLE if value is not None else InputAvailabilityStatus.MISSING,
                value=value,
            )
            for feature_id, value in zip(feature_ids, values[symbol], strict=True)
        )
        target_value = target_values.get(symbol)
        rows.append(
            CandidateDatasetRow(
                symbol=symbol,
                feature_values=feature_values,
                target=CandidateTargetValue(
                    target_id=TARGET,
                    status=(
                        TargetObservationStatus.AVAILABLE
                        if target_value is not None
                        else TargetObservationStatus.NOT_YET_OBSERVED
                    ),
                    value=target_value,
                    observed_at=OBSERVED_AT if target_value is not None else None,
                ),
            )
        )
    return CandidateResearchDataset(
        dataset_id=DatasetId(dataset_id),
        source_dataset_ids=(DatasetId("source-rehearsal"),),
        data_eligibility=DataEligibility.REHEARSAL,
        universe_id=UniverseId("universe-r5-test"),
        decision_time=DECISION_TIME,
        population_symbols=symbols,
        target_id=TARGET,
        target_materialization_artifact_id=ArtifactId(f"target-artifact-{dataset_id}"),
        feature_definition_ids=feature_ids,
        feature_materialization_ids=tuple(
            FeatureMaterializationId(f"fm-{str(feature_id)}-{dataset_id}") for feature_id in feature_ids
        ),
        rows=tuple(rows),
    )


def _component(
    feature_id: FeatureDefinitionId,
    *,
    direction: CompositeFeatureDirection = CompositeFeatureDirection.HIGHER_IS_BETTER,
    weight: float = 1.0,
    role: CompositeFeatureRole = CompositeFeatureRole.OPPORTUNITY,
) -> CompositeFeatureComponent:
    return CompositeFeatureComponent(
        feature_id=feature_id,
        direction=direction,
        weight=weight,
        role=role,
    )


def test_rank_normalization_prevents_raw_feature_scale_from_dominating() -> None:
    small_scale = _dataset(
        dataset_id="candidate-small-scale",
        feature_ids=(MOMENTUM, LIQUIDITY),
        values={
            "000001.SZ": (0.03, 1.0),
            "000002.SZ": (0.02, 2.0),
            "000003.SZ": (0.01, 3.0),
        },
    )
    huge_scale = _dataset(
        dataset_id="candidate-huge-scale",
        feature_ids=(MOMENTUM, LIQUIDITY),
        values={
            "000001.SZ": (0.03, 1.0),
            "000002.SZ": (0.02, 2.0),
            "000003.SZ": (0.01, 3_000_000_000_000.0),
        },
    )
    spec = TransparentCompositeSpec((_component(MOMENTUM), _component(LIQUIDITY)))

    small = rank_candidates_by_transparent_composite(
        small_scale,
        spec=spec,
        model_id=ModelId("b1-scale-test"),
        code_revision="abc123",
        config_hash="config-v1",
    )
    huge = rank_candidates_by_transparent_composite(
        huge_scale,
        spec=spec,
        model_id=ModelId("b1-scale-test"),
        code_revision="abc123",
        config_hash="config-v1",
    )

    assert [(item.symbol, item.model_score) for item in small.predictions] == [
        (item.symbol, item.model_score) for item in huge.predictions
    ]


def test_lower_is_better_direction_supports_explicit_risk_penalty() -> None:
    dataset = _dataset(
        dataset_id="candidate-risk-direction",
        feature_ids=(MOMENTUM, VOLATILITY),
        values={
            "000001.SZ": (0.03, 0.30),
            "000002.SZ": (0.02, 0.10),
            "000003.SZ": (0.01, 0.20),
        },
    )
    spec = TransparentCompositeSpec(
        (
            _component(MOMENTUM, weight=0.3),
            _component(
                VOLATILITY,
                direction=CompositeFeatureDirection.LOWER_IS_BETTER,
                weight=0.7,
                role=CompositeFeatureRole.RISK_PENALTY,
            ),
        )
    )

    result = rank_candidates_by_transparent_composite(
        dataset,
        spec=spec,
        model_id=ModelId("b1-risk-penalty"),
        code_revision="abc123",
        config_hash="config-v1",
    )

    assert result.predictions[0].symbol == "000002.SZ"
    assert result.predictions[0].rank == 1


def test_strict_complete_case_rejects_missing_component_without_dropping_candidate() -> None:
    dataset = _dataset(
        dataset_id="candidate-missing-component",
        feature_ids=(MOMENTUM, LIQUIDITY),
        values={
            "000001.SZ": (0.03, 10.0),
            "000002.SZ": (0.02, None),
            "000003.SZ": (0.01, 30.0),
        },
    )
    spec = TransparentCompositeSpec((_component(MOMENTUM), _component(LIQUIDITY)))

    result = rank_candidates_by_transparent_composite(
        dataset,
        spec=spec,
        model_id=ModelId("b1-missing-test"),
        code_revision="abc123",
        config_hash="config-v1",
    )

    assert result.candidate_population_size == 3
    assert result.ranked_population_size == 2
    assert {item.symbol for item in result.predictions} == {"000001.SZ", "000003.SZ"}
    assert len(result.rejections) == 1
    assert result.rejections[0].symbol == "000002.SZ"
    assert result.rejections[0].feature_id == LIQUIDITY
    assert result.rejections[0].reason_code == "COMPOSITE_FEATURE_MISSING"


def test_equivalent_component_order_and_common_weight_scaling_share_spec_identity() -> None:
    first = TransparentCompositeSpec(
        (
            _component(MOMENTUM, weight=1.0),
            _component(LIQUIDITY, weight=2.0, role=CompositeFeatureRole.QUALITY),
        )
    )
    equivalent = TransparentCompositeSpec(
        (
            _component(LIQUIDITY, weight=20.0, role=CompositeFeatureRole.QUALITY),
            _component(MOMENTUM, weight=10.0),
        )
    )

    assert first.spec_hash == equivalent.spec_hash


def test_b1_ranking_is_compatible_with_existing_cross_sectional_evaluation() -> None:
    dataset = _dataset(
        dataset_id="candidate-b1-evaluation",
        feature_ids=(MOMENTUM, LIQUIDITY),
        values={
            "000001.SZ": (0.03, 30.0),
            "000002.SZ": (0.02, 20.0),
            "000003.SZ": (0.01, 10.0),
        },
        target_values={
            "000001.SZ": 0.03,
            "000002.SZ": 0.02,
            "000003.SZ": 0.01,
        },
    )
    spec = TransparentCompositeSpec((_component(MOMENTUM), _component(LIQUIDITY)))
    ranking = rank_candidates_by_transparent_composite(
        dataset,
        spec=spec,
        model_id=ModelId("b1-evaluation-test"),
        code_revision="abc123",
        config_hash="config-v1",
    )

    evaluation = evaluate_candidate_ranking_slice(dataset, ranking, top_k=2)
    panel_evaluation = evaluate_candidate_ranking_panel(
        assemble_candidate_research_panel((dataset,)),
        (ranking,),
        top_k=2,
    )

    assert isinstance(ranking, CompositeCandidateRankingRun)
    assert evaluation.ranking_coverage == pytest.approx(1.0)
    assert evaluation.spearman_rank_ic == pytest.approx(1.0)
    assert evaluation.top_k_mean_target == pytest.approx(0.025)
    assert panel_evaluation.slice_evaluations == (evaluation,)


def test_b1_ranking_does_not_read_future_target_values() -> None:
    first = _dataset(
        dataset_id="candidate-b1-target-a",
        feature_ids=(MOMENTUM, LIQUIDITY),
        values={
            "000001.SZ": (0.03, 30.0),
            "000002.SZ": (0.02, None),
            "000003.SZ": (0.01, 10.0),
        },
        target_values={
            "000001.SZ": 0.50,
            "000002.SZ": -0.20,
            "000003.SZ": 0.10,
        },
    )
    second = _dataset(
        dataset_id="candidate-b1-target-b",
        feature_ids=(MOMENTUM, LIQUIDITY),
        values={
            "000001.SZ": (0.03, 30.0),
            "000002.SZ": (0.02, None),
            "000003.SZ": (0.01, 10.0),
        },
        target_values={
            "000001.SZ": -0.50,
            "000002.SZ": 0.80,
            "000003.SZ": -0.10,
        },
    )
    spec = TransparentCompositeSpec((_component(MOMENTUM), _component(LIQUIDITY)))

    first_run = rank_candidates_by_transparent_composite(
        first,
        spec=spec,
        model_id=ModelId("b1-target-blindness"),
        code_revision="abc123",
        config_hash="config-v1",
    )
    second_run = rank_candidates_by_transparent_composite(
        second,
        spec=spec,
        model_id=ModelId("b1-target-blindness"),
        code_revision="abc123",
        config_hash="config-v1",
    )

    assert tuple((item.symbol, item.model_score, item.rank) for item in first_run.predictions) == tuple(
        (item.symbol, item.model_score, item.rank) for item in second_run.predictions
    )
    assert tuple((item.symbol, item.reason_code) for item in first_run.rejections) == tuple(
        (item.symbol, item.reason_code) for item in second_run.rejections
    )
    assert first_run.experiment_id != second_run.experiment_id
