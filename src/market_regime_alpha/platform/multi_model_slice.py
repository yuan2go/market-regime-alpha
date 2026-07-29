"""First vertical slice: comparable multi-model Candidate ranking.

The slice runs multiple fixed model specifications against one immutable
CandidateResearchDataset. It enforces one Universe, Decision Time, Target, and
population, preserving complete ranking/rejection evidence for each model.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
import json
from typing import TypeAlias

from market_regime_alpha.candidates.baselines import (
    CandidateRankingRun,
    CandidateRankingRejection,
    rank_candidates_by_feature,
)
from market_regime_alpha.candidates.composite_baseline import (
    CompositeCandidateRankingRun,
    CompositeFeatureComponent,
    CompositeFeatureDirection,
    CompositeFeatureRole,
    TransparentCompositeSpec,
    rank_candidates_by_transparent_composite,
)
from market_regime_alpha.candidates.contracts import CandidatePrediction
from market_regime_alpha.candidates.dataset import CandidateResearchDataset
from market_regime_alpha.core.identity import ExperimentId, FeatureDefinitionId, ModelId


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class SingleFeatureCandidateModelSpec:
    model_id: ModelId
    feature_id: FeatureDefinitionId
    config_version: str = "single-feature-candidate-v1"

    def __post_init__(self) -> None:
        _require_non_empty("config_version", self.config_version)

    @property
    def config_hash(self) -> str:
        payload = {
            "kind": "SINGLE_FEATURE",
            "model_id": str(self.model_id),
            "feature_id": str(self.feature_id),
            "config_version": self.config_version,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CompositeCandidateModelSpec:
    model_id: ModelId
    composite: TransparentCompositeSpec
    config_version: str = "transparent-composite-candidate-v1"

    def __post_init__(self) -> None:
        _require_non_empty("config_version", self.config_version)

    @property
    def config_hash(self) -> str:
        payload = {
            "kind": "TRANSPARENT_COMPOSITE",
            "model_id": str(self.model_id),
            "composite_spec_hash": self.composite.spec_hash,
            "config_version": self.config_version,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


CandidateModelSpec: TypeAlias = SingleFeatureCandidateModelSpec | CompositeCandidateModelSpec


@dataclass(frozen=True, slots=True)
class ModelSliceResult:
    model_id: ModelId
    experiment_id: ExperimentId
    config_hash: str
    ranking_coverage: float
    predictions: tuple[CandidatePrediction, ...]
    rejections: tuple[CandidateRankingRejection, ...]


@dataclass(frozen=True, slots=True)
class PairwiseTopKOverlap:
    model_a: ModelId
    model_b: ModelId
    top_k: int
    overlap_count: int
    union_count: int
    jaccard: float


@dataclass(frozen=True, slots=True)
class MultiModelCandidateSliceRun:
    dataset_id: str
    universe_id: str
    target_id: str
    decision_time: str
    population_size: int
    top_k_values: tuple[int, ...]
    results: tuple[ModelSliceResult, ...]
    overlaps: tuple[PairwiseTopKOverlap, ...]


def build_default_candidate_slice_specs(
    *,
    momentum_feature_id: FeatureDefinitionId,
    volume_feature_id: FeatureDefinitionId,
    volatility_feature_id: FeatureDefinitionId,
) -> tuple[CandidateModelSpec, ...]:
    """Return the frozen B0/B1/B2 model ladder for the first platform slice."""

    return (
        SingleFeatureCandidateModelSpec(
            model_id=ModelId("platform-b0-momentum-v1"),
            feature_id=momentum_feature_id,
        ),
        CompositeCandidateModelSpec(
            model_id=ModelId("platform-b1-balanced-v1"),
            composite=TransparentCompositeSpec(
                components=(
                    CompositeFeatureComponent(
                        momentum_feature_id,
                        CompositeFeatureDirection.HIGHER_IS_BETTER,
                        0.50,
                        CompositeFeatureRole.OPPORTUNITY,
                    ),
                    CompositeFeatureComponent(
                        volume_feature_id,
                        CompositeFeatureDirection.HIGHER_IS_BETTER,
                        0.30,
                        CompositeFeatureRole.QUALITY,
                    ),
                    CompositeFeatureComponent(
                        volatility_feature_id,
                        CompositeFeatureDirection.LOWER_IS_BETTER,
                        0.20,
                        CompositeFeatureRole.RISK_PENALTY,
                    ),
                )
            ),
        ),
        CompositeCandidateModelSpec(
            model_id=ModelId("platform-b2-volume-momentum-v1"),
            composite=TransparentCompositeSpec(
                components=(
                    CompositeFeatureComponent(
                        momentum_feature_id,
                        CompositeFeatureDirection.HIGHER_IS_BETTER,
                        0.45,
                        CompositeFeatureRole.OPPORTUNITY,
                    ),
                    CompositeFeatureComponent(
                        volume_feature_id,
                        CompositeFeatureDirection.HIGHER_IS_BETTER,
                        0.55,
                        CompositeFeatureRole.OPPORTUNITY,
                    ),
                )
            ),
        ),
    )


def run_multi_model_candidate_slice(
    dataset: CandidateResearchDataset,
    *,
    model_specs: tuple[CandidateModelSpec, ...],
    code_revision: str,
    top_k_values: tuple[int, ...] = (5, 10, 20),
) -> MultiModelCandidateSliceRun:
    """Run fixed candidate models under one directly comparable research scope."""

    _require_non_empty("code_revision", code_revision)
    if len(model_specs) < 2:
        raise ValueError("multi-model slice requires at least two models")
    model_ids = tuple(spec.model_id for spec in model_specs)
    if len(model_ids) != len(set(model_ids)):
        raise ValueError("model_specs must have unique model identities")
    if not top_k_values or tuple(sorted(top_k_values)) != top_k_values or len(top_k_values) != len(set(top_k_values)):
        raise ValueError("top_k_values must be non-empty, unique, and sorted")
    if any(value <= 0 for value in top_k_values):
        raise ValueError("top_k_values must be positive")

    results: list[ModelSliceResult] = []
    for spec in model_specs:
        run: CandidateRankingRun | CompositeCandidateRankingRun
        if isinstance(spec, SingleFeatureCandidateModelSpec):
            run = rank_candidates_by_feature(
                dataset,
                feature_id=spec.feature_id,
                model_id=spec.model_id,
                code_revision=code_revision,
                config_hash=spec.config_hash,
            )
        else:
            run = rank_candidates_by_transparent_composite(
                dataset,
                spec=spec.composite,
                model_id=spec.model_id,
                code_revision=code_revision,
                config_hash=spec.config_hash,
            )
        results.append(
            ModelSliceResult(
                model_id=spec.model_id,
                experiment_id=run.experiment_id,
                config_hash=spec.config_hash,
                ranking_coverage=run.ranking_coverage,
                predictions=run.predictions,
                rejections=run.rejections,
            )
        )

    overlaps: list[PairwiseTopKOverlap] = []
    for first, second in combinations(results, 2):
        for top_k in top_k_values:
            first_symbols = {item.symbol for item in first.predictions[:top_k]}
            second_symbols = {item.symbol for item in second.predictions[:top_k]}
            union = first_symbols | second_symbols
            intersection = first_symbols & second_symbols
            overlaps.append(
                PairwiseTopKOverlap(
                    model_a=first.model_id,
                    model_b=second.model_id,
                    top_k=top_k,
                    overlap_count=len(intersection),
                    union_count=len(union),
                    jaccard=(len(intersection) / len(union)) if union else 0.0,
                )
            )

    return MultiModelCandidateSliceRun(
        dataset_id=str(dataset.dataset_id),
        universe_id=str(dataset.universe_id),
        target_id=str(dataset.target_id),
        decision_time=dataset.decision_time.isoformat(),
        population_size=len(dataset.population_symbols),
        top_k_values=top_k_values,
        results=tuple(results),
        overlaps=tuple(overlaps),
    )
