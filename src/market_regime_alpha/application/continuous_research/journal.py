"""Public Journal seam for PostgreSQL-authoritative Continuous Research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Protocol

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousRunState,
    ContinuousSessionPhase,
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


RUNTIME_TICK_RECEIPT_SCHEMA = "continuous-runtime-tick-receipt-v1"


class ContinuousTickStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DATA_BLOCKED = "DATA_BLOCKED"


class ProviderAttemptStatus(str, Enum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    RATE_LIMITED = "RATE_LIMITED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    LEASE_EXPIRED = "LEASE_EXPIRED"


class ChangeDecisionType(str, Enum):
    INITIAL_EVIDENCE = "INITIAL_EVIDENCE"
    MATERIAL_CHANGE = "MATERIAL_CHANGE"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class ContinuousChildKind(str, Enum):
    DAILY_DATASET = "DAILY_DATASET"
    FEATURE_MATERIALIZATION = "FEATURE_MATERIALIZATION"
    STATE_SYSTEM = "STATE_SYSTEM"
    CONTROLLED_OPERATION = "CONTROLLED_OPERATION"
    CANONICAL_LIFECYCLE = "CANONICAL_LIFECYCLE"


class ChildReferenceDisposition(str, Enum):
    CREATED = "CREATED"
    REUSED = "REUSED"


@dataclass(frozen=True, slots=True)
class RuntimeArtifactReference:
    reference_kind: str
    artifact_id: ArtifactId
    content_hash: str

    def __post_init__(self) -> None:
        require_text("reference_kind", self.reference_kind)
        require_sha256("reference content_hash", self.content_hash)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "reference_kind": self.reference_kind,
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> RuntimeArtifactReference:
        if set(payload) != {"reference_kind", "artifact_id", "content_hash"}:
            raise ValueError("Runtime Artifact reference fields mismatch")
        return cls(
            reference_kind=str(payload["reference_kind"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class ClaimedRuntimeTick:
    run_id: ArtifactId
    tick_id: ArtifactId
    tick_sequence: int
    claim_id: str
    fencing_token: int
    tick_version: int
    lease_acquired_at: datetime
    lease_expires_at: datetime
    heartbeat_at: datetime

    def __post_init__(self) -> None:
        for label, integer_value in (
            ("tick_sequence", self.tick_sequence),
            ("fencing_token", self.fencing_token),
            ("tick_version", self.tick_version),
        ):
            if (
                isinstance(integer_value, bool)
                or not isinstance(integer_value, int)
                or integer_value < 1
            ):
                raise ValueError(f"{label} must be a positive integer")
        require_text("claim_id", self.claim_id)
        for label, timestamp in (
            ("lease_acquired_at", self.lease_acquired_at),
            ("lease_expires_at", self.lease_expires_at),
            ("heartbeat_at", self.heartbeat_at),
        ):
            require_utc_second(label, timestamp)
        if self.lease_expires_at <= self.lease_acquired_at:
            raise ValueError("lease must expire after acquisition")
        if not self.lease_acquired_at <= self.heartbeat_at < self.lease_expires_at:
            raise ValueError("heartbeat must be inside the active lease")


@dataclass(frozen=True, slots=True)
class RuntimeTickReceipt:
    schema_version: str
    receipt_id: ArtifactId
    receipt_hash: str
    run_id: ArtifactId
    tick_id: ArtifactId
    tick_sequence: int
    claim_id: str
    fencing_token: int
    input_references: tuple[RuntimeArtifactReference, ...]
    output_references: tuple[RuntimeArtifactReference, ...]
    reason_codes: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_TICK_RECEIPT_SCHEMA:
            raise ValueError("unsupported Runtime Tick receipt schema")
        require_sha256("receipt_hash", self.receipt_hash)
        require_text("claim_id", self.claim_id)
        for label, value in (
            ("tick_sequence", self.tick_sequence),
            ("fencing_token", self.fencing_token),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        require_utc_second("created_at", self.created_at)
        for label, references in (
            ("input", self.input_references),
            ("output", self.output_references),
        ):
            keys = tuple(
                (item.reference_kind, str(item.artifact_id), item.content_hash)
                for item in references
            )
            if keys != tuple(sorted(set(keys))):
                raise ValueError(f"{label} references must be unique and sorted")
        require_unique_text("receipt reason", self.reason_codes)
        if not self.reason_codes or self.reason_codes != tuple(sorted(self.reason_codes)):
            raise ValueError("receipt reasons must be non-empty and sorted")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        claim: ClaimedRuntimeTick,
        input_references: tuple[RuntimeArtifactReference, ...],
        output_references: tuple[RuntimeArtifactReference, ...],
        reason_codes: tuple[str, ...],
        created_at: datetime,
    ) -> RuntimeTickReceipt:
        inputs = tuple(
            sorted(
                set(input_references),
                key=lambda item: (
                    item.reference_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        )
        outputs = tuple(
            sorted(
                set(output_references),
                key=lambda item: (
                    item.reference_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        )
        values: dict[str, Any] = {
            "run_id": claim.run_id,
            "tick_id": claim.tick_id,
            "tick_sequence": claim.tick_sequence,
            "claim_id": claim.claim_id,
            "fencing_token": claim.fencing_token,
            "input_references": inputs,
            "output_references": outputs,
            "reason_codes": tuple(sorted(set(reason_codes))),
            "created_at": created_at,
        }
        digest = canonical_hash(_receipt_payload(**values))
        return cls(
            schema_version=RUNTIME_TICK_RECEIPT_SCHEMA,
            receipt_id=ArtifactId(
                f"continuous-tick-receipt-{digest.split(':', 1)[1][:24]}"
            ),
            receipt_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _receipt_payload(
            run_id=self.run_id,
            tick_id=self.tick_id,
            tick_sequence=self.tick_sequence,
            claim_id=self.claim_id,
            fencing_token=self.fencing_token,
            input_references=self.input_references,
            output_references=self.output_references,
            reason_codes=self.reason_codes,
            created_at=self.created_at,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.receipt_hash:
            raise ValueError("Runtime Tick receipt hash mismatch")
        expected = f"continuous-tick-receipt-{digest.split(':', 1)[1][:24]}"
        if str(self.receipt_id) != expected:
            raise ValueError("Runtime Tick receipt identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "receipt_hash": self.receipt_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> RuntimeTickReceipt:
        expected = {
            "schema_version",
            "receipt_id",
            "receipt_hash",
            "run_id",
            "tick_id",
            "tick_sequence",
            "claim_id",
            "fencing_token",
            "input_references",
            "output_references",
            "reason_codes",
            "created_at",
        }
        if set(payload) != expected:
            raise ValueError("Runtime Tick receipt fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            receipt_id=ArtifactId(str(payload["receipt_id"])),
            receipt_hash=str(payload["receipt_hash"]),
            run_id=ArtifactId(str(payload["run_id"])),
            tick_id=ArtifactId(str(payload["tick_id"])),
            tick_sequence=_integer(payload["tick_sequence"], "tick_sequence"),
            claim_id=str(payload["claim_id"]),
            fencing_token=_integer(payload["fencing_token"], "fencing_token"),
            input_references=_references(
                payload["input_references"], "input_references"
            ),
            output_references=_references(
                payload["output_references"], "output_references"
            ),
            reason_codes=_strings(payload["reason_codes"], "reason_codes"),
            created_at=parse_utc_second("created_at", payload["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class ContinuousRuntimeEvent:
    event_id: int
    event_type: str
    event_time: datetime
    tick_id: ArtifactId | None
    fencing_token: int | None
    payload_json: str


@dataclass(frozen=True, slots=True)
class ContinuousTickSnapshot:
    command: RuntimeTickCommand
    tick_sequence: int
    session_phase: ContinuousSessionPhase
    status: ContinuousTickStatus
    version: int
    claim_id: str | None
    fencing_token: int
    lease_acquired_at: datetime | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    provider_attempt_id: int | None
    evidence_commit_id: ArtifactId | None
    change_decision_id: ArtifactId | None
    receipt: RuntimeTickReceipt | None
    last_error: str | None
    retry_at: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ContinuousRunSnapshot:
    command: ContinuousResearchCommand
    status: ContinuousRunState
    current_tick_sequence: int
    version: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    archived_at: datetime | None
    ticks: tuple[ContinuousTickSnapshot, ...]
    events: tuple[ContinuousRuntimeEvent, ...]


class ContinuousResearchJournal(Protocol):
    def create_or_get(
        self, command: ContinuousResearchCommand
    ) -> ContinuousRunSnapshot: ...

    def admit_tick(
        self,
        command: RuntimeTickCommand,
        *,
        session_phase: ContinuousSessionPhase,
    ) -> ContinuousTickSnapshot: ...

    def claim_next(self, run_id: ArtifactId) -> ClaimedRuntimeTick: ...

    def claim_tick(
        self, *, run_id: ArtifactId, tick_id: ArtifactId
    ) -> ClaimedRuntimeTick: ...

    def heartbeat(self, claim: ClaimedRuntimeTick) -> ClaimedRuntimeTick: ...

    def complete_tick(
        self,
        *,
        claim: ClaimedRuntimeTick,
        receipt: RuntimeTickReceipt,
        run_state: ContinuousRunState,
    ) -> ContinuousTickSnapshot: ...

    def fail_tick(
        self,
        *,
        claim: ClaimedRuntimeTick,
        error: str,
        retryable: bool,
        retry_at: datetime | None,
    ) -> ContinuousTickSnapshot: ...

    def resume(self, run_id: ArtifactId) -> ContinuousRunSnapshot: ...

    def get_run(self, run_id: ArtifactId) -> ContinuousRunSnapshot: ...

    def get_tick(
        self, run_id: ArtifactId, tick_id: ArtifactId
    ) -> ContinuousTickSnapshot: ...


def _receipt_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_TICK_RECEIPT_SCHEMA,
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "tick_sequence": values["tick_sequence"],
        "claim_id": values["claim_id"],
        "fencing_token": values["fencing_token"],
        "input_references": [
            item.to_canonical_dict() for item in values["input_references"]
        ],
        "output_references": [
            item.to_canonical_dict() for item in values["output_references"]
        ],
        "reason_codes": list(values["reason_codes"]),
        "created_at": canonical_datetime(values["created_at"]),
    }


def _references(value: object, label: str) -> tuple[RuntimeArtifactReference, ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must be an object array")
    return tuple(RuntimeArtifactReference.from_canonical_dict(item) for item in value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


__all__ = [
    "ChangeDecisionType",
    "ChildReferenceDisposition",
    "ClaimedRuntimeTick",
    "ContinuousChildKind",
    "ContinuousResearchJournal",
    "ContinuousRunSnapshot",
    "ContinuousRuntimeEvent",
    "ContinuousTickSnapshot",
    "ContinuousTickStatus",
    "ProviderAttemptStatus",
    "RuntimeArtifactReference",
    "RuntimeTickReceipt",
]
