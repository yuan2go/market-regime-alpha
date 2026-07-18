"""Application facade for coverage-first MR-2B F2B v3 evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from typing import Any, Iterable, Mapping

from market_regime_alpha.research.mr2b_f2a_reader import VerifiedF2ARun
from market_regime_alpha.research.mr2b_f2b_primary import PrimaryGateResult
from market_regime_alpha.research.mr2b_f2b_secondary import benjamini_hochberg
from market_regime_alpha.research.mr2b_f2b_statistics import (
    BootstrapResult,
    CircularShiftResult,
    ConcentrationResult,
    PermutationResult,
    PrimaryObservationSet,
    SeedPanelRobustness,
    TemporalStability,
    build_primary_observations,
    circular_shift_randomization,
    concentration_diagnostics,
    count_preserving_permutation,
    seed_panel_robustness,
)
from market_regime_alpha.research.mr2b_f2b_v3_competing_events import (
    CompetingEventResultV3,
    build_competing_event_diagnostics_v3,
)
from market_regime_alpha.research.mr2b_f2b_v3_primary import evaluate_primary_gate_v3
from market_regime_alpha.research.mr2b_f2b_v3_protocol import F2BProtocolV3
from market_regime_alpha.research.mr2b_f2b_v3_statistics import (
    PrimaryCoverageAssessment,
    assess_primary_coverage,
    protocol_bootstrap,
    protocol_temporal_stability,
)
from market_regime_alpha.research.prr_artifact_reader import VerifiedMR1Run, VerifiedPRRDataset


F2B_V3_PRIMARY_OBSERVATION_SCHEMA_VERSION = "mr-2b-f2b-primary-observation-v3"


@dataclass(frozen=True, slots=True)
class F2BResultsV3:
    protocol: F2BProtocolV3
    primary_set: PrimaryObservationSet
    coverage: PrimaryCoverageAssessment
    bootstraps: tuple[BootstrapResult, ...]
    circular: CircularShiftResult | None
    permutation: PermutationResult | None
    temporal: TemporalStability | None
    concentration: ConcentrationResult | None
    seed_panels: SeedPanelRobustness | None
    primary_gate: PrimaryGateResult
    secondary_rows: tuple[dict[str, Any], ...]
    multiple_testing: dict[str, Any]
    competing_events: CompetingEventResultV3

    @property
    def statistics_executed(self) -> bool:
        return self.coverage.sufficient_for_statistics

    @property
    def primary_observation_rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "schema_version": F2B_V3_PRIMARY_OBSERVATION_SCHEMA_VERSION,
                **asdict(row),
                "decision_date": row.decision_date.isoformat(),
                "context_label": row.context_label.value,
                "data_eligibility": "EXPLORATORY",
            }
            for row in self.primary_set.observations
        )

    @property
    def bootstrap_distribution_rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "method_id": result.method_id,
                "block_length": result.block_length,
                "draw_index": index,
                "effect": effect,
                "valid": True,
            }
            for result in self.bootstraps
            for index, effect in enumerate(result.effects)
        )

    @property
    def circular_shift_rows(self) -> tuple[dict[str, Any], ...]:
        if self.circular is None:
            return ()
        return tuple(
            {"method_id": self.circular.method_id, "shift": index, "effect": effect}
            for index, effect in enumerate(self.circular.effects, start=1)
        )

    @property
    def random_permutation_rows(self) -> tuple[dict[str, Any], ...]:
        if self.permutation is None:
            return ()
        return tuple(
            {"method_id": self.permutation.method_id, "draw_index": index, "effect": effect}
            for index, effect in enumerate(self.permutation.effects)
        )

    @property
    def temporal_rows(self) -> tuple[dict[str, Any], ...]:
        if self.temporal is None:
            return ()
        rows: list[dict[str, Any]] = [
            {
                "diagnostic_type": "FIRST_HALF",
                "effect": self.temporal.first_half_effect,
                "UP_count": self.temporal.first_half_up_count,
                "DOWN_count": self.temporal.first_half_down_count,
            },
            {
                "diagnostic_type": "SECOND_HALF",
                "effect": self.temporal.second_half_effect,
                "UP_count": self.temporal.second_half_up_count,
                "DOWN_count": self.temporal.second_half_down_count,
            },
            {
                "diagnostic_type": "LEAVE_ONE_OUT_SUMMARY",
                "minimum_effect": self.temporal.leave_one_out_min_effect,
                "maximum_effect": self.temporal.leave_one_out_max_effect,
                "positive_ratio": self.temporal.leave_one_out_positive_ratio,
                "sign_flip_count": self.temporal.leave_one_out_sign_flip_count,
            },
        ]
        rows.extend({"diagnostic_type": "ROLLING", **row} for row in self.temporal.rolling_rows)
        return tuple(rows)

    @property
    def seed_panel_rows(self) -> tuple[dict[str, Any], ...]:
        return () if self.seed_panels is None else self.seed_panels.rows

    @property
    def concentration_payload(self) -> dict[str, Any]:
        if self.concentration is None:
            return {"status": "NOT_RUN_INSUFFICIENT_PRIMARY_COVERAGE"}
        return asdict(self.concentration)

    @property
    def primary_assessment_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": "mr-2b-f2b-primary-assessment-v3",
            "primary_hypothesis_id": self.protocol.primary_hypothesis_id,
            "alternative": self.protocol.alternative,
            "assessment": self.primary_gate.assessment.value,
            "statistics_executed": self.statistics_executed,
            "insufficiency_reasons": list(self.coverage.insufficiency_reasons),
            "passed_conditions": list(self.primary_gate.passed_conditions),
            "failed_conditions": list(self.primary_gate.failed_conditions),
            "failure_reasons": list(self.primary_gate.failure_reasons),
            "coverage": asdict(self.coverage),
            "authority": "EXPLORATORY",
            "formal_oos_alpha": "NOT_ESTABLISHED",
            "model_winner": "NOT_SELECTED",
            "production_regime_gate": "NOT_AUTHORIZED",
        }
        if not self.statistics_executed:
            payload["statistical_status"] = "NOT_RUN_INSUFFICIENT_PRIMARY_COVERAGE"
            return payload
        primary_bootstrap = self.bootstraps[0]
        assert self.circular is not None and self.permutation is not None
        assert self.temporal is not None and self.seed_panels is not None
        payload.update(
            {
                "observed_up_mean": primary_bootstrap.observed_up_mean,
                "observed_down_mean": primary_bootstrap.observed_down_mean,
                "observed_effect": primary_bootstrap.observed_effect,
                "bootstrap": _summary(primary_bootstrap),
                "bootstrap_sensitivity": [_summary(row) for row in self.bootstraps[1:]],
                "circular_shift": _summary(self.circular),
                "random_permutation": _summary(self.permutation),
                "temporal": _summary(self.temporal),
                "concentration": self.concentration_payload,
                "seed_panel_robustness": _summary(self.seed_panels),
            }
        )
        return payload


def build_f2b_v3_results(
    *, dataset: VerifiedPRRDataset, mr1: VerifiedMR1Run, f2a: VerifiedF2ARun, protocol: F2BProtocolV3
) -> F2BResultsV3:
    if dataset.dataset_id != mr1.dataset_id or dataset.dataset_id != f2a.dataset_id:
        raise ValueError("F2B v3 Dataset identity chain mismatch")
    if mr1.run_id != f2a.mr1_run_id:
        raise ValueError("F2B v3 MR-1 identity chain mismatch")
    primary = build_primary_observations(
        f2a.daily_candidate_excess,
        dataset_id=dataset.dataset_id,
        mr1_run_id=mr1.run_id,
        f2a_run_id=f2a.run_id,
        model_id=protocol.model_id,
        exit_time=protocol.exit_time,
        cost_scenario=protocol.cost_scenario,
    )
    up_count = sum(row.context_label.value == "UP" for row in primary.observations)
    down_count = len(primary.observations) - up_count
    coverage = assess_primary_coverage(primary, up_count=up_count, down_count=down_count, protocol=protocol)
    competing = build_competing_event_diagnostics_v3(
        target_rows=mr1.morning_targets,
        ranking_rows=dataset.ranking_rows,
        multiseed_selection_rows=f2a.multiseed_selections,
        primary_model_id=protocol.model_id,
        top_k=int(mr1.manifest["top_k"]),
    )
    if not coverage.sufficient_for_statistics:
        gate = evaluate_primary_gate_v3(coverage=coverage, evidence=None, protocol=protocol)
        return F2BResultsV3(
            protocol, primary, coverage, (), None, None, None, None, None, gate, (),
            _empty_multiple_testing(protocol), competing,
        )
    bootstraps = tuple(
        protocol_bootstrap(primary, block_length=block, protocol=protocol)
        for block in (protocol.bootstrap_block_length, *protocol.bootstrap_sensitivity_block_lengths)
    )
    circular = circular_shift_randomization(primary.observations)
    permutation = count_preserving_permutation(
        primary.observations,
        draws=protocol.random_permutation_draws,
        seed=protocol.random_permutation_seed,
    )
    temporal = protocol_temporal_stability(primary, protocol=protocol)
    concentration = concentration_diagnostics(primary.observations)
    panels = seed_panel_robustness(primary.observations, multiseed_return_rows=f2a.multiseed_returns)
    largest = concentration.largest_absolute_contribution_share
    top3 = concentration.top_3_absolute_contribution_share
    evidence = {
        "observed_effect": bootstraps[0].observed_effect,
        "bootstrap_valid_draws": bootstraps[0].valid_draw_count,
        "bootstrap_ci_lower": bootstraps[0].ci_lower_95,
        "circular_shift_p_value": circular.one_sided_p_value,
        "first_half_effect": temporal.first_half_effect,
        "second_half_effect": temporal.second_half_effect,
        "half_coverage_complete": temporal.half_coverage_complete,
        "largest_absolute_contribution_share": 1.0 if largest is None else largest,
        "top_3_absolute_contribution_share": 1.0 if top3 is None else top3,
        "panel_effects": tuple(row["effect"] for row in panels.rows),
    }
    gate = evaluate_primary_gate_v3(coverage=coverage, evidence=evidence, protocol=protocol)
    secondary, disclosure = _secondary_inventory(
        f2a.daily_candidate_excess,
        dataset_id=dataset.dataset_id,
        mr1_run_id=mr1.run_id,
        f2a_run_id=f2a.run_id,
        protocol=protocol,
    )
    return F2BResultsV3(
        protocol, primary, coverage, bootstraps, circular, permutation, temporal,
        concentration, panels, gate, secondary, disclosure, competing,
    )


def _secondary_inventory(
    rows: Iterable[Mapping[str, Any]],
    *, dataset_id: str, mr1_run_id: str, f2a_run_id: str, protocol: F2BProtocolV3,
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    raw = tuple(dict(row) for row in rows)
    comparisons = tuple(sorted({(str(row["model_id"]), str(row["exit_time"]), str(row["cost_scenario"])) for row in raw}))
    if len(comparisons) != 108:
        raise ValueError("F2B v3 comparison family must contain exactly 108 comparisons")
    output: list[dict[str, Any]] = []
    for model_id, exit_time, scenario in comparisons:
        observed = build_primary_observations(
            raw, dataset_id=dataset_id, mr1_run_id=mr1_run_id, f2a_run_id=f2a_run_id,
            model_id=model_id, exit_time=exit_time, cost_scenario=scenario,
        )
        circular = circular_shift_randomization(observed.observations)
        bootstrap = protocol_bootstrap(
            observed,
            block_length=protocol.secondary_bootstrap_block_length,
            protocol=replace(
                protocol,
                bootstrap_draws=protocol.secondary_bootstrap_draws,
                bootstrap_seed=_comparison_seed(model_id, exit_time, scenario),
            ),
        )
        temporal = protocol_temporal_stability(observed, protocol=protocol)
        concentration = concentration_diagnostics(observed.observations)
        is_primary = (model_id, exit_time, scenario) == (protocol.model_id, protocol.exit_time, protocol.cost_scenario)
        output.append(
            {
                "model_id": model_id, "exit_time": exit_time, "cost_scenario": scenario,
                "UP_count": sum(row.context_label.value == "UP" for row in observed.observations),
                "DOWN_count": sum(row.context_label.value == "DOWN" for row in observed.observations),
                "up_mean": bootstrap.observed_up_mean, "down_mean": bootstrap.observed_down_mean,
                "effect": bootstrap.observed_effect, "circular_shift_p_value": circular.one_sided_p_value,
                "secondary_bootstrap_ci_lower": bootstrap.ci_lower_95,
                "secondary_bootstrap_ci_upper": bootstrap.ci_upper_95,
                "first_half_effect": temporal.first_half_effect, "second_half_effect": temporal.second_half_effect,
                "largest_contribution_share": concentration.largest_absolute_contribution_share,
                "top_3_contribution_share": concentration.top_3_absolute_contribution_share,
                "comparison_role": "PRIMARY" if is_primary else "SECONDARY_POST_HOC",
                "raw_p_value": circular.one_sided_p_value, "bh_q_value": None, "bh_rank": None,
                "family_size": 0 if is_primary else 107,
                "status": "PRIMARY_REPORTED_SEPARATELY" if is_primary else "SECONDARY_NOT_FDR_SIGNIFICANT",
                "data_eligibility": "EXPLORATORY",
            }
        )
    indexes = [index for index, row in enumerate(output) if row["comparison_role"] == "SECONDARY_POST_HOC"]
    q_values = benjamini_hochberg(float(output[index]["raw_p_value"]) for index in indexes)
    ranked = sorted(indexes, key=lambda index: (output[index]["raw_p_value"], index))
    ranks = {index: rank for rank, index in enumerate(ranked, start=1)}
    for index, q_value in zip(indexes, q_values, strict=True):
        output[index]["bh_q_value"] = q_value
        output[index]["bh_rank"] = ranks[index]
        if q_value <= protocol.multiple_testing_alpha:
            output[index]["status"] = "SECONDARY_POST_HOC_CANDIDATE"
    secondary = tuple(output[index] for index in indexes)
    disclosure = {
        "schema_version": "mr-2b-f2b-multiple-testing-disclosure-v3",
        "comparison_count": len(output), "primary_count": 1, "secondary_count": len(secondary),
        "method_id": protocol.multiple_testing_method_id, "alpha": protocol.multiple_testing_alpha,
        "minimum_raw_p_value": min(float(row["raw_p_value"]) for row in secondary),
        "minimum_bh_q_value": min(float(row["bh_q_value"]) for row in secondary),
        "fdr_candidate_count": sum(row["status"] == "SECONDARY_POST_HOC_CANDIDATE" for row in secondary),
        "secondary_can_replace_primary": False,
    }
    return tuple(output), disclosure


def _empty_multiple_testing(protocol: F2BProtocolV3) -> dict[str, Any]:
    return {
        "schema_version": "mr-2b-f2b-multiple-testing-disclosure-v3",
        "comparison_count": 0,
        "primary_count": 0,
        "secondary_count": 0,
        "method_id": protocol.multiple_testing_method_id,
        "alpha": protocol.multiple_testing_alpha,
        "status": "NOT_RUN_INSUFFICIENT_PRIMARY_COVERAGE",
        "secondary_can_replace_primary": False,
    }


def _comparison_seed(model_id: str, exit_time: str, scenario: str) -> int:
    return int.from_bytes(sha256(f"{model_id}|{exit_time}|{scenario}".encode()).digest()[:8], "big")


def _summary(value: Any) -> dict[str, Any]:
    payload = asdict(value)
    payload.pop("effects", None)
    payload.pop("rolling_rows", None)
    payload.pop("rows", None)
    return payload
