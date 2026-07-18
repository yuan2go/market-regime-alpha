"""Directional fail-closed Primary gate for MR-2B F2B."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real
from typing import Mapping


class PrimaryAssessment(str, Enum):
    PRIMARY_HYPOTHESIS_SUPPORTED_EXPLORATORY = "PRIMARY_HYPOTHESIS_SUPPORTED_EXPLORATORY"
    PRIMARY_HYPOTHESIS_NOT_SUPPORTED = "PRIMARY_HYPOTHESIS_NOT_SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class PrimaryGateResult:
    assessment: PrimaryAssessment
    passed_conditions: tuple[str, ...]
    failed_conditions: tuple[str, ...]
    failure_reasons: tuple[str, ...]
    authority: str = "EXPLORATORY"


def evaluate_primary_gate(evidence: Mapping[str, object]) -> PrimaryGateResult:
    required = {
        "up_count", "down_count", "context_complete", "observed_effect",
        "bootstrap_valid_draws", "bootstrap_ci_lower", "circular_shift_p_value",
        "first_half_effect", "second_half_effect", "half_coverage_complete",
        "largest_absolute_contribution_share", "top_3_absolute_contribution_share",
        "panel_effects", "artifact_semantics_verified",
    }
    if required - evidence.keys():
        raise ValueError("Primary gate evidence is incomplete")
    up, down = _integer(evidence["up_count"], "up_count"), _integer(evidence["down_count"], "down_count")
    insufficient: list[str] = []
    if min(up, down) < 15:
        insufficient.append("INSUFFICIENT_SLICE_SIZE")
    if not bool(evidence["context_complete"]):
        insufficient.append("CONTEXT_COVERAGE_INCOMPLETE")
    if _integer(evidence["bootstrap_valid_draws"], "bootstrap_valid_draws") < 9_500:
        insufficient.append("BOOTSTRAP_VALID_DRAWS_INSUFFICIENT")
    if not bool(evidence["half_coverage_complete"]):
        insufficient.append("INSUFFICIENT_HALF_COVERAGE")
    if not bool(evidence["artifact_semantics_verified"]):
        insufficient.append("ARTIFACT_SEMANTICS_UNVERIFIED")
    if insufficient:
        return PrimaryGateResult(PrimaryAssessment.INSUFFICIENT_EVIDENCE, (), tuple(insufficient), tuple(insufficient))

    effect = _real(evidence["observed_effect"], "observed_effect")
    failures: list[str] = []
    passed: list[str] = []
    checks = (
        (effect > 0, "POSITIVE_DIRECTION", "OPPOSITE_DIRECTION"),
        (effect >= 0.001, "ECONOMIC_EFFECT_FLOOR", "BELOW_ECONOMIC_EFFECT_FLOOR"),
        (_real(evidence["bootstrap_ci_lower"], "bootstrap_ci_lower") > 0, "BOOTSTRAP_INTERVAL_POSITIVE", "BOOTSTRAP_INTERVAL_INCLUDES_ZERO"),
        (_real(evidence["circular_shift_p_value"], "circular_shift_p_value") <= 0.05, "RANDOMIZATION_SIGNIFICANT", "RANDOMIZATION_NOT_SIGNIFICANT"),
        (
            _real(evidence["first_half_effect"], "first_half_effect") > 0
            and _real(evidence["second_half_effect"], "second_half_effect") > 0,
            "TEMPORAL_DIRECTION_CONSISTENT",
            "TEMPORAL_DIRECTION_INCONSISTENT",
        ),
        (
            _real(evidence["largest_absolute_contribution_share"], "largest_absolute_contribution_share") <= 0.50
            and _real(evidence["top_3_absolute_contribution_share"], "top_3_absolute_contribution_share") <= 0.75,
            "EFFECT_NOT_CONCENTRATED",
            "CONCENTRATED_EFFECT",
        ),
        (all(value > 0 for value in _real_tuple(evidence["panel_effects"], "panel_effects")), "COMPARATOR_PANELS_POSITIVE", "COMPARATOR_PANEL_UNSTABLE"),
    )
    for accepted, passed_name, failed_name in checks:
        (passed if accepted else failures).append(passed_name if accepted else failed_name)
    assessment = (
        PrimaryAssessment.PRIMARY_HYPOTHESIS_SUPPORTED_EXPLORATORY
        if not failures
        else PrimaryAssessment.PRIMARY_HYPOTHESIS_NOT_SUPPORTED
    )
    return PrimaryGateResult(assessment, tuple(passed), tuple(failures), tuple(failures))


def _real(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise TypeError(f"{label} must be a finite real number")
    return float(value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an int")
    return value


def _real_tuple(value: object, label: str) -> tuple[float, ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{label} must be a sequence")
    return tuple(_real(item, label) for item in value)
