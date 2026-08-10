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
from market_regime_alpha.platform.runtime_governance import (
    ModelQualificationDecision,
    ModelQualificationEvidence,
    QualificationEvidenceKind,
    QualificationEvidenceOutcome,
    QualificationStatus,
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


@dataclass(frozen=True, slots=True)
class GovernanceQualificationBinding:
    """Existing Model Governance decision with its exact immutable evidence set."""

    decision: ModelQualificationDecision
    evidence: tuple[ModelQualificationEvidence, ...]

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.evidence, key=lambda item: str(item.evidence_id)))
        if self.evidence != ordered:
            raise ValueError("Governance evidence must be unique and sorted")
        if self.decision.status is not QualificationStatus.QUALIFIED:
            raise ValueError("Validation qualification requires an existing QUALIFIED Governance decision")
        if self.decision.evidence_ids != tuple(item.evidence_id for item in ordered) or self.decision.evidence_hashes != tuple(
            item.evidence_hash for item in ordered
        ):
            raise ValueError("Governance decision/evidence set mismatch")
        if any(
            item.outcome is not QualificationEvidenceOutcome.SATISFIED
            or item.model_id != self.decision.model_id
            or item.definition_hash != self.decision.definition_hash
            or item.lineage_id != self.decision.lineage_id
            or item.lineage_hash != self.decision.lineage_hash
            for item in ordered
        ):
            raise ValueError("Governance evidence is not satisfied or lineage-bound")

    @property
    def decision_reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference("MODEL_QUALIFICATION_DECISION", self.decision.decision_id, self.decision.decision_hash)

    def require_artifact(
        self,
        reference: ValidationArtifactReference,
        evidence_kind: QualificationEvidenceKind,
    ) -> None:
        if not any(
            item.evidence_kind is evidence_kind
            and item.evidence.reference_kind == reference.artifact_kind
            and item.evidence.artifact_id == reference.artifact_id
            and item.evidence.content_hash == reference.content_hash
            for item in self.evidence
        ):
            raise ValueError(f"Governance decision lacks bound {evidence_kind.value} evidence")


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
