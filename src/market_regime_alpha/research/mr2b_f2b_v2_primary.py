"""Protocol-driven directional Primary gate for F2B v2."""

from __future__ import annotations

from typing import Mapping

from market_regime_alpha.research.mr2b_f2b_primary import (
    PrimaryAssessment,
    PrimaryGateResult,
    _integer,
    _real,
    _real_tuple,
)
from market_regime_alpha.research.mr2b_f2b_v2_protocol import F2BProtocolV2
from market_regime_alpha.research.mr2b_f2b_v2_statistics import PrimaryCoverageAssessment


def evaluate_primary_gate_v2(
    *,
    coverage: PrimaryCoverageAssessment,
    evidence: Mapping[str, object] | None,
    protocol: F2BProtocolV2,
) -> PrimaryGateResult:
    if not coverage.sufficient_for_statistics:
        reasons = coverage.insufficiency_reasons
        return PrimaryGateResult(PrimaryAssessment.INSUFFICIENT_EVIDENCE, (), reasons, reasons)
    if evidence is None:
        raise ValueError("sufficient Primary coverage requires statistical evidence")
    required = {
        "observed_effect",
        "bootstrap_valid_draws",
        "bootstrap_ci_lower",
        "circular_shift_p_value",
        "first_half_effect",
        "second_half_effect",
        "half_coverage_complete",
        "largest_absolute_contribution_share",
        "top_3_absolute_contribution_share",
        "panel_effects",
    }
    if required - evidence.keys():
        raise ValueError("F2B v2 Primary gate evidence is incomplete")
    minimum_valid = int(protocol.bootstrap_draws * protocol.minimum_valid_bootstrap_draw_ratio)
    insufficient: list[str] = []
    if _integer(evidence["bootstrap_valid_draws"], "bootstrap_valid_draws") < minimum_valid:
        insufficient.append("BOOTSTRAP_VALID_DRAWS_INSUFFICIENT")
    if not bool(evidence["half_coverage_complete"]):
        insufficient.append("INSUFFICIENT_HALF_COVERAGE")
    if insufficient:
        reasons = tuple(insufficient)
        return PrimaryGateResult(PrimaryAssessment.INSUFFICIENT_EVIDENCE, (), reasons, reasons)

    effect = _real(evidence["observed_effect"], "observed_effect")
    panels = _real_tuple(evidence["panel_effects"], "panel_effects")
    if len(panels) != protocol.seed_panel_count:
        raise ValueError("F2B v2 seed-panel cardinality mismatch")
    checks = (
        (effect > 0, "POSITIVE_DIRECTION", "OPPOSITE_DIRECTION"),
        (
            effect >= protocol.economic_effect_floor,
            "ECONOMIC_EFFECT_FLOOR",
            "BELOW_ECONOMIC_EFFECT_FLOOR",
        ),
        (
            _real(evidence["bootstrap_ci_lower"], "bootstrap_ci_lower") > 0,
            "BOOTSTRAP_INTERVAL_POSITIVE",
            "BOOTSTRAP_INTERVAL_INCLUDES_ZERO",
        ),
        (
            _real(evidence["circular_shift_p_value"], "circular_shift_p_value")
            <= protocol.circular_shift_alpha,
            "RANDOMIZATION_SIGNIFICANT",
            "RANDOMIZATION_NOT_SIGNIFICANT",
        ),
        (
            _real(evidence["first_half_effect"], "first_half_effect") > 0
            and _real(evidence["second_half_effect"], "second_half_effect") > 0,
            "TEMPORAL_DIRECTION_CONSISTENT",
            "TEMPORAL_DIRECTION_INCONSISTENT",
        ),
        (
            _real(
                evidence["largest_absolute_contribution_share"],
                "largest_absolute_contribution_share",
            )
            <= protocol.largest_contribution_limit
            and _real(
                evidence["top_3_absolute_contribution_share"],
                "top_3_absolute_contribution_share",
            )
            <= protocol.top_3_contribution_limit,
            "EFFECT_NOT_CONCENTRATED",
            "CONCENTRATED_EFFECT",
        ),
        (
            sum(value > 0 for value in panels) >= protocol.required_positive_panel_count,
            "COMPARATOR_PANELS_POSITIVE",
            "COMPARATOR_PANEL_UNSTABLE",
        ),
    )
    passed: list[str] = []
    failures: list[str] = []
    for accepted, passed_name, failed_name in checks:
        (passed if accepted else failures).append(passed_name if accepted else failed_name)
    assessment = (
        PrimaryAssessment.PRIMARY_HYPOTHESIS_SUPPORTED_EXPLORATORY
        if not failures
        else PrimaryAssessment.PRIMARY_HYPOTHESIS_NOT_SUPPORTED
    )
    return PrimaryGateResult(assessment, tuple(passed), tuple(failures), tuple(failures))
