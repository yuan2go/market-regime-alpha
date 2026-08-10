"""Prospective-evidence attestation mechanism without granting prospective PASS."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    ProspectiveShadowOutcome,
)
from market_regime_alpha.application.shadow_research.contracts import ShadowDecision
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode


class ClockMode(str, Enum):
    LIVE_TRUSTED = "LIVE_TRUSTED"
    SIMULATED = "SIMULATED"
    UNKNOWN = "UNKNOWN"


class RuntimeOrigin(str, Enum):
    LIVE_ACQUISITION = "LIVE_ACQUISITION"
    REPLAY = "REPLAY"
    FIXTURE = "FIXTURE"
    UNKNOWN = "UNKNOWN"


class AttestationStatus(str, Enum):
    ENGINEERING_ATTESTABLE = "ENGINEERING_ATTESTABLE"
    INELIGIBLE = "INELIGIBLE"


@dataclass(frozen=True, slots=True)
class AttestationCheck:
    check_name: str
    satisfied: bool
    reason_code: str

    def __post_init__(self) -> None:
        require_text("check_name", self.check_name)
        require_text("reason_code", self.reason_code)
        if not isinstance(self.satisfied, bool):
            raise TypeError("Attestation check satisfied must be bool")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "satisfied": self.satisfied,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class ProspectiveEvidenceAttestation:
    attestation_id: ArtifactId
    attestation_hash: str
    shadow_decision: RuntimeArtifactReference
    outcome_settlement: RuntimeArtifactReference
    frozen_summary: RuntimeArtifactReference
    source_archive: RuntimeArtifactReference
    source_dataset: RuntimeArtifactReference
    source_acquisition_receipts: tuple[RuntimeArtifactReference, ...]
    run_id: ArtifactId
    tick_id: ArtifactId
    decision_frozen_at: datetime
    outcome_available_at: datetime
    code_revision: str
    runtime_mode: RuntimeAuthorityMode
    clock_mode: ClockMode
    runtime_origin: RuntimeOrigin
    checks: tuple[AttestationCheck, ...]
    status: AttestationStatus
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "prospective-evidence-attestation/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "prospective-evidence-attestation/v1":
            raise ValueError("unsupported prospective attestation schema")
        require_sha256("attestation_hash", self.attestation_hash)
        require_text("code_revision", self.code_revision)
        for label, value in (
            ("decision_frozen_at", self.decision_frozen_at),
            ("outcome_available_at", self.outcome_available_at),
            ("created_at", self.created_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{label} must be timezone-aware")
        if self.created_at < self.outcome_available_at:
            raise ValueError("Attestation cannot predate Outcome availability")
        if self.checks != tuple(sorted(self.checks, key=lambda item: item.check_name)):
            raise ValueError("Attestation checks must be unique and sorted")
        if len({item.check_name for item in self.checks}) != len(self.checks):
            raise ValueError("Attestation checks must be unique")
        if self.source_acquisition_receipts != tuple(
            sorted(
                set(self.source_acquisition_receipts),
                key=lambda item: (
                    item.reference_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        ):
            raise ValueError("Attestation source receipts must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Attestation limitations must be unique and sorted")
        required = {
            "FORMAL_PROVIDER_QUALIFICATION_NOT_ESTABLISHED",
            "NO_PROSPECTIVE_PASS_ISSUED",
            "NOT_ALPHA_VALIDATION",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Attestation authority ceiling is incomplete")
        expected = AttestationStatus.ENGINEERING_ATTESTABLE if all(item.satisfied for item in self.checks) else AttestationStatus.INELIGIBLE
        if self.status is not expected:
            raise ValueError("Attestation status does not match checks")
        if canonical_hash(self.identity_payload()) != self.attestation_hash:
            raise ValueError("Attestation hash does not match content")
        if str(self.attestation_id) != f"prospective-attestation:{self.attestation_hash[7:]}":
            raise ValueError("Attestation id does not match content")

    @property
    def prospective_proven(self) -> bool:
        return False

    @classmethod
    def create(
        cls,
        *,
        decision: ShadowDecision,
        outcome: ProspectiveShadowOutcome,
        source_acquisition_receipts: tuple[RuntimeArtifactReference, ...],
        code_revision: str,
        runtime_mode: RuntimeAuthorityMode,
        clock_mode: ClockMode,
        runtime_origin: RuntimeOrigin,
        created_at: datetime,
    ) -> ProspectiveEvidenceAttestation:
        if outcome.shadow_decision.artifact_id != decision.decision_id:
            raise ValueError("Attestation Outcome does not bind frozen Decision")
        ordered_receipts = tuple(
            sorted(
                set(source_acquisition_receipts),
                key=lambda item: (
                    item.reference_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        )
        if ordered_receipts != decision.provider_source_references:
            raise ValueError("Attestation source receipts do not match frozen Decision")
        checks = tuple(
            sorted(
                (
                    AttestationCheck(
                        "DECISION_PRECEDES_OUTCOME",
                        decision.decision_frozen_at < outcome.outcome_available_at,
                        "DECISION_BEFORE_OUTCOME"
                        if decision.decision_frozen_at < outcome.outcome_available_at
                        else "TEMPORAL_ORDER_INVALID",
                    ),
                    AttestationCheck(
                        "LIVE_CLOCK",
                        clock_mode is ClockMode.LIVE_TRUSTED,
                        "TRUSTED_LIVE_CLOCK" if clock_mode is ClockMode.LIVE_TRUSTED else "CLOCK_NOT_LIVE_TRUSTED",
                    ),
                    AttestationCheck(
                        "LIVE_RUNTIME_ORIGIN",
                        runtime_origin is RuntimeOrigin.LIVE_ACQUISITION,
                        "LIVE_ACQUISITION_ORIGIN"
                        if runtime_origin is RuntimeOrigin.LIVE_ACQUISITION
                        else "REPLAY_OR_FIXTURE_NOT_PROSPECTIVE",
                    ),
                    AttestationCheck(
                        "SHADOW_RUNTIME_MODE",
                        runtime_mode is RuntimeAuthorityMode.SHADOW,
                        "SHADOW_RUNTIME_BOUND" if runtime_mode is RuntimeAuthorityMode.SHADOW else "RUNTIME_MODE_INVALID",
                    ),
                    AttestationCheck(
                        "SOURCE_ACQUISITION_RECEIPTS",
                        bool(source_acquisition_receipts),
                        "SOURCE_RECEIPTS_BOUND" if source_acquisition_receipts else "SOURCE_RECEIPTS_MISSING",
                    ),
                ),
                key=lambda item: item.check_name,
            )
        )
        values: dict[str, Any] = {
            "shadow_decision": RuntimeArtifactReference("SHADOW_DECISION", decision.decision_id, decision.decision_hash),
            "outcome_settlement": RuntimeArtifactReference("FACTUAL_OUTCOME_V1", outcome.settlement_id, outcome.settlement_hash),
            "frozen_summary": decision.summary,
            "source_archive": outcome.source_archive,
            "source_dataset": outcome.source_dataset,
            "source_acquisition_receipts": ordered_receipts,
            "run_id": decision.run_id,
            "tick_id": decision.tick_id,
            "decision_frozen_at": decision.decision_frozen_at,
            "outcome_available_at": outcome.outcome_available_at,
            "code_revision": code_revision,
            "runtime_mode": runtime_mode,
            "clock_mode": clock_mode,
            "runtime_origin": runtime_origin,
            "checks": checks,
            "status": (
                AttestationStatus.ENGINEERING_ATTESTABLE if all(item.satisfied for item in checks) else AttestationStatus.INELIGIBLE
            ),
            "created_at": created_at,
            "limitations": tuple(
                sorted(
                    {
                        "FORMAL_PROVIDER_QUALIFICATION_NOT_ESTABLISHED",
                        "NO_PROSPECTIVE_PASS_ISSUED",
                        "NOT_ALPHA_VALIDATION",
                    }
                )
            ),
        }
        digest = canonical_hash(_payload(**values))
        return cls(
            attestation_id=ArtifactId(f"prospective-attestation:{digest[7:]}"),
            attestation_hash=digest,
            **values,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _payload(**{name: getattr(self, name) for name in _value_names()})

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": str(self.attestation_id),
            "attestation_hash": self.attestation_hash,
            **self.identity_payload(),
            "authority": {"prospective_proven": False, "alpha_validated": False},
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ProspectiveEvidenceAttestation:
        if payload.get("authority") != {
            "prospective_proven": False,
            "alpha_validated": False,
        }:
            raise ValueError("Attestation authority declaration mismatch")
        return cls(
            attestation_id=ArtifactId(str(payload["attestation_id"])),
            attestation_hash=str(payload["attestation_hash"]),
            shadow_decision=_reference(payload["shadow_decision"]),
            outcome_settlement=_reference(payload["outcome_settlement"]),
            frozen_summary=_reference(payload["frozen_summary"]),
            source_archive=_reference(payload["source_archive"]),
            source_dataset=_reference(payload["source_dataset"]),
            source_acquisition_receipts=tuple(_reference(item) for item in _objects(payload["source_acquisition_receipts"])),
            run_id=ArtifactId(str(payload["run_id"])),
            tick_id=ArtifactId(str(payload["tick_id"])),
            decision_frozen_at=_instant(payload["decision_frozen_at"]),
            outcome_available_at=_instant(payload["outcome_available_at"]),
            code_revision=str(payload["code_revision"]),
            runtime_mode=RuntimeAuthorityMode(str(payload["runtime_mode"])),
            clock_mode=ClockMode(str(payload["clock_mode"])),
            runtime_origin=RuntimeOrigin(str(payload["runtime_origin"])),
            checks=tuple(
                AttestationCheck(
                    check_name=str(item["check_name"]),
                    satisfied=_boolean(item["satisfied"]),
                    reason_code=str(item["reason_code"]),
                )
                for item in _objects(payload["checks"])
            ),
            status=AttestationStatus(str(payload["status"])),
            created_at=_instant(payload["created_at"]),
            limitations=tuple(str(item) for item in _array(payload["limitations"])),
            schema_version=str(payload["schema_version"]),
        )


def _value_names() -> tuple[str, ...]:
    return (
        "shadow_decision",
        "outcome_settlement",
        "frozen_summary",
        "source_archive",
        "source_dataset",
        "source_acquisition_receipts",
        "run_id",
        "tick_id",
        "decision_frozen_at",
        "outcome_available_at",
        "code_revision",
        "runtime_mode",
        "clock_mode",
        "runtime_origin",
        "checks",
        "status",
        "created_at",
        "limitations",
    )


def _payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "prospective-evidence-attestation/v1",
        "shadow_decision": values["shadow_decision"].to_canonical_dict(),
        "outcome_settlement": values["outcome_settlement"].to_canonical_dict(),
        "frozen_summary": values["frozen_summary"].to_canonical_dict(),
        "source_archive": values["source_archive"].to_canonical_dict(),
        "source_dataset": values["source_dataset"].to_canonical_dict(),
        "source_acquisition_receipts": [item.to_canonical_dict() for item in values["source_acquisition_receipts"]],
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "decision_frozen_at": canonical_datetime(values["decision_frozen_at"]),
        "outcome_available_at": canonical_datetime(values["outcome_available_at"]),
        "code_revision": values["code_revision"],
        "runtime_mode": values["runtime_mode"].value,
        "clock_mode": values["clock_mode"].value,
        "runtime_origin": values["runtime_origin"].value,
        "checks": [item.to_canonical_dict() for item in values["checks"]],
        "status": values["status"].value,
        "created_at": canonical_datetime(values["created_at"]),
        "limitations": list(values["limitations"]),
    }


def _reference(value: object) -> RuntimeArtifactReference:
    if not isinstance(value, Mapping):
        raise ValueError("reference must be an object")
    return RuntimeArtifactReference(
        str(value["reference_kind"]),
        ArtifactId(str(value["artifact_id"])),
        str(value["content_hash"]),
    )


def _objects(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError("expected object array")
    return tuple(value)


def _array(value: object) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return tuple(value)


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expected timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("expected boolean")
    return value


__all__ = [
    "AttestationCheck",
    "AttestationStatus",
    "ClockMode",
    "ProspectiveEvidenceAttestation",
    "RuntimeOrigin",
]
