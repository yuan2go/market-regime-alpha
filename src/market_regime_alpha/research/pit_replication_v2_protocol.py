"""Frozen protocol binding for PIT blocked/invalid evidence v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from market_regime_alpha.research.pit_replication_protocol import (
    PIT_REPLICATION_PROTOCOL_SCHEMA_VERSION,
    PITCandidateReplicationProtocol,
    frozen_pit_replication_protocol,
)
from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash


PIT_REPLICATION_V2_PROTOCOL_SCHEMA_VERSION = "pit-candidate-replication-protocol-v2"


@dataclass(frozen=True, slots=True)
class PITCandidateReplicationProtocolV2:
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
        if self.schema_version != PIT_REPLICATION_V2_PROTOCOL_SCHEMA_VERSION:
            raise ValueError("unsupported PIT replication v2 Protocol schema")
        payload = self.to_canonical_dict()
        payload["schema_version"] = PIT_REPLICATION_PROTOCOL_SCHEMA_VERSION
        payload["comparator_model_ids"] = tuple(payload["comparator_model_ids"])
        payload["matched_k_seed_set"] = tuple(payload["matched_k_seed_set"])
        PITCandidateReplicationProtocol(**payload)

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["comparator_model_ids"] = list(self.comparator_model_ids)
        payload["matched_k_seed_set"] = list(self.matched_k_seed_set)
        return payload

    @property
    def protocol_id(self) -> str:
        return canonical_identity_hash(self.to_canonical_dict())


def frozen_pit_replication_v2_protocol() -> PITCandidateReplicationProtocolV2:
    payload = frozen_pit_replication_protocol().to_canonical_dict()
    payload["schema_version"] = PIT_REPLICATION_V2_PROTOCOL_SCHEMA_VERSION
    payload["comparator_model_ids"] = tuple(payload["comparator_model_ids"])
    payload["matched_k_seed_set"] = tuple(payload["matched_k_seed_set"])
    return PITCandidateReplicationProtocolV2(**payload)
