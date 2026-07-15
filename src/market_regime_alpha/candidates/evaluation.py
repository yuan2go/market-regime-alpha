"""Cross-sectional rehearsal evaluation for R5 Candidate ranking baselines.

Metrics here are descriptive research evidence. They do not by themselves establish formal
Alpha, Strategy authority, or live trading authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import mean

from market_regime_alpha.candidates.baselines import CandidateRankingRun
from market_regime_alpha.candidates.dataset import CandidateResearchDataset, TargetObservationStatus
from market_regime_alpha.candidates.panel import CandidateResearchPanel
from market_regime_alpha.core.identity import DatasetId, ExperimentId, ModelId, TargetId
from market_regime_alpha.core.time import DecisionTime


@dataclass(frozen=True, slots=True)
class CandidateSliceEvaluation:
    """Descriptive evaluation of one Candidate ranking cross-section."""

    dataset_id: DatasetId
    experiment_id: ExperimentId
    model_id: ModelId
    target_id: TargetId
    decision_time: DecisionTime
    candidate_population_size: int
    ranked_population_size: int
    target_available_population_size: int
    evaluated_prediction_count: int
    ranking_coverage: float
    target_coverage: float
    evaluated_prediction_coverage: float
    spearman_rank_ic: float | None
    top_k_requested: int
    top_k_observed_count: int
    top_k_mean_target: float | None
    ranked_mean_target: float | None


@dataclass(frozen=True, slots=True)
class CandidatePanelEvaluation:
    """Chronological collection of per-slice rehearsal evaluations."""

    panel_dataset_id: DatasetId
    model_id: ModelId
    target_id: TargetId
    slice_evaluations: tuple[CandidateSliceEvaluation, ...]
    candidate_population_size: int
    ranked_population_size: int
    evaluated_prediction_count: int
    ranking_coverage: float
    evaluated_prediction_coverage: float
    mean_slice_rank_ic: float | None
    mean_slice_top_k_target: float | None

    @property
    def slice_count(self) -> int:
        return len(self.slice_evaluations)


def evaluate_candidate_ranking_slice(
    dataset: CandidateResearchDataset,
    ranking: CandidateRankingRun,
    *,
    top_k: int = 5,
) -> CandidateSliceEvaluation:
    """Evaluate one ranking against only Target observations explicitly marked AVAILABLE."""

    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if ranking.dataset_id != dataset.dataset_id:
        raise ValueError("ranking dataset does not match Candidate research dataset")
    if ranking.universe_id != dataset.universe_id:
        raise ValueError("ranking universe does not match Candidate research dataset")
    if ranking.target_id != dataset.target_id:
        raise ValueError("ranking target does not match Candidate research dataset")
    if ranking.decision_time != dataset.decision_time:
        raise ValueError("ranking Decision Time does not match Candidate research dataset")
    if ranking.candidate_population_size != len(dataset.population_symbols):
        raise ValueError("ranking Candidate Population size does not match dataset")

    target_by_symbol = {
        row.symbol: row.target
        for row in dataset.rows
    }
    available_target_symbols = {
        symbol
        for symbol, target in target_by_symbol.items()
        if target.status is TargetObservationStatus.AVAILABLE
    }
    evaluated_pairs: list[tuple[float, float]] = []
    evaluated_target_values: list[float] = []
    for prediction in ranking.predictions:
        target = target_by_symbol[prediction.symbol]
        if target.status is not TargetObservationStatus.AVAILABLE:
            continue
        assert target.value is not None
        assert prediction.model_score is not None
        evaluated_pairs.append((float(prediction.model_score), float(target.value)))
        evaluated_target_values.append(float(target.value))

    top_predictions = ranking.predictions[:top_k]
    top_k_values: list[float] = []
    for prediction in top_predictions:
        target = target_by_symbol[prediction.symbol]
        if target.status is TargetObservationStatus.AVAILABLE:
            assert target.value is not None
            top_k_values.append(float(target.value))

    candidate_population_size = len(dataset.population_symbols)
    target_available_population_size = len(available_target_symbols)
    evaluated_prediction_count = len(evaluated_pairs)
    return CandidateSliceEvaluation(
        dataset_id=dataset.dataset_id,
        experiment_id=ranking.experiment_id,
        model_id=ranking.model_id,
        target_id=dataset.target_id,
        decision_time=dataset.decision_time,
        candidate_population_size=candidate_population_size,
        ranked_population_size=ranking.ranked_population_size,
        target_available_population_size=target_available_population_size,
        evaluated_prediction_count=evaluated_prediction_count,
        ranking_coverage=_safe_ratio(ranking.ranked_population_size, candidate_population_size),
        target_coverage=_safe_ratio(target_available_population_size, candidate_population_size),
        evaluated_prediction_coverage=_safe_ratio(evaluated_prediction_count, candidate_population_size),
        spearman_rank_ic=_spearman(evaluated_pairs),
        top_k_requested=top_k,
        top_k_observed_count=len(top_k_values),
        top_k_mean_target=mean(top_k_values) if top_k_values else None,
        ranked_mean_target=mean(evaluated_target_values) if evaluated_target_values else None,
    )


def evaluate_candidate_ranking_panel(
    panel: CandidateResearchPanel,
    rankings: tuple[CandidateRankingRun, ...],
    *,
    top_k: int = 5,
) -> CandidatePanelEvaluation:
    """Evaluate exactly one ranking run for each identified Candidate panel slice."""

    ranking_by_dataset = {ranking.dataset_id: ranking for ranking in rankings}
    if len(ranking_by_dataset) != len(rankings):
        raise ValueError("rankings must have unique Candidate dataset identities")
    expected_ids = set(panel.slice_dataset_ids)
    if set(ranking_by_dataset) != expected_ids:
        raise ValueError("rankings must cover every Candidate panel slice exactly once")

    ordered_rankings = tuple(ranking_by_dataset[slice_.dataset_id] for slice_ in panel.slices)
    model_ids = {ranking.model_id for ranking in ordered_rankings}
    if len(model_ids) != 1:
        raise ValueError("panel evaluation requires one Model Identity")
    model_id = next(iter(model_ids))

    slice_evaluations = tuple(
        evaluate_candidate_ranking_slice(slice_, ranking, top_k=top_k)
        for slice_, ranking in zip(panel.slices, ordered_rankings, strict=True)
    )
    candidate_population_size = sum(item.candidate_population_size for item in slice_evaluations)
    ranked_population_size = sum(item.ranked_population_size for item in slice_evaluations)
    evaluated_prediction_count = sum(item.evaluated_prediction_count for item in slice_evaluations)
    rank_ics = [item.spearman_rank_ic for item in slice_evaluations if item.spearman_rank_ic is not None]
    top_k_targets = [item.top_k_mean_target for item in slice_evaluations if item.top_k_mean_target is not None]
    return CandidatePanelEvaluation(
        panel_dataset_id=panel.dataset_id,
        model_id=model_id,
        target_id=panel.target_id,
        slice_evaluations=slice_evaluations,
        candidate_population_size=candidate_population_size,
        ranked_population_size=ranked_population_size,
        evaluated_prediction_count=evaluated_prediction_count,
        ranking_coverage=_safe_ratio(ranked_population_size, candidate_population_size),
        evaluated_prediction_coverage=_safe_ratio(evaluated_prediction_count, candidate_population_size),
        mean_slice_rank_ic=mean(rank_ics) if rank_ics else None,
        mean_slice_top_k_target=mean(top_k_targets) if top_k_targets else None,
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _spearman(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    x_values = [pair[0] for pair in pairs]
    y_values = [pair[1] for pair in pairs]
    x_ranks = _average_ranks(x_values)
    y_ranks = _average_ranks(y_values)
    x_mean = mean(x_ranks)
    y_mean = mean(y_ranks)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_ranks, y_ranks, strict=True))
    x_ss = sum((x - x_mean) ** 2 for x in x_ranks)
    y_ss = sum((y - y_mean) ** 2 for y in y_ranks)
    denominator = math.sqrt(x_ss * y_ss)
    if denominator == 0.0:
        return None
    return numerator / denominator


def _average_ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        end = position + 1
        while end < len(indexed) and indexed[end][1] == indexed[position][1]:
            end += 1
        average_rank = (position + 1 + end) / 2.0
        for index in range(position, end):
            original_index = indexed[index][0]
            ranks[original_index] = average_rank
        position = end
    return ranks
