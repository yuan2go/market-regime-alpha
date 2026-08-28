"""UTC boundary validation for canonical timestamps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def require_utc(value: datetime, *, field: str = "timestamp") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, order=True, slots=True)
class KnownTime:
    value: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_utc(self.value, field="known_time"))


@dataclass(frozen=True, order=True, slots=True)
class DecisionTime:
    value: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            require_utc(self.value, field="decision_time"),
        )


__all__ = ["DecisionTime", "KnownTime", "require_utc"]
