"""Fail-closed Production Admission gap projection.

No current PostgreSQL owner resolves every admission floor.  Consequently this
module records missing/rejected floors only; it cannot promote references into
review eligibility or Production authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from market_regime_alpha.application.research_validation.common import ValidationArtifactReference, content_identity, timestamp
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


class AdmissionFloor(str, Enum):
    FORMAL_PIT = "FORMAL_PIT"
    FORMAL_OOS = "FORMAL_OOS"
    ECONOMIC_VALIDATION = "ECONOMIC_VALIDATION"
    CALIBRATION = "CALIBRATION"
    COST_CAPACITY = "COST_CAPACITY"
    ENTRY_QUALIFICATION = "ENTRY_QUALIFICATION"
    HOLDING_EXIT_VALIDATION = "HOLDING_EXIT_VALIDATION"
    SUSTAINED_STRATEGY_SHADOW = "SUSTAINED_STRATEGY_SHADOW"
    OPERATOR_APPROVAL = "OPERATOR_APPROVAL"
    AUTH_RBAC = "AUTH_RBAC"
    BROKER_READINESS = "BROKER_READINESS"


class AdmissionFloorStatus(str, Enum):
    MISSING = "MISSING"
    REJECTED = "REJECTED"


class ProductionAdmissionStatus(str, Enum):
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class AdmissionFloorAssessment:
    floor: AdmissionFloor
    status: AdmissionFloorStatus
    evidence_reference: ValidationArtifactReference | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Admission floor reasons must be unique and sorted")


@dataclass(frozen=True, slots=True)
class ProductionAdmissionDecision:
    decision_id: ArtifactId
    decision_hash: str
    governance_version: str
    assessments: tuple[AdmissionFloorAssessment, ...]
    status: ProductionAdmissionStatus
    blocked_floors: tuple[AdmissionFloor, ...]
    evaluated_at: datetime
    governance_decision_reference: ValidationArtifactReference | None
    automatic_promotion: bool
    limitations: tuple[str, ...]
    schema_version: str = "production-admission-decision/v1"

    def __post_init__(self) -> None:
        require_sha256("decision_hash", self.decision_hash)
        if self.assessments != tuple(sorted(self.assessments, key=lambda item: item.floor.value)) or {
            item.floor for item in self.assessments
        } != set(AdmissionFloor):
            raise ValueError("Production Admission must assess every Governance floor")
        expected_blocked = tuple(sorted(AdmissionFloor, key=lambda item: item.value))
        if self.blocked_floors != expected_blocked:
            raise ValueError("Production Admission blocked-floor projection mismatch")
        if self.automatic_promotion:
            raise ValueError("automatic Production promotion is prohibited")
        if self.status is not ProductionAdmissionStatus.BLOCKED:
            raise ValueError("Production Admission is currently a blocked projection")
        if self.governance_decision_reference is not None:
            raise ValueError("blocked Admission cannot claim a Governance authorization")
        if canonical_hash(self.identity_payload()) != self.decision_hash:
            raise ValueError("Production Admission hash mismatch")

    @property
    def production_authorized(self) -> bool:
        return False

    def identity_payload(self) -> dict[str, Any]:
        return _payload(
            self.governance_version,
            self.assessments,
            self.status,
            self.blocked_floors,
            self.evaluated_at,
            self.governance_decision_reference,
            self.limitations,
        )


def evaluate_production_admission(
    *,
    governance_version: str,
    assessments: tuple[AdmissionFloorAssessment, ...],
    evaluated_at: datetime,
) -> ProductionAdmissionDecision:
    ordered = tuple(sorted(assessments, key=lambda item: item.floor.value))
    if len(ordered) != len(AdmissionFloor) or {item.floor for item in ordered} != set(AdmissionFloor):
        raise ValueError("Production Admission requires every floor exactly once")
    status = ProductionAdmissionStatus.BLOCKED
    blocked = tuple(sorted(AdmissionFloor, key=lambda item: item.value))
    limitations = tuple(
        sorted(
            {
                "ADMISSION_FLOOR_OWNER_RESOLUTION_NOT_IMPLEMENTED",
                "AUTOMATIC_PROMOTION_FALSE",
                "BROKER_MUTATION_FALSE",
                "PRODUCTION_AUTHORIZED_FALSE",
            }
        )
    )
    governance_ref = None
    payload = _payload(governance_version, ordered, status, blocked, evaluated_at, None, limitations)
    artifact_id, digest = content_identity("production-admission-decision", payload)
    return ProductionAdmissionDecision(
        artifact_id,
        digest,
        governance_version,
        ordered,
        status,
        blocked,
        evaluated_at,
        governance_ref,
        False,
        limitations,
    )


def current_engineering_blocked_admission(
    *, governance_version: str, evidence: dict[AdmissionFloor, ValidationArtifactReference], evaluated_at: datetime
) -> ProductionAdmissionDecision:
    """Current baseline: mechanics can be referenced but real floors stay closed."""
    assessments = tuple(
        AdmissionFloorAssessment(
            floor=floor,
            status=AdmissionFloorStatus.MISSING,
            evidence_reference=evidence.get(floor),
            reason_codes=(f"{floor.value}_REAL_EVIDENCE_NOT_ESTABLISHED",),
        )
        for floor in AdmissionFloor
    )
    return evaluate_production_admission(governance_version=governance_version, assessments=assessments, evaluated_at=evaluated_at)


def _payload(
    version: str,
    assessments: tuple[AdmissionFloorAssessment, ...],
    status: ProductionAdmissionStatus,
    blocked: tuple[AdmissionFloor, ...],
    evaluated_at: datetime,
    governance: ValidationArtifactReference | None,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "production-admission-decision/v1",
        "governance_version": version,
        "assessments": [
            {
                "floor": item.floor.value,
                "status": item.status.value,
                "evidence_reference": None if item.evidence_reference is None else item.evidence_reference.to_canonical_dict(),
                "reason_codes": list(item.reason_codes),
            }
            for item in assessments
        ],
        "status": status.value,
        "blocked_floors": [item.value for item in blocked],
        "evaluated_at": timestamp(evaluated_at),
        "governance_decision_reference": None if governance is None else governance.to_canonical_dict(),
        "automatic_promotion": False,
        "limitations": list(limitations),
    }
