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
from market_regime_alpha.runtime.application import (
    CommandContext,
    CommandFailureDescriptor,
    ConcurrentCommandSucceeded,
    RuntimeCommandFailureRecorder,
)
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
from market_regime_alpha.shared.time import DecisionTime

from market_regime_alpha.market.application.results import MarketMutationResult

_P = ParamSpec("_P")
_R = TypeVar("_R")


class _SourceArtifactVerificationFailure(ArtifactIntegrityError):
    """The verification observation and original command failure are durable."""


_ConcurrentCommandSucceeded = ConcurrentCommandSucceeded


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
        self._failure_recorder = RuntimeCommandFailureRecorder(
            uow_provider,
            id_factory=id_factory,
        )

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
            self._failure_recorder.record_idempotency_rejection(
                self._failure_descriptor(
                    operation=operation,
                    scope_id=scope_id,
                    request_hash=request_hash,
                    error_class=error_class,
                    error_code=error_code,
                ),
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
            self._failure_recorder.record(
                self._failure_descriptor(
                    operation=operation,
                    scope_id=scope_id,
                    request_hash=request_hash,
                    error_class=error_class,
                    error_code=error_code,
                ),
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    @staticmethod
    def _failure_descriptor(
        *,
        operation: str,
        scope_id: str,
        request_hash: str,
        error_class: str,
        error_code: str,
    ) -> CommandFailureDescriptor:
        return CommandFailureDescriptor(
            command_kind=operation,
            scope_id=scope_id,
            request_hash=request_hash,
            error_class=error_class,
            error_code=error_code,
            aggregate_kind="MARKET_COMMAND",
            failure_action="MARKET_COMMAND_FAILED",
            rejection_command_kind="MARKET_COMMAND_REJECTION",
            rejection_action="MARKET_COMMAND_REJECTED",
            rejection_key_prefix="market-command-rejection",
        )

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
        self._failure_recorder.record(
            self._failure_descriptor(
                operation=operation,
                scope_id=scope_id,
                request_hash=request_hash,
                error_class=error_class,
                error_code=error_code,
            ),
            context=context,
            runtime_claim=runtime_claim,
        )

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
        self._failure_recorder.append_idempotency_rejection(
            uow,
            descriptor=self._failure_descriptor(
                operation=operation,
                scope_id=scope_id,
                request_hash=rejected_request_hash,
                error_class="COMMAND",
                error_code=rejection_code,
            ),
            rejection_code=rejection_code,
            context=context,
            runtime_claim=runtime_claim,
        )

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
