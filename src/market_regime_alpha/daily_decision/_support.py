"""Internal canonicalization helpers for Phase D daily decision contracts."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Any, Mapping


def canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def require_text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def require_strings(
    label: str,
    values: tuple[str, ...],
    *,
    required: bool = False,
) -> None:
    if required and not values:
        raise ValueError(f"{label} must not be empty")
    for value in values:
        require_text(label, value)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def require_finite(label: str, value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{label} must be finite")
    return float(value)
