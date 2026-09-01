"""Immutable Evaluation-bound Research Evidence semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import re
from enum import StrEnum
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")


class EvidenceClass(StrEnum):
    SOFTWARE_VERIFICATION = "SOFTWARE_VERIFICATION"
    SOURCE_CAPTURE = "SOURCE_CAPTURE"
    TEMPORAL_LINEAGE = "TEMPORAL_LINEAGE"
    DATASET_LINEAGE = "DATASET_LINEAGE"
    RESEARCH_RESULT = "RESEARCH_RESULT"
    OUTCOME_OBSERVATION = "OUTCOME_OBSERVATION"
    REPLAY_COMPARISON = "REPLAY_COMPARISON"
    OPERATOR_ATTESTATION = "OPERATOR_ATTESTATION"


class EvidenceOriginClass(StrEnum):
    FIXTURE = "FIXTURE"
    RECORDED_PROVIDER = "RECORDED_PROVIDER"
    QUALIFIED_ARCHIVE = "QUALIFIED_ARCHIVE"
    PROSPECTIVE_CAPTURE = "PROSPECTIVE_CAPTURE"
    DERIVED_CANONICAL = "DERIVED_CANONICAL"
    OPERATOR_ATTESTED = "OPERATOR_ATTESTED"


class EvidenceScope(StrEnum):
    RUN = "RUN"
    METRIC = "METRIC"


class EvidenceRole(StrEnum):
    PRIMARY_RESULT = "PRIMARY_RESULT"
    ROBUSTNESS = "ROBUSTNESS"
    LINEAGE = "LINEAGE"
    MISSINGNESS = "MISSINGNESS"
    LIMITATION = "LIMITATION"
    REPLAY = "REPLAY"
    PROCESS_CONTROL = "PROCESS_CONTROL"


class EvidenceDirection(StrEnum):
    SUPPORT = "SUPPORT"
    COUNTER = "COUNTER"
    NEUTRAL = "NEUTRAL"


class EvidenceDependencyRole(StrEnum):
    DERIVED_FROM = "DERIVED_FROM"
    CORROBORATES = "CORROBORATES"
    QUALIFIES = "QUALIFIES"
    CONTRADICTS = "CONTRADICTS"


class ResearchProofClass(StrEnum):
    ENGINEERING = "ENGINEERING"
    EXPLORATORY = "EXPLORATORY"
    PIT_QUALIFIED = "PIT_QUALIFIED"
    FORMAL_OOS = "FORMAL_OOS"
    PROSPECTIVE = "PROSPECTIVE"


@dataclass(frozen=True, slots=True)
class EvidenceDependencyPlan:
    evidence_dependency_id: UUID
    parent_evidence_item_id: UUID
    ordinal: int
    dependency_role: EvidenceDependencyRole
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Evidence dependency ordinal must be positive")
        if not isinstance(self.dependency_role, EvidenceDependencyRole):
            raise TypeError("dependency_role must be EvidenceDependencyRole")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "dependency_role": self.dependency_role,
                        "evidence_dependency_id": self.evidence_dependency_id,
                        "ordinal": self.ordinal,
                        "parent_evidence_item_id": self.parent_evidence_item_id,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class EvidenceItemPlan:
    evidence_item_id: UUID
    evaluation_run_id: UUID
    evaluation_metric_id: UUID | None
    evidence_code: str
    scope: EvidenceScope
    evidence_class: EvidenceClass
    origin_class: EvidenceOriginClass
    role: EvidenceRole
    direction: EvidenceDirection
    proof_ceiling: ResearchProofClass
    observed_at: datetime
    evidence_artifact: ArtifactBinding
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    dependencies: tuple[EvidenceDependencyPlan, ...]
    dependency_count: int = field(init=False)
    dependency_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.evidence_code):
            raise ValueError("evidence_code has an invalid format")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))
        if self.scope is EvidenceScope.RUN and self.evaluation_metric_id is not None:
            raise ValueError("RUN-scoped Evidence forbids an EvaluationMetric")
        if self.scope is EvidenceScope.METRIC and self.evaluation_metric_id is None:
            raise ValueError("METRIC-scoped Evidence requires an EvaluationMetric")
        expected_ordinals = tuple(range(1, len(self.dependencies) + 1))
        if tuple(item.ordinal for item in self.dependencies) != expected_ordinals:
            raise ValueError("Evidence dependency ordinals must be contiguous")
        parent_ids = tuple(item.parent_evidence_item_id for item in self.dependencies)
        if len(set(parent_ids)) != len(parent_ids):
            raise ValueError("Evidence dependency roster contains a duplicate parent")
        if self.evidence_item_id in parent_ids:
            raise ValueError("Evidence cannot depend on itself")
        provenance_hash = ContentHash(str(self.provenance_sha256))
        roster_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item.content_sha256),
                        "dependency_role": item.dependency_role,
                        "evidence_dependency_id": item.evidence_dependency_id,
                        "ordinal": item.ordinal,
                        "parent_evidence_item_id": item.parent_evidence_item_id,
                    }
                    for item in self.dependencies
                )
            )
        )
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(self, "dependency_count", len(self.dependencies))
        object.__setattr__(self, "dependency_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "dependency_count": len(self.dependencies),
                        "dependency_roster_sha256": roster_hash,
                        "direction": self.direction,
                        "evaluation_metric_id": self.evaluation_metric_id,
                        "evaluation_run_id": self.evaluation_run_id,
                        "evidence_artifact": self.evidence_artifact,
                        "evidence_class": self.evidence_class,
                        "evidence_code": self.evidence_code,
                        "evidence_item_id": self.evidence_item_id,
                        "observed_at": self.observed_at,
                        "origin_class": self.origin_class,
                        "proof_ceiling": self.proof_ceiling,
                        "provenance_sha256": provenance_hash,
                        "role": self.role,
                        "scope": self.scope,
                    }
                )
            ),
        )


__all__ = [
    "EvidenceClass",
    "EvidenceDependencyPlan",
    "EvidenceDependencyRole",
    "EvidenceDirection",
    "EvidenceItemPlan",
    "EvidenceOriginClass",
    "EvidenceRole",
    "EvidenceScope",
    "ResearchProofClass",
]
