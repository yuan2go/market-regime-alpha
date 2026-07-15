"""Canonical input availability and validity semantics.

This module intentionally does not define strategy actions. In particular, NO_ACTION
belongs to the Strategy action vocabulary and must not be encoded as an input status.
"""

from __future__ import annotations

from enum import Enum


class InputAvailabilityStatus(str, Enum):
    """Availability/validity state for an input consumed by a downstream contract."""

    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    INVALID = "INVALID"
    UNSUPPORTED = "UNSUPPORTED"
    BLOCKED = "BLOCKED"

    @property
    def is_usable(self) -> bool:
        return self is InputAvailabilityStatus.AVAILABLE
