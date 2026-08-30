"""Shared command mechanics for Selection-owned Candidate Authority."""

from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
from typing import Callable, Iterator, ParamSpec, TypeVar

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


def replay_concurrent_success(
    command: Callable[_P, _R],
) -> Callable[_P, _R]:
    """Resolve a post-preflight race through the ordinary replay path."""

    @wraps(command)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return command(*args, **kwargs)
        except ConcurrentCommandSucceeded:
            return command(*args, **kwargs)

    return wrapped


@contextmanager
def candidate_failure_boundary(
    failure_recorder: RuntimeCommandFailureRecorder,
    *,
    operation: str,
    scope_id: str,
    request_hash: str | Callable[[], str],
    context: CommandContext,
    runtime_claim: AttemptClaim | None,
) -> Iterator[None]:
    """Record deterministic rejection only after the business UoW rolls back."""

    def descriptor() -> CommandFailureDescriptor:
        semantic_hash = request_hash() if callable(request_hash) else request_hash
        return CommandFailureDescriptor(
            command_kind=operation,
            scope_id=scope_id,
            request_hash=semantic_hash,
            error_class="COMMAND",
            error_code=f"{operation}_REJECTED",
            aggregate_kind="CANDIDATE_COMMAND",
            failure_action="CANDIDATE_COMMAND_FAILED",
            rejection_command_kind="CANDIDATE_COMMAND_REJECTION",
            rejection_action="CANDIDATE_COMMAND_REJECTED",
            rejection_key_prefix="candidate-command-rejection",
        )
    try:
        yield
    except StaleFenceError:
        raise
    except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
        failure_recorder.record_idempotency_rejection(
            descriptor(),
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
            descriptor(),
            context=context,
            runtime_claim=runtime_claim,
        )
        raise


__all__ = ["candidate_failure_boundary", "replay_concurrent_success"]
