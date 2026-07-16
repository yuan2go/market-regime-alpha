"""Fixed B0 controls and B1 ablation ladder for Tencent composite research."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from market_regime_alpha.candidates.composite_baseline import TransparentCompositeSpec
from market_regime_alpha.candidates.dataset import CandidateResearchDataset
from market_regime_alpha.core.identity import TargetId
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility, DatasetContract
from market_regime_alpha.research.r5_baseline_runner import (
    NamedCandidatePanelEvaluation as _NamedCandidatePanelEvaluation,
    R5TargetBaselineRun,
    candidate_evaluation_record,
    r5_b1_fixed_specs,
    run_r5_target_baselines,
)
from market_regime_alpha.research.tencent_composite_contracts import PreparedCompositeData
from market_regime_alpha.research.tencent_composite_materialization import (
    materialize_tencent_composite_slice,
)


NamedCandidatePanelEvaluation = _NamedCandidatePanelEvaluation
TencentCompositeTargetRun = R5TargetBaselineRun


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
                    "b0": [
                        candidate_evaluation_record(item)
                        for item in target.b0_evaluations
                    ],
                    "b1": [
                        candidate_evaluation_record(item)
                        for item in target.b1_evaluations
                    ],
                }
                for target in self.target_runs
            ],
        }


def r5_b1_exploratory_specs() -> dict[str, TransparentCompositeSpec]:
    """Return the frozen, equal-weight B1-A through B1-E ablation ladder."""

    return r5_b1_fixed_specs()


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
        run_r5_target_baselines(
            datasets=tuple(datasets_by_target[target_id]),
            code_revision=code_revision,
            config_hash=config_hash,
            model_identity_prefix="tencent-exploratory",
            panel_limitations=("TENCENT_COMPOSITE_EXPLORATORY",),
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
