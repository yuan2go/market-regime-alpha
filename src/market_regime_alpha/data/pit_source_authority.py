"""Provider temporal evidence and Source Qualification contracts for Formal PIT."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_contracts import (
    PITArtifactKind,
    PITArtifactReference,
    PITContractError,
    PITFactEvidenceMode,
    PITFactKind,
    PITProviderEvidence,
    PITProviderEvidenceKind,
    PITProviderEvidenceUse,
    PITSourceAuthorityStatus,
    PITSourceEvidenceLevel,
    provider_evidence_key,
)
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import (
    parse_utc_second,
    require_utc_second,
)


@dataclass(frozen=True, slots=True)
class PITFactTemporalAuthority:
    mode: PITFactEvidenceMode
    provider_id: str
    provider_contract: str
    provider_available_at: datetime
    provider_recorded_at: datetime
    provider_revision: str | None = None
    provider_dataset_version: str | None = None
    provider_archive: PITArtifactReference | None = None
    provider_evidence: tuple[PITProviderEvidence, ...] = ()

    def __post_init__(self) -> None:
        require_text("provider_id", self.provider_id)
        require_text("provider_contract", self.provider_contract)
        require_utc_second("provider_available_at", self.provider_available_at)
        require_utc_second("provider_recorded_at", self.provider_recorded_at)
        if self.provider_recorded_at < self.provider_available_at:
            raise PITContractError("Provider fact was recorded before available")
        if self.provider_evidence != tuple(
            sorted(set(self.provider_evidence), key=provider_evidence_key)
        ):
            raise PITContractError("provider_evidence must be sorted and unique")
        if self.mode is PITFactEvidenceMode.PROSPECTIVE_CAPTURED_PIT:
            if any(
                value is not None
                for value in (
                    self.provider_revision,
                    self.provider_dataset_version,
                    self.provider_archive,
                )
            ) or self.provider_evidence:
                raise PITContractError(
                    "prospective captured PIT cannot claim historical Provider authority"
                )
            return
        if not self.provider_revision or not self.provider_dataset_version:
            raise PITContractError(
                "historical Provider PIT requires revision and dataset version"
            )
        require_text("provider_revision", self.provider_revision)
        require_text("provider_dataset_version", self.provider_dataset_version)
        if (
            self.provider_archive is None
            or self.provider_archive.reference_kind
            != PITArtifactKind.PROVIDER_ARCHIVE.value
        ):
            raise PITContractError(
                "historical Provider PIT requires resolved Provider archive authority"
            )
        required = {
            PITProviderEvidenceKind.HISTORICAL_AVAILABILITY,
            PITProviderEvidenceKind.REVISION_POLICY,
            PITProviderEvidenceKind.ARCHIVE_INTEGRITY,
        }
        if not required.issubset(
            {item.evidence_kind for item in self.provider_evidence}
        ):
            raise PITContractError(
                "historical Provider PIT requires typed availability/revision/archive evidence"
            )
        if any(
            item.provider_id != self.provider_id
            or item.provider_contract != self.provider_contract
            or item.evidence_use is not PITProviderEvidenceUse.HISTORICAL_PROVIDER_PIT
            for item in self.provider_evidence
        ):
            raise PITContractError(
                "historical Provider evidence must bind the Provider, contract and use"
            )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "provider_id": self.provider_id,
            "provider_contract": self.provider_contract,
            "provider_available_at": canonical_datetime(self.provider_available_at),
            "provider_recorded_at": canonical_datetime(self.provider_recorded_at),
            "provider_revision": self.provider_revision,
            "provider_dataset_version": self.provider_dataset_version,
            "provider_archive": (
                None
                if self.provider_archive is None
                else self.provider_archive.to_canonical_dict()
            ),
            "provider_evidence": [
                item.to_canonical_dict() for item in self.provider_evidence
            ],
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> PITFactTemporalAuthority:
        _require_fields(
            payload,
            {
                "mode",
                "provider_id",
                "provider_contract",
                "provider_available_at",
                "provider_recorded_at",
                "provider_revision",
                "provider_dataset_version",
                "provider_archive",
                "provider_evidence",
            },
            "PIT Fact Temporal Authority",
        )
        archive = payload["provider_archive"]
        revision = payload["provider_revision"]
        dataset_version = payload["provider_dataset_version"]
        return cls(
            mode=PITFactEvidenceMode(_string(payload["mode"])),
            provider_id=_string(payload["provider_id"]),
            provider_contract=_string(payload["provider_contract"]),
            provider_available_at=parse_utc_second(
                "provider_available_at", payload["provider_available_at"]
            ),
            provider_recorded_at=parse_utc_second(
                "provider_recorded_at", payload["provider_recorded_at"]
            ),
            provider_revision=None if revision is None else _string(revision),
            provider_dataset_version=(
                None if dataset_version is None else _string(dataset_version)
            ),
            provider_archive=(
                None
                if archive is None
                else PITArtifactReference.from_canonical_dict(_mapping(archive))
            ),
            provider_evidence=tuple(
                PITProviderEvidence.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["provider_evidence"])
            ),
        )


@dataclass(frozen=True, slots=True)
class PITSourceQualification:
    qualification_id: ArtifactId
    qualification_hash: str
    source_manifest: PITArtifactReference
    provider_id: str
    provider_contract: str
    status: PITSourceAuthorityStatus
    evidence_level: PITSourceEvidenceLevel
    provider_evidence: tuple[PITProviderEvidence, ...]
    qualified_fact_kinds: tuple[PITFactKind, ...]
    qualification_policy: PITArtifactReference
    revision: int
    supersedes_qualification_id: ArtifactId | None
    effective_at: datetime
    recorded_at: datetime
    actor: str
    reason: str
    schema_version: str = "pit-source-qualification-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "pit-source-qualification-v1":
            raise ValueError("unsupported PIT Source Qualification schema")
        require_sha256("qualification_hash", self.qualification_hash)
        for label, value in (
            ("provider_id", self.provider_id),
            ("provider_contract", self.provider_contract),
            ("actor", self.actor),
            ("reason", self.reason),
        ):
            require_text(label, value)
        if self.qualification_policy.reference_kind != PITArtifactKind.CONFIGURATION.value:
            raise PITContractError(
                "Provider qualification policy requires CONFIGURATION authority"
            )
        evidence_keys = tuple(
            provider_evidence_key(item) for item in self.provider_evidence
        )
        if not evidence_keys or evidence_keys != tuple(sorted(set(evidence_keys))):
            raise PITContractError(
                "Provider qualification evidence must be sorted and unique"
            )
        if any(
            item.provider_id != self.provider_id
            or item.provider_contract != self.provider_contract
            or item.evidence_use is not PITProviderEvidenceUse.SOURCE_QUALIFICATION
            for item in self.provider_evidence
        ):
            raise PITContractError(
                "qualification evidence must bind the Provider, contract and use"
            )
        if self.qualified_fact_kinds != tuple(
            sorted(set(self.qualified_fact_kinds), key=lambda item: item.value)
        ) or not self.qualified_fact_kinds:
            raise PITContractError(
                "qualified_fact_kinds must be non-empty, sorted and unique"
            )
        if isinstance(self.revision, bool) or self.revision <= 0:
            raise ValueError("source qualification revision must be positive")
        if (self.revision == 1) != (self.supersedes_qualification_id is None):
            raise ValueError("source qualification supersession/revision mismatch")
        require_utc_second("effective_at", self.effective_at)
        require_utc_second("recorded_at", self.recorded_at)
        if self.recorded_at < self.effective_at:
            raise ValueError("source qualification recorded before effective")
        if canonical_hash(self.semantic_payload()) != self.qualification_hash:
            raise ValueError("PIT Source Qualification hash mismatch")
        if self.qualification_id != _content_id(
            "pit-source-qualification", self.qualification_hash
        ):
            raise ValueError("PIT Source Qualification identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> PITSourceQualification:
        normalized = dict(values)
        normalized["provider_evidence"] = tuple(
            sorted(set(values["provider_evidence"]), key=provider_evidence_key)
        )
        normalized["qualified_fact_kinds"] = tuple(
            sorted(set(values["qualified_fact_kinds"]), key=lambda item: item.value)
        )
        digest = canonical_hash(_source_qualification_payload(**normalized))
        return cls(
            qualification_id=_content_id("pit-source-qualification", digest),
            qualification_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _source_qualification_payload(
            source_manifest=self.source_manifest,
            provider_id=self.provider_id,
            provider_contract=self.provider_contract,
            status=self.status,
            evidence_level=self.evidence_level,
            provider_evidence=self.provider_evidence,
            qualified_fact_kinds=self.qualified_fact_kinds,
            qualification_policy=self.qualification_policy,
            revision=self.revision,
            supersedes_qualification_id=self.supersedes_qualification_id,
            effective_at=self.effective_at,
            recorded_at=self.recorded_at,
            actor=self.actor,
            reason=self.reason,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "qualification_id": str(self.qualification_id),
            "qualification_hash": self.qualification_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> PITSourceQualification:
        expected = {
            "schema_version", "qualification_id", "qualification_hash",
            "source_manifest", "provider_id", "provider_contract", "status",
            "evidence_level", "provider_evidence", "qualified_fact_kinds",
            "qualification_policy", "revision", "supersedes_qualification_id",
            "effective_at", "recorded_at", "actor", "reason",
        }
        _require_fields(payload, expected, "PIT Source Qualification")
        supersedes = payload["supersedes_qualification_id"]
        return cls(
            qualification_id=ArtifactId(_string(payload["qualification_id"])),
            qualification_hash=_string(payload["qualification_hash"]),
            source_manifest=PITArtifactReference.from_canonical_dict(
                _mapping(payload["source_manifest"])
            ),
            provider_id=_string(payload["provider_id"]),
            provider_contract=_string(payload["provider_contract"]),
            status=PITSourceAuthorityStatus(_string(payload["status"])),
            evidence_level=PITSourceEvidenceLevel(_string(payload["evidence_level"])),
            provider_evidence=tuple(
                PITProviderEvidence.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["provider_evidence"])
            ),
            qualified_fact_kinds=tuple(
                PITFactKind(_string(item))
                for item in _sequence(payload["qualified_fact_kinds"])
            ),
            qualification_policy=PITArtifactReference.from_canonical_dict(
                _mapping(payload["qualification_policy"])
            ),
            revision=_integer(payload["revision"]),
            supersedes_qualification_id=(
                ArtifactId(_string(supersedes)) if supersedes is not None else None
            ),
            effective_at=parse_utc_second("effective_at", payload["effective_at"]),
            recorded_at=parse_utc_second("recorded_at", payload["recorded_at"]),
            actor=_string(payload["actor"]),
            reason=_string(payload["reason"]),
            schema_version=_string(payload["schema_version"]),
        )


def _source_qualification_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "pit-source-qualification-v1",
        "source_manifest": values["source_manifest"].to_canonical_dict(),
        "provider_id": values["provider_id"],
        "provider_contract": values["provider_contract"],
        "status": values["status"].value,
        "evidence_level": values["evidence_level"].value,
        "provider_evidence": [
            item.to_canonical_dict() for item in values["provider_evidence"]
        ],
        "qualified_fact_kinds": [
            item.value for item in values["qualified_fact_kinds"]
        ],
        "qualification_policy": values["qualification_policy"].to_canonical_dict(),
        "revision": values["revision"],
        "supersedes_qualification_id": (
            str(values["supersedes_qualification_id"])
            if values["supersedes_qualification_id"] is not None
            else None
        ),
        "effective_at": canonical_datetime(values["effective_at"]),
        "recorded_at": canonical_datetime(values["recorded_at"]),
        "actor": values["actor"],
        "reason": values["reason"],
    }


def _content_id(prefix: str, content_hash: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{content_hash.split(':', 1)[1][:24]}")


def _require_fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("expected string")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("expected integer")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _sequence(value: object) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected array")
    return tuple(value)


__all__ = ["PITFactTemporalAuthority", "PITSourceQualification"]
