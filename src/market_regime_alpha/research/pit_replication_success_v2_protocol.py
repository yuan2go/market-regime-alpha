"""Frozen protocol for sealed PIT Candidate replication success evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash
from market_regime_alpha.research.r5_baseline_runner import r5_b1_fixed_specs


@dataclass(frozen=True, slots=True)
class PITCandidateReplicationProtocolV2:
    schema_version: str
    experiment_id: str
    ranking_model_id: str
    ranking_model_spec_hash: str
    ranking_dataset_target_id: str
    primary_evaluation_mark_id: str
    primary_evaluation_time: str
    primary_return_definition_id: str
    path_target_ids: tuple[str, ...]
    cost_model_id: str
    cost_scenario: str
    top_k: int
    universe_contract_id: str
    eligibility_policy_id: str
    orderability_policy_id: str
    matched_k_algorithm_id: str
    matched_k_seed_set: tuple[int, ...]
    minimum_decision_dates: int
    minimum_average_population_size: int
    minimum_symbol_coverage: float
    economic_effect_floor: float
    bootstrap_method_id: str
    bootstrap_draws: int
    bootstrap_block_length: int
    bootstrap_seed: int
    bootstrap_interval: float
    rolling_window: int
    largest_contribution_limit: float
    top_3_contribution_limit: float
    required_positive_seed_panels: int
    cost_robustness_scenarios: tuple[str, ...]
    authority_ceiling: str

    def __post_init__(self) -> None:
        if self.schema_version != "pit-candidate-replication-protocol-v2":
            raise ValueError("PIT replication success Protocol schema mismatch")
        if self.ranking_model_id != "prr-mvp-1-b1-e-v1" or self.top_k != 5:
            raise ValueError("PIT replication freezes B1-E Top-5")
        if self.ranking_model_spec_hash != r5_b1_fixed_specs()["B1-E"].spec_hash:
            raise ValueError("PIT replication B1-E model specification mismatch")
        if self.ranking_dataset_target_id == self.primary_evaluation_mark_id:
            raise ValueError("ranking Target and evaluation mark must remain separate")
        if self.primary_evaluation_time != "10:30":
            raise ValueError("PIT replication evaluation time is frozen at 10:30")
        if self.cost_scenario != "BASE" or self.top_k != 5:
            raise ValueError("PIT replication cost/Top-K contract mismatch")
        if self.matched_k_seed_set != tuple(range(256)):
            raise ValueError("PIT replication matched-K seeds must be 0..255")
        if self.cost_robustness_scenarios != ("LOW", "BASE", "HIGH"):
            raise ValueError("PIT replication cost robustness scenarios are frozen")
        if self.required_positive_seed_panels != 4:
            raise ValueError("PIT replication requires all four seed panels")
        if self.minimum_decision_dates <= 0 or self.minimum_average_population_size <= 0:
            raise ValueError("PIT replication sample requirements must be positive")
        if not 0 < self.minimum_symbol_coverage <= 1:
            raise ValueError("PIT replication symbol coverage must be in (0, 1]")
        if self.authority_ceiling not in {
            "REHEARSAL_NOT_FORMAL_OOS",
            "TEST_ONLY_NOT_RESEARCH_EVIDENCE",
        }:
            raise ValueError("PIT replication authority ceiling is invalid")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["path_target_ids"] = list(self.path_target_ids)
        payload["matched_k_seed_set"] = list(self.matched_k_seed_set)
        payload["cost_robustness_scenarios"] = list(self.cost_robustness_scenarios)
        return payload

    @property
    def protocol_id(self) -> str:
        return canonical_identity_hash(self.to_canonical_dict())


def frozen_pit_replication_success_v2_protocol(
    *, test_only: bool = False
) -> PITCandidateReplicationProtocolV2:
    return PITCandidateReplicationProtocolV2(
        schema_version="pit-candidate-replication-protocol-v2",
        experiment_id="pit-b1e-unconditional-candidate-lift-replication-v2",
        ranking_model_id="prr-mvp-1-b1-e-v1",
        ranking_model_spec_hash=r5_b1_fixed_specs()["B1-E"].spec_hash,
        ranking_dataset_target_id="target-r5-decision-reference-to-next-session-close-return-v1",
        primary_evaluation_mark_id="next-session-exact-1030-unadjusted-mark-v1",
        primary_evaluation_time="10:30",
        primary_return_definition_id="decision-reference-to-next-session-1030-return-v1",
        path_target_ids=("MORNING_UP_005_DOWN_005_V1",),
        cost_model_id="mr1-exploratory-reference-cost-v1",
        cost_scenario="BASE",
        top_k=5,
        universe_contract_id="historical-pit-universe-artifact-v2",
        eligibility_policy_id="r5-provider-rehearsal-trading-eligibility@v2",
        orderability_policy_id="xuntou-research-orderability-v4",
        matched_k_algorithm_id="mr1-matched-k-sha256-rank-blind-v1",
        matched_k_seed_set=tuple(range(256)),
        minimum_decision_dates=2 if test_only else 250,
        minimum_average_population_size=5 if test_only else 100,
        minimum_symbol_coverage=1.0 if test_only else 0.95,
        economic_effect_floor=0.001,
        bootstrap_method_id="circular-moving-block-bootstrap-daily-lift-v1",
        bootstrap_draws=100 if test_only else 10_000,
        bootstrap_block_length=2 if test_only else 5,
        bootstrap_seed=20260718,
        bootstrap_interval=0.95,
        rolling_window=2 if test_only else 20,
        largest_contribution_limit=0.50,
        top_3_contribution_limit=0.75,
        required_positive_seed_panels=4,
        cost_robustness_scenarios=("LOW", "BASE", "HIGH"),
        authority_ceiling=(
            "TEST_ONLY_NOT_RESEARCH_EVIDENCE" if test_only else "REHEARSAL_NOT_FORMAL_OOS"
        ),
    )
