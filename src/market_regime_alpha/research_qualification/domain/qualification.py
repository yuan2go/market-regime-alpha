"""Purpose-specific Research Qualification Policy and Decision semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.research_qualification.domain.assessment import AssessmentStatus
from market_regime_alpha.research_qualification.domain.evidence import (
    EvidenceClass,
    EvidenceOriginClass,
    EvidenceRole,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    CandidateDisposition,
    EvaluationReducer,
    EvaluationSliceKind,
    MetricDirection,
    PartitionPurpose,
    SourceMetricValueType,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")


class QualificationPurpose(StrEnum):
    DISCOVERY = "DISCOVERY"
    VALIDATION = "VALIDATION"
    LOCKED_OOS = "LOCKED_OOS"
    PROSPECTIVE = "PROSPECTIVE"


class QualificationOperator(StrEnum):
    AT_LEAST = "AT_LEAST"
    AT_MOST = "AT_MOST"
    EQUALS = "EQUALS"


class FloorMissingnessPolicy(StrEnum):
    REJECT = "REJECT"
    INCONCLUSIVE = "INCONCLUSIVE"


class FloorResultStatus(StrEnum):
    SATISFIED = "SATISFIED"
    REJECTED = "REJECTED"
    MISSING = "MISSING"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"


class QualificationDecisionStatus(StrEnum):
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class QualificationPolicyFloorPlan:
    research_qualification_policy_floor_id: UUID
    floor_code: str
    ordinal: int
    evaluation_protocol_id: UUID
    evaluation_protocol_metric_id: UUID
    evaluation_protocol_metric_sha256: ContentHash | str
    required_partition_purpose: PartitionPurpose
    required_evaluation_status: str
    metric_code: str
    source_value_type: SourceMetricValueType
    reducer: EvaluationReducer
    slice_kind: EvaluationSliceKind
    candidate_disposition: CandidateDisposition | None
    direction: MetricDirection
    operator: QualificationOperator
    decimal_threshold: Decimal | None
    boolean_threshold: bool | None
    minimum_member_count: int
    minimum_estimable_count: int
    missingness_policy: FloorMissingnessPolicy
    required_evidence_class: EvidenceClass
    required_origin_class: EvidenceOriginClass
    required_evidence_role: EvidenceRole
    minimum_support_evidence_count: int
    maximum_counter_evidence_count: int
    required: bool
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.floor_code) or not _CODE.fullmatch(self.metric_code):
            raise ValueError("Qualification floor code has an invalid format")
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Qualification floor ordinal must be positive")
        if self.required_evaluation_status != "COMPLETED":
            raise ValueError("Qualification floors require COMPLETED Evaluation")
        compatible = {
            EvaluationReducer.MEAN_DECIMAL: SourceMetricValueType.DECIMAL,
            EvaluationReducer.MEDIAN_DECIMAL: SourceMetricValueType.DECIMAL,
            EvaluationReducer.TRUE_RATE: SourceMetricValueType.BOOLEAN,
            EvaluationReducer.ESTIMABLE_RATE: SourceMetricValueType.DECIMAL,
        }
        if compatible[self.reducer] is not self.source_value_type:
            raise ValueError("Qualification floor reducer/source type mismatch")
        if self.source_value_type is SourceMetricValueType.DECIMAL:
            if self.decimal_threshold is None or self.boolean_threshold is not None:
                raise ValueError("Decimal Qualification floor requires Decimal threshold")
            if self.operator is QualificationOperator.EQUALS:
                raise ValueError("Decimal Qualification floor forbids EQUALS")
        elif self.decimal_threshold is not None or self.boolean_threshold is None:
            raise ValueError("Boolean Qualification floor requires Boolean threshold")
        elif self.operator is not QualificationOperator.EQUALS:
            raise ValueError("Boolean Qualification floor requires EQUALS")
        if self.slice_kind is EvaluationSliceKind.CANDIDATE_DISPOSITION:
            if not isinstance(self.candidate_disposition, CandidateDisposition):
                raise ValueError("candidate_disposition is required for this slice")
        elif self.candidate_disposition is not None:
            raise ValueError("candidate_disposition is forbidden for ALL_MEMBERS")
        for name, value, minimum in (
            ("minimum_member_count", self.minimum_member_count, 1),
            ("minimum_estimable_count", self.minimum_estimable_count, 1),
            ("minimum_support_evidence_count", self.minimum_support_evidence_count, 0),
            ("maximum_counter_evidence_count", self.maximum_counter_evidence_count, 0),
        ):
            if isinstance(value, bool) or value < minimum:
                raise ValueError(f"{name} is below its minimum")
        metric_hash = ContentHash(str(self.evaluation_protocol_metric_sha256))
        object.__setattr__(self, "evaluation_protocol_metric_sha256", metric_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(canonical_json_sha256({name: getattr(self, name) for name in self.__dataclass_fields__ if name != "content_sha256"})),
        )


@dataclass(frozen=True, slots=True)
class ResearchQualificationPolicyPlan:
    research_qualification_policy_id: UUID
    policy_code: str
    version: int
    supersedes_policy_id: UUID | None
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    qualification_purpose: QualificationPurpose
    required_assessment_status: AssessmentStatus
    require_preaccess_freeze: bool
    floors: tuple[QualificationPolicyFloorPlan, ...]
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    floor_count: int = field(init=False)
    floor_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.policy_code):
            raise ValueError("policy_code has an invalid format")
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Policy version must be positive")
        if (self.version == 1) != (self.supersedes_policy_id is None):
            raise ValueError("Policy supersession shape is invalid")
        if not self.floors:
            raise ValueError("Qualification Policy requires a floor roster")
        if tuple(item.ordinal for item in self.floors) != tuple(range(1, len(self.floors) + 1)):
            raise ValueError("Qualification floor ordinals must be contiguous")
        if len({item.floor_code for item in self.floors}) != len(self.floors):
            raise ValueError("Qualification floor codes must be unique")
        floor_bindings = tuple(
            (
                item.evaluation_protocol_metric_id,
                item.required_partition_purpose,
            )
            for item in self.floors
        )
        if len(set(floor_bindings)) != len(floor_bindings):
            raise ValueError("Qualification floor metric bindings must be unique")
        if not any(item.required for item in self.floors):
            raise ValueError("Qualification Policy requires a required floor")
        if self.qualification_purpose in {QualificationPurpose.LOCKED_OOS, QualificationPurpose.PROSPECTIVE} and not self.require_preaccess_freeze:
            raise ValueError("protected Qualification requires pre-access Policy freeze")
        target_hash = ContentHash(str(self.target_definition_sha256))
        provenance_hash = ContentHash(str(self.provenance_sha256))
        roster_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "boolean_threshold": item.boolean_threshold,
                        "candidate_disposition": item.candidate_disposition,
                        "content_sha256": str(item.content_sha256),
                        "decimal_threshold": item.decimal_threshold,
                        "direction": item.direction,
                        "evaluation_protocol_id": item.evaluation_protocol_id,
                        "evaluation_protocol_metric_id": item.evaluation_protocol_metric_id,
                        "evaluation_protocol_metric_sha256": str(
                            item.evaluation_protocol_metric_sha256
                        ),
                        "floor_code": item.floor_code,
                        "maximum_counter_evidence_count": item.maximum_counter_evidence_count,
                        "minimum_estimable_count": item.minimum_estimable_count,
                        "minimum_member_count": item.minimum_member_count,
                        "minimum_support_evidence_count": item.minimum_support_evidence_count,
                        "missingness_policy": item.missingness_policy,
                        "operator": item.operator,
                        "ordinal": item.ordinal,
                        "reducer": item.reducer,
                        "required": item.required,
                        "required_evaluation_status": item.required_evaluation_status,
                        "required_evidence_class": item.required_evidence_class,
                        "required_evidence_role": item.required_evidence_role,
                        "required_origin_class": item.required_origin_class,
                        "required_partition_purpose": item.required_partition_purpose,
                        "research_qualification_policy_floor_id": (
                            item.research_qualification_policy_floor_id
                        ),
                        "slice_kind": item.slice_kind,
                        "source_value_type": item.source_value_type,
                    }
                    for item in self.floors
                )
            )
        )
        object.__setattr__(self, "target_definition_sha256", target_hash)
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(self, "floor_count", len(self.floors))
        object.__setattr__(self, "floor_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "floor_count": len(self.floors),
                        "floor_roster_sha256": roster_hash,
                        "policy_code": self.policy_code,
                        "provenance_sha256": provenance_hash,
                        "qualification_purpose": self.qualification_purpose,
                        "required_assessment_status": self.required_assessment_status,
                        "require_preaccess_freeze": self.require_preaccess_freeze,
                        "research_qualification_policy_id": self.research_qualification_policy_id,
                        "supersedes_policy_id": self.supersedes_policy_id,
                        "target_definition_id": self.target_definition_id,
                        "target_definition_sha256": target_hash,
                        "target_version": self.target_version,
                        "version": self.version,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ResearchQualificationDecisionPlan:
    research_qualification_decision_id: UUID
    decision_code: str
    revision: int
    supersedes_decision_id: UUID | None
    research_assessment_id: UUID
    research_qualification_policy_id: UUID
    effective_at: datetime
    known_at: datetime
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.decision_code):
            raise ValueError("decision_code has an invalid format")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("Qualification Decision revision must be positive")
        if (self.revision == 1) != (self.supersedes_decision_id is None):
            raise ValueError("Qualification Decision supersession shape is invalid")
        for name in ("effective_at", "known_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.effective_at > self.known_at:
            raise ValueError("effective_at cannot follow known_at")
        object.__setattr__(self, "effective_at", self.effective_at.astimezone(UTC))
        object.__setattr__(self, "known_at", self.known_at.astimezone(UTC))
        provenance_hash = ContentHash(str(self.provenance_sha256))
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "decision_code": self.decision_code,
                        "effective_at": self.effective_at,
                        "known_at": self.known_at,
                        "provenance_sha256": provenance_hash,
                        "research_assessment_id": self.research_assessment_id,
                        "research_qualification_policy_id": (
                            self.research_qualification_policy_id
                        ),
                        "revision": self.revision,
                        "supersedes_decision_id": self.supersedes_decision_id,
                    }
                )
            ),
        )


def qualification_decision_status(
    *,
    assessment_status: AssessmentStatus,
    required_assessment_status: AssessmentStatus,
    required_floor_statuses: tuple[FloorResultStatus, ...],
) -> QualificationDecisionStatus:
    if not required_floor_statuses:
        raise ValueError("Qualification decision requires every floor result")
    if assessment_status is AssessmentStatus.REJECTED:
        return QualificationDecisionStatus.REJECTED
    if FloorResultStatus.REJECTED in required_floor_statuses:
        return QualificationDecisionStatus.REJECTED
    if assessment_status is required_assessment_status and all(
        item is FloorResultStatus.SATISFIED for item in required_floor_statuses
    ):
        return QualificationDecisionStatus.ADMITTED
    return QualificationDecisionStatus.INCONCLUSIVE


__all__ = [
    "FloorMissingnessPolicy",
    "FloorResultStatus",
    "QualificationDecisionStatus",
    "QualificationOperator",
    "QualificationPolicyFloorPlan",
    "QualificationPurpose",
    "ResearchQualificationDecisionPlan",
    "ResearchQualificationPolicyPlan",
    "qualification_decision_status",
]
