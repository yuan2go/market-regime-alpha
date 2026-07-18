"""Application facade for the frozen MR-2B F2B statistical closure."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from market_regime_alpha.research.mr2b_f2a_reader import VerifiedF2ARun
from market_regime_alpha.research.mr2b_f2b_competing_events import (
    CompetingEventResult,
    build_competing_event_diagnostics,
)
from market_regime_alpha.research.mr2b_f2b_primary import PrimaryGateResult, evaluate_primary_gate
from market_regime_alpha.research.mr2b_f2b_protocol import F2BProtocol
from market_regime_alpha.research.mr2b_f2b_secondary import build_secondary_inventory
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
    moving_block_bootstrap,
    seed_panel_robustness,
    temporal_stability,
)
from market_regime_alpha.research.prr_artifact_reader import VerifiedMR1Run, VerifiedPRRDataset


F2B_RESULT_SCHEMA_VERSION = "mr-2b-f2b-statistical-closure-v1"
F2B_PRIMARY_OBSERVATION_SCHEMA_VERSION = "mr-2b-f2b-primary-observation-v1"


@dataclass(frozen=True, slots=True)
class F2BResults:
    protocol: F2BProtocol
    primary_set: PrimaryObservationSet
    bootstraps: tuple[BootstrapResult, ...]
    circular: CircularShiftResult
    permutation: PermutationResult
    temporal: TemporalStability
    concentration: ConcentrationResult
    seed_panels: SeedPanelRobustness
    primary_gate: PrimaryGateResult
    secondary_rows: tuple[dict[str, Any], ...]
    multiple_testing: dict[str, Any]
    competing_events: CompetingEventResult

    @property
    def primary_observation_rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "schema_version": F2B_PRIMARY_OBSERVATION_SCHEMA_VERSION,
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
        return tuple(
            {"method_id": self.circular.method_id, "shift": index, "effect": effect}
            for index, effect in enumerate(self.circular.effects, start=1)
        )

    @property
    def random_permutation_rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {"method_id": self.permutation.method_id, "draw_index": index, "effect": effect}
            for index, effect in enumerate(self.permutation.effects)
        )

    @property
    def temporal_rows(self) -> tuple[dict[str, Any], ...]:
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
        rows.extend({"diagnostic_type": "ROLLING_20", **row} for row in self.temporal.rolling_rows)
        return tuple(rows)

    @property
    def seed_panel_rows(self) -> tuple[dict[str, Any], ...]:
        return self.seed_panels.rows

    @property
    def concentration_payload(self) -> dict[str, Any]:
        return asdict(self.concentration)

    @property
    def primary_assessment_payload(self) -> dict[str, Any]:
        primary_bootstrap = next(
            row for row in self.bootstraps if row.block_length == self.protocol.bootstrap_block_length
        )
        return {
            "schema_version": "mr-2b-f2b-primary-assessment-v1",
            "primary_hypothesis_id": self.protocol.primary_hypothesis_id,
            "alternative": self.protocol.alternative,
            "assessment": self.primary_gate.assessment.value,
            "passed_conditions": list(self.primary_gate.passed_conditions),
            "failed_conditions": list(self.primary_gate.failed_conditions),
            "failure_reasons": list(self.primary_gate.failure_reasons),
            "UP_count": sum(row.context_label.value == "UP" for row in self.primary_set.observations),
            "DOWN_count": sum(row.context_label.value == "DOWN" for row in self.primary_set.observations),
            "FLAT_count": self.primary_set.flat_count,
            "unavailable_count": self.primary_set.unavailable_count,
            "observed_up_mean": primary_bootstrap.observed_up_mean,
            "observed_down_mean": primary_bootstrap.observed_down_mean,
            "observed_effect": primary_bootstrap.observed_effect,
            "bootstrap": _bootstrap_summary(primary_bootstrap),
            "bootstrap_sensitivity": [
                _bootstrap_summary(row)
                for row in self.bootstraps
                if row.block_length != self.protocol.bootstrap_block_length
            ],
            "circular_shift": _without_effects(self.circular),
            "random_permutation": _without_effects(self.permutation),
            "temporal": {
                key: value
                for key, value in asdict(self.temporal).items()
                if key != "rolling_rows"
            },
            "concentration": self.concentration_payload,
            "seed_panel_robustness": {
                key: value for key, value in asdict(self.seed_panels).items() if key != "rows"
            },
            "authority": "EXPLORATORY",
            "formal_oos_alpha": "NOT_ESTABLISHED",
            "model_winner": "NOT_SELECTED",
            "production_regime_gate": "NOT_AUTHORIZED",
        }


def build_f2b_results(
    *, dataset: VerifiedPRRDataset, mr1: VerifiedMR1Run, f2a: VerifiedF2ARun, protocol: F2BProtocol
) -> F2BResults:
    if dataset.dataset_id != mr1.dataset_id or dataset.dataset_id != f2a.dataset_id:
        raise ValueError("F2B Dataset identity chain mismatch")
    if mr1.run_id != f2a.mr1_run_id:
        raise ValueError("F2B MR-1 identity chain mismatch")
    primary = build_primary_observations(
        f2a.daily_candidate_excess,
        dataset_id=dataset.dataset_id,
        mr1_run_id=mr1.run_id,
        f2a_run_id=f2a.run_id,
        model_id=protocol.model_id,
        exit_time=protocol.exit_time,
        cost_scenario=protocol.cost_scenario,
    )
    bootstraps = tuple(
        moving_block_bootstrap(
            primary.observations,
            draws=protocol.bootstrap_draws,
            block_length=block_length,
            seed=protocol.bootstrap_seed,
            minimum_slice_size=protocol.minimum_slice_size,
            effect_floor=protocol.economic_effect_floor,
        )
        for block_length in (
            protocol.bootstrap_block_length,
            *protocol.bootstrap_sensitivity_block_lengths,
        )
    )
    circular = circular_shift_randomization(primary.observations)
    permutation = count_preserving_permutation(
        primary.observations,
        draws=protocol.random_permutation_draws,
        seed=protocol.random_permutation_seed,
    )
    temporal = temporal_stability(primary.observations)
    concentration = concentration_diagnostics(primary.observations)
    if concentration.status != "AVAILABLE":
        largest = top3 = 1.0
    else:
        assert concentration.largest_absolute_contribution_share is not None
        assert concentration.top_3_absolute_contribution_share is not None
        largest = concentration.largest_absolute_contribution_share
        top3 = concentration.top_3_absolute_contribution_share
    panels = seed_panel_robustness(
        primary.observations, multiseed_return_rows=f2a.multiseed_returns
    )
    primary_bootstrap = bootstraps[0]
    gate = evaluate_primary_gate(
        {
            "up_count": sum(row.context_label.value == "UP" for row in primary.observations),
            "down_count": sum(row.context_label.value == "DOWN" for row in primary.observations),
            "context_complete": primary.unavailable_count == 0,
            "observed_effect": primary_bootstrap.observed_effect,
            "bootstrap_valid_draws": primary_bootstrap.valid_draw_count,
            "bootstrap_ci_lower": primary_bootstrap.ci_lower_95,
            "circular_shift_p_value": circular.one_sided_p_value,
            "first_half_effect": temporal.first_half_effect,
            "second_half_effect": temporal.second_half_effect,
            "half_coverage_complete": temporal.half_coverage_complete,
            "largest_absolute_contribution_share": largest,
            "top_3_absolute_contribution_share": top3,
            "panel_effects": (
                panels.panel_A_effect,
                panels.panel_B_effect,
                panels.panel_C_effect,
                panels.panel_D_effect,
            ),
            "artifact_semantics_verified": True,
        }
    )
    secondary, disclosure = build_secondary_inventory(
        f2a.daily_candidate_excess,
        dataset_id=dataset.dataset_id,
        mr1_run_id=mr1.run_id,
        f2a_run_id=f2a.run_id,
        protocol=protocol,
    )
    competing = build_competing_event_diagnostics(
        target_rows=mr1.morning_targets,
        ranking_rows=dataset.ranking_rows,
        multiseed_selection_rows=f2a.multiseed_selections,
        primary_model_id=protocol.model_id,
        top_k=int(mr1.manifest["top_k"]),
    )
    return F2BResults(
        protocol, primary, bootstraps, circular, permutation, temporal, concentration,
        panels, gate, secondary, disclosure, competing,
    )


def _bootstrap_summary(result: BootstrapResult) -> dict[str, Any]:
    return {key: value for key, value in asdict(result).items() if key != "effects"}


def _without_effects(result: CircularShiftResult | PermutationResult) -> dict[str, Any]:
    return {key: value for key, value in asdict(result).items() if key != "effects"}
