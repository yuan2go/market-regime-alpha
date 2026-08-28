"""UTC boundary validation for canonical timestamps."""

from __future__ import annotations

from datetime import datetime, timezone


def require_utc(value: datetime, *, field: str = "timestamp") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


__all__ = ["require_utc"]
