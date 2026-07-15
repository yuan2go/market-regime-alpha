"""Transparent B1 cross-sectional composite Candidate ranking baseline.

The B1 baseline combines a small pre-declared Feature set only after within-cross-section
rank-percentile normalization. It preserves complete Candidate Population accounting, rejects
incomplete rows explicitly, and never reads future Target values when computing scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math

from market_regime_alpha.candidates.baselines import CandidateRankingRejection
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


class CompositeFeatureDirection(str, Enum):
    """Direction that maps a raw Feature ranking into a higher-is-better percentile."""

    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"


class CompositeFeatureRole(str, Enum):
    """Declared research role of one B1 component.

    The role is metadata for attribution and does not silently change the arithmetic. Direction
    controls the ranking transform; the role records whether the researcher intends the component
    as opportunity evidence, a quality descriptor, or a risk penalty.
    """

    OPPORTUNITY = "OPPORTUNITY"
    QUALITY = "QUALITY"
    RISK_PENALTY = "RISK_PENALTY"


@dataclass(frozen=True, slots=True)
class CompositeFeatureComponent:
    """One explicit component of a transparent B1 composite."""

    feature_id: FeatureDefinitionId
    direction: CompositeFeatureDirection
    weight: float
    role: CompositeFeatureRole

    def __post_init__(self) -> None:
        if not isinstance(self.direction, CompositeFeatureDirection):
            raise TypeError("direction must be a CompositeFeatureDirection")
        if not isinstance(self.role, CompositeFeatureRole):
            raise TypeError("role must be a CompositeFeatureRole")
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)):
            raise TypeError("weight must be a finite positive number")
        if not math.isfinite(float(self.weight)) or float(self.weight) <= 0.0:
            raise ValueError("weight must be a finite positive number")


@dataclass(frozen=True, slots=True)
class TransparentCompositeSpec:
    """Versioned B1 arithmetic specification.

    Equivalent common scaling of all weights is canonicalized away. Component order is also
    canonicalized by Feature Definition identity so configuration identity reflects result-affecting
    semantics rather than input ordering.
    """

    components: tuple[CompositeFeatureComponent, ...]
    normalization_version: str = "cross-sectional-average-rank-percentile-v1"
    missing_policy: str = "STRICT_COMPLETE_CASE_REJECT"

    def __post_init__(self) -> None:
        if not self.components:
            raise ValueError("transparent composite requires at least one component")
        feature_ids = [component.feature_id for component in self.components]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("transparent composite component Feature identities must be unique")
        for label, value in (
            ("normalization_version", self.normalization_version),
            ("missing_policy", self.missing_policy),
        ):
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        if self.missing_policy != "STRICT_COMPLETE_CASE_REJECT":
            raise ValueError("B1 currently supports only STRICT_COMPLETE_CASE_REJECT")

    @property
    def ordered_components(self) -> tuple[CompositeFeatureComponent, ...]:
        return tuple(sorted(self.components, key=lambda component: str(component.feature_id)))

    @property
    def normalized_components(self) -> tuple[tuple[CompositeFeatureComponent, float], ...]:
        ordered = self.ordered_components
        total = sum(float(component.weight) for component in ordered)
        return tuple((component, float(component.weight) / total) for component in ordered)

    @property
    def spec_hash(self) -> str:
        payload = {
            "schema_version": "transparent-composite-spec-v1",
            "normalization_version": self.normalization_version,
            "missing_policy": self.missing_policy,
            "components": [
                {
                    "feature_id": str(component.feature_id),
                    "direction": component.direction.value,
                    "role": component.role.value,
                    "normalized_weight": format(normalized_weight, ".17g"),
                }
                for component, normalized_weight in self.normalized_components
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CompositeCandidateRankingRun:
    """One B1 composite ranking with full-population accounting and explicit component identity."""

    dataset_id: DatasetId
    experiment_id: ExperimentId
    model_id: ModelId
    universe_id: UniverseId
    target_id: TargetId
    decision_time: DecisionTime
    component_feature_ids: tuple[FeatureDefinitionId, ...]
    composite_spec_hash: str
    normalization_version: str
    candidate_population_size: int
    ranked_population_size: int
    predictions: tuple[CandidatePrediction, ...]
    rejections: tuple[CandidateRankingRejection, ...]

    def __post_init__(self) -> None:
        if not self.component_feature_ids:
            raise ValueError("component_feature_ids must not be empty")
        if len(self.component_feature_ids) != len(set(self.component_feature_ids)):
            raise ValueError("component_feature_ids must be unique")
        if self.candidate_population_size < 0 or self.ranked_population_size < 0:
            raise ValueError("population sizes must be non-negative")
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


def rank_candidates_by_transparent_composite(
    dataset: CandidateResearchDataset,
    *,
    spec: TransparentCompositeSpec,
    model_id: ModelId,
    code_revision: str,
    config_hash: str,
) -> CompositeCandidateRankingRun:
    """Rank a strict complete-case Candidate cross-section by a transparent weighted percentile score."""

    component_indices: dict[FeatureDefinitionId, int] = {}
    materialization_ids = []
    for component in spec.ordered_components:
        try:
            feature_index = dataset.feature_definition_ids.index(component.feature_id)
        except ValueError as exc:
            raise ValueError(f"composite feature not present in Candidate dataset: {component.feature_id}") from exc
        component_indices[component.feature_id] = feature_index
        materialization_ids.append(dataset.feature_materialization_ids[feature_index])

    experiment = ExperimentIdentity(
        code_revision=code_revision,
        dataset_id=dataset.dataset_id,
        config_hash=config_hash,
        universe_id=dataset.universe_id,
        target_id=dataset.target_id,
        feature_definition_ids=tuple(component.feature_id for component in spec.ordered_components),
        feature_materialization_ids=tuple(materialization_ids),
        model_id=model_id,
        semantic_refs=(
            ("baseline_kind", "transparent_cross_sectional_composite_rank"),
            ("composite_spec_hash", spec.spec_hash),
            ("normalization_version", spec.normalization_version),
            ("missing_policy", spec.missing_policy),
        ),
    )

    complete_values: dict[str, dict[FeatureDefinitionId, float]] = {}
    rejections: list[CandidateRankingRejection] = []
    for row in dataset.rows:
        values: dict[FeatureDefinitionId, float] = {}
        rejection: CandidateRankingRejection | None = None
        for component in spec.ordered_components:
            cell = row.feature_values[component_indices[component.feature_id]]
            if cell.status is not InputAvailabilityStatus.AVAILABLE:
                rejection = CandidateRankingRejection(
                    symbol=row.symbol,
                    reason_code=f"COMPOSITE_FEATURE_{cell.status.value}",
                    feature_id=component.feature_id,
                )
                break
            if isinstance(cell.value, bool) or not isinstance(cell.value, (int, float)):
                rejection = CandidateRankingRejection(
                    symbol=row.symbol,
                    reason_code="COMPOSITE_FEATURE_NON_NUMERIC",
                    feature_id=component.feature_id,
                )
                break
            numeric = float(cell.value)
            if not math.isfinite(numeric):
                rejection = CandidateRankingRejection(
                    symbol=row.symbol,
                    reason_code="COMPOSITE_FEATURE_INVALID_NUMERIC",
                    feature_id=component.feature_id,
                )
                break
            values[component.feature_id] = numeric
        if rejection is not None:
            rejections.append(rejection)
        else:
            complete_values[row.symbol] = values

    percentiles_by_feature: dict[FeatureDefinitionId, dict[str, float]] = {}
    for component in spec.ordered_components:
        raw_values = {
            symbol: values[component.feature_id]
            for symbol, values in complete_values.items()
        }
        percentiles_by_feature[component.feature_id] = _directional_rank_percentiles(
            raw_values,
            direction=component.direction,
        )

    normalized_weights = dict(
        (component.feature_id, normalized_weight)
        for component, normalized_weight in spec.normalized_components
    )
    scores = {
        symbol: sum(
            normalized_weights[component.feature_id]
            * percentiles_by_feature[component.feature_id][symbol]
            for component in spec.ordered_components
        )
        for symbol in complete_values
    }

    ordered_scores = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
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
        for rank, (symbol, score) in enumerate(ordered_scores, start=1)
    )
    rejections.sort(key=lambda item: item.symbol)

    return CompositeCandidateRankingRun(
        dataset_id=dataset.dataset_id,
        experiment_id=experiment.experiment_id,
        model_id=model_id,
        universe_id=dataset.universe_id,
        target_id=dataset.target_id,
        decision_time=dataset.decision_time,
        component_feature_ids=tuple(component.feature_id for component in spec.ordered_components),
        composite_spec_hash=spec.spec_hash,
        normalization_version=spec.normalization_version,
        candidate_population_size=len(dataset.population_symbols),
        ranked_population_size=len(predictions),
        predictions=predictions,
        rejections=tuple(rejections),
    )


def _directional_rank_percentiles(
    values_by_symbol: dict[str, float],
    *,
    direction: CompositeFeatureDirection,
) -> dict[str, float]:
    """Return average-rank percentiles on [0, 1], where 1 is always best."""

    if not values_by_symbol:
        return {}
    reverse = direction is CompositeFeatureDirection.HIGHER_IS_BETTER
    ordered = sorted(values_by_symbol.items(), key=lambda item: item[1], reverse=reverse)
    count = len(ordered)
    if count == 1:
        return {ordered[0][0]: 1.0}

    result: dict[str, float] = {}
    position = 0
    while position < count:
        end = position + 1
        while end < count and ordered[end][1] == ordered[position][1]:
            end += 1
        average_rank = (position + 1 + end) / 2.0
        percentile = 1.0 - (average_rank - 1.0) / (count - 1.0)
        for index in range(position, end):
            result[ordered[index][0]] = percentile
        position = end
    return result
