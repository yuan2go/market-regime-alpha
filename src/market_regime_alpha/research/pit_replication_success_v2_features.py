"""Reconstruct frozen B1-E scores from persisted Feature evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
import math
from typing import Any, Iterable, Mapping

from market_regime_alpha.candidates.composite_baseline import _directional_rank_percentiles
from market_regime_alpha.features.rehearsal_baselines import r5_baseline_feature_definitions
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    PITCandidateReplicationProtocolV2,
)
from market_regime_alpha.research.r5_baseline_runner import r5_b1_fixed_specs


@dataclass(frozen=True, slots=True)
class RegisteredFeatureDefinition:
    feature_id: str
    implementation_version: str
    direction: str
    availability_rule_id: str
    missing_policy: str
    research_role: str


def frozen_b1e_feature_registry() -> tuple[RegisteredFeatureDefinition, ...]:
    definitions = {str(value.feature_id): value for value in r5_baseline_feature_definitions()}
    spec = r5_b1_fixed_specs()["B1-E"]
    return tuple(
        RegisteredFeatureDefinition(
            str(component.feature_id),
            "r5-rehearsal-baseline-v1",
            component.direction.value,
            definitions[str(component.feature_id)].availability_rule,
            definitions[str(component.feature_id)].missingness_policy,
            component.role.value,
        )
        for component in spec.ordered_components
    )


def feature_set_payload() -> dict[str, Any]:
    return {
        "schema_version": "pit-b1e-feature-set-v1",
        "features": [asdict(value) for value in frozen_b1e_feature_registry()],
        "feature_tuning_on_validation": False,
        "ablation_executed": False,
    }


def model_spec_payload(protocol: PITCandidateReplicationProtocolV2) -> dict[str, Any]:
    spec = r5_b1_fixed_specs()["B1-E"]
    return {
        "schema_version": "pit-b1e-model-spec-v1",
        "model_id": protocol.ranking_model_id,
        "model_spec_hash": spec.spec_hash,
        "normalization_version": spec.normalization_version,
        "missing_policy": spec.missing_policy,
        "components": [
            {
                "feature_id": str(component.feature_id),
                "direction": component.direction.value,
                "normalized_weight": weight,
                "role": component.role.value,
            }
            for component, weight in spec.normalized_components
        ],
    }


def reconstruct_b1e_scores(
    feature_rows: Iterable[Mapping[str, Any]],
    *,
    protocol: PITCandidateReplicationProtocolV2,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    if protocol.ranking_model_spec_hash != r5_b1_fixed_specs()["B1-E"].spec_hash:
        raise ValueError("B1-E model specification is not frozen")
    rows = tuple(dict(row) for row in feature_rows)
    seen: set[tuple[str, str, str]] = set()
    grouped: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    required = tuple(value.feature_id for value in frozen_b1e_feature_registry())
    for row in rows:
        decision_date = _text(row, "decision_date")
        symbol = _text(row, "symbol")
        feature_id = _text(row, "feature_id")
        key = (decision_date, symbol, feature_id)
        if key in seen:
            raise ValueError("duplicate Candidate Feature evidence")
        seen.add(key)
        if feature_id not in required:
            raise ValueError("unknown B1-E Feature evidence")
        if row.get("feature_status") != "AVAILABLE":
            continue
        observed_at = datetime.fromisoformat(_text(row, "feature_observed_at"))
        available_at = datetime.fromisoformat(_text(row, "feature_available_at"))
        decision_time = datetime.fromisoformat(_text(row, "decision_time"))
        if observed_at > decision_time or available_at > decision_time:
            raise ValueError("Feature evidence is unavailable at Decision Time")
        value = row.get("feature_value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("available Feature value must be finite numeric")
        grouped[decision_date][symbol][feature_id] = float(value)

    spec = r5_b1_fixed_specs()["B1-E"]
    score_rows: list[dict[str, Any]] = []
    ranking_rows: list[dict[str, Any]] = []
    for decision_date, by_symbol in sorted(grouped.items()):
        complete = {
            symbol: values for symbol, values in by_symbol.items() if set(values) == set(required)
        }
        percentiles: dict[str, dict[str, float]] = {}
        for component in spec.ordered_components:
            feature_id = str(component.feature_id)
            percentiles[feature_id] = _directional_rank_percentiles(
                {symbol: values[feature_id] for symbol, values in complete.items()},
                direction=component.direction,
            )
        weights = {str(component.feature_id): weight for component, weight in spec.normalized_components}
        scores = {
            symbol: sum(weights[feature_id] * percentiles[feature_id][symbol] for feature_id in required)
            for symbol in complete
        }
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        rank_by_symbol = {symbol: index for index, (symbol, _) in enumerate(ranked, start=1)}
        all_symbols = sorted(by_symbol)
        for symbol in all_symbols:
            eligible = symbol in complete
            score_rows.append(
                {
                    "schema_version": "pit-b1e-model-score-v1",
                    "decision_date": decision_date,
                    "symbol": symbol,
                    "model_id": protocol.ranking_model_id,
                    "model_spec_hash": protocol.ranking_model_spec_hash,
                    "component_feature_ids": list(required),
                    "component_normalized_ranks": (
                        [percentiles[value][symbol] for value in required] if eligible else []
                    ),
                    "component_directions": [
                        component.direction.value for component in spec.ordered_components
                    ],
                    "component_weights": [weights[value] for value in required],
                    "composite_score": scores.get(symbol),
                    "rank": rank_by_symbol.get(symbol),
                    "eligible_for_ranking": eligible,
                    "rejection_reason": None if eligible else "STRICT_COMPLETE_CASE_REJECT",
                }
            )
            ranking_rows.append(
                {
                    "decision_date": decision_date,
                    "symbol": symbol,
                    "model_id": protocol.ranking_model_id,
                    "target_id": protocol.ranking_dataset_target_id,
                    "score": scores.get(symbol),
                    "rank": rank_by_symbol.get(symbol),
                    "eligible_for_ranking": eligible,
                    "rejection_reason": None if eligible else "STRICT_COMPLETE_CASE_REJECT",
                }
            )
    return tuple(score_rows), tuple(ranking_rows)


def _text(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be non-empty")
    return value
