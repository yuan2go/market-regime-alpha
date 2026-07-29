"""Daily runtime states and legal forward transitions."""

from __future__ import annotations

from enum import Enum


class DailyRunStatus(str, Enum):
    CREATED = "CREATED"
    SOURCE_ACQUIRING = "SOURCE_ACQUIRING"
    SOURCE_FROZEN = "SOURCE_FROZEN"
    DATA_BLOCKED = "DATA_BLOCKED"
    UNIVERSE_READY = "UNIVERSE_READY"
    FEATURES_READY = "FEATURES_READY"
    PREDICTIONS_PUBLISHED = "PREDICTIONS_PUBLISHED"
    DECISION_PUBLISHED = "DECISION_PUBLISHED"
    OUTCOME_PENDING = "OUTCOME_PENDING"
    REVIEW_PUBLISHED = "REVIEW_PUBLISHED"
    FAILED = "FAILED"


TERMINAL_DAILY_RUN_STATUSES = frozenset(
    {
        DailyRunStatus.DATA_BLOCKED,
        DailyRunStatus.REVIEW_PUBLISHED,
    }
)

_ALLOWED_TRANSITIONS: dict[DailyRunStatus, frozenset[DailyRunStatus]] = {
    DailyRunStatus.CREATED: frozenset({DailyRunStatus.SOURCE_ACQUIRING}),
    DailyRunStatus.SOURCE_ACQUIRING: frozenset({DailyRunStatus.SOURCE_FROZEN}),
    DailyRunStatus.SOURCE_FROZEN: frozenset(
        {
            DailyRunStatus.DATA_BLOCKED,
            DailyRunStatus.UNIVERSE_READY,
        }
    ),
    DailyRunStatus.UNIVERSE_READY: frozenset(
        {
            DailyRunStatus.DATA_BLOCKED,
            DailyRunStatus.FEATURES_READY,
        }
    ),
    DailyRunStatus.FEATURES_READY: frozenset(
        {
            DailyRunStatus.DATA_BLOCKED,
            DailyRunStatus.PREDICTIONS_PUBLISHED,
        }
    ),
    DailyRunStatus.PREDICTIONS_PUBLISHED: frozenset(
        {DailyRunStatus.DECISION_PUBLISHED}
    ),
    DailyRunStatus.DECISION_PUBLISHED: frozenset(
        {DailyRunStatus.OUTCOME_PENDING}
    ),
    DailyRunStatus.OUTCOME_PENDING: frozenset(
        {DailyRunStatus.REVIEW_PUBLISHED}
    ),
    DailyRunStatus.DATA_BLOCKED: frozenset(),
    DailyRunStatus.REVIEW_PUBLISHED: frozenset(),
    DailyRunStatus.FAILED: frozenset(),
}


def validate_daily_run_transition(
    current: DailyRunStatus,
    target: DailyRunStatus,
) -> None:
    """Reject skipped, backward and post-terminal transitions."""

    if not isinstance(current, DailyRunStatus) or not isinstance(
        target,
        DailyRunStatus,
    ):
        raise TypeError("daily run states must be DailyRunStatus values")
    if current in TERMINAL_DAILY_RUN_STATUSES:
        raise ValueError(f"{current.value} is a terminal DailyRunStatus")
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise ValueError(
            f"invalid DailyRunStatus transition: {current.value}->{target.value}"
        )
