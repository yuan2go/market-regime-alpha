"""Explicit Market/PIT commands over a narrow bounded transaction."""

from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
from typing import Callable, Iterator, ParamSpec, TypeVar
from uuid import UUID, uuid4

from market_regime_alpha.market.ports import (
    MarketArtifactByteStore,
    MarketDatabaseClock,
    MarketUnitOfWork,
    MarketUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import (
    ArtifactByteStoreError,
    ArtifactIntegrityError,
    CommandInProgressError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    ReceiptRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import DecisionTime

from market_regime_alpha.market.application.results import MarketMutationResult

_P = ParamSpec("_P")
_R = TypeVar("_R")


class _SourceArtifactVerificationFailure(ArtifactIntegrityError):
    """The verification observation and original command failure are durable."""


class _ConcurrentCommandSucceeded(RuntimeError):
    """A concurrent exact command committed while this worker was outside SQL."""

    def __init__(self, *, runtime_finalized: bool = False) -> None:
        super().__init__("concurrent exact command already succeeded")
        self.runtime_finalized = runtime_finalized


def _replay_concurrent_success(command: Callable[_P, _R]) -> Callable[_P, _R]:
    """Resolve a post-preflight race through the canonical replay path."""

    @wraps(command)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return command(*args, **kwargs)
        except _ConcurrentCommandSucceeded as resolution:
            if resolution.runtime_finalized:
                replay_kwargs = dict(kwargs)
                replay_kwargs["runtime_claim"] = None
                return command(*args, **replay_kwargs)  # type: ignore[arg-type]
            return command(*args, **kwargs)

    return wrapped


class _MarketCommandSupport:
    def __init__(
        self,
        byte_store: MarketArtifactByteStore,
        uow_provider: MarketUnitOfWorkProvider,
        database_clock: MarketDatabaseClock,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._byte_store = byte_store
        self._uow_provider = uow_provider
        self._database_clock = database_clock
        self._id_factory = id_factory

    @contextmanager
    def _terminal_failure_boundary(
        self,
        *,
        operation: str,
        scope_id: str,
        request_hash: str,
        error_class: str,
        error_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> Iterator[None]:
        """Classify deterministic command rejection without weakening fencing."""
        try:
            yield
        except StaleFenceError:
            raise
        except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
            self._record_idempotency_rejection(
                operation=operation,
                scope_id=scope_id,
                rejected_request_hash=request_hash,
                rejection_code=exc.code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise
        except (
            ArtifactByteStoreError,
            ArtifactIntegrityError,
            CommandPreviouslyFailedError,
            RuntimeNotFoundError,
            RuntimeStateConflictError,
            ValueError,
        ):
            self._record_command_failure(
                operation=operation,
                scope_id=scope_id,
                request_hash=request_hash,
                error_class=error_class,
                error_code=error_code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    def _record_command_failure(
        self,
        *,
        operation: str,
        scope_id: str,
        request_hash: str,
        error_class: str,
        error_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        """Commit the original command's FAILED receipt after business rollback."""
        try:
            with self._uow_provider() as uow:
                if runtime_claim is not None:
                    uow.runtime_finalization.lock_live(runtime_claim)
                receipt = uow.receipts.start(
                    receipt_id=self._id_factory(),
                    command_kind=operation,
                    scope_id=scope_id,
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                )
                if receipt.is_new:
                    uow.receipts.fail(receipt_id=receipt.receipt_id, error_code=error_code, runtime_claim=runtime_claim)
                    uow.audit.append(
                        audit_event_id=self._id_factory(),
                        receipt_id=receipt.receipt_id,
                        actor_type=context.actor_type.value,
                        actor_id=context.actor_id,
                        aggregate_kind="MARKET_COMMAND",
                        aggregate_id=f"{operation}:{scope_id}",
                        action="MARKET_COMMAND_FAILED",
                        reason_code=error_code,
                        before_version=None,
                        after_version=None,
                        runtime_claim=runtime_claim,
                    )
                elif receipt.status == "SUCCEEDED":
                    raise _ConcurrentCommandSucceeded()
                elif receipt.status != "FAILED":
                    raise RuntimeStateConflictError("cannot replace a non-failed terminal command receipt")
                if runtime_claim is not None:
                    terminal_error_code = error_code if receipt.is_new else receipt.error_code or error_code
                    uow.runtime_finalization.fail(
                        runtime_claim, receipt_id=receipt.receipt_id, error_class=error_class, error_code=terminal_error_code
                    )
                uow.commit()
        except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
            self._record_idempotency_rejection(
                operation=operation,
                scope_id=scope_id,
                rejected_request_hash=request_hash,
                rejection_code=exc.code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    def _record_idempotency_rejection(
        self,
        *,
        operation: str,
        scope_id: str,
        rejected_request_hash: str,
        rejection_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        """Terminalize a fenced Attempt without taking over another command key."""
        if runtime_claim is None:
            return
        with self._uow_provider() as uow:
            uow.runtime_finalization.lock_live(runtime_claim)
            self._append_idempotency_rejection(
                uow,
                operation=operation,
                scope_id=scope_id,
                rejected_request_hash=rejected_request_hash,
                rejection_code=rejection_code,
                context=context,
                runtime_claim=runtime_claim,
            )
            uow.commit()

    def _append_idempotency_rejection(
        self,
        uow: MarketUnitOfWork,
        *,
        operation: str,
        scope_id: str,
        rejected_request_hash: str,
        rejection_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim,
    ) -> None:
        """Append a rejection after the caller has locked the live Runtime claim."""
        rejection_scope = str(runtime_claim.attempt_id)
        rejection_key = f"market-command-rejection:{runtime_claim.attempt_id}"
        rejection_hash = canonical_json_sha256(
            {
                "operation": operation,
                "scope_id": scope_id,
                "idempotency_key": context.idempotency_key,
                "rejected_request_hash": rejected_request_hash,
                "rejection_code": rejection_code,
                "attempt_id": runtime_claim.attempt_id,
                "fence_token": runtime_claim.fence_token,
            }
        )
        receipt = uow.receipts.start(
            receipt_id=self._id_factory(),
            command_kind="MARKET_COMMAND_REJECTION",
            scope_id=rejection_scope,
            idempotency_key=rejection_key,
            request_hash=rejection_hash,
        )
        if receipt.is_new:
            uow.receipts.fail(receipt_id=receipt.receipt_id, error_code=rejection_code, runtime_claim=runtime_claim)
            uow.audit.append(
                audit_event_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="MARKET_COMMAND",
                aggregate_id=f"{operation}:{scope_id}",
                action="MARKET_COMMAND_REJECTED",
                reason_code=rejection_code,
                before_version=None,
                after_version=None,
                runtime_claim=runtime_claim,
            )
        elif receipt.status != "FAILED":
            raise RuntimeStateConflictError("idempotency rejection incident is not terminal FAILED")
        uow.runtime_finalization.fail(runtime_claim, receipt_id=receipt.receipt_id, error_class="COMMAND", error_code=rejection_code)

    def _finish_mutation(
        self,
        uow: MarketUnitOfWork,
        *,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: str,
        aggregate_version: int,
        result_hash: str,
        action: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> None:
        uow.receipts.succeed(
            receipt_id=receipt_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            result_hash=result_hash,
            runtime_claim=runtime_claim,
        )
        uow.audit.append(
            audit_event_id=self._id_factory(),
            receipt_id=receipt_id,
            actor_type=context.actor_type.value,
            actor_id=context.actor_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id,
            action=action,
            reason_code=context.reason_code,
            before_version=None,
            after_version=aggregate_version,
            runtime_claim=runtime_claim,
        )


def _required_result_hash(value: str | None) -> str:
    if value is None:
        raise ArtifactIntegrityError("terminal receipt has no result hash")
    return value


def _ensure_replay_succeeded(receipt: ReceiptRecord) -> None:
    if receipt.status in {"FAILED", "BLOCKED"}:
        raise CommandPreviouslyFailedError(receipt.error_code or "COMMAND_FAILED_WITHOUT_ERROR_CODE")
    if receipt.status != "SUCCEEDED":
        raise RuntimeStateConflictError(f"receipt {receipt.receipt_id} is not a replayable terminal result")


def _replayed_mutation(receipt, *, decision_visible_at: DecisionTime | None = None) -> MarketMutationResult:
    _ensure_replay_succeeded(receipt)
    if (
        receipt.result_aggregate_kind is None
        or receipt.result_aggregate_id is None
        or receipt.result_aggregate_version is None
        or (receipt.result_hash is None)
    ):
        raise ArtifactIntegrityError("terminal receipt has no complete result")
    return MarketMutationResult(
        aggregate_kind=receipt.result_aggregate_kind,
        aggregate_id=receipt.result_aggregate_id,
        aggregate_version=receipt.result_aggregate_version,
        result_hash=receipt.result_hash,
        receipt_id=receipt.receipt_id,
        replayed=True,
        decision_visible_at=decision_visible_at,
    )
