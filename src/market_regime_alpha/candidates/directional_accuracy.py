"""Target-aware directional diagnostics for Candidate ranking research.

These metrics describe realized Target outcomes after a ranking is fixed. They are not
Entry, Exit, probability, Portfolio, or execution contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from market_regime_alpha.candidates.dataset import (
    CandidateResearchDataset,
    TargetObservationStatus,
)
from market_regime_alpha.candidates.evaluation import (
    CandidateRankingLike,
    evaluate_candidate_ranking_slice,
)
from market_regime_alpha.candidates.panel import CandidateResearchPanel
from market_regime_alpha.candidates.rehearsal_targets import (
    R5_NEXT_SESSION_RETURN_TARGET_ID,
)
from market_regime_alpha.core.identity import (
    DatasetId,
    ExperimentId,
    ModelId,
    TargetId,
)
from market_regime_alpha.core.time import DecisionTime


R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC_ID = (
    "R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_V1"
)


@dataclass(frozen=True, slots=True)
class CandidateDirectionalAccuracySpec:
    """Identified sign rule for one Candidate Target and fixed selection depth."""

    spec_id: str
    target_id: TargetId
    top_k: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.spec_id, str)
            or not self.spec_id.strip()
            or self.spec_id != self.spec_id.strip()
        ):
            raise ValueError("spec_id must be a non-empty trimmed string")
        if not isinstance(self.target_id, TargetId):
            raise TypeError("target_id must be a TargetId")
        if isinstance(self.top_k, bool) or not isinstance(self.top_k, int):
            raise TypeError("top_k must be an integer")
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")


R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC = CandidateDirectionalAccuracySpec(
    spec_id=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC_ID,
    target_id=R5_NEXT_SESSION_RETURN_TARGET_ID,
    top_k=5,
)


@dataclass(frozen=True, slots=True)
class DirectionalOutcomeCounts:
    """Observed positive, negative, and neutral Target outcomes for one group."""

    observed_count: int
    positive_count: int
    negative_count: int
    neutral_count: int

    def __post_init__(self) -> None:
        counts = (
            self.observed_count,
            self.positive_count,
            self.negative_count,
            self.neutral_count,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in counts):
            raise TypeError("directional outcome counts must be integers")
        if any(value < 0 for value in counts):
            raise ValueError("directional outcome counts must be non-negative")
        if self.positive_count + self.negative_count + self.neutral_count != self.observed_count:
            raise ValueError("directional outcome categories must sum to observed_count")

    @property
    def positive_rate(self) -> float | None:
        return _optional_ratio(self.positive_count, self.observed_count)

    @property
    def negative_rate(self) -> float | None:
        return _optional_ratio(self.negative_count, self.observed_count)

    @property
    def neutral_rate(self) -> float | None:
        return _optional_ratio(self.neutral_count, self.observed_count)


@dataclass(frozen=True, slots=True)
class CandidateDirectionalSliceEvaluation:
    """Positive-return diagnostic for one fixed Candidate ranking cross-section."""

    spec_id: str
    dataset_id: DatasetId
    experiment_id: ExperimentId
    model_id: ModelId
    target_id: TargetId
    decision_time: DecisionTime
    candidate_population_size: int
    ranked_population_size: int
    target_available_population_size: int
    target_coverage: float
    top_k_requested: int
    top_k_observed_coverage: float
    candidate_population: DirectionalOutcomeCounts
    ranked_population: DirectionalOutcomeCounts
    top_k: DirectionalOutcomeCounts
    top_k_positive_rate_lift: float | None
    top_k_negative_rate_reduction: float | None


@dataclass(frozen=True, slots=True)
class CandidateDirectionalPanelEvaluation:
    """Chronological collection and aggregation of directional slice diagnostics."""

    spec_id: str
    panel_dataset_id: DatasetId
    model_id: ModelId
    target_id: TargetId
    slice_evaluations: tuple[CandidateDirectionalSliceEvaluation, ...]
    candidate_population_size: int
    ranked_population_size: int
    micro_candidate_population: DirectionalOutcomeCounts
    micro_ranked_population: DirectionalOutcomeCounts
    micro_top_k: DirectionalOutcomeCounts
    macro_candidate_positive_rate: float | None
    macro_ranked_positive_rate: float | None
    macro_top_k_positive_rate: float | None
    macro_top_k_negative_rate: float | None
    macro_top_k_positive_rate_lift: float | None
    macro_top_k_negative_rate_reduction: float | None
    comparable_slice_count: int
    improved_slice_count: int
    improved_slice_fraction: float | None

    @property
    def slice_count(self) -> int:
        return len(self.slice_evaluations)


def evaluate_candidate_directional_accuracy_slice(
    dataset: CandidateResearchDataset,
    ranking: CandidateRankingLike,
    *,
    spec: CandidateDirectionalAccuracySpec,
) -> CandidateDirectionalSliceEvaluation:
    """Evaluate one ranking without changing its Top-K membership from future Targets."""

    if dataset.target_id != spec.target_id:
        raise ValueError("directional accuracy spec Target does not match Candidate dataset")
    base = evaluate_candidate_ranking_slice(dataset, ranking, top_k=spec.top_k)
    target_by_symbol = {row.symbol: row.target for row in dataset.rows}
    candidate_values = tuple(
        float(row.target.value)
        for row in dataset.rows
        if row.target.status is TargetObservationStatus.AVAILABLE
        and row.target.value is not None
    )
    ranked_values_list: list[float] = []
    for prediction in ranking.predictions:
        target = target_by_symbol[prediction.symbol]
        if target.status is not TargetObservationStatus.AVAILABLE:
            continue
        assert target.value is not None
        ranked_values_list.append(float(target.value))
    top_k_values_list: list[float] = []
    for prediction in ranking.predictions[: spec.top_k]:
        target = target_by_symbol[prediction.symbol]
        if target.status is not TargetObservationStatus.AVAILABLE:
            continue
        assert target.value is not None
        top_k_values_list.append(float(target.value))
    ranked_values = tuple(ranked_values_list)
    top_k_values = tuple(top_k_values_list)
    candidate_counts = _outcome_counts(candidate_values)
    ranked_counts = _outcome_counts(ranked_values)
    top_k_counts = _outcome_counts(top_k_values)
    return CandidateDirectionalSliceEvaluation(
        spec_id=spec.spec_id,
        dataset_id=dataset.dataset_id,
        experiment_id=ranking.experiment_id,
        model_id=ranking.model_id,
        target_id=dataset.target_id,
        decision_time=dataset.decision_time,
        candidate_population_size=base.candidate_population_size,
        ranked_population_size=base.ranked_population_size,
        target_available_population_size=base.target_available_population_size,
        target_coverage=base.target_coverage,
        top_k_requested=spec.top_k,
        top_k_observed_coverage=top_k_counts.observed_count / spec.top_k,
        candidate_population=candidate_counts,
        ranked_population=ranked_counts,
        top_k=top_k_counts,
        top_k_positive_rate_lift=_difference(
            top_k_counts.positive_rate,
            candidate_counts.positive_rate,
        ),
        top_k_negative_rate_reduction=_difference(
            candidate_counts.negative_rate,
            top_k_counts.negative_rate,
        ),
    )


def evaluate_candidate_directional_accuracy_panel(
    panel: CandidateResearchPanel,
    rankings: tuple[CandidateRankingLike, ...],
    *,
    spec: CandidateDirectionalAccuracySpec,
) -> CandidateDirectionalPanelEvaluation:
    """Aggregate exact chronological slice coverage under one Model Identity."""

    if panel.target_id != spec.target_id:
        raise ValueError("directional accuracy spec Target does not match Candidate panel")
    ranking_by_dataset = {ranking.dataset_id: ranking for ranking in rankings}
    if len(ranking_by_dataset) != len(rankings):
        raise ValueError("rankings must have unique Candidate dataset identities")
    if set(ranking_by_dataset) != set(panel.slice_dataset_ids):
        raise ValueError("rankings must cover every Candidate panel slice exactly once")
    ordered_rankings = tuple(
        ranking_by_dataset[slice_.dataset_id] for slice_ in panel.slices
    )
    model_ids = {ranking.model_id for ranking in ordered_rankings}
    if len(model_ids) != 1:
        raise ValueError("panel directional evaluation requires one Model Identity")
    model_id = next(iter(model_ids))
    slices = tuple(
        evaluate_candidate_directional_accuracy_slice(slice_, ranking, spec=spec)
        for slice_, ranking in zip(panel.slices, ordered_rankings, strict=True)
    )
    candidate_micro = _sum_counts(
        tuple(item.candidate_population for item in slices)
    )
    ranked_micro = _sum_counts(tuple(item.ranked_population for item in slices))
    top_k_micro = _sum_counts(tuple(item.top_k for item in slices))
    comparable = tuple(
        item
        for item in slices
        if item.top_k.positive_rate is not None
        and item.candidate_population.positive_rate is not None
    )
    improved_count = sum(
        item.top_k.positive_rate > item.candidate_population.positive_rate
        for item in comparable
        if item.top_k.positive_rate is not None
        and item.candidate_population.positive_rate is not None
    )
    return CandidateDirectionalPanelEvaluation(
        spec_id=spec.spec_id,
        panel_dataset_id=panel.dataset_id,
        model_id=model_id,
        target_id=panel.target_id,
        slice_evaluations=slices,
        candidate_population_size=sum(item.candidate_population_size for item in slices),
        ranked_population_size=sum(item.ranked_population_size for item in slices),
        micro_candidate_population=candidate_micro,
        micro_ranked_population=ranked_micro,
        micro_top_k=top_k_micro,
        macro_candidate_positive_rate=_defined_mean(
            tuple(item.candidate_population.positive_rate for item in slices)
        ),
        macro_ranked_positive_rate=_defined_mean(
            tuple(item.ranked_population.positive_rate for item in slices)
        ),
        macro_top_k_positive_rate=_defined_mean(
            tuple(item.top_k.positive_rate for item in slices)
        ),
        macro_top_k_negative_rate=_defined_mean(
            tuple(item.top_k.negative_rate for item in slices)
        ),
        macro_top_k_positive_rate_lift=_defined_mean(
            tuple(item.top_k_positive_rate_lift for item in slices)
        ),
        macro_top_k_negative_rate_reduction=_defined_mean(
            tuple(item.top_k_negative_rate_reduction for item in slices)
        ),
        comparable_slice_count=len(comparable),
        improved_slice_count=improved_count,
        improved_slice_fraction=_optional_ratio(improved_count, len(comparable)),
    )


def _outcome_counts(values: tuple[float, ...]) -> DirectionalOutcomeCounts:
    return DirectionalOutcomeCounts(
        observed_count=len(values),
        positive_count=sum(value > 0.0 for value in values),
        negative_count=sum(value < 0.0 for value in values),
        neutral_count=sum(value == 0.0 for value in values),
    )


def _sum_counts(groups: tuple[DirectionalOutcomeCounts, ...]) -> DirectionalOutcomeCounts:
    return DirectionalOutcomeCounts(
        observed_count=sum(group.observed_count for group in groups),
        positive_count=sum(group.positive_count for group in groups),
        negative_count=sum(group.negative_count for group in groups),
        neutral_count=sum(group.neutral_count for group in groups),
    )


def _defined_mean(values: tuple[float | None, ...]) -> float | None:
    defined = tuple(value for value in values if value is not None)
    return mean(defined) if defined else None


def _optional_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right
