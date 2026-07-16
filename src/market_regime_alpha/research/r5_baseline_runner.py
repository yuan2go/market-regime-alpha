"""Provider-neutral fixed B0/B1 evaluation seam for R5 Candidate research."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from market_regime_alpha.candidates.baselines import rank_candidates_by_feature
from market_regime_alpha.candidates.composite_baseline import (
    CompositeFeatureComponent,
    CompositeFeatureDirection,
    CompositeFeatureRole,
    TransparentCompositeSpec,
    rank_candidates_by_transparent_composite,
)
from market_regime_alpha.candidates.dataset import CandidateResearchDataset
from market_regime_alpha.candidates.directional_accuracy import (
    R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
    CandidateDirectionalPanelEvaluation,
    DirectionalOutcomeCounts,
    evaluate_candidate_directional_accuracy_panel,
)
from market_regime_alpha.candidates.evaluation import (
    CandidatePanelEvaluation,
    CandidateRankingLike,
    evaluate_candidate_ranking_panel,
)
from market_regime_alpha.candidates.panel import (
    CandidateResearchPanel,
    assemble_candidate_research_panel,
)
from market_regime_alpha.candidates.rehearsal_targets import (
    R5_NEXT_SESSION_RETURN_TARGET_ID,
)
from market_regime_alpha.core.identity import FeatureDefinitionId, ModelId, TargetId
from market_regime_alpha.features.rehearsal_baselines import (
    LIQUIDITY_20S_ID,
    MOMENTUM_5S_ID,
    PRICE_VS_MA20_ID,
    VOLATILITY_20S_ID,
    r5_baseline_feature_definitions,
)


@dataclass(frozen=True, slots=True)
class NamedCandidatePanelEvaluation:
    """One declared model name paired with its chronological evaluation."""

    name: str
    feature_ids: tuple[FeatureDefinitionId, ...]
    evaluation: CandidatePanelEvaluation
    directional_accuracy: NamedDirectionalAccuracy


class DirectionalAccuracyApplicability(str, Enum):
    """Whether the fixed sign diagnostic is meaningful for one Target family."""

    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class NamedDirectionalAccuracy:
    """Explicit applicable or non-applicable directional evaluation state."""

    status: DirectionalAccuracyApplicability
    spec_id: str | None
    evaluation: CandidateDirectionalPanelEvaluation | None
    reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, DirectionalAccuracyApplicability):
            raise TypeError("status must be a DirectionalAccuracyApplicability")
        if self.status is DirectionalAccuracyApplicability.APPLICABLE:
            if self.spec_id is None or self.evaluation is None:
                raise ValueError("applicable directional accuracy requires spec and evaluation")
            if self.reason is not None:
                raise ValueError("applicable directional accuracy must not carry a reason")
            if self.spec_id != self.evaluation.spec_id:
                raise ValueError("directional accuracy spec identity must match evaluation")
            return
        if self.spec_id is not None or self.evaluation is not None:
            raise ValueError("non-applicable directional accuracy cannot carry evaluation")
        if (
            not isinstance(self.reason, str)
            or not self.reason.strip()
            or self.reason != self.reason.strip()
        ):
            raise ValueError("non-applicable directional accuracy requires a reason")


@dataclass(frozen=True, slots=True)
class R5TargetBaselineRun:
    """One Target panel and the fixed, untuned B0/B1 comparisons."""

    target_id: TargetId
    panel: CandidateResearchPanel
    b0_evaluations: tuple[NamedCandidatePanelEvaluation, ...]
    b1_evaluations: tuple[NamedCandidatePanelEvaluation, ...]

    def __post_init__(self) -> None:
        if self.target_id != self.panel.target_id:
            raise ValueError("target_id must match the Candidate panel")
        if len(self.b0_evaluations) != 4:
            raise ValueError("R5 baseline run requires four B0 controls")
        if tuple(item.name for item in self.b1_evaluations) != (
            "B1-A",
            "B1-B",
            "B1-C",
            "B1-D",
            "B1-E",
        ):
            raise ValueError("R5 baseline run requires the fixed B1-A through B1-E ladder")


def r5_b1_fixed_specs() -> dict[str, TransparentCompositeSpec]:
    """Return the frozen equal-weight B1-A through B1-E ablation ladder."""

    momentum = _component(
        MOMENTUM_5S_ID,
        CompositeFeatureDirection.HIGHER_IS_BETTER,
        CompositeFeatureRole.OPPORTUNITY,
    )
    liquidity = _component(
        LIQUIDITY_20S_ID,
        CompositeFeatureDirection.HIGHER_IS_BETTER,
        CompositeFeatureRole.QUALITY,
    )
    volatility = _component(
        VOLATILITY_20S_ID,
        CompositeFeatureDirection.LOWER_IS_BETTER,
        CompositeFeatureRole.RISK_PENALTY,
    )
    price_vs_ma = _component(
        PRICE_VS_MA20_ID,
        CompositeFeatureDirection.HIGHER_IS_BETTER,
        CompositeFeatureRole.QUALITY,
    )
    return {
        "B1-A": TransparentCompositeSpec((momentum,)),
        "B1-B": TransparentCompositeSpec((momentum, liquidity)),
        "B1-C": TransparentCompositeSpec((momentum, volatility)),
        "B1-D": TransparentCompositeSpec((momentum, liquidity, volatility)),
        "B1-E": TransparentCompositeSpec(
            (momentum, liquidity, volatility, price_vs_ma)
        ),
    }


def run_r5_target_baselines(
    *,
    datasets: tuple[CandidateResearchDataset, ...],
    code_revision: str,
    config_hash: str,
    model_identity_prefix: str,
    panel_limitations: tuple[str, ...] = (),
) -> R5TargetBaselineRun:
    """Evaluate the fixed B0 controls and B1 ablations for one Target family."""

    _require_non_empty("model_identity_prefix", model_identity_prefix)
    panel = assemble_candidate_research_panel(
        datasets,
        limitations=panel_limitations,
    )
    b0: list[NamedCandidatePanelEvaluation] = []
    for definition in r5_baseline_feature_definitions():
        model_id = ModelId(f"{model_identity_prefix}-b0-{definition.feature_id.value}")
        b0_rankings = tuple(
            rank_candidates_by_feature(
                dataset,
                feature_id=definition.feature_id,
                model_id=model_id,
                code_revision=code_revision,
                config_hash=config_hash,
            )
            for dataset in datasets
        )
        b0.append(
            NamedCandidatePanelEvaluation(
                name=f"B0-{definition.feature_id.value}",
                feature_ids=(definition.feature_id,),
                evaluation=evaluate_candidate_ranking_panel(panel, b0_rankings, top_k=5),
                directional_accuracy=_directional_accuracy(panel, b0_rankings),
            )
        )

    b1: list[NamedCandidatePanelEvaluation] = []
    for name, spec in r5_b1_fixed_specs().items():
        model_id = ModelId(f"{model_identity_prefix}-{name.lower()}-v1")
        b1_rankings = tuple(
            rank_candidates_by_transparent_composite(
                dataset,
                spec=spec,
                model_id=model_id,
                code_revision=code_revision,
                config_hash=config_hash,
            )
            for dataset in datasets
        )
        b1.append(
            NamedCandidatePanelEvaluation(
                name=name,
                feature_ids=tuple(component.feature_id for component in spec.components),
                evaluation=evaluate_candidate_ranking_panel(panel, b1_rankings, top_k=5),
                directional_accuracy=_directional_accuracy(panel, b1_rankings),
            )
        )
    return R5TargetBaselineRun(
        target_id=panel.target_id,
        panel=panel,
        b0_evaluations=tuple(b0),
        b1_evaluations=tuple(b1),
    )


def candidate_evaluation_record(
    item: NamedCandidatePanelEvaluation,
) -> dict[str, object]:
    """Return one descriptive evaluation as a JSON-ready record."""

    evaluation = item.evaluation
    return {
        "name": item.name,
        "model_id": str(evaluation.model_id),
        "feature_ids": [str(value) for value in item.feature_ids],
        "slice_count": evaluation.slice_count,
        "candidate_population_size": evaluation.candidate_population_size,
        "ranked_population_size": evaluation.ranked_population_size,
        "evaluated_prediction_count": evaluation.evaluated_prediction_count,
        "ranking_coverage": evaluation.ranking_coverage,
        "evaluated_prediction_coverage": evaluation.evaluated_prediction_coverage,
        "mean_slice_rank_ic": evaluation.mean_slice_rank_ic,
        "mean_slice_top_k_target": evaluation.mean_slice_top_k_target,
        "directional_accuracy": _directional_accuracy_record(
            item.directional_accuracy
        ),
    }


def _directional_accuracy(
    panel: CandidateResearchPanel,
    rankings: tuple[CandidateRankingLike, ...],
) -> NamedDirectionalAccuracy:
    if panel.target_id != R5_NEXT_SESSION_RETURN_TARGET_ID:
        return NamedDirectionalAccuracy(
            status=DirectionalAccuracyApplicability.NOT_APPLICABLE,
            spec_id=None,
            evaluation=None,
            reason="TARGET_SEMANTICS_NOT_POSITIVE_CLOSE_RETURN",
        )
    evaluation = evaluate_candidate_directional_accuracy_panel(
        panel,
        rankings,
        spec=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
    )
    return NamedDirectionalAccuracy(
        status=DirectionalAccuracyApplicability.APPLICABLE,
        spec_id=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC.spec_id,
        evaluation=evaluation,
        reason=None,
    )


def _directional_accuracy_record(
    value: NamedDirectionalAccuracy,
) -> dict[str, object]:
    return {
        "status": value.status.value,
        "spec_id": value.spec_id,
        "reason": value.reason,
        "metrics": (
            _directional_panel_record(value.evaluation)
            if value.evaluation is not None
            else None
        ),
    }


def _directional_panel_record(
    evaluation: CandidateDirectionalPanelEvaluation,
) -> dict[str, object]:
    return {
        "spec_id": evaluation.spec_id,
        "panel_dataset_id": str(evaluation.panel_dataset_id),
        "model_id": str(evaluation.model_id),
        "target_id": str(evaluation.target_id),
        "slice_count": evaluation.slice_count,
        "candidate_population_size": evaluation.candidate_population_size,
        "ranked_population_size": evaluation.ranked_population_size,
        "micro_candidate_population": _outcome_counts_record(
            evaluation.micro_candidate_population
        ),
        "micro_ranked_population": _outcome_counts_record(
            evaluation.micro_ranked_population
        ),
        "micro_top_k": _outcome_counts_record(evaluation.micro_top_k),
        "macro_candidate_positive_rate": evaluation.macro_candidate_positive_rate,
        "macro_ranked_positive_rate": evaluation.macro_ranked_positive_rate,
        "macro_top_k_positive_rate": evaluation.macro_top_k_positive_rate,
        "macro_top_k_negative_rate": evaluation.macro_top_k_negative_rate,
        "macro_top_k_positive_rate_lift": (
            evaluation.macro_top_k_positive_rate_lift
        ),
        "macro_top_k_negative_rate_reduction": (
            evaluation.macro_top_k_negative_rate_reduction
        ),
        "comparable_slice_count": evaluation.comparable_slice_count,
        "improved_slice_count": evaluation.improved_slice_count,
        "improved_slice_fraction": evaluation.improved_slice_fraction,
        "slices": [
            {
                "dataset_id": str(item.dataset_id),
                "experiment_id": str(item.experiment_id),
                "decision_time": item.decision_time.isoformat(),
                "candidate_population_size": item.candidate_population_size,
                "ranked_population_size": item.ranked_population_size,
                "target_available_population_size": (
                    item.target_available_population_size
                ),
                "target_coverage": item.target_coverage,
                "top_k_requested": item.top_k_requested,
                "top_k_observed_coverage": item.top_k_observed_coverage,
                "candidate_population": _outcome_counts_record(
                    item.candidate_population
                ),
                "ranked_population": _outcome_counts_record(
                    item.ranked_population
                ),
                "top_k": _outcome_counts_record(item.top_k),
                "top_k_positive_rate_lift": item.top_k_positive_rate_lift,
                "top_k_negative_rate_reduction": (
                    item.top_k_negative_rate_reduction
                ),
            }
            for item in evaluation.slice_evaluations
        ],
    }


def _outcome_counts_record(value: DirectionalOutcomeCounts) -> dict[str, object]:
    return {
        "observed_count": value.observed_count,
        "positive_count": value.positive_count,
        "negative_count": value.negative_count,
        "neutral_count": value.neutral_count,
        "positive_rate": value.positive_rate,
        "negative_rate": value.negative_rate,
        "neutral_rate": value.neutral_rate,
    }


def _component(
    feature_id: FeatureDefinitionId,
    direction: CompositeFeatureDirection,
    role: CompositeFeatureRole,
) -> CompositeFeatureComponent:
    return CompositeFeatureComponent(
        feature_id=feature_id,
        direction=direction,
        weight=1.0,
        role=role,
    )


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
