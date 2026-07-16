"""Fixed B0 controls and B1 ablation ladder for Tencent composite research."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

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
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility, DatasetContract
from market_regime_alpha.features.rehearsal_baselines import (
    LIQUIDITY_20S_ID,
    MOMENTUM_5S_ID,
    PRICE_VS_MA20_ID,
    VOLATILITY_20S_ID,
    r5_baseline_feature_definitions,
)
from market_regime_alpha.research.tencent_composite_contracts import PreparedCompositeData
from market_regime_alpha.research.tencent_composite_materialization import (
    materialize_tencent_composite_slice,
)


@dataclass(frozen=True, slots=True)
class NamedCandidatePanelEvaluation:
    """One declared model name paired with its full chronological evaluation."""

    name: str
    feature_ids: tuple[FeatureDefinitionId, ...]
    evaluation: CandidatePanelEvaluation


@dataclass(frozen=True, slots=True)
class TencentCompositeTargetRun:
    """One Target panel and all fixed B0/B1 comparisons."""

    target_id: TargetId
    panel: CandidateResearchPanel
    b0_evaluations: tuple[NamedCandidatePanelEvaluation, ...]
    b1_evaluations: tuple[NamedCandidatePanelEvaluation, ...]


@dataclass(frozen=True, slots=True)
class TencentCompositeCandidateRun:
    """Complete three-Target, 60-date exploratory Candidate experiment."""

    data_eligibility: DataEligibility
    decision_dates: tuple[date, ...]
    accepted_symbols: tuple[str, ...]
    target_runs: tuple[TencentCompositeTargetRun, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Tencent composite Candidate run must remain EXPLORATORY")
        if len(self.decision_dates) != 60:
            raise ValueError("Tencent composite Candidate run requires exactly 60 Decision Dates")
        if tuple(sorted(self.decision_dates)) != self.decision_dates:
            raise ValueError("decision_dates must be chronological")
        if len(self.target_runs) != 3:
            raise ValueError("Tencent composite Candidate run requires three Target families")

    @property
    def decision_date_count(self) -> int:
        return len(self.decision_dates)

    def panel_summary(self) -> dict[str, object]:
        """Return a JSON-ready summary without promoting model evidence."""

        return {
            "data_eligibility": self.data_eligibility.value,
            "decision_date_count": self.decision_date_count,
            "decision_dates": [value.isoformat() for value in self.decision_dates],
            "accepted_symbols": list(self.accepted_symbols),
            "limitations": list(self.limitations),
            "targets": [
                {
                    "target_id": str(target.target_id),
                    "panel_dataset_id": str(target.panel.dataset_id),
                    "slice_count": target.panel.slice_count,
                    "row_count": target.panel.row_count,
                    "data_eligibility": target.panel.data_eligibility.value,
                }
                for target in self.target_runs
            ],
        }

    def evaluation_summary(self) -> dict[str, object]:
        """Return descriptive B0/B1 metrics with no winner selection."""

        return {
            "selection_policy": "FIXED_UNTUNED_NO_WINNER_SELECTION",
            "targets": [
                {
                    "target_id": str(target.target_id),
                    "b0": [_evaluation_record(item) for item in target.b0_evaluations],
                    "b1": [_evaluation_record(item) for item in target.b1_evaluations],
                }
                for target in self.target_runs
            ],
        }


def r5_b1_exploratory_specs() -> dict[str, TransparentCompositeSpec]:
    """Return the frozen, equal-weight B1-A through B1-E ablation ladder."""

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


def run_tencent_composite_candidate_experiment(
    *,
    prepared: PreparedCompositeData,
    dataset_contract: DatasetContract,
    retrieved_at: RetrievedAt,
    code_revision: str,
    config_hash: str,
) -> TencentCompositeCandidateRun:
    """Materialize and evaluate exactly 60 completed Decision Dates."""

    if dataset_contract.eligibility is not DataEligibility.EXPLORATORY:
        raise ValueError("Tencent composite experiment requires EXPLORATORY data")
    if len(prepared.accepted_symbols) < 16:
        raise ValueError("Tencent composite experiment requires at least 16 accepted symbols")
    if len(prepared.common_session_dates) < 82:
        raise ValueError("Tencent composite experiment requires at least 82 common sessions")

    decision_dates = prepared.common_session_dates[-61:-1]
    datasets_by_target: dict[TargetId, list[CandidateResearchDataset]] = defaultdict(list)
    for decision_date in decision_dates:
        datasets = materialize_tencent_composite_slice(
            prepared=prepared,
            decision_date=decision_date,
            dataset_contract=dataset_contract,
            retrieved_at=retrieved_at,
            code_revision=code_revision,
            config_hash=config_hash,
        )
        for dataset in datasets:
            datasets_by_target[dataset.target_id].append(dataset)

    target_runs = tuple(
        _run_target_models(
            datasets=tuple(datasets_by_target[target_id]),
            code_revision=code_revision,
            config_hash=config_hash,
        )
        for target_id in sorted(datasets_by_target, key=str)
    )
    limitations = tuple(
        dict.fromkeys(
            (
                *dataset_contract.limitations,
                *prepared.limitations,
                "FIXED_B0_B1_LADDER_NOT_MODEL_SELECTION",
                "DESCRIPTIVE_EXPLORATORY_METRICS_NOT_ALPHA_EVIDENCE",
            )
        )
    )
    return TencentCompositeCandidateRun(
        data_eligibility=DataEligibility.EXPLORATORY,
        decision_dates=decision_dates,
        accepted_symbols=tuple(sorted(prepared.accepted_symbols)),
        target_runs=target_runs,
        limitations=limitations,
    )


def _run_target_models(
    *,
    datasets: tuple[CandidateResearchDataset, ...],
    code_revision: str,
    config_hash: str,
) -> TencentCompositeTargetRun:
    panel = assemble_candidate_research_panel(
        datasets,
        limitations=("TENCENT_COMPOSITE_EXPLORATORY",),
    )
    b0: list[NamedCandidatePanelEvaluation] = []
    for definition in r5_baseline_feature_definitions():
        model_id = ModelId(f"tencent-exploratory-b0-{definition.feature_id.value}")
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
    for name, spec in r5_b1_exploratory_specs().items():
        model_id = ModelId(f"tencent-exploratory-{name.lower()}-v1")
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
    return TencentCompositeTargetRun(
        target_id=panel.target_id,
        panel=panel,
        b0_evaluations=tuple(b0),
        b1_evaluations=tuple(b1),
    )


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


def _evaluation_record(item: NamedCandidatePanelEvaluation) -> dict[str, object]:
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
