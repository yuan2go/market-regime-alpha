"""Persistence boundary for the canonical Lifecycle Runtime Journal.

The journal is a recoverability and audit authority.  It stores references to
domain outputs; it does not become an authority for the referenced Artifacts,
trades, fills, positions, or model results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleAttemptId,
    LifecycleEvent,
    LifecycleObjectReference,
    LifecycleRun,
    LifecycleRunId,
    LifecycleStage,
    StageReceipt,
    require_utc_second,
    validate_lifecycle_object_references,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    WAITING_LIFECYCLE_RUN_STATUSES,
    LifecycleRunStatus,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.evidence.canonical import require_text


class LifecycleRepositoryError(RuntimeError):
    """Base class for durable lifecycle journal failures."""


class LifecycleRunNotFound(LifecycleRepositoryError, KeyError):
    """Raised when a lifecycle run identity is unknown."""


class LifecycleStageNotFound(LifecycleRepositoryError, KeyError):
    """Raised when a stage projection is unknown."""


class LifecycleIdempotencyConflict(LifecycleRepositoryError):
    """One idempotency key was reused for different command semantics."""


class LifecycleConcurrentModification(LifecycleRepositoryError):
    """A run or stage compare-and-set failed."""


class LifecycleClaimConflict(LifecycleConcurrentModification):
    """A stale claim token attempted to mutate journal state."""


class LifecycleUnsafeResume(LifecycleRepositoryError):
    """A run cannot be resumed from its current durable state."""


class LifecycleJournalIntegrityError(LifecycleRepositoryError):
    """Stored canonical JSON or its relational projection is inconsistent."""


def _require_positive(label: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


@dataclass(frozen=True, slots=True)
class StageTransition:
    """One atomic successful/waiting/blocked/not-applicable stage settlement."""

    run_id: LifecycleRunId
    stage_name: LifecycleStageName
    attempt_id: LifecycleAttemptId
    expected_run_version: int
    expected_stage_version: int
    claim_token: int
    target_run_status: LifecycleRunStatus
    receipt: StageReceipt
    input_references: tuple[LifecycleObjectReference, ...]
    output_references: tuple[LifecycleObjectReference, ...]
    blocker_reason: str | None
    completed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, LifecycleRunId):
            raise TypeError("run_id must be a LifecycleRunId")
        if not isinstance(self.stage_name, LifecycleStageName):
            raise TypeError("stage_name must be a LifecycleStageName")
        if not isinstance(self.attempt_id, LifecycleAttemptId):
            raise TypeError("attempt_id must be a LifecycleAttemptId")
        for label, value in (
            ("expected_run_version", self.expected_run_version),
            ("expected_stage_version", self.expected_stage_version),
            ("claim_token", self.claim_token),
        ):
            _require_positive(label, value)
        if not isinstance(self.target_run_status, LifecycleRunStatus):
            raise TypeError("target_run_status must be a LifecycleRunStatus")
        if not isinstance(self.receipt, StageReceipt):
            raise TypeError("receipt must be a StageReceipt")
        if self.receipt.run_id != self.run_id:
            raise ValueError("receipt binds a different run")
        if self.receipt.stage_name is not self.stage_name:
            raise ValueError("receipt binds a different stage")
        if self.receipt.stage_result not in {
            LifecycleStageStatus.COMPLETED,
            LifecycleStageStatus.WAITING,
            LifecycleStageStatus.BLOCKED,
            LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
        }:
            raise ValueError("receipt must settle the stage")
        for label, references in (
            ("input_references", self.input_references),
            ("output_references", self.output_references),
        ):
            validate_lifecycle_object_references(label, references)
        expected_input_hashes = tuple(
            sorted(item.content_hash for item in self.input_references)
        )
        expected_output_hashes = tuple(
            sorted(item.content_hash for item in self.output_references)
        )
        if self.receipt.input_hashes != expected_input_hashes:
            raise ValueError("receipt input_hashes do not bind input_references")
        if self.receipt.output_hashes != expected_output_hashes:
            raise ValueError("receipt output_hashes do not bind output_references")
        reasoned_stage = self.receipt.stage_result in {
            LifecycleStageStatus.WAITING,
            LifecycleStageStatus.BLOCKED,
            LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
        }
        reasoned_run = self.target_run_status in WAITING_LIFECYCLE_RUN_STATUSES
        if reasoned_stage or reasoned_run:
            if self.blocker_reason is None:
                raise ValueError("reasoned stage or run result requires blocker_reason")
            require_text("blocker_reason", self.blocker_reason)
        elif self.blocker_reason is not None:
            raise ValueError("unblocked stage and run cannot carry blocker_reason")
        if (
            self.receipt.stage_result is LifecycleStageStatus.BLOCKED
            and self.target_run_status
            is not LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
        ):
            raise ValueError("BLOCKED stage must block the run on model validation")
        if self.receipt.stage_result is LifecycleStageStatus.WAITING and (
            self.target_run_status not in WAITING_LIFECYCLE_RUN_STATUSES
            or self.target_run_status
            is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
        ):
            raise ValueError("WAITING stage must select a non-terminal waiting run state")
        if (
            self.receipt.stage_result
            in {LifecycleStageStatus.COMPLETED, LifecycleStageStatus.SKIPPED_NOT_APPLICABLE}
            and self.target_run_status
            in {LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION, LifecycleRunStatus.FAILED}
        ):
            raise ValueError("successful or skipped stage cannot block or fail the run")
        require_utc_second("completed_at", self.completed_at)
        if self.receipt.created_at != self.completed_at:
            raise ValueError("receipt and transition completion times must match")


@dataclass(frozen=True, slots=True)
class StageFailure:
    """One explicit attempt failure and its rollback-safe journal projection."""

    run_id: LifecycleRunId
    stage_name: LifecycleStageName
    attempt_id: LifecycleAttemptId
    expected_run_version: int
    expected_stage_version: int
    claim_token: int
    input_references: tuple[LifecycleObjectReference, ...]
    exception_type: str
    exception_message: str
    failed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, LifecycleRunId):
            raise TypeError("run_id must be a LifecycleRunId")
        if not isinstance(self.stage_name, LifecycleStageName):
            raise TypeError("stage_name must be a LifecycleStageName")
        if not isinstance(self.attempt_id, LifecycleAttemptId):
            raise TypeError("attempt_id must be a LifecycleAttemptId")
        for label, value in (
            ("expected_run_version", self.expected_run_version),
            ("expected_stage_version", self.expected_stage_version),
            ("claim_token", self.claim_token),
        ):
            _require_positive(label, value)
        validate_lifecycle_object_references(
            "input_references", self.input_references
        )
        require_text("exception_type", self.exception_type)
        require_text("exception_message", self.exception_message)
        require_utc_second("failed_at", self.failed_at)


@dataclass(frozen=True, slots=True)
class LifecycleHistory:
    """Deterministically ordered complete journal history for one run."""

    run: LifecycleRun
    stages: tuple[LifecycleStage, ...]
    attempts: tuple[LifecycleAttempt, ...]
    receipts: tuple[StageReceipt, ...]
    events: tuple[LifecycleEvent, ...]
    event_payloads: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        run_id = self.run.run_id
        for label, values in (
            ("stages", self.stages),
            ("attempts", self.attempts),
            ("receipts", self.receipts),
            ("events", self.events),
        ):
            if any(item.run_id != run_id for item in values):
                raise ValueError(f"{label} must bind the history run")
        order = {stage: index for index, stage in enumerate(LIFECYCLE_STAGE_ORDER)}
        if self.stages != tuple(
            sorted(self.stages, key=lambda item: order[item.stage_name])
        ):
            raise ValueError("stages must follow lifecycle order")
        if tuple(item.stage_name for item in self.stages) != LIFECYCLE_STAGE_ORDER:
            raise ValueError("history must contain the complete lifecycle stage set")
        if len({item.stage_name for item in self.stages}) != len(self.stages):
            raise ValueError("stages must be unique")
        if self.attempts != tuple(
            sorted(
                self.attempts,
                key=lambda item: (order[item.stage_name], item.attempt_number),
            )
        ):
            raise ValueError("attempts must be ordered by stage and attempt number")
        attempt_keys = {
            (item.stage_name, item.attempt_number) for item in self.attempts
        }
        if len(attempt_keys) != len(self.attempts):
            raise ValueError("attempt history keys must be unique")
        if self.receipts != tuple(
            sorted(self.receipts, key=lambda item: (item.created_at, str(item.receipt_id)))
        ):
            raise ValueError("receipts must be ordered by creation and identity")
        if len({item.receipt_id for item in self.receipts}) != len(self.receipts):
            raise ValueError("receipt identities must be unique")
        if self.events != tuple(
            sorted(self.events, key=lambda item: item.sequence_number)
        ):
            raise ValueError("events must be ordered by sequence")
        if tuple(item.sequence_number for item in self.events) != tuple(
            range(1, len(self.events) + 1)
        ):
            raise ValueError("event sequence must be unique and gap-free")
        if len(self.event_payloads) != len(self.events):
            raise ValueError("each event must retain its canonical payload JSON")
        if any(not isinstance(item, str) or not item for item in self.event_payloads):
            raise ValueError("event payloads must be non-empty canonical JSON strings")


class LifecycleRunRepository(Protocol):
    """Replaceable persistence boundary for lifecycle orchestration."""

    def create_or_get(
        self,
        command: CanonicalLifecycleCommand,
        *,
        created_at: datetime,
    ) -> LifecycleRun: ...

    def get_run(self, run_id: LifecycleRunId) -> LifecycleRun: ...

    def get_run_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> LifecycleRun | None: ...

    def get_command(
        self,
        run_id: LifecycleRunId,
    ) -> CanonicalLifecycleCommand: ...

    def get_stage(
        self,
        run_id: LifecycleRunId,
        stage: LifecycleStageName,
    ) -> LifecycleStage | None: ...

    def claim(
        self,
        run_id: LifecycleRunId,
        *,
        expected_version: int,
        claimed_at: datetime,
    ) -> LifecycleRun: ...

    def start_stage(
        self,
        run_id: LifecycleRunId,
        stage: LifecycleStageName,
        *,
        started_at: datetime,
        claim_token: int,
    ) -> LifecycleAttempt: ...

    def finish_stage(self, transition: StageTransition) -> LifecycleRun: ...

    def mark_stage_failed(self, failure: StageFailure) -> LifecycleRun: ...

    def resume(
        self,
        run_id: LifecycleRunId,
        *,
        resumed_at: datetime,
    ) -> LifecycleRun: ...

    def history(self, run_id: LifecycleRunId) -> LifecycleHistory: ...
