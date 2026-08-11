"""Canonical lifecycle run and stage state machines.

The tables in this module are the only source of truth for orchestration state
changes.  Domain services decide *what* happened; the runtime journal validates
that the resulting projection moves through an explicitly permitted edge.
"""

from __future__ import annotations

from enum import Enum


class InvalidLifecycleTransition(ValueError):
    """Raised when a run, stage, or ordered stage cursor moves illegally."""


class LifecycleRunType(str, Enum):
    CANONICAL_DECISION_LIFECYCLE = "CANONICAL_DECISION_LIFECYCLE"
    RISK_REDUCTION_CONTINUATION = "RISK_REDUCTION_CONTINUATION"
    REPLAY = "REPLAY"


class LifecycleRunStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    WAITING_FOR_ENTRY_CONFIRMATION = "WAITING_FOR_ENTRY_CONFIRMATION"
    BLOCKED_BY_MODEL_VALIDATION = "BLOCKED_BY_MODEL_VALIDATION"
    WAITING_FOR_MANUAL_CONFIRMATION = "WAITING_FOR_MANUAL_CONFIRMATION"
    WAITING_FOR_FILL = "WAITING_FOR_FILL"
    POSITION_OPEN = "POSITION_OPEN"
    WAITING_FOR_T1 = "WAITING_FOR_T1"
    READY_FOR_HOLDING_ASSESSMENT = "READY_FOR_HOLDING_ASSESSMENT"
    READY_FOR_EXIT_REVIEW = "READY_FOR_EXIT_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class LifecycleStageName(str, Enum):
    VERIFY_COMPOSITE_EVIDENCE = "VERIFY_COMPOSITE_EVIDENCE"
    PLATFORM_RESEARCH = "PLATFORM_RESEARCH"
    SIGNAL = "SIGNAL"
    PATH_FORECAST = "PATH_FORECAST"
    ENTRY_ASSESSMENT = "ENTRY_ASSESSMENT"
    OPPORTUNITY = "OPPORTUNITY"
    THESIS = "THESIS"
    PORTFOLIO_RISK = "PORTFOLIO_RISK"
    RISK_REDUCTION = "RISK_REDUCTION"
    MANUAL_CONFIRMATION = "MANUAL_CONFIRMATION"
    MANUAL_TRADE = "MANUAL_TRADE"
    FILL_POSITION = "FILL_POSITION"
    THESIS_HEALTH = "THESIS_HEALTH"
    HOLDING_ASSESSMENT = "HOLDING_ASSESSMENT"
    EXIT_ASSESSMENT = "EXIT_ASSESSMENT"
    OUTCOME_REVIEW = "OUTCOME_REVIEW"


LIFECYCLE_STAGE_ORDER: tuple[LifecycleStageName, ...] = tuple(LifecycleStageName)


class LifecycleCapabilityBoundary(str, Enum):
    """Executable ownership boundary; enum presence does not imply composition."""

    RESEARCH_DECISION_SUPPORT = "RESEARCH_DECISION_SUPPORT"
    MANUAL_ACCOUNT_OBSERVATION = "MANUAL_ACCOUNT_OBSERVATION"
    POSITION_REVIEW_CONTRACT_ONLY = "POSITION_REVIEW_CONTRACT_ONLY"


RESEARCH_DECISION_SUPPORT_STAGE_ORDER: tuple[LifecycleStageName, ...] = (
    LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
    LifecycleStageName.PLATFORM_RESEARCH,
    LifecycleStageName.SIGNAL,
    LifecycleStageName.PATH_FORECAST,
    LifecycleStageName.ENTRY_ASSESSMENT,
    LifecycleStageName.OPPORTUNITY,
    LifecycleStageName.THESIS,
    LifecycleStageName.PORTFOLIO_RISK,
    LifecycleStageName.RISK_REDUCTION,
)

MANUAL_ACCOUNT_OBSERVATION_STAGE_ORDER: tuple[LifecycleStageName, ...] = (
    LifecycleStageName.MANUAL_CONFIRMATION,
    LifecycleStageName.MANUAL_TRADE,
    LifecycleStageName.FILL_POSITION,
    LifecycleStageName.THESIS_HEALTH,
)

POSITION_REVIEW_CONTRACT_ONLY_STAGE_ORDER: tuple[LifecycleStageName, ...] = (
    LifecycleStageName.HOLDING_ASSESSMENT,
    LifecycleStageName.EXIT_ASSESSMENT,
    LifecycleStageName.OUTCOME_REVIEW,
)

