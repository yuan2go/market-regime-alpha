"""Stable target Runtime failure vocabulary."""

from market_regime_alpha.shared.errors import ConflictError, NotFoundError


class IdempotencyKeyReusedError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"


class CommandInProgressError(ConflictError):
    code = "COMMAND_IN_PROGRESS"


class StaleFenceError(ConflictError):
    code = "STALE_FENCE"


class RuntimeNotFoundError(NotFoundError):
    code = "RUNTIME_NOT_FOUND"


class RuntimeStateConflictError(ConflictError):
    code = "RUNTIME_STATE_CONFLICT"


class ArtifactIntegrityError(ConflictError):
    code = "ARTIFACT_INTEGRITY_FAILED"


__all__ = [
    "CommandInProgressError",
    "ArtifactIntegrityError",
    "IdempotencyKeyReusedError",
    "RuntimeNotFoundError",
    "RuntimeStateConflictError",
    "StaleFenceError",
]
