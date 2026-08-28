"""Stable target Runtime failure vocabulary."""

from market_regime_alpha.shared.errors import ConflictError, NotFoundError


class IdempotencyKeyReusedError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"


class CommandInProgressError(ConflictError):
    code = "COMMAND_IN_PROGRESS"


class CommandPreviouslyFailedError(ConflictError):
    code = "COMMAND_PREVIOUSLY_FAILED"

    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(f"command already failed with {error_code}")


class StaleFenceError(ConflictError):
    code = "STALE_FENCE"


class RuntimeNotFoundError(NotFoundError):
    code = "RUNTIME_NOT_FOUND"


class RuntimeStateConflictError(ConflictError):
    code = "RUNTIME_STATE_CONFLICT"


class ArtifactIntegrityError(ConflictError):
    code = "ARTIFACT_INTEGRITY_FAILED"


class ArtifactByteStoreError(RuntimeError):
    """Physical content-store operation could not establish a safe identity."""


__all__ = [
    "CommandInProgressError",
    "CommandPreviouslyFailedError",
    "ArtifactIntegrityError",
    "ArtifactByteStoreError",
    "IdempotencyKeyReusedError",
    "RuntimeNotFoundError",
    "RuntimeStateConflictError",
    "StaleFenceError",
]
