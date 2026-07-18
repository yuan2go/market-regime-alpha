"""Frozen governance contract for PIT Candidate replication validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from market_regime_alpha.research.r5_baseline_runner import r5_b1_fixed_specs
from market_regime_alpha.research.xuntou_provider_adapter import XUNTOU_LIQUIDITY_MEASURE_ID
from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash


PIT_REPLICATION_PROTOCOL_SCHEMA_VERSION = "pit-candidate-replication-protocol-v1"
PIT_REPLICATION_EXPERIMENT_ID = "pit-b1e-unconditional-candidate-lift-replication-v1"
PIT_REPLICATION_MATCHED_K_ALGORITHM_ID = "mr1-matched-k-sha256-rank-blind-v1"
PIT_REPLICATION_UNIVERSE_CONTRACT_ID = "historical-pit-universe-artifact-v2"
PIT_REPLICATION_ELIGIBILITY_POLICY_ID = "r5-provider-rehearsal-trading-eligibility@v2"
PIT_REPLICATION_BUYABILITY_POLICY_ID = "xuntou-explicit-decision-buyability-fail-closed-v1"
PIT_REPLICATION_PRIMARY_METRIC_ID = "daily-net-lift-vs-model-population-multiseed-median-v1"


@dataclass(frozen=True, slots=True)
class PITCandidateReplicationProtocol:
    schema_version: str
    experiment_id: str
    candidate_model_id: str
    candidate_model_spec_hash: str
    comparator_model_ids: tuple[str, ...]
    target_id: str
    exit_time: str
    cost_scenario: str
    top_k: int
    context_id: str | None
    universe_contract_id: str
    eligibility_policy_id: str
    buyability_policy_id: str
    liquidity_measure_id: str
    minimum_liquidity_value: float
    matched_k_algorithm_id: str
    matched_k_seed_set: tuple[int, ...]
    primary_metric_id: str
    development_partition_id: str
    validation_partition_id: str
    oos_partition_id: str | None
    minimum_decision_dates: int
    minimum_average_population_size: int
    minimum_symbol_coverage: float
    feature_tuning_policy: str
    model_winner_selection: str
    authority_ceiling: str

    def __post_init__(self) -> None:
        if self.schema_version != PIT_REPLICATION_PROTOCOL_SCHEMA_VERSION:
            raise ValueError("unsupported PIT replication Protocol schema")
        if self.candidate_model_id != "prr-mvp-1-b1-e-v1" or self.top_k != 5:
            raise ValueError("PIT replication Candidate model and Top-K are frozen")
        if self.context_id is not None:
            raise ValueError("PIT replication must remain unconditional")
        partitions = tuple(
            value for value in (
                self.development_partition_id,
                self.validation_partition_id,
                self.oos_partition_id,
            ) if value is not None
        )
        if len(partitions) != len(set(partitions)):
            raise ValueError("PIT replication partition identities must not overlap")
        if self.feature_tuning_policy != "FORBIDDEN_ON_VALIDATION_PARTITION":
            raise ValueError("Feature tuning on validation is forbidden")
        if self.model_winner_selection != "FORBIDDEN":
            raise ValueError("model winner selection is forbidden")
        if not self.matched_k_seed_set or len(self.matched_k_seed_set) != len(set(self.matched_k_seed_set)):
            raise ValueError("matched-K seed set must be non-empty and unique")
        if tuple(sorted(self.matched_k_seed_set)) != self.matched_k_seed_set:
            raise ValueError("matched-K seed set must be ordered")
        if self.minimum_decision_dates <= 0 or self.minimum_average_population_size <= 0:
            raise ValueError("PIT replication minimum sample requirements must be positive")
        if not 0 < self.minimum_symbol_coverage <= 1:
            raise ValueError("PIT replication symbol coverage must be within (0, 1]")
        if self.authority_ceiling != "REHEARSAL_NOT_FORMAL_OOS":
            raise ValueError("PIT replication authority ceiling is invalid")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["comparator_model_ids"] = list(self.comparator_model_ids)
        payload["matched_k_seed_set"] = list(self.matched_k_seed_set)
        return payload

    @property
    def protocol_id(self) -> str:
        return canonical_identity_hash(self.to_canonical_dict())


@dataclass(frozen=True, slots=True)
class CandidateFeatureExperiment:
    experiment_id: str
    base_model_id: str
    added_feature_ids: tuple[str, ...]
    removed_feature_ids: tuple[str, ...]
    development_partition_id: str
    validation_partition_id: str | None
    status: str

    def __post_init__(self) -> None:
        if not self.experiment_id or not self.base_model_id:
            raise ValueError("Feature experiment identities must be non-empty")
        if self.status == "TUNING_ON_VALIDATION":
            raise ValueError("validation partition cannot be used for Feature tuning")
        if self.validation_partition_id == self.development_partition_id:
            raise ValueError("Feature experiment partitions must not overlap")


def frozen_pit_replication_protocol() -> PITCandidateReplicationProtocol:
    spec = r5_b1_fixed_specs()["B1-E"]
    return PITCandidateReplicationProtocol(
        schema_version=PIT_REPLICATION_PROTOCOL_SCHEMA_VERSION,
        experiment_id=PIT_REPLICATION_EXPERIMENT_ID,
        candidate_model_id="prr-mvp-1-b1-e-v1",
        candidate_model_spec_hash=spec.spec_hash,
        comparator_model_ids=("MODEL_POPULATION_ALL_CANDIDATE", "MULTISEED_MATCHED_K_MEDIAN"),
        target_id="target-r5-decision-reference-to-next-session-close-return-v1",
        exit_time="10:30",
        cost_scenario="BASE",
        top_k=5,
        context_id=None,
        universe_contract_id=PIT_REPLICATION_UNIVERSE_CONTRACT_ID,
        eligibility_policy_id=PIT_REPLICATION_ELIGIBILITY_POLICY_ID,
        buyability_policy_id=PIT_REPLICATION_BUYABILITY_POLICY_ID,
        liquidity_measure_id=XUNTOU_LIQUIDITY_MEASURE_ID,
        minimum_liquidity_value=50_000_000.0,
        matched_k_algorithm_id=PIT_REPLICATION_MATCHED_K_ALGORITHM_ID,
        matched_k_seed_set=tuple(range(256)),
        primary_metric_id=PIT_REPLICATION_PRIMARY_METRIC_ID,
        development_partition_id="DEVELOPMENT_EXPLORATORY_CURRENT_60_V1",
        validation_partition_id="REPLICATION_VALIDATION_FUTURE_XUNTOU_PIT_V1",
        oos_partition_id=None,
        minimum_decision_dates=250,
        minimum_average_population_size=100,
        minimum_symbol_coverage=0.95,
        feature_tuning_policy="FORBIDDEN_ON_VALIDATION_PARTITION",
        model_winner_selection="FORBIDDEN",
        authority_ceiling="REHEARSAL_NOT_FORMAL_OOS",
    )