POSTGRES_COMPOSED_STAGE_ORDER: tuple[LifecycleStageName, ...] = (
    RESEARCH_DECISION_SUPPORT_STAGE_ORDER + MANUAL_ACCOUNT_OBSERVATION_STAGE_ORDER
)


def lifecycle_stage_boundary(
    stage: LifecycleStageName,
) -> LifecycleCapabilityBoundary:
    """Return the real owner/composition boundary for a lifecycle stage."""

    if not isinstance(stage, LifecycleStageName):
        raise TypeError("stage must be LifecycleStageName")
    if stage in RESEARCH_DECISION_SUPPORT_STAGE_ORDER:
        return LifecycleCapabilityBoundary.RESEARCH_DECISION_SUPPORT
    if stage in MANUAL_ACCOUNT_OBSERVATION_STAGE_ORDER:
        return LifecycleCapabilityBoundary.MANUAL_ACCOUNT_OBSERVATION
    return LifecycleCapabilityBoundary.POSITION_REVIEW_CONTRACT_ONLY


class LifecycleStageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"


TERMINAL_LIFECYCLE_RUN_STATUSES = frozenset(
    {
        LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
        LifecycleRunStatus.COMPLETED,
    }
)

TERMINAL_LIFECYCLE_STAGE_STATUSES = frozenset(
    {
        LifecycleStageStatus.COMPLETED,
        LifecycleStageStatus.BLOCKED,
        LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
    }
)

WAITING_LIFECYCLE_RUN_STATUSES = frozenset(
    {
        LifecycleRunStatus.WAITING_FOR_ENTRY_CONFIRMATION,
        LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
        LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION,
        LifecycleRunStatus.WAITING_FOR_FILL,
        LifecycleRunStatus.WAITING_FOR_T1,
    }
)

_RUNNING_TARGETS = frozenset(
    {
        LifecycleRunStatus.WAITING_FOR_ENTRY_CONFIRMATION,
        LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
        LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION,
        LifecycleRunStatus.WAITING_FOR_FILL,
        LifecycleRunStatus.POSITION_OPEN,
        LifecycleRunStatus.WAITING_FOR_T1,
        LifecycleRunStatus.READY_FOR_HOLDING_ASSESSMENT,
        LifecycleRunStatus.READY_FOR_EXIT_REVIEW,
        LifecycleRunStatus.COMPLETED,
        LifecycleRunStatus.FAILED,
    }
)

ALLOWED_LIFECYCLE_RUN_TRANSITIONS: dict[
    LifecycleRunStatus, frozenset[LifecycleRunStatus]
] = {
    LifecycleRunStatus.CREATED: frozenset(
        {LifecycleRunStatus.RUNNING, LifecycleRunStatus.FAILED}
    ),
    LifecycleRunStatus.RUNNING: _RUNNING_TARGETS,
    LifecycleRunStatus.RETRYING: frozenset(
        {LifecycleRunStatus.RUNNING, LifecycleRunStatus.FAILED}
    ),
    LifecycleRunStatus.WAITING_FOR_ENTRY_CONFIRMATION: frozenset(
        {LifecycleRunStatus.RUNNING, LifecycleRunStatus.FAILED}
    ),
    LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION: frozenset(),
    LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION: frozenset(
        {LifecycleRunStatus.RUNNING, LifecycleRunStatus.FAILED}
    ),
    LifecycleRunStatus.WAITING_FOR_FILL: frozenset(
        {LifecycleRunStatus.RUNNING, LifecycleRunStatus.FAILED}
    ),
    LifecycleRunStatus.POSITION_OPEN: frozenset(
        {
            LifecycleRunStatus.RUNNING,
            LifecycleRunStatus.WAITING_FOR_T1,
            LifecycleRunStatus.READY_FOR_HOLDING_ASSESSMENT,
            LifecycleRunStatus.READY_FOR_EXIT_REVIEW,
            LifecycleRunStatus.FAILED,
        }
    ),
    LifecycleRunStatus.WAITING_FOR_T1: frozenset(
        {LifecycleRunStatus.RUNNING, LifecycleRunStatus.FAILED}
    ),
    LifecycleRunStatus.READY_FOR_HOLDING_ASSESSMENT: frozenset(
        {
            LifecycleRunStatus.RUNNING,
            LifecycleRunStatus.READY_FOR_EXIT_REVIEW,
            LifecycleRunStatus.FAILED,
        }
    ),
    LifecycleRunStatus.READY_FOR_EXIT_REVIEW: frozenset(
        {
            LifecycleRunStatus.RUNNING,
            LifecycleRunStatus.COMPLETED,
            LifecycleRunStatus.FAILED,
        }
    ),
    LifecycleRunStatus.COMPLETED: frozenset(),
    LifecycleRunStatus.FAILED: frozenset({LifecycleRunStatus.RETRYING}),
}

