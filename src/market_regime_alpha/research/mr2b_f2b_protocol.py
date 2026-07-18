"""Frozen directional protocol for MR-2B F2B statistical closure."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from market_regime_alpha.research.mr2b_context import MR2B_CONTEXT_DEFINITION_ID
from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash


F2B_PROTOCOL_SCHEMA_VERSION = "mr-2b-f2b-protocol-v1"
F2B_PRIMARY_HYPOTHESIS_ID = "mr2b-primary-b1e-1030-base-up-greater-than-down-v1"
F2B_PRIMARY_MODEL_ID = "prr-mvp-1-b1-e-v1"
F2B_PRIMARY_METRIC_ID = "daily-net-lift-vs-multiseed-matched-k-median-v1"
F2B_BOOTSTRAP_METHOD_ID = "circular-moving-block-bootstrap-paired-observations-v1"
F2B_BOOTSTRAP_INTERVAL_ID = "bootstrap-percentile-r7-v1"
F2B_RANDOMIZATION_METHOD_ID = "context-label-circular-shift-randomization-v1"
F2B_PERMUTATION_METHOD_ID = "count-preserving-label-permutation-v1"
F2B_TEMPORAL_RULE_ID = "chronological-halves-rolling20-loo-v1"
F2B_CONCENTRATION_RULE_ID = "difference-mean-absolute-contribution-v1"
F2B_SEED_PANEL_RULE_ID = "seed-modulo-four-panel-median-v1"
F2B_SECONDARY_FAMILY_ID = "mr2b-108-model-exit-cost-directional-family-v1"
F2B_MULTIPLE_TESTING_METHOD_ID = "benjamini-hochberg-fdr-v1"


@dataclass(frozen=True, slots=True)
class F2BProtocol:
    schema_version: str
    primary_hypothesis_id: str
    model_id: str
    exit_time: str
    cost_scenario: str
    context_definition_id: str
    eligible_context_labels: tuple[str, ...]
    metric_id: str
    alternative: str
    minimum_slice_size: int
    economic_effect_floor: float
    bootstrap_method_id: str
    bootstrap_draws: int
    bootstrap_block_length: int
    bootstrap_sensitivity_block_lengths: tuple[int, ...]
    bootstrap_seed: int
    bootstrap_interval: float
    bootstrap_interval_method_id: str
    primary_randomization_method_id: str
    random_permutation_method_id: str
    random_permutation_draws: int
    random_permutation_seed: int
    first_second_half_rule_id: str
    concentration_rule_id: str
    seed_panel_rule_id: str
    secondary_family_id: str
    multiple_testing_method_id: str
    multiple_testing_alpha: float
    authority_ceiling: str

    def __post_init__(self) -> None:
        if self.schema_version != F2B_PROTOCOL_SCHEMA_VERSION:
            raise ValueError("unsupported F2B protocol schema")
        if self.alternative != "UP_GREATER_THAN_DOWN":
            raise ValueError("F2B Primary alternative must remain UP_GREATER_THAN_DOWN")
        if self.eligible_context_labels != ("UP", "DOWN"):
            raise ValueError("F2B Primary labels must be the ordered UP/DOWN pair")
        if self.minimum_slice_size <= 0 or self.economic_effect_floor <= 0:
            raise ValueError("F2B slice size and economic floor must be positive")
        if self.bootstrap_draws <= 0 or self.random_permutation_draws <= 0:
            raise ValueError("F2B draw counts must be positive")
        if self.bootstrap_block_length <= 0 or any(
            value <= 0 for value in self.bootstrap_sensitivity_block_lengths
        ):
            raise ValueError("F2B block lengths must be positive")
        if not 0 < self.bootstrap_interval < 1:
            raise ValueError("F2B bootstrap interval must be within (0, 1)")
        if not 0 < self.multiple_testing_alpha < 1:
            raise ValueError("F2B FDR alpha must be within (0, 1)")
        if self.authority_ceiling != "EXPLORATORY":
            raise ValueError("F2B authority ceiling must remain EXPLORATORY")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["eligible_context_labels"] = list(self.eligible_context_labels)
        payload["bootstrap_sensitivity_block_lengths"] = list(
            self.bootstrap_sensitivity_block_lengths
        )
        return payload

    @property
    def protocol_id(self) -> str:
        return canonical_identity_hash(self.to_canonical_dict())


def frozen_f2b_protocol() -> F2BProtocol:
    return F2BProtocol(
        schema_version=F2B_PROTOCOL_SCHEMA_VERSION,
        primary_hypothesis_id=F2B_PRIMARY_HYPOTHESIS_ID,
        model_id=F2B_PRIMARY_MODEL_ID,
        exit_time="10:30",
        cost_scenario="BASE",
        context_definition_id=MR2B_CONTEXT_DEFINITION_ID,
        eligible_context_labels=("UP", "DOWN"),
        metric_id=F2B_PRIMARY_METRIC_ID,
        alternative="UP_GREATER_THAN_DOWN",
        minimum_slice_size=15,
        economic_effect_floor=0.001,
        bootstrap_method_id=F2B_BOOTSTRAP_METHOD_ID,
        bootstrap_draws=10_000,
        bootstrap_block_length=5,
        bootstrap_sensitivity_block_lengths=(3, 10),
        bootstrap_seed=20_260_718,
        bootstrap_interval=0.95,
        bootstrap_interval_method_id=F2B_BOOTSTRAP_INTERVAL_ID,
        primary_randomization_method_id=F2B_RANDOMIZATION_METHOD_ID,
        random_permutation_method_id=F2B_PERMUTATION_METHOD_ID,
        random_permutation_draws=10_000,
        random_permutation_seed=20_260_719,
        first_second_half_rule_id=F2B_TEMPORAL_RULE_ID,
        concentration_rule_id=F2B_CONCENTRATION_RULE_ID,
        seed_panel_rule_id=F2B_SEED_PANEL_RULE_ID,
        secondary_family_id=F2B_SECONDARY_FAMILY_ID,
        multiple_testing_method_id=F2B_MULTIPLE_TESTING_METHOD_ID,
        multiple_testing_alpha=0.05,
        authority_ceiling="EXPLORATORY",
    )
