"""Deterministic JSON and SHA-256 helpers shared by new Platform V2 contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping


SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def normalize_canonical_datetime(value: datetime) -> datetime:
    """Return the repository canonical instant: aware UTC at whole-second precision."""

    if not isinstance(value, datetime):
        raise TypeError("canonical datetime must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("canonical datetime must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def canonical_datetime(value: datetime) -> str:
    """Encode one canonical instant as UTC RFC3339 using the ``Z`` suffix."""

    return normalize_canonical_datetime(value).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(payload: Mapping[str, Any]) -> str:
    return f"sha256:{sha256(canonical_json(payload).encode('utf-8')).hexdigest()}"


def require_sha256(label: str, value: str) -> None:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a sha256-prefixed lowercase digest")


def require_text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def require_unique_text(label: str, values: tuple[str, ...]) -> None:
    for value in values:
        require_text(label, value)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")
