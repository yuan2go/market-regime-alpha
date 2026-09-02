from __future__ import annotations

from dataclasses import replace

import pytest

from market_regime_alpha.research_qualification.application import (
    build_decision_proof_runtime_profile,
    build_due_proof_runtime_profile,
)
from market_regime_alpha.runtime.domain import StepDependency, validate_step_dag


def test_decision_proof_profile_is_complete_ordered_and_mandatory() -> None:
    steps, dependencies = build_decision_proof_runtime_profile(
        request_seed="decision-profile",
    )

    assert tuple(step.step_kind for step in steps) == (
        "CAPTURE",
        "NORMALIZE_PIT",
        "FREEZE_UNIVERSE",
        "ASSESS_ELIGIBILITY",
        "REGISTER_DATASET",
        "BUILD_CANDIDATE_SET",
        "OPEN_DECISION_RUN",
        "ASSESS_CONTEXT",
        "SIGNAL_AND_FORECAST",
        "DECIDE_AND_RISK",
    )
    assert all(step.required for step in steps)
    assert tuple(step.ordinal for step in steps) == tuple(range(1, 11))
    assert len(dependencies) == 9
    validate_step_dag(steps, dependencies)


def test_due_proof_profile_is_complete_ordered_and_mandatory() -> None:
    steps, dependencies = build_due_proof_runtime_profile(
        request_seed="due-profile",
    )

    assert tuple(step.step_kind for step in steps) == (
        "SETTLE_OUTCOME",
        "ACQUIRE_OUTCOME_INPUTS",
        "EVALUATE",
        "RECORD_EVIDENCE",
        "ASSESS_RESEARCH",
        "QUALIFY",
    )
    assert all(step.required for step in steps)
    assert tuple(step.ordinal for step in steps) == tuple(range(1, 7))
    assert len(dependencies) == 5
    validate_step_dag(steps, dependencies)


@pytest.mark.parametrize("profile", ["decision", "due"])
def test_formal_profile_rejects_missing_optional_reordered_and_bypass(
    profile: str,
) -> None:
    builder = (
        build_decision_proof_runtime_profile
        if profile == "decision"
        else build_due_proof_runtime_profile
    )
    steps, dependencies = builder(request_seed=f"{profile}-invalid")

    with pytest.raises(ValueError, match="profile"):
        validate_step_dag(steps[:-1], dependencies[:-1])
    with pytest.raises(ValueError, match="mandatory"):
        validate_step_dag(
            (replace(steps[0], required=False), *steps[1:]),
            dependencies,
        )
    with pytest.raises(ValueError, match="contiguous"):
        validate_step_dag(
            (steps[0], replace(steps[1], ordinal=99), *steps[2:]),
            dependencies,
        )
    with pytest.raises(ValueError, match="direct REQUIRED_SUCCESS"):
        validate_step_dag(steps, dependencies[:-1])
    with pytest.raises(ValueError, match="bypass"):
        validate_step_dag(
            steps,
            (
                *dependencies,
                StepDependency(steps[0].step_key, steps[2].step_key),
            ),
        )
