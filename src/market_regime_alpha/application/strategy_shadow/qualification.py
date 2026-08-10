"""Sustained Strategy Shadow qualification remains an explicit Governance act."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    GOVERNED_NON_PRODUCTION_LIMITATIONS,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.strategy_shadow.operations import StrategyShadowDailyReport
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


@dataclass(frozen=True, slots=True)
class StrategyShadowQualificationProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    protocol_version: str
    minimum_sessions: int
    minimum_distinct_days: int
    maximum_incidents: int
    maximum_drifts: int
    locked_at: datetime

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        minimum_sessions: int,
        minimum_distinct_days: int,
        maximum_incidents: int,
        maximum_drifts: int,
        locked_at: datetime,
    ) -> StrategyShadowQualificationProtocol:
        if minimum_sessions <= 0 or minimum_distinct_days <= 0 or maximum_incidents < 0 or maximum_drifts < 0:
            raise ValueError("Strategy Shadow qualification floors are invalid")
        payload = {
            "schema": "strategy-shadow-qualification-protocol/v1",
            "protocol_version": protocol_version,
            "minimum_sessions": minimum_sessions,
            "minimum_distinct_days": minimum_distinct_days,
            "maximum_incidents": maximum_incidents,
            "maximum_drifts": maximum_drifts,
            "locked_at": timestamp(locked_at),
        }
        artifact_id, digest = content_identity("strategy-shadow-qualification-protocol", payload)
        return cls(
            artifact_id, digest, protocol_version, minimum_sessions, minimum_distinct_days, maximum_incidents, maximum_drifts, locked_at
        )


@dataclass(frozen=True, slots=True)
class StrategyShadowQualificationEvidence:
    evidence_id: ArtifactId
    evidence_hash: str
    protocol_reference: ValidationArtifactReference
    report_references: tuple[ValidationArtifactReference, ...]
    prospective_attestation_references: tuple[ValidationArtifactReference, ...]
    governance_approval_reference: ValidationArtifactReference | None
    sustained_strategy_shadow_proven: bool
    reason_codes: tuple[str, ...]
    created_at: datetime
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("evidence_hash", self.evidence_hash)
        if self.sustained_strategy_shadow_proven and (
            not self.prospective_attestation_references or self.governance_approval_reference is None
        ):
            raise ValueError("sustained Strategy Shadow proof requires Prospective and Governance evidence")
        if canonical_hash(self.identity_payload()) != self.evidence_hash:
            raise ValueError("Strategy Shadow qualification evidence hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _payload(
            self.protocol_reference,
            self.report_references,
            self.prospective_attestation_references,
            self.governance_approval_reference,
            self.sustained_strategy_shadow_proven,
            self.reason_codes,
            self.created_at,
            self.limitations,
        )


def evaluate_strategy_shadow_qualification(
    *,
    protocol: StrategyShadowQualificationProtocol,
    reports: tuple[StrategyShadowDailyReport, ...],
    prospective_attestation_references: tuple[ValidationArtifactReference, ...],
    governance_approval_reference: ValidationArtifactReference | None,
    created_at: datetime,
) -> StrategyShadowQualificationEvidence:
    sessions = sum(item.scheduled_count for item in reports)
    days = len({item.trading_date for item in reports})
    incidents = sum(item.incident_count for item in reports)
    drifts = sum(item.drift_count for item in reports)
    floors = (
        sessions >= protocol.minimum_sessions
        and days >= protocol.minimum_distinct_days
        and incidents <= protocol.maximum_incidents
        and drifts <= protocol.maximum_drifts
    )
    proven = floors and bool(prospective_attestation_references) and governance_approval_reference is not None
    report_refs = tuple(
        sorted(
            (ValidationArtifactReference("STRATEGY_SHADOW_DAILY_REPORT", item.report_id, item.report_hash) for item in reports),
            key=lambda item: str(item.artifact_id),
        )
    )
    attestation_refs = tuple(sorted(set(prospective_attestation_references), key=lambda item: str(item.artifact_id)))
    reasons = ("SUSTAINED_STRATEGY_SHADOW_PROVEN_BY_GOVERNANCE",) if proven else ("STRATEGY_SHADOW_PROVEN_FALSE",)
    limitations = (
        GOVERNED_NON_PRODUCTION_LIMITATIONS if proven else tuple(sorted({*ENGINEERING_LIMITATIONS, "STRATEGY_SHADOW_PROVEN_FALSE"}))
    )
    protocol_ref = ValidationArtifactReference("STRATEGY_SHADOW_QUALIFICATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    payload = _payload(protocol_ref, report_refs, attestation_refs, governance_approval_reference, proven, reasons, created_at, limitations)
    artifact_id, digest = content_identity("strategy-shadow-qualification-evidence", payload)
    return StrategyShadowQualificationEvidence(
        artifact_id,
        digest,
        protocol_ref,
        report_refs,
        attestation_refs,
        governance_approval_reference,
        proven,
        reasons,
        created_at,
        limitations,
    )


def _payload(
    protocol: ValidationArtifactReference,
    reports: tuple[ValidationArtifactReference, ...],
    attestations: tuple[ValidationArtifactReference, ...],
    approval: ValidationArtifactReference | None,
    proven: bool,
    reasons: tuple[str, ...],
    created_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema": "strategy-shadow-qualification-evidence/v1",
        "protocol_reference": protocol.to_canonical_dict(),
        "report_references": [item.to_canonical_dict() for item in reports],
        "prospective_attestation_references": [item.to_canonical_dict() for item in attestations],
        "governance_approval_reference": None if approval is None else approval.to_canonical_dict(),
        "sustained_strategy_shadow_proven": proven,
        "reason_codes": list(reasons),
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }
