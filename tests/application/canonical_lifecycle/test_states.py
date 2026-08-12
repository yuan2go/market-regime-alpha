from __future__ import annotations

from itertools import product
from typing import Any, cast

import pytest

from market_regime_alpha.application.canonical_lifecycle.states import (
    ALLOWED_LIFECYCLE_RUN_TRANSITIONS,
    ALLOWED_LIFECYCLE_STAGE_TRANSITIONS,
    LIFECYCLE_STAGE_ORDER,
    MANUAL_ACCOUNT_OBSERVATION_STAGE_ORDER,
    POSITION_REVIEW_CONTRACT_ONLY_STAGE_ORDER,
    POSTGRES_COMPOSED_STAGE_ORDER,
    RESEARCH_DECISION_SUPPORT_STAGE_ORDER,
    InvalidLifecycleTransition,
    LifecycleCapabilityBoundary,
    LifecycleRunStatus,
    LifecycleStageName,
    LifecycleStageStatus,
    lifecycle_stage_boundary,
    validate_lifecycle_run_transition,
    validate_lifecycle_stage_progression,
    validate_lifecycle_stage_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    tuple(
        (current, target)
        for current, targets in ALLOWED_LIFECYCLE_RUN_TRANSITIONS.items()
        for target in targets
    ),
)
def test_every_declared_run_transition_is_legal(
    current: LifecycleRunStatus, target: LifecycleRunStatus
) -> None:
    validate_lifecycle_run_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    tuple(
        (current, target)
        for current, target in product(LifecycleRunStatus, repeat=2)
        if target not in ALLOWED_LIFECYCLE_RUN_TRANSITIONS[current]
    ),
)
def test_every_undeclared_run_transition_is_illegal(
    current: LifecycleRunStatus, target: LifecycleRunStatus
) -> None:
    with pytest.raises(InvalidLifecycleTransition):
        validate_lifecycle_run_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    tuple(
        (current, target)
        for current, targets in ALLOWED_LIFECYCLE_STAGE_TRANSITIONS.items()
        for target in targets
    ),
)
def test_every_declared_stage_transition_is_legal(
    current: LifecycleStageStatus, target: LifecycleStageStatus
) -> None:
    validate_lifecycle_stage_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    tuple(
        (current, target)
        for current, target in product(LifecycleStageStatus, repeat=2)
        if target not in ALLOWED_LIFECYCLE_STAGE_TRANSITIONS[current]
    ),
)
def test_every_undeclared_stage_transition_is_illegal(
    current: LifecycleStageStatus, target: LifecycleStageStatus
) -> None:
    with pytest.raises(InvalidLifecycleTransition):
        validate_lifecycle_stage_transition(current, target)


def test_stage_progression_requires_a_contiguous_slice() -> None:
    validate_lifecycle_stage_progression(
        (
            LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
            LifecycleStageName.PLATFORM_RESEARCH,
        ),
        LifecycleStageName.SIGNAL,
    )
    validate_lifecycle_stage_progression(
        (LifecycleStageName.RISK_REDUCTION,),
        LifecycleStageName.MANUAL_CONFIRMATION,
        start_stage=LifecycleStageName.RISK_REDUCTION,
    )

    with pytest.raises(InvalidLifecycleTransition, match="skipping"):
        validate_lifecycle_stage_progression(
            (LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,),
            LifecycleStageName.SIGNAL,
        )
    with pytest.raises(InvalidLifecycleTransition, match="contiguous"):
        validate_lifecycle_stage_progression(
            (
                LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
                LifecycleStageName.SIGNAL,
            ),
            LifecycleStageName.PATH_FORECAST,
        )


def test_transition_validators_reject_untyped_values() -> None:
    with pytest.raises(TypeError):
        validate_lifecycle_run_transition(
            cast(Any, "CREATED"), LifecycleRunStatus.RUNNING
        )
    with pytest.raises(TypeError):
        validate_lifecycle_stage_transition(
            cast(Any, "PENDING"), LifecycleStageStatus.RUNNING
        )


def test_lifecycle_capability_boundaries_express_real_composition() -> None:
    assert (
        RESEARCH_DECISION_SUPPORT_STAGE_ORDER
        + MANUAL_ACCOUNT_OBSERVATION_STAGE_ORDER
        + POSITION_REVIEW_CONTRACT_ONLY_STAGE_ORDER
        == LIFECYCLE_STAGE_ORDER
    )
    assert POSTGRES_COMPOSED_STAGE_ORDER == LIFECYCLE_STAGE_ORDER[:13]
    assert lifecycle_stage_boundary(LifecycleStageName.SIGNAL) is (
        LifecycleCapabilityBoundary.RESEARCH_DECISION_SUPPORT
    )
    assert lifecycle_stage_boundary(LifecycleStageName.FILL_POSITION) is (
        LifecycleCapabilityBoundary.MANUAL_ACCOUNT_OBSERVATION
    )
    assert lifecycle_stage_boundary(LifecycleStageName.OUTCOME_REVIEW) is (
        LifecycleCapabilityBoundary.POSITION_REVIEW_CONTRACT_ONLY
    )

    with pytest.raises(TypeError, match="LifecycleStageName"):
        lifecycle_stage_boundary(cast(Any, "OUTCOME_REVIEW"))
