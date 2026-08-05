"""External seams for the sole Continuous Research orchestration owner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from market_regime_alpha.application.continuous_research.evidence import (
    EvidenceCommit,
    EvidenceQualityStatus,
    ProviderAttemptOutcome,
    ProviderAttemptSnapshot,
)
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    ProviderAttemptStatus,
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.market_data.contracts import require_utc_second


@dataclass(frozen=True, slots=True)
class ProviderAcquisitionRequest:
    provider_id: str
    product: str
    request_hash: str
    provider_revision: str | None

    def __post_init__(self) -> None:
        require_text("provider_id", self.provider_id)
        require_text("product", self.product)
        require_sha256("request_hash", self.request_hash)
        if self.provider_revision is not None:
            require_text("provider_revision", self.provider_revision)


@dataclass(frozen=True, slots=True)
class ValidatedEvidencePayload:
    evidence_scope: str
    raw_artifact_id: ArtifactId | None
    raw_artifact_hash: str | None
    evidence_artifact_id: ArtifactId
    evidence_artifact_hash: str
    material_identity_hash: str
    effective_at: datetime
    retrieved_at: datetime
    available_at: datetime
    as_of_time: datetime
    evidence_qualification: str
    limitations: tuple[str, ...]
    downstream_contract_satisfied: bool

    def __post_init__(self) -> None:
        require_text("evidence_scope", self.evidence_scope)
        if (self.raw_artifact_id is None) != (self.raw_artifact_hash is None):
            raise ValueError("raw Artifact identity and hash must be paired")
        for label, content_hash in (
            ("raw_artifact_hash", self.raw_artifact_hash),
            ("evidence_artifact_hash", self.evidence_artifact_hash),
            ("material_identity_hash", self.material_identity_hash),
        ):
            if content_hash is not None:
                require_sha256(label, content_hash)
        for label, timestamp in (
            ("effective_at", self.effective_at),
            ("retrieved_at", self.retrieved_at),
            ("available_at", self.available_at),
            ("as_of_time", self.as_of_time),
        ):
            require_utc_second(label, timestamp)
        require_text("evidence_qualification", self.evidence_qualification)
        require_unique_text("Evidence limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Evidence limitations must be sorted")
        for required in ("FORMAL_PIT_NOT_ESTABLISHED", "NO_TRADING_AUTHORITY"):
            if required not in self.limitations:
                raise ValueError("validated Evidence payload authority ceiling is incomplete")
        if not isinstance(self.downstream_contract_satisfied, bool):
            raise TypeError("downstream_contract_satisfied must be bool")


@dataclass(frozen=True, slots=True)
class ProviderAcquisitionResult:
    status: ProviderAttemptStatus
    completed_at: datetime
    raw_response_hash: str | None
    source_manifest_id: ArtifactId | None
    source_manifest_hash: str | None
    error_code: str | None
    error_message: str | None
    reason_codes: tuple[str, ...]
    retry_at: datetime | None
    evidence: ValidatedEvidencePayload | None

    def __post_init__(self) -> None:
        if self.status is ProviderAttemptStatus.SUCCEEDED:
            if self.evidence is None or self.source_manifest_id is None:
                raise ValueError("successful acquisition requires validated Evidence")
        elif self.evidence is not None:
            raise ValueError("failed acquisition cannot carry Evidence")
        self.to_outcome()

    @classmethod
    def succeeded(
        cls,
        *,
        completed_at: datetime,
        raw_response_hash: str,
        source_manifest_id: ArtifactId,
        source_manifest_hash: str,
        reason_codes: tuple[str, ...],
        evidence: ValidatedEvidencePayload,
    ) -> ProviderAcquisitionResult:
        return cls(
            status=ProviderAttemptStatus.SUCCEEDED,
            completed_at=completed_at,
            raw_response_hash=raw_response_hash,
            source_manifest_id=source_manifest_id,
            source_manifest_hash=source_manifest_hash,
            error_code=None,
            error_message=None,
            reason_codes=tuple(sorted(set(reason_codes))),
            retry_at=None,
            evidence=evidence,
        )

    @classmethod
    def failed(
        cls,
        *,
        status: ProviderAttemptStatus,
        completed_at: datetime,
        error_code: str,
        error_message: str,
        reason_codes: tuple[str, ...],
        retry_at: datetime | None,
        raw_response_hash: str | None = None,
    ) -> ProviderAcquisitionResult:
        return cls(
            status=status,
            completed_at=completed_at,
            raw_response_hash=raw_response_hash,
            source_manifest_id=None,
            source_manifest_hash=None,
            error_code=error_code,
            error_message=error_message,
            reason_codes=tuple(sorted(set(reason_codes))),
            retry_at=retry_at,
            evidence=None,
        )

    def to_outcome(self) -> ProviderAttemptOutcome:
        return ProviderAttemptOutcome.create(
            status=self.status,
            completed_at=self.completed_at,
            raw_response_hash=self.raw_response_hash,
            source_manifest_id=self.source_manifest_id,
            source_manifest_hash=self.source_manifest_hash,
            error_code=self.error_code,
            error_message=self.error_message,
            reason_codes=self.reason_codes,
            retry_at=self.retry_at,
        )

    def build_evidence(
        self,
        *,
        attempt: ProviderAttemptSnapshot,
        trading_date: date,
        request_scope_hash: str,
        provider_configuration_id: ArtifactId,
        provider_configuration_hash: str,
    ) -> EvidenceCommit:
        if self.evidence is None:
            raise ValueError("failed acquisition cannot build Evidence")
        limitations = tuple(
            sorted(
                {
                    *self.evidence.limitations,
                    (
                        "DOWNSTREAM_CONTRACT_SATISFIED"
                        if self.evidence.downstream_contract_satisfied
                        else "DOWNSTREAM_CONTRACT_NOT_SATISFIED"
                    ),
                }
            )
        )
        return EvidenceCommit.create(
            attempt=attempt,
            evidence_scope=self.evidence.evidence_scope,
            trading_date=trading_date,
            request_scope_hash=request_scope_hash,
            raw_artifact_id=self.evidence.raw_artifact_id,
            raw_artifact_hash=self.evidence.raw_artifact_hash,
            evidence_artifact_id=self.evidence.evidence_artifact_id,
            evidence_artifact_hash=self.evidence.evidence_artifact_hash,
            material_identity_hash=self.evidence.material_identity_hash,
            provider_configuration_id=provider_configuration_id,
            provider_configuration_hash=provider_configuration_hash,
            effective_at=self.evidence.effective_at,
            retrieved_at=self.evidence.retrieved_at,
            available_at=self.evidence.available_at,
            as_of_time=self.evidence.as_of_time,
            quality_status=EvidenceQualityStatus.PIT_INCOMPLETE,
            evidence_qualification=self.evidence.evidence_qualification,
            limitations=limitations,
        )


class ProviderAcquisitionPort(Protocol):
    def acquire(
        self, request: ProviderAcquisitionRequest
    ) -> ProviderAcquisitionResult: ...


@dataclass(frozen=True, slots=True)
class ChildExecutionRequest:
    trading_date: date
    run_id: ArtifactId
    tick_id: ArtifactId
    tick_sequence: int
    provider_attempt_id: int
    source_manifest_id: ArtifactId
    source_manifest_hash: str
    evidence_commit_id: ArtifactId
    evidence_commit_hash: str
    decision_id: ArtifactId
    decision_hash: str
    input_references: tuple[RuntimeArtifactReference, ...]
    configuration_references: tuple[RuntimeArtifactReference, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("tick_sequence", self.tick_sequence),
            ("provider_attempt_id", self.provider_attempt_id),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be positive")
        for label, content_hash in (
            ("source_manifest_hash", self.source_manifest_hash),
            ("evidence_commit_hash", self.evidence_commit_hash),
            ("decision_hash", self.decision_hash),
        ):
            require_sha256(label, content_hash)
        _require_reference_set("input", self.input_references)
        _require_reference_set("configuration", self.configuration_references)

    @property
    def idempotency_key(self) -> str:
        digest = canonical_hash(
            {
                "schema_version": "continuous-child-execution-request-v1",
                "trading_date": self.trading_date.isoformat(),
                "run_id": str(self.run_id),
                "tick_id": str(self.tick_id),
                "tick_sequence": self.tick_sequence,
                "provider_attempt_id": self.provider_attempt_id,
                "source_manifest_id": str(self.source_manifest_id),
                "source_manifest_hash": self.source_manifest_hash,
                "evidence_commit_id": str(self.evidence_commit_id),
                "evidence_commit_hash": self.evidence_commit_hash,
                "decision_id": str(self.decision_id),
                "decision_hash": self.decision_hash,
                "input_references": [
                    item.to_canonical_dict() for item in self.input_references
                ],
                "configuration_references": [
                    item.to_canonical_dict()
                    for item in self.configuration_references
                ],
            }
        )
        return f"continuous-children-{digest.split(':', 1)[1][:32]}"


@dataclass(frozen=True, slots=True)
class ChildExecutionResult:
    child_kind: ContinuousChildKind
    child_run_id: ArtifactId
    child_receipt_id: ArtifactId
    child_receipt_hash: str
    child_artifact_id: ArtifactId | None
    child_artifact_hash: str | None
    input_references: tuple[RuntimeArtifactReference, ...]
    configuration_references: tuple[RuntimeArtifactReference, ...]

    def __post_init__(self) -> None:
        require_sha256("child_receipt_hash", self.child_receipt_hash)
        if (self.child_artifact_id is None) != (self.child_artifact_hash is None):
            raise ValueError("child Artifact identity and hash must be paired")
        if self.child_artifact_hash is not None:
            require_sha256("child_artifact_hash", self.child_artifact_hash)
        _require_reference_set("input", self.input_references)
        _require_reference_set("configuration", self.configuration_references)


class ContinuousResearchChildPort(Protocol):
    def lookup_children(
        self, request: ChildExecutionRequest
    ) -> tuple[ChildExecutionResult, ...] | None: ...

    def execute_children(
        self, request: ChildExecutionRequest
    ) -> tuple[ChildExecutionResult, ...]: ...


def _reference_key(reference: RuntimeArtifactReference) -> tuple[str, str, str]:
    return (
        reference.reference_kind,
        str(reference.artifact_id),
        reference.content_hash,
    )


def _require_reference_set(
    label: str, references: tuple[RuntimeArtifactReference, ...]
) -> None:
    keys = tuple(_reference_key(item) for item in references)
    if not references or keys != tuple(sorted(set(keys))):
        raise ValueError(f"{label} references must be non-empty, unique, and sorted")


__all__ = [
    "ChildExecutionRequest",
    "ChildExecutionResult",
    "ContinuousResearchChildPort",
    "ProviderAcquisitionPort",
    "ProviderAcquisitionRequest",
    "ProviderAcquisitionResult",
    "ValidatedEvidencePayload",
]
