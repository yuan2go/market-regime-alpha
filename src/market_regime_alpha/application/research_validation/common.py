"""Shared immutable contracts for research-validation engineering.

These contracts deliberately describe engineering evidence.  They cannot grant
PIT, OOS, model-governance, Entry, or trading authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)


class ResearchEvidenceAuthority(str, Enum):
    EXPLORATORY = "EXPLORATORY"
    ENGINEERING_ONLY = "ENGINEERING_ONLY"
    FORMAL_OOS = "FORMAL_OOS"


@dataclass(frozen=True, slots=True)
class ValidationArtifactReference:
    artifact_kind: str
    artifact_id: ArtifactId
    content_hash: str

    def __post_init__(self) -> None:
        require_text("artifact_kind", self.artifact_kind)
        require_sha256("content_hash", self.content_hash)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "artifact_kind": self.artifact_kind,
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> ValidationArtifactReference:
        return cls(
            artifact_kind=str(value["artifact_kind"]),
            artifact_id=ArtifactId(str(value["artifact_id"])),
            content_hash=str(value["content_hash"]),
        )


def content_identity(prefix: str, payload: Mapping[str, Any]) -> tuple[ArtifactId, str]:
    require_text("prefix", prefix)
    digest = canonical_hash(dict(payload))
    return ArtifactId(f"{prefix}:{digest[7:]}"), digest


def decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def timestamp(value: datetime) -> str:
    return canonical_datetime(value)


ENGINEERING_LIMITATIONS = (
    "ALPHA_VALIDATED_FALSE",
    "EXPLORATORY_ONLY",
    "FORMAL_OOS_FALSE",
    "NO_TRADING_AUTHORITY",
    "PRODUCTION_AUTHORIZED_FALSE",
)

GOVERNED_NON_PRODUCTION_LIMITATIONS = (
    "ALPHA_VALIDATED_FALSE",
    "NO_TRADING_AUTHORITY",
    "PRODUCTION_AUTHORIZED_FALSE",
)
