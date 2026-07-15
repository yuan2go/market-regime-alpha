"""Simple deterministic Candidate ranking baselines for R5 rehearsal.

The first baseline ranks one registered numeric Feature. It preserves the complete Candidate
Population through explicit predictions plus explicit ranking rejections and never reads the
future Target value when computing scores.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from market_regime_alpha.candidates.contracts import CandidatePrediction
from market_regime_alpha.candidates.dataset import CandidateResearchDataset
from market_regime_alpha.core.identity import (
    DatasetId,
    ExperimentId,
    FeatureDefinitionId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.research.experiment_identity import ExperimentIdentity


@dataclass(frozen=True, slots=True)
class CandidateRankingRejection:
    """Explicit reason one Candidate could not enter the selected baseline ranking."""

    symbol: str
    reason_code: str
    feature_id: FeatureDefinitionId

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip() or self.symbol != self.symbol.strip():
            raise ValueError("symbol must be a non-empty trimmed string")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip() or self.reason_code != self.reason_code.strip():
            raise ValueError("reason_code must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class CandidateRankingRun:
    """One deterministic cross-sectional baseline ranking with full-population accounting."""

    dataset_id: DatasetId
    experiment_id: ExperimentId
    model_id: ModelId
    universe_id: UniverseId
    target_id: TargetId
    decision_time: DecisionTime
    selected_feature_id: FeatureDefinitionId
    candidate_population_size: int
    ranked_population_size: int
    predictions: tuple[CandidatePrediction, ...]
    rejections: tuple[CandidateRankingRejection, ...]

    def __post_init__(self) -> None:
        if self.candidate_population_size < 0:
            raise ValueError("candidate_population_size must be non-negative")
        if self.ranked_population_size < 0:
            raise ValueError("ranked_population_size must be non-negative")
        if self.ranked_population_size != len(self.predictions):
            raise ValueError("ranked_population_size must match predictions")
        if self.candidate_population_size != len(self.predictions) + len(self.rejections):
            raise ValueError("predictions plus rejections must cover the Candidate Population")
        prediction_symbols = [prediction.symbol for prediction in self.predictions]
        rejection_symbols = [rejection.symbol for rejection in self.rejections]
        all_symbols = prediction_symbols + rejection_symbols
        if len(all_symbols) != len(set(all_symbols)):
            raise ValueError("ranking run symbols must be unique across predictions and rejections")
        expected_ranks = tuple(range(1, len(self.predictions) + 1))
        actual_ranks = tuple(prediction.rank for prediction in self.predictions)
        if actual_ranks != expected_ranks:
            raise ValueError("prediction ranks must be contiguous and ordered")

    @property
    def ranking_coverage(self) -> float:
        if self.candidate_population_size == 0:
            return 0.0
        return self.ranked_population_size / self.candidate_population_size


def rank_candidates_by_feature(
    dataset: CandidateResearchDataset,
    *,
    feature_id: FeatureDefinitionId,
    model_id: ModelId,
    code_revision: str,
    config_hash: str,
) -> CandidateRankingRun:
    """Rank available finite numeric values descending; reject unavailable/non-numeric cells."""

    try:
        feature_index = dataset.feature_definition_ids.index(feature_id)
    except ValueError as exc:
        raise ValueError(f"feature not present in Candidate dataset: {feature_id}") from exc

    feature_materialization_id = dataset.feature_materialization_ids[feature_index]
    experiment = ExperimentIdentity(
        code_revision=code_revision,
        dataset_id=dataset.dataset_id,
        config_hash=config_hash,
        universe_id=dataset.universe_id,
        target_id=dataset.target_id,
        feature_definition_ids=(feature_id,),
        feature_materialization_ids=(feature_materialization_id,),
        model_id=model_id,
        semantic_refs=(("baseline_kind", "single_feature_descending_rank"),),
    )

    rankable: list[tuple[str, float]] = []
    rejections: list[CandidateRankingRejection] = []
    for row in dataset.rows:
        cell = row.feature_values[feature_index]
        if cell.status is not InputAvailabilityStatus.AVAILABLE:
            rejections.append(
                CandidateRankingRejection(
                    symbol=row.symbol,
                    reason_code=f"FEATURE_{cell.status.value}",
                    feature_id=feature_id,
                )
            )
            continue
        if isinstance(cell.value, bool) or not isinstance(cell.value, (int, float)):
            rejections.append(
                CandidateRankingRejection(
                    symbol=row.symbol,
                    reason_code="FEATURE_NON_NUMERIC",
                    feature_id=feature_id,
                )
            )
            continue
        score = float(cell.value)
        if not math.isfinite(score):
            rejections.append(
                CandidateRankingRejection(
                    symbol=row.symbol,
                    reason_code="FEATURE_INVALID_NUMERIC",
                    feature_id=feature_id,
                )
            )
            continue
        rankable.append((row.symbol, score))

    rankable.sort(key=lambda item: (-item[1], item[0]))
    predictions = tuple(
        CandidatePrediction(
            symbol=symbol,
            universe_id=dataset.universe_id,
            model_id=model_id,
            target_id=dataset.target_id,
            decision_time=dataset.decision_time,
            experiment_id=experiment.experiment_id,
            population_size=len(dataset.population_symbols),
            model_score=score,
            rank=rank,
        )
        for rank, (symbol, score) in enumerate(rankable, start=1)
    )
    rejections.sort(key=lambda item: item.symbol)
    return CandidateRankingRun(
        dataset_id=dataset.dataset_id,
        experiment_id=experiment.experiment_id,
        model_id=model_id,
        universe_id=dataset.universe_id,
        target_id=dataset.target_id,
        decision_time=dataset.decision_time,
        selected_feature_id=feature_id,
        candidate_population_size=len(dataset.population_symbols),
        ranked_population_size=len(predictions),
        predictions=predictions,
        rejections=tuple(rejections),
    )