ALLOWED_LIFECYCLE_STAGE_TRANSITIONS: dict[
    LifecycleStageStatus, frozenset[LifecycleStageStatus]
] = {
    LifecycleStageStatus.PENDING: frozenset({LifecycleStageStatus.RUNNING}),
    LifecycleStageStatus.RUNNING: frozenset(
        {
            LifecycleStageStatus.COMPLETED,
            LifecycleStageStatus.WAITING,
            LifecycleStageStatus.BLOCKED,
            LifecycleStageStatus.FAILED,
            LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
        }
    ),
    LifecycleStageStatus.COMPLETED: frozenset(),
    LifecycleStageStatus.WAITING: frozenset({LifecycleStageStatus.RUNNING}),
    LifecycleStageStatus.BLOCKED: frozenset(),
    LifecycleStageStatus.FAILED: frozenset({LifecycleStageStatus.RUNNING}),
    LifecycleStageStatus.SKIPPED_NOT_APPLICABLE: frozenset(),
}


def validate_lifecycle_run_transition(
    current: LifecycleRunStatus,
    target: LifecycleRunStatus,
) -> None:
    if not isinstance(current, LifecycleRunStatus) or not isinstance(
        target, LifecycleRunStatus
    ):
        raise TypeError("run states must be LifecycleRunStatus values")
    if target not in ALLOWED_LIFECYCLE_RUN_TRANSITIONS[current]:
        raise InvalidLifecycleTransition(
            f"invalid lifecycle run transition: {current.value}->{target.value}"
        )


def validate_lifecycle_stage_transition(
    current: LifecycleStageStatus,
    target: LifecycleStageStatus,
) -> None:
    if not isinstance(current, LifecycleStageStatus) or not isinstance(
        target, LifecycleStageStatus
    ):
        raise TypeError("stage states must be LifecycleStageStatus values")
    if target not in ALLOWED_LIFECYCLE_STAGE_TRANSITIONS[current]:
        raise InvalidLifecycleTransition(
            f"invalid lifecycle stage transition: {current.value}->{target.value}"
        )


def validate_lifecycle_stage_progression(
    completed_stages: tuple[LifecycleStageName, ...],
    target: LifecycleStageName,
    *,
    start_stage: LifecycleStageName = LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
) -> None:
    """Require ``target`` to be the next stage in one contiguous ordered slice.

    ``start_stage`` allows a bounded continuation such as H4.5 to enter at
    ``RISK_REDUCTION`` without weakening the no-skipping rule within that run.
    """

    if not isinstance(completed_stages, tuple) or any(
        not isinstance(item, LifecycleStageName) for item in completed_stages
    ):
        raise TypeError("completed_stages must be a tuple of LifecycleStageName")
    if not isinstance(target, LifecycleStageName) or not isinstance(
        start_stage, LifecycleStageName
    ):
        raise TypeError("target and start_stage must be LifecycleStageName values")
    start_index = LIFECYCLE_STAGE_ORDER.index(start_stage)
    expected_completed = LIFECYCLE_STAGE_ORDER[
        start_index : start_index + len(completed_stages)
    ]
    if completed_stages != expected_completed:
        raise InvalidLifecycleTransition(
            "completed stages must form a contiguous ordered lifecycle slice"
        )
    target_index = start_index + len(completed_stages)
    if target_index >= len(LIFECYCLE_STAGE_ORDER):
        raise InvalidLifecycleTransition("no lifecycle stage remains after completion")
    expected_target = LIFECYCLE_STAGE_ORDER[target_index]
    if target is not expected_target:
        raise InvalidLifecycleTransition(
            f"stage skipping is forbidden: expected {expected_target.value}, "
            f"got {target.value}"
        )
