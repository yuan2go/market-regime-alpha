from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_regime_alpha.candidates.baselines import (
    CandidateRankingRejection,
    CandidateRankingRun,
    rank_candidates_by_feature,
)
from market_regime_alpha.candidates.contracts import CandidatePrediction
from market_regime_alpha.candidates.dataset import (
    CandidateDatasetRow,
    CandidateFeatureValue,
    CandidateResearchDataset,
    CandidateTargetValue,
    TargetObservationStatus,
)
from market_regime_alpha.candidates.evaluation import evaluate_candidate_ranking_slice
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    ExperimentId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility


DECISION_TIME = DecisionTime(datetime(2026, 7, 15, 6, 55, tzinfo=timezone.utc))
OBSERVED_AT = AvailabilityTime(datetime(2026, 7, 16, 7, 5, tzinfo=timezone.utc))
FEATURE_ID = FeatureDefinitionId("feature-r5-momentum-5s-v1")
TARGET_ID = TargetId("target-r5-next-session-v1")
MODEL_ID = ModelId("candidate-r5-single-feature-rank-v1")
UNIVERSE_ID = UniverseId("universe-r5-v1")


def _dataset(dataset_id: str, target_values: tuple[float, float, float]) -> CandidateResearchDataset:
    symbols = ("000001.SZ", "000002.SZ", "000003.SZ")
    feature_values = (0.30, None, 0.10)
    rows = []
    for symbol, feature_value, target_value in zip(symbols, feature_values, target_values, strict=True):
        feature_status = (
            InputAvailabilityStatus.AVAILABLE
            if feature_value is not None
            else InputAvailabilityStatus.MISSING
        )
        rows.append(
            CandidateDatasetRow(
                symbol=symbol,
                feature_values=(
                    CandidateFeatureValue(
                        feature_id=FEATURE_ID,
                        status=feature_status,
                        value=feature_value,
                    ),
                ),
                target=CandidateTargetValue(
                    target_id=TARGET_ID,
                    status=TargetObservationStatus.AVAILABLE,
                    value=target_value,
                    observed_at=OBSERVED_AT,
                ),
            )
        )
    return CandidateResearchDataset(
        dataset_id=DatasetId(dataset_id),
        source_dataset_ids=(DatasetId(f"source-{dataset_id}"),),
        data_eligibility=DataEligibility.REHEARSAL,
        universe_id=UNIVERSE_ID,
        decision_time=DECISION_TIME,
        population_symbols=symbols,
        target_id=TARGET_ID,
        target_materialization_artifact_id=ArtifactId(f"target-artifact-{dataset_id}"),
        feature_definition_ids=(FEATURE_ID,),
        feature_materialization_ids=(FeatureMaterializationId(f"fm-{dataset_id}"),),
        rows=tuple(rows),
    )


def test_single_feature_ranking_does_not_read_future_target_values() -> None:
    first = _dataset("candidate-dataset-target-a", (0.50, -0.20, 0.10))
    second = _dataset("candidate-dataset-target-b", (-0.50, 0.80, -0.10))

    first_run = rank_candidates_by_feature(
        first,
        feature_id=FEATURE_ID,
        model_id=MODEL_ID,
        code_revision="abc123",
        config_hash="single-feature-rank-v1",
    )
    second_run = rank_candidates_by_feature(
        second,
        feature_id=FEATURE_ID,
        model_id=MODEL_ID,
        code_revision="abc123",
        config_hash="single-feature-rank-v1",
    )

    assert tuple((item.symbol, item.model_score, item.rank) for item in first_run.predictions) == tuple(
        (item.symbol, item.model_score, item.rank) for item in second_run.predictions
    )
    assert tuple((item.symbol, item.reason_code) for item in first_run.rejections) == tuple(
        (item.symbol, item.reason_code) for item in second_run.rejections
    )
    assert first_run.experiment_id != second_run.experiment_id


def test_evaluation_rejects_ranking_that_does_not_account_for_exact_population() -> None:
    dataset = _dataset("candidate-dataset-population-guard", (0.10, 0.20, 0.30))
    bad_run = CandidateRankingRun(
        dataset_id=dataset.dataset_id,
        experiment_id=ExperimentId("exp-bad-population-accounting"),
        model_id=MODEL_ID,
        universe_id=dataset.universe_id,
        target_id=dataset.target_id,
        decision_time=dataset.decision_time,
        selected_feature_id=FEATURE_ID,
        candidate_population_size=3,
        ranked_population_size=1,
        predictions=(
            CandidatePrediction(
                symbol="999999.SZ",
                universe_id=dataset.universe_id,
                model_id=MODEL_ID,
                target_id=dataset.target_id,
                decision_time=dataset.decision_time,
                experiment_id=ExperimentId("exp-bad-population-accounting"),
                population_size=3,
                model_score=0.9,
                rank=1,
            ),
        ),
        rejections=(
            CandidateRankingRejection("000001.SZ", "FEATURE_MISSING", FEATURE_ID),
            CandidateRankingRejection("000002.SZ", "FEATURE_MISSING", FEATURE_ID),
        ),
    )

    with pytest.raises(ValueError, match="exactly preserve Candidate Population symbols"):
        evaluate_candidate_ranking_slice(dataset, bad_run)
