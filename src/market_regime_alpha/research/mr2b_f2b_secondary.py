"""Secondary-comparison multiple-testing primitives for MR-2B F2B."""

from __future__ import annotations

import math
from hashlib import sha256
from typing import Any, Iterable, Mapping

from market_regime_alpha.research.mr2b_f2b_protocol import F2BProtocol
from market_regime_alpha.research.mr2b_f2b_statistics import (
    build_primary_observations,
    circular_shift_randomization,
    concentration_diagnostics,
    moving_block_bootstrap,
    temporal_stability,
)


def benjamini_hochberg(p_values: Iterable[float]) -> tuple[float, ...]:
    values = tuple(_probability(value) for value in p_values)
    if not values:
        raise ValueError("BH family must not be empty")
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    adjusted = [0.0] * len(values)
    running = 1.0
    for reverse_index in range(len(ordered) - 1, -1, -1):
        original_index, value = ordered[reverse_index]
        rank = reverse_index + 1
        running = min(running, value * len(values) / rank)
        adjusted[original_index] = min(1.0, running)
    return tuple(adjusted)


def build_secondary_inventory(
    rows: Iterable[Mapping[str, Any]],
    *,
    dataset_id: str,
    mr1_run_id: str,
    f2a_run_id: str,
    protocol: F2BProtocol,
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    raw = tuple(dict(row) for row in rows)
    comparisons = tuple(
        sorted(
            {
                (str(row["model_id"]), str(row["exit_time"]), str(row["cost_scenario"]))
                for row in raw
            }
        )
    )
    if len(comparisons) != 108:
        raise ValueError("F2B fixed comparison family must contain exactly 108 comparisons")
    provisional: list[dict[str, Any]] = []
    for model_id, exit_time, scenario in comparisons:
        observations = build_primary_observations(
            raw,
            dataset_id=dataset_id,
            mr1_run_id=mr1_run_id,
            f2a_run_id=f2a_run_id,
            model_id=model_id,
            exit_time=exit_time,
            cost_scenario=scenario,
        )
        if observations.flat_count or observations.unavailable_count:
            raise ValueError("Secondary comparison Context coverage must be complete for F2B")
        circular = circular_shift_randomization(observations.observations)
        bootstrap = moving_block_bootstrap(
            observations.observations,
            draws=2_000,
            block_length=5,
            seed=_comparison_seed(model_id, exit_time, scenario),
            minimum_slice_size=protocol.minimum_slice_size,
            effect_floor=protocol.economic_effect_floor,
        )
        temporal = temporal_stability(observations.observations)
        concentration = concentration_diagnostics(observations.observations)
        up_count = sum(row.context_label.value == "UP" for row in observations.observations)
        down_count = len(observations.observations) - up_count
        is_primary = (
            model_id == protocol.model_id
            and exit_time == protocol.exit_time
            and scenario == protocol.cost_scenario
        )
        provisional.append(
            {
                "model_id": model_id,
                "exit_time": exit_time,
                "cost_scenario": scenario,
                "UP_count": up_count,
                "DOWN_count": down_count,
                "up_mean": bootstrap.observed_up_mean,
                "down_mean": bootstrap.observed_down_mean,
                "effect": bootstrap.observed_effect,
                "circular_shift_p_value": circular.one_sided_p_value,
                "secondary_bootstrap_ci_lower": bootstrap.ci_lower_95,
                "secondary_bootstrap_ci_upper": bootstrap.ci_upper_95,
                "first_half_effect": temporal.first_half_effect,
                "second_half_effect": temporal.second_half_effect,
                "largest_contribution_share": concentration.largest_absolute_contribution_share,
                "top_3_contribution_share": concentration.top_3_absolute_contribution_share,
                "comparison_role": "PRIMARY" if is_primary else "SECONDARY_POST_HOC",
                "raw_p_value": circular.one_sided_p_value,
                "bh_q_value": None,
                "bh_rank": None,
                "family_size": 0 if is_primary else 107,
                "status": "PRIMARY_REPORTED_SEPARATELY" if is_primary else "SECONDARY_NOT_FDR_SIGNIFICANT",
                "data_eligibility": "EXPLORATORY",
            }
        )
    secondary_indexes = [index for index, row in enumerate(provisional) if row["comparison_role"] == "SECONDARY_POST_HOC"]
    q_values = benjamini_hochberg(provisional[index]["raw_p_value"] for index in secondary_indexes)
    ranked = sorted(secondary_indexes, key=lambda index: (provisional[index]["raw_p_value"], index))
    ranks = {index: rank for rank, index in enumerate(ranked, start=1)}
    for index, q_value in zip(secondary_indexes, q_values, strict=True):
        provisional[index]["bh_q_value"] = q_value
        provisional[index]["bh_rank"] = ranks[index]
        if q_value <= protocol.multiple_testing_alpha:
            provisional[index]["status"] = "SECONDARY_POST_HOC_CANDIDATE"
    secondary = tuple(provisional[index] for index in secondary_indexes)
    disclosure = {
        "schema_version": "mr-2b-f2b-multiple-testing-disclosure-v1",
        "comparison_count": len(provisional),
        "primary_count": 1,
        "secondary_count": len(secondary),
        "method_id": protocol.multiple_testing_method_id,
        "alpha": protocol.multiple_testing_alpha,
        "minimum_raw_p_value": min(float(row["raw_p_value"]) for row in secondary),
        "minimum_bh_q_value": min(float(row["bh_q_value"]) for row in secondary),
        "fdr_candidate_count": sum(row["status"] == "SECONDARY_POST_HOC_CANDIDATE" for row in secondary),
        "secondary_can_replace_primary": False,
    }
    return tuple(provisional), disclosure


def _comparison_seed(model_id: str, exit_time: str, scenario: str) -> int:
    digest = sha256(f"{model_id}|{exit_time}|{scenario}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _probability(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise TypeError("p-values must be finite real numbers")
    result = float(value)
    if not 0 <= result <= 1:
        raise ValueError("p-values must be within [0, 1]")
    return result
