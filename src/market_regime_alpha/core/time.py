"""Semantic time primitives used by V2 contracts.

Bare timestamps are intentionally avoided where different time meanings coexist.
All semantic times must be timezone-aware.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def _require_aware_datetime(value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError("semantic time value must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("semantic time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SemanticTime:
    """Base immutable wrapper for a timezone-aware datetime."""

    value: datetime

    def __post_init__(self) -> None:
        _require_aware_datetime(self.value)

    def isoformat(self) -> str:
        return self.value.isoformat()

    def as_utc(self) -> datetime:
        return self.value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class DecisionTime(SemanticTime):
    """Time at which a prediction or decision is assumed to be made."""


@dataclass(frozen=True, slots=True)
class AvailabilityTime(SemanticTime):
    """Earliest time information is treated as available to the decision system."""


@dataclass(frozen=True, slots=True)
class FinalizationTime(SemanticTime):
    """Time at which an observation or artifact is treated as finalized."""


@dataclass(frozen=True, slots=True)
class AsOfTime(SemanticTime):
    """Reference time for the information state represented by an artifact."""


@dataclass(frozen=True, slots=True)
class ExecutionEligibleTime(SemanticTime):
    """Earliest time at which an approved action may become execution-eligible."""


@dataclass(frozen=True, slots=True)
class RetrievedAt(SemanticTime):
    """Time at which the project retrieved or recorded a source artifact."""
