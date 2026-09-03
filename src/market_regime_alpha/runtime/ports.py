"""Narrow Runtime persistence ports; no table-level CRUD or factory surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.runtime.domain import (
    RunSpec,
    ScheduleSpec,
    StepDependency,
    StepSpec,
)


@dataclass(frozen=True, slots=True)
class ReceiptRecord:
    receipt_id: UUID
    status: str
    request_hash: str
    result_aggregate_kind: str | None
    result_aggregate_id: str | None
    result_aggregate_version: int | None
    result_hash: str | None
    error_code: str | None
    is_new: bool


@dataclass(frozen=True, slots=True)
class AttemptClaim:
    attempt_id: UUID
    run_id: UUID
    step_id: UUID
    step_key: str
    attempt_no: int
    fence_token: int
    lease_owner: str
    lease_until: datetime


@dataclass(frozen=True, slots=True)
class StepTrace:
    step_id: UUID
    step_key: str
    step_kind: str
    implementation: str
    implementation_version: str
    request_hash: str
    input_evidence_hash: str | None
    deadline_at: datetime | None
    state: str
    current_fence: int
    current_attempt_id: UUID | None
    attempt_states: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunTrace:
    run_id: UUID
    schedule_id: UUID
    fire_key: str
    runtime_mode: str
    code_sha: str
    config_artifact_id: UUID
    config_hash: str
    run_state: str
    version: int
    steps: tuple[StepTrace, ...]


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    attempt_id: UUID
    run_id: UUID
    step_id: UUID
    fence_token: int
    outcome: str
    attempt_version: int
    step_version: int
    run_version: int


@dataclass(frozen=True, slots=True)
class PublishedArtifact:
    content_sha256: str
    size_bytes: int
    media_type: str
    locator: str


@dataclass(frozen=True, slots=True)
class ByteVerification:
    result: str
    observed_exists: bool
    observed_size_bytes: int | None
    observed_sha256: str | None


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: UUID
    content_sha256: str
    size_bytes: int
    media_type: str
    locator: str
    integrity_state: str
    retention_until: datetime | None
    pin_reason_code: str | None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class ArtifactVerificationRecord:
    verification_id: UUID
    artifact_id: UUID
    result: str
    observed_exists: bool
    observed_size_bytes: int | None
    observed_sha256: str | None


@dataclass(frozen=True, slots=True)
class ArtifactGcStatus:
    content_sha256: str
    artifact_id: UUID | None
    state: str | None
    due: bool
    referenced: bool
    pinned: bool
    operation_token: UUID | None


class ArtifactByteStore(Protocol):
    def publish_bytes(
        self,
        content: bytes,
        *,
        media_type: str,
        expected_sha256: str | None = None,
    ) -> PublishedArtifact: ...

    def verify(self, content_sha256: str, *, expected_size: int) -> ByteVerification: ...

    def canonical_locator(self, content_sha256: str) -> str: ...

    def list_objects(self) -> tuple[PublishedArtifact, ...]: ...

    def quarantine(self, content_sha256: str) -> None: ...

    def is_quarantined(self, content_sha256: str) -> bool: ...

    def list_quarantined_hashes(self) -> tuple[str, ...]: ...

    def delete_quarantined(self, content_sha256: str) -> None: ...


class ArtifactRepository(Protocol):
    def register(
        self,
        *,
        artifact_id: UUID,
        published: PublishedArtifact,
        retention_until: datetime | None,
        pin_reason_code: str | None,
    ) -> ArtifactRecord: ...

    def get(self, artifact_id: UUID) -> ArtifactRecord: ...

    def get_by_hash(self, content_sha256: str) -> ArtifactRecord | None: ...

    def record_verification(
        self,
        *,
        verification_id: UUID,
        receipt_id: UUID,
        artifact: ArtifactRecord,
        verifier_id: str,
        policy: str,
        verification: ByteVerification,
    ) -> ArtifactVerificationRecord: ...

    def verification_for_receipt(
        self, receipt_id: UUID
    ) -> ArtifactVerificationRecord: ...

    def gc_status(self, content_sha256: str) -> ArtifactGcStatus: ...

    def observe_gc_candidate(
        self,
        *,
        content_sha256: str,
        grace: timedelta,
    ) -> bool: ...

    def clear_gc_candidate(
        self,
        *,
        content_sha256: str,
        operator_id: str,
        reason_code: str,
    ) -> None: ...

    def begin_quarantine(self, content_sha256: str, operation_token: UUID) -> None: ...

    def finish_quarantine(self, content_sha256: str, operation_token: UUID) -> None: ...

    def begin_delete(self, content_sha256: str, operation_token: UUID) -> None: ...

    def finish_delete(
        self,
        content_sha256: str,
        operation_token: UUID,
        *,
        verification_id: UUID,
        receipt_id: UUID,
        verifier_id: str,
    ) -> None: ...


class RuntimeRepository(Protocol):
    def insert_schedule(self, schedule: ScheduleSpec) -> None: ...

    def insert_run(
        self,
        run: RunSpec,
        steps: tuple[tuple[UUID, StepSpec], ...],
        dependencies: tuple[StepDependency, ...],
    ) -> None: ...

    def start_run(self, run_id: UUID) -> int: ...

    def claim_next(
        self,
        *,
        attempt_id: UUID,
        run_id: UUID | None,
        worker_id: str,
        lease_duration: timedelta,
    ) -> AttemptClaim | None: ...

    def load_claim(self, attempt_id: UUID) -> AttemptClaim: ...

    def start_attempt(self, claim: AttemptClaim) -> int: ...

    def heartbeat_attempt(
        self,
        claim: AttemptClaim,
        lease_duration: timedelta,
    ) -> datetime: ...

    def succeed_attempt(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        result_hash: str,
    ) -> tuple[int, int]: ...

    def fail_attempt(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        error_class: str,
        error_code: str,
    ) -> tuple[str, int, int]: ...

    def expired_attempt_ids(self) -> tuple[UUID, ...]: ...

    def deadline_expired_step_ids(self) -> tuple[UUID, ...]: ...

    def recover_expired_attempt(
        self, attempt_id: UUID, *, receipt_id: UUID
    ) -> RecoveryDecision | None: ...

    def expire_step_deadline(
        self,
        step_id: UUID,
        *,
        attempt_id: UUID,
        receipt_id: UUID,
        lease_owner: str,
    ) -> RecoveryDecision | None: ...

    def resume_waiting_step(
        self,
        *,
        run_id: UUID,
        step_id: UUID,
        resolution_code: str,
    ) -> tuple[int, int]: ...

    def inspect_run(self, run_id: UUID) -> RunTrace: ...


class CommandReceiptRepository(Protocol):
    def start(
        self,
        *,
        receipt_id: UUID,
        command_kind: str,
        scope_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> ReceiptRecord: ...

    def succeed(
        self,
        *,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: str,
        aggregate_version: int,
        result_hash: str,
        runtime_claim: AttemptClaim | None = None,
    ) -> None: ...

    def fail(
        self,
        *,
        receipt_id: UUID,
        error_code: str,
        runtime_claim: AttemptClaim | None = None,
    ) -> None: ...


class AuditRepository(Protocol):
    def append(
        self,
        *,
        audit_event_id: UUID,
        receipt_id: UUID | None,
        actor_type: str,
        actor_id: str,
        aggregate_kind: str,
        aggregate_id: str,
        action: str,
        reason_code: str,
        before_version: int | None,
        after_version: int | None,
        runtime_claim: AttemptClaim | None = None,
    ) -> None: ...


class RuntimeCommandFinalization(Protocol):
    """Minimum live-fence and terminalization surface for business contexts."""

    def lock_live(self, claim: AttemptClaim) -> None: ...

    def succeed(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        result_hash: str,
    ) -> tuple[int, int]: ...

    def fail(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        error_class: str,
        error_code: str,
    ) -> tuple[str, int, int]: ...


class CommandFailureUnitOfWork(Protocol):
    """Only the cross-cutting repositories needed to durably reject a command."""

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> RuntimeCommandFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class CommandFailureUnitOfWorkProvider(Protocol):
    def __call__(self) -> CommandFailureUnitOfWork: ...


class RuntimeUnitOfWork(Protocol):
    @property
    def runtime(self) -> RuntimeRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def artifacts(self) -> ArtifactRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class RuntimeUnitOfWorkProvider(Protocol):
    def __call__(self) -> RuntimeUnitOfWork: ...


__all__ = [
    "AttemptClaim",
    "ArtifactByteStore",
    "ArtifactGcStatus",
    "ArtifactRecord",
    "ArtifactRepository",
    "ArtifactVerificationRecord",
    "AuditRepository",
    "ByteVerification",
    "CommandFailureUnitOfWork",
    "CommandFailureUnitOfWorkProvider",
    "CommandReceiptRepository",
    "ReceiptRecord",
    "RecoveryDecision",
    "RunTrace",
    "RuntimeRepository",
    "RuntimeCommandFinalization",
    "RuntimeUnitOfWork",
    "RuntimeUnitOfWorkProvider",
    "StepTrace",
    "PublishedArtifact",
]
