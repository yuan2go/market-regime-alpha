"""Frozen single-source protocol for MR-2B F2B v2 hardening."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from market_regime_alpha.research.mr2b_context import MR2B_CONTEXT_DEFINITION_ID
from market_regime_alpha.research.mr2b_f2b_protocol import (
    F2B_BOOTSTRAP_INTERVAL_ID,
    F2B_BOOTSTRAP_METHOD_ID,
    F2B_CONCENTRATION_RULE_ID,
    F2B_MULTIPLE_TESTING_METHOD_ID,
    F2B_PERMUTATION_METHOD_ID,
    F2B_PRIMARY_HYPOTHESIS_ID,
    F2B_PRIMARY_METRIC_ID,
    F2B_PRIMARY_MODEL_ID,
    F2B_RANDOMIZATION_METHOD_ID,
    F2B_SECONDARY_FAMILY_ID,
    F2B_SEED_PANEL_RULE_ID,
    F2B_TEMPORAL_RULE_ID,
)
from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash


F2B_V2_PROTOCOL_SCHEMA_VERSION = "mr-2b-f2b-protocol-v2"


@dataclass(frozen=True, slots=True)
class F2BProtocolV2:
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
    minimum_valid_bootstrap_draw_ratio: float
    primary_randomization_method_id: str
    circular_shift_alpha: float
    random_permutation_method_id: str
    random_permutation_draws: int
    random_permutation_seed: int
    half_minimum_slice_size: int
    rolling_window: int
    first_second_half_rule_id: str
    largest_contribution_limit: float
    top_3_contribution_limit: float
    concentration_rule_id: str
    seed_panel_count: int
    required_positive_panel_count: int
    seed_panel_rule_id: str
    secondary_family_id: str
    secondary_bootstrap_draws: int
    secondary_bootstrap_block_length: int
    secondary_randomization_alpha: float
    multiple_testing_method_id: str
    multiple_testing_alpha: float
    authority_ceiling: str

    def __post_init__(self) -> None:
        if self.schema_version != F2B_V2_PROTOCOL_SCHEMA_VERSION:
            raise ValueError("unsupported F2B v2 Protocol schema")
        if self.alternative != "UP_GREATER_THAN_DOWN":
            raise ValueError("F2B v2 alternative is frozen")
        if self.eligible_context_labels != ("UP", "DOWN"):
            raise ValueError("F2B v2 labels are frozen")
        positive = (
            self.minimum_slice_size,
            self.bootstrap_draws,
            self.bootstrap_block_length,
            self.half_minimum_slice_size,
            self.rolling_window,
            self.seed_panel_count,
            self.required_positive_panel_count,
            self.secondary_bootstrap_draws,
            self.secondary_bootstrap_block_length,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("F2B v2 integer parameters must be positive")
        probabilities = (
            self.bootstrap_interval,
            self.minimum_valid_bootstrap_draw_ratio,
            self.circular_shift_alpha,
            self.largest_contribution_limit,
            self.top_3_contribution_limit,
            self.secondary_randomization_alpha,
            self.multiple_testing_alpha,
        )
        if any(not 0 < value <= 1 for value in probabilities):
            raise ValueError("F2B v2 probability parameters are invalid")
        if self.authority_ceiling != "EXPLORATORY":
            raise ValueError("F2B v2 authority must remain EXPLORATORY")

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


def frozen_f2b_v2_protocol() -> F2BProtocolV2:
    return F2BProtocolV2(
        schema_version=F2B_V2_PROTOCOL_SCHEMA_VERSION,
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
        minimum_valid_bootstrap_draw_ratio=0.95,
        primary_randomization_method_id=F2B_RANDOMIZATION_METHOD_ID,
        circular_shift_alpha=0.05,
        random_permutation_method_id=F2B_PERMUTATION_METHOD_ID,
        random_permutation_draws=10_000,
        random_permutation_seed=20_260_719,
        half_minimum_slice_size=5,
        rolling_window=20,
        first_second_half_rule_id=F2B_TEMPORAL_RULE_ID,
        largest_contribution_limit=0.50,
        top_3_contribution_limit=0.75,
        concentration_rule_id=F2B_CONCENTRATION_RULE_ID,
        seed_panel_count=4,
        required_positive_panel_count=4,
        seed_panel_rule_id=F2B_SEED_PANEL_RULE_ID,
        secondary_family_id=F2B_SECONDARY_FAMILY_ID,
        secondary_bootstrap_draws=2_000,
        secondary_bootstrap_block_length=5,
        secondary_randomization_alpha=0.05,
        multiple_testing_method_id=F2B_MULTIPLE_TESTING_METHOD_ID,
        multiple_testing_alpha=0.05,
        authority_ceiling="EXPLORATORY",
    )
