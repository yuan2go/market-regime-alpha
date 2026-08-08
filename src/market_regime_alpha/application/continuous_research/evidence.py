"""Provider Attempt and validated Evidence contracts for Continuous Research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    ClaimedRuntimeTick,
    ProviderAttemptStatus,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second


CONTINUOUS_EVIDENCE_COMMIT_SCHEMA = "continuous-evidence-commit-v1"


class EvidenceQualityStatus(str, Enum):
    VALIDATED = "VALIDATED"
    DEGRADED = "DEGRADED"
    PIT_INCOMPLETE = "PIT_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ProviderAttemptOutcome:
    status: ProviderAttemptStatus
    completed_at: datetime
    raw_response_hash: str | None
    source_manifest_id: ArtifactId | None
    source_manifest_hash: str | None
    error_code: str | None
    error_message: str | None
    reason_codes: tuple[str, ...]
    retry_at: datetime | None

    def __post_init__(self) -> None:
        if self.status in {
            ProviderAttemptStatus.STARTED,
            ProviderAttemptStatus.LEASE_EXPIRED,
        }:
            raise ValueError("Provider Attempt outcome must be a worker terminal status")
        require_utc_second("completed_at", self.completed_at)
        if self.raw_response_hash is not None:
            require_sha256("raw_response_hash", self.raw_response_hash)
        if (self.source_manifest_id is None) != (self.source_manifest_hash is None):
            raise ValueError("SourceManifest identity and hash must be paired")
        if self.source_manifest_hash is not None:
            require_sha256("source_manifest_hash", self.source_manifest_hash)
        if self.status is ProviderAttemptStatus.SUCCEEDED:
            if self.source_manifest_id is None:
                raise ValueError("successful Attempt requires validated SourceManifest")
            if self.error_code is not None or self.error_message is not None:
                raise ValueError("successful Attempt cannot carry an error")
        elif self.source_manifest_id is not None:
            raise ValueError("failed Attempt cannot carry SourceManifest")
        for label, value in (
            ("error_code", self.error_code),
            ("error_message", self.error_message),
        ):
            if value is not None:
                require_text(label, value)
        require_unique_text("Provider Attempt reason", self.reason_codes)
        if not self.reason_codes or self.reason_codes != tuple(sorted(self.reason_codes)):
            raise ValueError("Provider Attempt reasons must be non-empty and sorted")
        if self.retry_at is not None:
            require_utc_second("retry_at", self.retry_at)

    @classmethod
    def create(
        cls,
        *,
        status: ProviderAttemptStatus,
        completed_at: datetime,
        raw_response_hash: str | None,
        source_manifest_id: ArtifactId | None,
        source_manifest_hash: str | None,
        error_code: str | None,
        error_message: str | None,
        reason_codes: tuple[str, ...],
        retry_at: datetime | None,
    ) -> ProviderAttemptOutcome:
        return cls(
            status=status,
            completed_at=completed_at,
            raw_response_hash=raw_response_hash,
            source_manifest_id=source_manifest_id,
            source_manifest_hash=source_manifest_hash,
            error_code=error_code,
            error_message=error_message,
            reason_codes=tuple(sorted(set(reason_codes))),
            retry_at=retry_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "completed_at": canonical_datetime(self.completed_at),
            "raw_response_hash": self.raw_response_hash,
            "source_manifest_id": (
                None if self.source_manifest_id is None else str(self.source_manifest_id)
            ),
            "source_manifest_hash": self.source_manifest_hash,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "reason_codes": list(self.reason_codes),
            "retry_at": (
                None if self.retry_at is None else canonical_datetime(self.retry_at)
            ),
        }


@dataclass(frozen=True, slots=True)
class ProviderAttemptSnapshot:
    attempt_id: int
    run_id: ArtifactId
    tick_id: ArtifactId
    attempt_number: int
    claim_id: str
    fencing_token: int
    tick_version: int
    provider_id: str
    product: str
    request_hash: str
    started_at: datetime
    completed_at: datetime | None
    lease_expires_at: datetime
    heartbeat_at: datetime
    status: ProviderAttemptStatus
    raw_response_hash: str | None
    source_manifest_id: ArtifactId | None
    source_manifest_hash: str | None
    error_code: str | None
    error_message: str | None
    reason_codes: tuple[str, ...]
    retry_at: datetime | None
    provider_revision: str | None

    def __post_init__(self) -> None:
        for label, integer_value in (
            ("attempt_id", self.attempt_id),
            ("attempt_number", self.attempt_number),
            ("fencing_token", self.fencing_token),
            ("tick_version", self.tick_version),
        ):
            if (
                isinstance(integer_value, bool)
                or not isinstance(integer_value, int)
                or integer_value < 1
            ):
                raise ValueError(f"{label} must be a positive integer")
        for label, text_value in (
            ("claim_id", self.claim_id),
            ("provider_id", self.provider_id),
            ("product", self.product),
        ):
            require_text(label, text_value)
        require_sha256("request_hash", self.request_hash)
        for label, timestamp in (
            ("started_at", self.started_at),
            ("lease_expires_at", self.lease_expires_at),
            ("heartbeat_at", self.heartbeat_at),
        ):
            require_utc_second(label, timestamp)
        if self.completed_at is not None:
            require_utc_second("completed_at", self.completed_at)
            if self.completed_at < self.started_at:
                raise ValueError("Provider Attempt cannot complete before it starts")
        if (self.status is ProviderAttemptStatus.STARTED) != (
            self.completed_at is None
        ):
            raise ValueError("Provider Attempt status/completion mismatch")
        if self.raw_response_hash is not None:
            require_sha256("raw_response_hash", self.raw_response_hash)
        if (self.source_manifest_id is None) != (self.source_manifest_hash is None):
            raise ValueError("SourceManifest identity and hash must be paired")
        if self.source_manifest_hash is not None:
            require_sha256("source_manifest_hash", self.source_manifest_hash)
        if self.status is ProviderAttemptStatus.SUCCEEDED:
            if self.source_manifest_id is None:
                raise ValueError("successful Attempt requires validated SourceManifest")
        elif self.status is not ProviderAttemptStatus.STARTED and self.source_manifest_id is not None:
            raise ValueError("failed Attempt cannot carry SourceManifest")
        require_unique_text("Provider Attempt reason", self.reason_codes)
        if self.reason_codes != tuple(sorted(self.reason_codes)):
            raise ValueError("Provider Attempt reasons must be sorted")
        if self.retry_at is not None:
            require_utc_second("retry_at", self.retry_at)
        if self.provider_revision is not None:
            require_text("provider_revision", self.provider_revision)


@dataclass(frozen=True, slots=True)
class StartedProviderAttempt:
    attempt: ProviderAttemptSnapshot
    claim: ClaimedRuntimeTick


@dataclass(frozen=True, slots=True)
class EvidenceCommit:
    schema_version: str
    evidence_commit_id: ArtifactId
    commit_hash: str
    run_id: ArtifactId
    tick_id: ArtifactId
    attempt_id: int
    evidence_scope: str
    trading_date: date
    request_scope_hash: str
    source_manifest_id: ArtifactId
    source_manifest_hash: str
    raw_artifact_id: ArtifactId | None
    raw_artifact_hash: str | None
    evidence_artifact_id: ArtifactId
    evidence_artifact_hash: str
    material_identity_hash: str
    provider_configuration_id: ArtifactId
    provider_configuration_hash: str
    effective_at: datetime
    retrieved_at: datetime
    available_at: datetime
    as_of_time: datetime
    quality_status: EvidenceQualityStatus
    evidence_qualification: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTINUOUS_EVIDENCE_COMMIT_SCHEMA:
            raise ValueError("unsupported Continuous Evidence Commit schema")
        if isinstance(self.attempt_id, bool) or self.attempt_id < 1:
            raise ValueError("attempt_id must be positive")
        require_text("evidence_scope", self.evidence_scope)
        for label, value in (
            ("commit_hash", self.commit_hash),
            ("request_scope_hash", self.request_scope_hash),
            ("source_manifest_hash", self.source_manifest_hash),
            ("evidence_artifact_hash", self.evidence_artifact_hash),
            ("material_identity_hash", self.material_identity_hash),
            ("provider_configuration_hash", self.provider_configuration_hash),
        ):
            require_sha256(label, value)
        if (self.raw_artifact_id is None) != (self.raw_artifact_hash is None):
            raise ValueError("raw Artifact identity and hash must be paired")
        if self.raw_artifact_hash is not None:
            require_sha256("raw_artifact_hash", self.raw_artifact_hash)
        for label, timestamp in (
            ("effective_at", self.effective_at),
            ("retrieved_at", self.retrieved_at),
            ("available_at", self.available_at),
            ("as_of_time", self.as_of_time),
        ):
            require_utc_second(label, timestamp)
        if self.available_at < self.effective_at or self.retrieved_at < self.effective_at:
            raise ValueError("Evidence cannot be available/retrieved before effective_at")
        if self.available_at > self.as_of_time:
            raise ValueError("Evidence AvailableAt cannot exceed AsOfTime")
        require_text("evidence_qualification", self.evidence_qualification)
        require_unique_text("Evidence limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Evidence limitations must be sorted")
        for required in ("FORMAL_PIT_NOT_ESTABLISHED", "NO_TRADING_AUTHORITY"):
            if required not in self.limitations:
                raise ValueError("Evidence authority ceiling is incomplete")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        attempt: ProviderAttemptSnapshot,
        evidence_scope: str,
        trading_date: date,
        request_scope_hash: str,
        raw_artifact_id: ArtifactId | None,
        raw_artifact_hash: str | None,
        evidence_artifact_id: ArtifactId,
        evidence_artifact_hash: str,
        material_identity_hash: str,
        provider_configuration_id: ArtifactId,
        provider_configuration_hash: str,
        effective_at: datetime,
        retrieved_at: datetime,
        available_at: datetime,
        as_of_time: datetime,
        quality_status: EvidenceQualityStatus,
        evidence_qualification: str,
        limitations: tuple[str, ...],
    ) -> EvidenceCommit:
        if (
            attempt.status is not ProviderAttemptStatus.SUCCEEDED
            or attempt.source_manifest_id is None
            or attempt.source_manifest_hash is None
        ):
            raise ValueError(
                "Evidence requires a successful validated Provider Attempt"
            )
        values: dict[str, Any] = {
            "run_id": attempt.run_id,
            "tick_id": attempt.tick_id,
            "attempt_id": attempt.attempt_id,
            "evidence_scope": evidence_scope,
            "trading_date": trading_date,
            "request_scope_hash": request_scope_hash,
            "source_manifest_id": attempt.source_manifest_id,
            "source_manifest_hash": attempt.source_manifest_hash,
            "raw_artifact_id": raw_artifact_id,
            "raw_artifact_hash": raw_artifact_hash,
            "evidence_artifact_id": evidence_artifact_id,
            "evidence_artifact_hash": evidence_artifact_hash,
            "material_identity_hash": material_identity_hash,
            "provider_configuration_id": provider_configuration_id,
            "provider_configuration_hash": provider_configuration_hash,
            "effective_at": effective_at,
            "retrieved_at": retrieved_at,
            "available_at": available_at,
            "as_of_time": as_of_time,
            "quality_status": quality_status,
            "evidence_qualification": evidence_qualification,
            "limitations": tuple(sorted(set(limitations))),
        }
        digest = canonical_hash(_evidence_payload(**values))
        return cls(
            schema_version=CONTINUOUS_EVIDENCE_COMMIT_SCHEMA,
            evidence_commit_id=ArtifactId(
                f"evidence-commit-{digest.split(':', 1)[1][:24]}"
            ),
            commit_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _evidence_payload(
            run_id=self.run_id,
            tick_id=self.tick_id,
            attempt_id=self.attempt_id,
            evidence_scope=self.evidence_scope,
            trading_date=self.trading_date,
            request_scope_hash=self.request_scope_hash,
            source_manifest_id=self.source_manifest_id,
            source_manifest_hash=self.source_manifest_hash,
            raw_artifact_id=self.raw_artifact_id,
            raw_artifact_hash=self.raw_artifact_hash,
            evidence_artifact_id=self.evidence_artifact_id,
            evidence_artifact_hash=self.evidence_artifact_hash,
            material_identity_hash=self.material_identity_hash,
            provider_configuration_id=self.provider_configuration_id,
            provider_configuration_hash=self.provider_configuration_hash,
            effective_at=self.effective_at,
            retrieved_at=self.retrieved_at,
            available_at=self.available_at,
            as_of_time=self.as_of_time,
            quality_status=self.quality_status,
            evidence_qualification=self.evidence_qualification,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.commit_hash:
            raise ValueError("Continuous Evidence Commit hash mismatch")
        expected = f"evidence-commit-{digest.split(':', 1)[1][:24]}"
        if str(self.evidence_commit_id) != expected:
            raise ValueError("Continuous Evidence Commit identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evidence_commit_id": str(self.evidence_commit_id),
            "commit_hash": self.commit_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> EvidenceCommit:
        expected = {"evidence_commit_id", "commit_hash", *_evidence_payload_keys()}
        if set(payload) != expected:
            raise ValueError("Continuous Evidence Commit fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            evidence_commit_id=ArtifactId(str(payload["evidence_commit_id"])),
            commit_hash=str(payload["commit_hash"]),
            run_id=ArtifactId(str(payload["run_id"])),
            tick_id=ArtifactId(str(payload["tick_id"])),
            attempt_id=_integer(payload["attempt_id"], "attempt_id"),
            evidence_scope=str(payload["evidence_scope"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            request_scope_hash=str(payload["request_scope_hash"]),
            source_manifest_id=ArtifactId(str(payload["source_manifest_id"])),
            source_manifest_hash=str(payload["source_manifest_hash"]),
            raw_artifact_id=(
                None
                if payload["raw_artifact_id"] is None
                else ArtifactId(str(payload["raw_artifact_id"]))
            ),
            raw_artifact_hash=(
                None
                if payload["raw_artifact_hash"] is None
                else str(payload["raw_artifact_hash"])
            ),
            evidence_artifact_id=ArtifactId(str(payload["evidence_artifact_id"])),
            evidence_artifact_hash=str(payload["evidence_artifact_hash"]),
            material_identity_hash=str(payload["material_identity_hash"]),
            provider_configuration_id=ArtifactId(
                str(payload["provider_configuration_id"])
            ),
            provider_configuration_hash=str(
                payload["provider_configuration_hash"]
            ),
            effective_at=parse_utc_second("effective_at", payload["effective_at"]),
            retrieved_at=parse_utc_second("retrieved_at", payload["retrieved_at"]),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            as_of_time=parse_utc_second("as_of_time", payload["as_of_time"]),
            quality_status=EvidenceQualityStatus(str(payload["quality_status"])),
            evidence_qualification=str(payload["evidence_qualification"]),
            limitations=_strings(payload["limitations"], "limitations"),
        )


@dataclass(frozen=True, slots=True)
class CurrentEvidenceSnapshot:
    run_id: ArtifactId
    evidence_scope: str
    evidence_commit_id: ArtifactId
    evidence_commit_hash: str
    material_identity_hash: str
    version: int
    last_accepted_fencing_token: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EvidenceCommitResult:
    evidence: EvidenceCommit
    current: CurrentEvidenceSnapshot
    claim: ClaimedRuntimeTick
    current_advanced: bool


def _evidence_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTINUOUS_EVIDENCE_COMMIT_SCHEMA,
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "attempt_id": values["attempt_id"],
        "evidence_scope": values["evidence_scope"],
        "trading_date": values["trading_date"].isoformat(),
        "request_scope_hash": values["request_scope_hash"],
        "source_manifest_id": str(values["source_manifest_id"]),
        "source_manifest_hash": values["source_manifest_hash"],
        "raw_artifact_id": (
            None if values["raw_artifact_id"] is None else str(values["raw_artifact_id"])
        ),
        "raw_artifact_hash": values["raw_artifact_hash"],
        "evidence_artifact_id": str(values["evidence_artifact_id"]),
        "evidence_artifact_hash": values["evidence_artifact_hash"],
        "material_identity_hash": values["material_identity_hash"],
        "provider_configuration_id": str(values["provider_configuration_id"]),
        "provider_configuration_hash": values["provider_configuration_hash"],
        "effective_at": canonical_datetime(values["effective_at"]),
        "retrieved_at": canonical_datetime(values["retrieved_at"]),
        "available_at": canonical_datetime(values["available_at"]),
        "as_of_time": canonical_datetime(values["as_of_time"]),
        "quality_status": values["quality_status"].value,
        "evidence_qualification": values["evidence_qualification"],
        "limitations": list(values["limitations"]),
    }


def _evidence_payload_keys() -> set[str]:
    return {
        "schema_version",
        "run_id",
        "tick_id",
        "attempt_id",
        "evidence_scope",
        "trading_date",
        "request_scope_hash",
        "source_manifest_id",
        "source_manifest_hash",
        "raw_artifact_id",
        "raw_artifact_hash",
        "evidence_artifact_id",
        "evidence_artifact_hash",
        "material_identity_hash",
        "provider_configuration_id",
        "provider_configuration_hash",
        "effective_at",
        "retrieved_at",
        "available_at",
        "as_of_time",
        "quality_status",
        "evidence_qualification",
        "limitations",
    }


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


__all__ = [
    "CONTINUOUS_EVIDENCE_COMMIT_SCHEMA",
    "CurrentEvidenceSnapshot",
    "EvidenceCommit",
    "EvidenceCommitResult",
    "EvidenceQualityStatus",
    "ProviderAttemptOutcome",
    "ProviderAttemptSnapshot",
    "StartedProviderAttempt",
]
