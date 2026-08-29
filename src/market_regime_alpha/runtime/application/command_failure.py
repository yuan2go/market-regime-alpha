"""Narrow cross-context persistence contract for deterministic command failure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.runtime.application.service import CommandContext
from market_regime_alpha.runtime.errors import (
    CommandInProgressError,
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    CommandFailureUnitOfWork,
    CommandFailureUnitOfWorkProvider,
    ReceiptRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class CommandFailureDescriptor:
    """Context-owned names and identities; contains no Domain interpretation."""

    command_kind: str
    scope_id: str
    request_hash: str
    error_class: str
    error_code: str
    aggregate_kind: str
    failure_action: str
    rejection_command_kind: str
    rejection_action: str
    rejection_key_prefix: str


class ConcurrentCommandSucceeded(RuntimeError):
    """An exact command committed before its deterministic failure was recorded."""

    def __init__(self, *, runtime_finalized: bool = False) -> None:
        super().__init__("concurrent exact command already succeeded")
        self.runtime_finalized = runtime_finalized


class RuntimeCommandFailureRecorder:
    """Persist failed receipt, audit, and Runtime failure after business rollback."""

    def __init__(
        self,
        uow_provider: CommandFailureUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory

    def record(
        self,
        descriptor: CommandFailureDescriptor,
        *,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        """Commit a deterministic failure in a fresh, short owner UoW."""
        try:
            with self._uow_provider() as uow:
                if runtime_claim is not None:
                    uow.runtime_finalization.lock_live(runtime_claim)
                receipt = self.append_failure(
                    uow,
                    descriptor=descriptor,
                    context=context,
                    runtime_claim=runtime_claim,
                )
                if receipt.status == "SUCCEEDED":
                    raise ConcurrentCommandSucceeded()
                uow.commit()
        except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
            self.record_idempotency_rejection(
                descriptor,
                rejection_code=exc.code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    def append_failure(
        self,
        uow: CommandFailureUnitOfWork,
        *,
        descriptor: CommandFailureDescriptor,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> ReceiptRecord:
        """Append failure facts after the caller has acquired any live fence."""
        receipt = uow.receipts.start(
            receipt_id=self._id_factory(),
            command_kind=descriptor.command_kind,
            scope_id=descriptor.scope_id,
            idempotency_key=context.idempotency_key,
            request_hash=descriptor.request_hash,
        )
        if receipt.is_new:
            uow.receipts.fail(
                receipt_id=receipt.receipt_id,
                error_code=descriptor.error_code,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind=descriptor.aggregate_kind,
                aggregate_id=f"{descriptor.command_kind}:{descriptor.scope_id}",
                action=descriptor.failure_action,
                reason_code=descriptor.error_code,
                before_version=None,
                after_version=None,
                runtime_claim=runtime_claim,
            )
        elif receipt.status not in {"FAILED", "SUCCEEDED"}:
            raise RuntimeStateConflictError(
                "cannot replace a non-failed terminal command receipt"
            )
        if runtime_claim is not None and receipt.status != "SUCCEEDED":
            terminal_error_code = (
                descriptor.error_code
                if receipt.is_new
                else receipt.error_code or descriptor.error_code
            )
            uow.runtime_finalization.fail(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                error_class=descriptor.error_class,
                error_code=terminal_error_code,
            )
        return receipt

    def record_idempotency_rejection(
        self,
        descriptor: CommandFailureDescriptor,
        *,
        rejection_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        """Fail a fenced Attempt without taking over another command receipt."""
        if runtime_claim is None:
            return
        with self._uow_provider() as uow:
            uow.runtime_finalization.lock_live(runtime_claim)
            self.append_idempotency_rejection(
                uow,
                descriptor=descriptor,
                rejection_code=rejection_code,
                context=context,
                runtime_claim=runtime_claim,
            )
            uow.commit()

    def append_idempotency_rejection(
        self,
        uow: CommandFailureUnitOfWork,
        *,
        descriptor: CommandFailureDescriptor,
        rejection_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim,
    ) -> None:
        rejection_scope = str(runtime_claim.attempt_id)
        rejection_key = (
            f"{descriptor.rejection_key_prefix}:{runtime_claim.attempt_id}"
        )
        rejection_hash = canonical_json_sha256(
            {
                "attempt_id": runtime_claim.attempt_id,
                "command_kind": descriptor.command_kind,
                "fence_token": runtime_claim.fence_token,
                "idempotency_key": context.idempotency_key,
                "rejected_request_hash": descriptor.request_hash,
                "rejection_code": rejection_code,
                "scope_id": descriptor.scope_id,
            }
        )
        receipt = uow.receipts.start(
            receipt_id=self._id_factory(),
            command_kind=descriptor.rejection_command_kind,
            scope_id=rejection_scope,
            idempotency_key=rejection_key,
            request_hash=rejection_hash,
        )
        if receipt.is_new:
            uow.receipts.fail(
                receipt_id=receipt.receipt_id,
                error_code=rejection_code,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind=descriptor.aggregate_kind,
                aggregate_id=f"{descriptor.command_kind}:{descriptor.scope_id}",
                action=descriptor.rejection_action,
                reason_code=rejection_code,
                before_version=None,
                after_version=None,
                runtime_claim=runtime_claim,
            )
        elif receipt.status != "FAILED":
            raise RuntimeStateConflictError(
                "idempotency rejection incident is not terminal FAILED"
            )
        uow.runtime_finalization.fail(
            runtime_claim,
            receipt_id=receipt.receipt_id,
            error_class="COMMAND",
            error_code=rejection_code,
        )


__all__ = [
    "CommandFailureDescriptor",
    "ConcurrentCommandSucceeded",
    "RuntimeCommandFailureRecorder",
]
