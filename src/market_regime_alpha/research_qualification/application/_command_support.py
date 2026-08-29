"""Shared mechanics for the two explicit Research Definition commands."""

from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
from typing import Callable, Iterator, ParamSpec, TypeVar
from uuid import UUID

from market_regime_alpha.research_qualification.ports import ResearchUnitOfWork
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
from market_regime_alpha.runtime.ports import AttemptClaim


_P = ParamSpec("_P")
_R = TypeVar("_R")


class ResearchFailureAlreadyRecorded(ArtifactIntegrityError):
    """A Research-owned failure transaction already committed its evidence."""


def replay_concurrent_success(
    command: Callable[_P, _R],
) -> Callable[_P, _R]:
    @wraps(command)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return command(*args, **kwargs)
        except ConcurrentCommandSucceeded:
            return command(*args, **kwargs)

    return wrapped


@contextmanager
def terminal_failure_boundary(
    failure_recorder: RuntimeCommandFailureRecorder,
    *,
    operation: str,
    scope_id: str,
    request_hash: str,
    error_class: str,
    error_code: str,
    context: CommandContext,
    runtime_claim: AttemptClaim | None,
) -> Iterator[None]:
    descriptor = failure_descriptor(
        operation=operation,
        scope_id=scope_id,
        request_hash=request_hash,
        error_class=error_class,
        error_code=error_code,
    )
    try:
        yield
    except StaleFenceError:
        raise
    except ResearchFailureAlreadyRecorded:
        raise
    except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
        failure_recorder.record_idempotency_rejection(
            descriptor,
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
        failure_recorder.record(
            descriptor,
            context=context,
            runtime_claim=runtime_claim,
        )
        raise


def failure_descriptor(
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
        aggregate_kind="RESEARCH_COMMAND",
        failure_action="RESEARCH_COMMAND_FAILED",
        rejection_command_kind="RESEARCH_COMMAND_REJECTION",
        rejection_action="RESEARCH_COMMAND_REJECTED",
        rejection_key_prefix="research-command-rejection",
    )


def finish_success(
    uow: ResearchUnitOfWork,
    *,
    id_factory: Callable[[], UUID],
    receipt_id: UUID,
    aggregate_kind: str,
    aggregate_id: str,
    aggregate_version: int,
    result_hash: str,
    action: str,
    context: CommandContext,
    runtime_claim: AttemptClaim | None,
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
        audit_event_id=id_factory(),
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


def finalize_runtime(
    uow: ResearchUnitOfWork,
    claim: AttemptClaim | None,
    *,
    receipt_id: UUID,
    result_hash: str,
) -> None:
    if claim is not None:
        uow.runtime_finalization.succeed(
            claim,
            receipt_id=receipt_id,
            result_hash=result_hash,
        )


__all__ = [
    "ResearchFailureAlreadyRecorded",
    "failure_descriptor",
    "finalize_runtime",
    "finish_success",
    "replay_concurrent_success",
    "terminal_failure_boundary",
]
