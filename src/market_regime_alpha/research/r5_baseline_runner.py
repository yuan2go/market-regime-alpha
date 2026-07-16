"""Provider-neutral fixed B0/B1 evaluation seam for R5 Candidate research."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime_alpha.candidates.baselines import rank_candidates_by_feature
from market_regime_alpha.candidates.composite_baseline import (
    CompositeFeatureComponent,
    CompositeFeatureDirection,
    CompositeFeatureRole,
    TransparentCompositeSpec,
    rank_candidates_by_transparent_composite,
)
from market_regime_alpha.candidates.dataset import CandidateResearchDataset
from market_regime_alpha.candidates.evaluation import (
    CandidatePanelEvaluation,
    evaluate_candidate_ranking_panel,
)
from market_regime_alpha.candidates.panel import (
    CandidateResearchPanel,
    assemble_candidate_research_panel,
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
