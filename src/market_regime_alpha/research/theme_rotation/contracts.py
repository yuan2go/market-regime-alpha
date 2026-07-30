"""Formal Theme Rotation research-priority contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.evidence.envelope import ArtifactEnvelope


class RotationState(str, Enum):
    STARTING = "STARTING"
    STRENGTHENING = "STRENGTHENING"
    LEADING = "LEADING"
    DIVERGING = "DIVERGING"
    WEAKENING = "WEAKENING"
    FAILED = "FAILED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class ThemeRotationItem:
    theme_id: str
    theme_name: str
    benchmark_id: str
    proxy_etf_ids: tuple[str, ...]
    rotation_state: RotationState
    rotation_score: float | None
    rank: int
    confidence: float
    relative_strength_1d: float | None
    relative_strength_3d: float | None
    relative_strength_5d: float | None
    relative_strength_10d: float | None
    amount_expansion: float | None
    breadth: float | None
    new_high_breadth: float | None
    leader_strength: float | None
    participation_change: float | None
    persistence: float | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.rank <= 0:
            raise ValueError("Theme rank must be positive")
        if self.rotation_score is not None and (
            not isfinite(self.rotation_score)
            or not -1.0 <= self.rotation_score <= 1.0
        ):
            raise ValueError("Theme rotation score must be within [-1, 1]")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Theme confidence must be within [0, 1]")
        if (
            self.rotation_state is RotationState.DATA_INSUFFICIENT
            and self.rotation_score is not None
        ):
            raise ValueError("insufficient Theme cannot carry a rotation score")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "theme_id": self.theme_id,
            "theme_name": self.theme_name,
            "benchmark_id": self.benchmark_id,
            "proxy_etf_ids": list(self.proxy_etf_ids),
            "rotation_state": self.rotation_state.value,
            "rotation_score": self.rotation_score,
            "rank": self.rank,
            "confidence": self.confidence,
            "relative_strength_1d": self.relative_strength_1d,
            "relative_strength_3d": self.relative_strength_3d,
            "relative_strength_5d": self.relative_strength_5d,
            "relative_strength_10d": self.relative_strength_10d,
            "amount_expansion": self.amount_expansion,
            "breadth": self.breadth,
            "new_high_breadth": self.new_high_breadth,
            "leader_strength": self.leader_strength,
            "participation_change": self.participation_change,
            "persistence": self.persistence,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> ThemeRotationItem:
        expected = {
            "theme_id",
            "theme_name",
            "benchmark_id",
            "proxy_etf_ids",
            "rotation_state",
            "rotation_score",
            "rank",
            "confidence",
            "relative_strength_1d",
            "relative_strength_3d",
            "relative_strength_5d",
            "relative_strength_10d",
            "amount_expansion",
            "breadth",
            "new_high_breadth",
            "leader_strength",
            "participation_change",
            "persistence",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("ThemeRotationItem fields mismatch")
        return cls(
            theme_id=str(payload["theme_id"]),
            theme_name=str(payload["theme_name"]),
            benchmark_id=str(payload["benchmark_id"]),
            proxy_etf_ids=_strings(payload["proxy_etf_ids"]),
            rotation_state=RotationState(str(payload["rotation_state"])),
            rotation_score=_optional_float(payload["rotation_score"]),
            rank=int(payload["rank"]),
            confidence=float(payload["confidence"]),
            relative_strength_1d=_optional_float(
                payload["relative_strength_1d"]
            ),
            relative_strength_3d=_optional_float(
                payload["relative_strength_3d"]
            ),
            relative_strength_5d=_optional_float(
                payload["relative_strength_5d"]
            ),
            relative_strength_10d=_optional_float(
                payload["relative_strength_10d"]
            ),
            amount_expansion=_optional_float(payload["amount_expansion"]),
            breadth=_optional_float(payload["breadth"]),
            new_high_breadth=_optional_float(payload["new_high_breadth"]),
            leader_strength=_optional_float(payload["leader_strength"]),
            participation_change=_optional_float(
                payload["participation_change"]
            ),
            persistence=_optional_float(payload["persistence"]),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class ThemeRotationSnapshot:
    """Theme priority evidence; never a stock buy signal."""

    envelope: ArtifactEnvelope
    themes: tuple[ThemeRotationItem, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if tuple(item.rank for item in self.themes) != tuple(
            range(1, len(self.themes) + 1)
        ):
            raise ValueError("Theme Rotation ranks must be contiguous")
        if len({item.theme_id for item in self.themes}) != len(self.themes):
            raise ValueError("Theme Rotation themes must be unique")
        self.envelope.verify_payload(self.artifact_payload())

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "themes": [item.to_canonical_dict() for item in self.themes],
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_canonical_dict(),
            **self.artifact_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> ThemeRotationSnapshot:
        if set(payload) != {"envelope", "themes", "reason_codes"}:
            raise ValueError("ThemeRotationSnapshot fields mismatch")
        return cls(
            envelope=ArtifactEnvelope.from_canonical_dict(
                _object(payload["envelope"])
            ),
            themes=tuple(
                ThemeRotationItem.from_canonical_dict(_object(item))
                for item in _array(payload["themes"])
            ),
            reason_codes=_strings(payload["reason_codes"]),
        )


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Theme Rotation value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Theme Rotation value must be an array")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError("Theme Rotation value must be a string array")
    return tuple(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Theme Rotation value must be numeric")
    return float(value)
