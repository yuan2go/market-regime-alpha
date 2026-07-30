"""Uniform immutable metadata envelope for Platform Architecture V2 Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)


class EvidenceAuthority(str, Enum):
    IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT = (
        "IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT"
    )


@dataclass(frozen=True, slots=True)
class ArtifactEnvelope:
    """Common identity, time, configuration, lineage and authority boundary."""

    SCHEMA_VERSION = "platform-v2-artifact-envelope-v1"
    FORMAL_PIT = "FORMAL_PIT_NOT_ESTABLISHED"
    FORMAL_OOS_ALPHA = "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
    TRADING_AUTHORITY = "TRADING_AUTHORITY_NOT_GRANTED"

    schema_version: str
    artifact_type: str
    artifact_id: ArtifactId
    content_hash: str
    decision_date: date
    decision_time: DecisionTime
    created_at: datetime
    code_revision: str
    configuration_id: ArtifactId
    configuration_hash: str
    source_manifest_id: ArtifactId
    source_manifest_hash: str
    input_artifact_ids: tuple[ArtifactId, ...]
    input_content_hashes: tuple[str, ...]
    model_id: ModelId | None
    model_version: str | None
    data_eligibility: DataEligibility
    evidence_authority: EvidenceAuthority
    status: str
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    formal_pit: str = FORMAL_PIT
    formal_oos_alpha: str = FORMAL_OOS_ALPHA
    trading_authority: str = TRADING_AUTHORITY

    def __post_init__(self) -> None:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError("unsupported Platform V2 Artifact Envelope schema")
        for label, value in (
            ("artifact_type", self.artifact_type),
            ("code_revision", self.code_revision),
            ("status", self.status),
        ):
            require_text(label, value)
        require_sha256("content_hash", self.content_hash)
        require_sha256("configuration_hash", self.configuration_hash)
        require_sha256("source_manifest_hash", self.source_manifest_hash)
        if self.decision_time.value.date() != self.decision_date:
            raise ValueError("decision_date must match Decision Time")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.created_at < self.decision_time.value:
            raise ValueError("created_at cannot precede Decision Time")
        if len(self.input_artifact_ids) != len(self.input_content_hashes):
            raise ValueError("input Artifact identities and hashes must align")
        if len(self.input_artifact_ids) != len(set(self.input_artifact_ids)):
            raise ValueError("input Artifact identities must be unique")
        if tuple(sorted(self.input_artifact_ids, key=str)) != self.input_artifact_ids:
            raise ValueError("input Artifact identities must be sorted")
        for value in self.input_content_hashes:
            require_sha256("input_content_hash", value)
        if self.model_id is None and self.model_version is not None:
            raise ValueError("model_version requires model_id")
        if self.model_id is not None:
            if self.model_version is None:
                raise ValueError("model_id requires model_version")
            require_text("model_version", self.model_version)
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Platform V2 public research must remain EXPLORATORY")
        if not isinstance(self.evidence_authority, EvidenceAuthority):
            raise TypeError("evidence_authority must be EvidenceAuthority")
        require_unique_text("reason_code", self.reason_codes)
        require_unique_text("limitation", self.limitations)
        if (
            self.formal_pit != self.FORMAL_PIT
            or self.formal_oos_alpha != self.FORMAL_OOS_ALPHA
            or self.trading_authority != self.TRADING_AUTHORITY
        ):
            raise ValueError("Platform V2 Artifact authority cannot be inflated")

    @classmethod
    def create(
        cls,
        *,
        artifact_type: str,
        artifact_payload: Mapping[str, Any],
        decision_date: date,
        decision_time: DecisionTime,
        created_at: datetime,
        code_revision: str,
        configuration_id: ArtifactId,
        configuration_hash: str,
        source_manifest_id: ArtifactId,
        source_manifest_hash: str,
        input_artifact_ids: tuple[ArtifactId, ...],
        input_content_hashes: tuple[str, ...],
        model_id: ModelId | None,
        model_version: str | None,
        data_eligibility: DataEligibility,
        evidence_authority: EvidenceAuthority,
        status: str,
        reason_codes: tuple[str, ...] = (),
        limitations: tuple[str, ...] = (),
    ) -> ArtifactEnvelope:
        ordered = sorted(
            zip(input_artifact_ids, input_content_hashes, strict=True),
            key=lambda item: str(item[0]),
        )
        ids = tuple(item[0] for item in ordered)
        hashes = tuple(item[1] for item in ordered)
        metadata = {
            "schema_version": cls.SCHEMA_VERSION,
            "artifact_type": artifact_type,
            "decision_date": decision_date.isoformat(),
            "decision_time": decision_time.isoformat(),
            "created_at": created_at.isoformat(),
            "code_revision": code_revision,
            "configuration_id": str(configuration_id),
            "configuration_hash": configuration_hash,
            "source_manifest_id": str(source_manifest_id),
            "source_manifest_hash": source_manifest_hash,
            "input_artifact_ids": [str(item) for item in ids],
            "input_content_hashes": list(hashes),
            "model_id": str(model_id) if model_id is not None else None,
            "model_version": model_version,
            "data_eligibility": data_eligibility.value,
            "evidence_authority": evidence_authority.value,
            "status": status,
            "reason_codes": list(reason_codes),
            "limitations": list(limitations),
            "formal_pit": cls.FORMAL_PIT,
            "formal_oos_alpha": cls.FORMAL_OOS_ALPHA,
            "trading_authority": cls.TRADING_AUTHORITY,
        }
        content_hash = canonical_hash(
            {"envelope": metadata, "artifact_payload": dict(artifact_payload)}
        )
        prefix = artifact_type.lower().replace("_", "-")
        return cls(
            schema_version=cls.SCHEMA_VERSION,
            artifact_type=artifact_type,
            artifact_id=ArtifactId(
                f"{prefix}-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            decision_date=decision_date,
            decision_time=decision_time,
            created_at=created_at,
            code_revision=code_revision,
            configuration_id=configuration_id,
            configuration_hash=configuration_hash,
            source_manifest_id=source_manifest_id,
            source_manifest_hash=source_manifest_hash,
            input_artifact_ids=ids,
            input_content_hashes=hashes,
            model_id=model_id,
            model_version=model_version,
            data_eligibility=data_eligibility,
            evidence_authority=evidence_authority,
            status=status,
            reason_codes=reason_codes,
            limitations=limitations,
        )

    def _binding_metadata(self) -> dict[str, Any]:
        payload = self.to_canonical_dict()
        payload.pop("artifact_id")
        payload.pop("content_hash")
        return payload

    def verify_payload(self, artifact_payload: Mapping[str, Any]) -> None:
        expected = canonical_hash(
            {
                "envelope": self._binding_metadata(),
                "artifact_payload": dict(artifact_payload),
            }
        )
        if expected != self.content_hash:
            raise ValueError("Platform V2 Artifact payload hash mismatch")
        expected_id = (
            f"{self.artifact_type.lower().replace('_', '-')}-"
            f"{self.content_hash.split(':', 1)[1][:24]}"
        )
        if str(self.artifact_id) != expected_id:
            raise ValueError("Platform V2 Artifact identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_type": self.artifact_type,
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            "decision_date": self.decision_date.isoformat(),
            "decision_time": self.decision_time.isoformat(),
            "created_at": self.created_at.isoformat(),
            "code_revision": self.code_revision,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "source_manifest_id": str(self.source_manifest_id),
            "source_manifest_hash": self.source_manifest_hash,
            "input_artifact_ids": [str(item) for item in self.input_artifact_ids],
            "input_content_hashes": list(self.input_content_hashes),
            "model_id": str(self.model_id) if self.model_id is not None else None,
            "model_version": self.model_version,
            "data_eligibility": self.data_eligibility.value,
            "evidence_authority": self.evidence_authority.value,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "limitations": list(self.limitations),
            "formal_pit": self.formal_pit,
            "formal_oos_alpha": self.formal_oos_alpha,
            "trading_authority": self.trading_authority,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ArtifactEnvelope:
        expected = {
            "schema_version",
            "artifact_type",
            "artifact_id",
            "content_hash",
            "decision_date",
            "decision_time",
            "created_at",
            "code_revision",
            "configuration_id",
            "configuration_hash",
            "source_manifest_id",
            "source_manifest_hash",
            "input_artifact_ids",
            "input_content_hashes",
            "model_id",
            "model_version",
            "data_eligibility",
            "evidence_authority",
            "status",
            "reason_codes",
            "limitations",
            "formal_pit",
            "formal_oos_alpha",
            "trading_authority",
        }
        if set(payload) != expected:
            raise ValueError("Platform V2 Artifact Envelope fields mismatch")
        model_id = payload["model_id"]
        result = cls(
            schema_version=str(payload["schema_version"]),
            artifact_type=str(payload["artifact_type"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            decision_date=date.fromisoformat(str(payload["decision_date"])),
            decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["decision_time"]))
            ),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            code_revision=str(payload["code_revision"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            source_manifest_id=ArtifactId(str(payload["source_manifest_id"])),
            source_manifest_hash=str(payload["source_manifest_hash"]),
            input_artifact_ids=tuple(
                ArtifactId(str(item))
                for item in _array(payload["input_artifact_ids"])
            ),
            input_content_hashes=tuple(
                str(item) for item in _array(payload["input_content_hashes"])
            ),
            model_id=ModelId(str(model_id)) if model_id is not None else None,
            model_version=(
                str(payload["model_version"])
                if payload["model_version"] is not None
                else None
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            evidence_authority=EvidenceAuthority(
                str(payload["evidence_authority"])
            ),
            status=str(payload["status"]),
            reason_codes=tuple(
                str(item) for item in _array(payload["reason_codes"])
            ),
            limitations=tuple(
                str(item) for item in _array(payload["limitations"])
            ),
            formal_pit=str(payload["formal_pit"]),
            formal_oos_alpha=str(payload["formal_oos_alpha"]),
            trading_authority=str(payload["trading_authority"]),
        )
        return result


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Platform V2 Artifact Envelope array field is invalid")
    return value
