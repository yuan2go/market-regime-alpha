"""Shared validation and identity primitives for daily research contracts."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId


_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class DailyDataAuthority(str, Enum):
    """Allowed data classifications for V1 daily decision evidence."""

    EXPLORATORY = "EXPLORATORY"
    AUXILIARY = "AUXILIARY"
    TEST_ONLY_NOT_RESEARCH_EVIDENCE = "TEST_ONLY_NOT_RESEARCH_EVIDENCE"


class InstrumentType(str, Enum):
    """Instrument families ranked independently by V1."""

    A_SHARE_STOCK = "A_SHARE_STOCK"
    ETF = "ETF"


class DecisionDataQuality(str, Enum):
    """Decision-record data quality, not model performance."""

    COMPLETE = "COMPLETE"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


class EntryState(str, Enum):
    """Entry timing decision for an already identified recommendation."""

    ENTER = "ENTER"
    WAIT_PULLBACK = "WAIT_PULLBACK"
    WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
    REJECT = "REJECT"


def text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def hash_value(label: str, value: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a sha256-prefixed lowercase digest")


def finite(label: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite when present")


def positive_price(label: str, value: float | None) -> None:
    finite(label, value)
    if value is not None and float(value) <= 0.0:
        raise ValueError(f"{label} must be positive when present")


def strings(
    label: str,
    values: tuple[str, ...],
    *,
    required: bool = False,
    sorted_values: bool = False,
) -> None:
    if required and not values:
        raise ValueError(f"{label} must not be empty")
    for value in values:
        text(label, value)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")
    if sorted_values and tuple(sorted(values)) != values:
        raise ValueError(f"{label} values must be sorted")


def exact_fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def datetime_value(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def required_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def required_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    return float(value)


def required_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def required_date(value: object, label: str) -> date:
    raw = required_string(value, label)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc


def object_value(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    return required_float(value, "optional numeric field")


def canonical_content_hash(payload: Mapping[str, Any]) -> str:
    """Hash one JSON-compatible semantic payload deterministically."""

    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def identity(prefix: str, content_hash: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{content_hash.split(':', 1)[1][:24]}")
