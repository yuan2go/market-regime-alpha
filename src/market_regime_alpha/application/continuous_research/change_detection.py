"""Canonical material identity and append-only Change Decision contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.evidence import EvidenceCommit
from market_regime_alpha.application.continuous_research.journal import (
    ClaimedRuntimeTick,
    ChangeDecisionType,
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_unique_text,
)
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second


CONTINUOUS_CHANGE_DECISION_SCHEMA = "continuous-change-decision-v1"
MATERIAL_IDENTITY_SCHEMA = "continuous-material-identity-v1"


@dataclass(frozen=True, slots=True)
class MaterialIdentityInput:
    """Semantic inputs plus explicitly non-semantic observation metadata."""

    raw_content_hash: str
    normalized_content_hash: str
    source_manifest_semantic_hash: str
    request_scope_hash: str
    as_of_time: datetime
    configuration_references: tuple[RuntimeArtifactReference, ...]
    retrieved_at: datetime
    attempt_id: int
    retry_count: int
    fencing_token: int

    def __post_init__(self) -> None:
        for label, content_hash in (
            ("raw_content_hash", self.raw_content_hash),
            ("normalized_content_hash", self.normalized_content_hash),
            ("source_manifest_semantic_hash", self.source_manifest_semantic_hash),
            ("request_scope_hash", self.request_scope_hash),
        ):
            require_sha256(label, content_hash)
        require_utc_second("as_of_time", self.as_of_time)
        require_utc_second("retrieved_at", self.retrieved_at)
        for label, value in (
            ("attempt_id", self.attempt_id),
            ("fencing_token", self.fencing_token),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        if (
            isinstance(self.retry_count, bool)
            or not isinstance(self.retry_count, int)
            or self.retry_count < 0
        ):
            raise ValueError("retry_count must be a non-negative integer")
        keys = tuple(_reference_key(item) for item in self.configuration_references)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("configuration references must be unique and sorted")

    @property
    def material_identity_hash(self) -> str:
        return canonical_hash(self.semantic_payload())

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": MATERIAL_IDENTITY_SCHEMA,
            "raw_content_hash": self.raw_content_hash,
            "normalized_content_hash": self.normalized_content_hash,
            "source_manifest_semantic_hash": self.source_manifest_semantic_hash,
            "request_scope_hash": self.request_scope_hash,
            "as_of_time": canonical_datetime(self.as_of_time),
            "configuration_references": [
                item.to_canonical_dict() for item in self.configuration_references
            ],
        }


@dataclass(frozen=True, slots=True)
class ChangeDecision:
    schema_version: str
    decision_id: ArtifactId
    decision_hash: str
    run_id: ArtifactId
    tick_id: ArtifactId
    provider_attempt_id: int
    evidence_commit_id: ArtifactId
    evidence_commit_hash: str
    previous_evidence_commit_id: ArtifactId | None
    previous_evidence_commit_hash: str | None
    decision_type: ChangeDecisionType
    previous_material_identity_hash: str | None
    current_material_identity_hash: str
    reason_codes: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version != CONTINUOUS_CHANGE_DECISION_SCHEMA:
            raise ValueError("unsupported Continuous Change Decision schema")
        if (
            isinstance(self.provider_attempt_id, bool)
            or not isinstance(self.provider_attempt_id, int)
            or self.provider_attempt_id < 1
        ):
            raise ValueError("provider_attempt_id must be positive")
        require_sha256("decision_hash", self.decision_hash)
        require_sha256("evidence_commit_hash", self.evidence_commit_hash)
        require_sha256(
            "current_material_identity_hash", self.current_material_identity_hash
        )
        if (self.previous_evidence_commit_id is None) != (
            self.previous_evidence_commit_hash is None
        ) or (self.previous_evidence_commit_id is None) != (
            self.previous_material_identity_hash is None
        ):
            raise ValueError("previous Evidence identity/hash/material must be paired")
        if self.previous_evidence_commit_hash is not None:
            require_sha256(
                "previous_evidence_commit_hash", self.previous_evidence_commit_hash
            )
        if self.previous_material_identity_hash is not None:
            require_sha256(
                "previous_material_identity_hash",
                self.previous_material_identity_hash,
            )
        if self.decision_type is ChangeDecisionType.INITIAL_EVIDENCE:
            if self.previous_evidence_commit_id is not None:
                raise ValueError("INITIAL_EVIDENCE cannot have previous Evidence")
        elif self.previous_evidence_commit_id is None:
            raise ValueError("non-initial Change Decision requires previous Evidence")
        if (
            self.decision_type is ChangeDecisionType.NO_MATERIAL_CHANGE
            and self.previous_material_identity_hash
            != self.current_material_identity_hash
        ):
            raise ValueError("NO_MATERIAL_CHANGE requires identical material identity")
        if (
            self.decision_type is ChangeDecisionType.MATERIAL_CHANGE
            and self.previous_material_identity_hash
            == self.current_material_identity_hash
        ):
            raise ValueError("MATERIAL_CHANGE requires different material identity")
        require_unique_text("Change Decision reason", self.reason_codes)
        if not self.reason_codes or self.reason_codes != tuple(sorted(self.reason_codes)):
            raise ValueError("Change Decision reasons must be non-empty and sorted")
        require_utc_second("created_at", self.created_at)
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        evidence: EvidenceCommit,
        previous_evidence: EvidenceCommit | None,
        downstream_contract_satisfied: bool,
        created_at: datetime,
    ) -> ChangeDecision:
        if not isinstance(evidence, EvidenceCommit):
            raise TypeError("evidence must be an EvidenceCommit")
        if previous_evidence is not None:
            if not isinstance(previous_evidence, EvidenceCommit):
                raise TypeError("previous_evidence must be an EvidenceCommit")
            if (
                previous_evidence.run_id != evidence.run_id
                or previous_evidence.evidence_scope != evidence.evidence_scope
                or previous_evidence.trading_date != evidence.trading_date
            ):
                raise ValueError("previous Evidence scope does not match current Evidence")
        if not isinstance(downstream_contract_satisfied, bool):
            raise TypeError("downstream_contract_satisfied must be bool")
        if not downstream_contract_satisfied:
            decision_type = ChangeDecisionType.DATA_INSUFFICIENT
            reasons = ("DOWNSTREAM_MINIMUM_NOT_SATISFIED",)
        elif previous_evidence is None:
            decision_type = ChangeDecisionType.INITIAL_EVIDENCE
            reasons = ("INITIAL_VALIDATED_EVIDENCE",)
        elif (
            previous_evidence.material_identity_hash
            == evidence.material_identity_hash
        ):
            decision_type = ChangeDecisionType.NO_MATERIAL_CHANGE
            reasons = ("MATERIAL_IDENTITY_UNCHANGED",)
        else:
            decision_type = ChangeDecisionType.MATERIAL_CHANGE
            reasons = ("MATERIAL_IDENTITY_CHANGED",)
        values: dict[str, Any] = {
            "run_id": evidence.run_id,
            "tick_id": evidence.tick_id,
            "provider_attempt_id": evidence.attempt_id,
            "evidence_commit_id": evidence.evidence_commit_id,
            "evidence_commit_hash": evidence.commit_hash,
            "previous_evidence_commit_id": (
                None
                if previous_evidence is None
                else previous_evidence.evidence_commit_id
            ),
            "previous_evidence_commit_hash": (
                None if previous_evidence is None else previous_evidence.commit_hash
            ),
            "decision_type": decision_type,
            "previous_material_identity_hash": (
                None
                if previous_evidence is None
                else previous_evidence.material_identity_hash
            ),
            "current_material_identity_hash": evidence.material_identity_hash,
            "reason_codes": reasons,
        }
        digest = canonical_hash(_decision_semantic_payload(**values))
        return cls(
            schema_version=CONTINUOUS_CHANGE_DECISION_SCHEMA,
            decision_id=ArtifactId(
                f"change-decision-{digest.split(':', 1)[1][:24]}"
            ),
            decision_hash=digest,
            created_at=created_at,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _decision_semantic_payload(
            run_id=self.run_id,
            tick_id=self.tick_id,
            provider_attempt_id=self.provider_attempt_id,
            evidence_commit_id=self.evidence_commit_id,
            evidence_commit_hash=self.evidence_commit_hash,
            previous_evidence_commit_id=self.previous_evidence_commit_id,
            previous_evidence_commit_hash=self.previous_evidence_commit_hash,
            decision_type=self.decision_type,
            previous_material_identity_hash=self.previous_material_identity_hash,
            current_material_identity_hash=self.current_material_identity_hash,
            reason_codes=self.reason_codes,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.decision_hash:
            raise ValueError("Continuous Change Decision hash mismatch")
        expected = f"change-decision-{digest.split(':', 1)[1][:24]}"
        if str(self.decision_id) != expected:
            raise ValueError("Continuous Change Decision identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "decision_hash": self.decision_hash,
            **self.semantic_payload(),
            "created_at": canonical_datetime(self.created_at),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ChangeDecision:
        expected = {
            "schema_version",
            "decision_id",
            "decision_hash",
            "run_id",
            "tick_id",
            "provider_attempt_id",
            "evidence_commit_id",
            "evidence_commit_hash",
            "previous_evidence_commit_id",
            "previous_evidence_commit_hash",
            "decision_type",
            "previous_material_identity_hash",
            "current_material_identity_hash",
            "reason_codes",
            "created_at",
        }
        if set(payload) != expected:
            raise ValueError("Continuous Change Decision fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            decision_id=ArtifactId(str(payload["decision_id"])),
            decision_hash=str(payload["decision_hash"]),
            run_id=ArtifactId(str(payload["run_id"])),
            tick_id=ArtifactId(str(payload["tick_id"])),
            provider_attempt_id=_integer(
                payload["provider_attempt_id"], "provider_attempt_id"
            ),
            evidence_commit_id=ArtifactId(str(payload["evidence_commit_id"])),
            evidence_commit_hash=str(payload["evidence_commit_hash"]),
            previous_evidence_commit_id=(
                None
                if payload["previous_evidence_commit_id"] is None
                else ArtifactId(str(payload["previous_evidence_commit_id"]))
            ),
            previous_evidence_commit_hash=_optional_text(
                payload["previous_evidence_commit_hash"]
            ),
            decision_type=ChangeDecisionType(str(payload["decision_type"])),
            previous_material_identity_hash=_optional_text(
                payload["previous_material_identity_hash"]
            ),
            current_material_identity_hash=str(
                payload["current_material_identity_hash"]
            ),
            reason_codes=_strings(payload["reason_codes"], "reason_codes"),
            created_at=parse_utc_second("created_at", payload["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class RecordedChangeDecision:
    decision: ChangeDecision
    claim: ClaimedRuntimeTick


def _decision_semantic_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTINUOUS_CHANGE_DECISION_SCHEMA,
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "provider_attempt_id": values["provider_attempt_id"],
        "evidence_commit_id": str(values["evidence_commit_id"]),
        "evidence_commit_hash": values["evidence_commit_hash"],
        "previous_evidence_commit_id": (
            None
            if values["previous_evidence_commit_id"] is None
            else str(values["previous_evidence_commit_id"])
        ),
        "previous_evidence_commit_hash": values["previous_evidence_commit_hash"],
        "decision_type": values["decision_type"].value,
        "previous_material_identity_hash": values[
            "previous_material_identity_hash"
        ],
        "current_material_identity_hash": values["current_material_identity_hash"],
        "reason_codes": list(values["reason_codes"]),
    }


def _reference_key(reference: RuntimeArtifactReference) -> tuple[str, str, str]:
    return (
        reference.reference_kind,
        str(reference.artifact_id),
        reference.content_hash,
    )


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


__all__ = [
    "CONTINUOUS_CHANGE_DECISION_SCHEMA",
    "MATERIAL_IDENTITY_SCHEMA",
    "ChangeDecision",
    "MaterialIdentityInput",
    "RecordedChangeDecision",
]
