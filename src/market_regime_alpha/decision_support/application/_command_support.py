"""Shared failure recording for narrow Decision Support commands."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from market_regime_alpha.decision_support.errors import DecisionAuthorityIntegrityError, DecisionTransactionRetryExhaustedError
from market_regime_alpha.runtime.application import (
    CommandContext,
    CommandFailureDescriptor,
    ConcurrentCommandSucceeded,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    CommandInProgressError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import AttemptClaim


def failure_descriptor(*, operation: str, scope_id: str, request_hash: str) -> CommandFailureDescriptor:
    return CommandFailureDescriptor(
        command_kind=operation,
        scope_id=scope_id,
        request_hash=request_hash,
        error_class="COMMAND",
        error_code=f"{operation}_REJECTED",
        aggregate_kind="DECISION_SUPPORT_COMMAND",
        failure_action="DECISION_SUPPORT_COMMAND_FAILED",
        rejection_command_kind="DECISION_SUPPORT_COMMAND_REJECTION",
        rejection_action="DECISION_SUPPORT_COMMAND_REJECTED",
        rejection_key_prefix="decision-support-command-rejection",
    )


@contextmanager
def record_failures(
    recorder: RuntimeCommandFailureRecorder,
    descriptor: CommandFailureDescriptor,
    *,
    context: CommandContext,
    runtime_claim: AttemptClaim | None,
) -> Iterator[None]:
    try:
        yield
    except (StaleFenceError, ConcurrentCommandSucceeded):
        raise
    except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
        recorder.record_idempotency_rejection(
            descriptor,
            rejection_code=exc.code,
            context=context,
            runtime_claim=runtime_claim,
        )
        raise
    except (
        ArtifactIntegrityError,
        CommandPreviouslyFailedError,
        DecisionAuthorityIntegrityError,
        DecisionTransactionRetryExhaustedError,
        RuntimeNotFoundError,
        RuntimeStateConflictError,
        ValueError,
    ) as exc:
        recorder.record(
            CommandFailureDescriptor(
                command_kind=descriptor.command_kind,
                scope_id=descriptor.scope_id,
                request_hash=descriptor.request_hash,
                error_class=descriptor.error_class,
                error_code=getattr(exc, "code", descriptor.error_code),
                aggregate_kind=descriptor.aggregate_kind,
                failure_action=descriptor.failure_action,
                rejection_command_kind=descriptor.rejection_command_kind,
                rejection_action=descriptor.rejection_action,
                rejection_key_prefix=descriptor.rejection_key_prefix,
            ),
            context=context,
            runtime_claim=runtime_claim,
        )
        raise


__all__ = ["failure_descriptor", "record_failures"]
