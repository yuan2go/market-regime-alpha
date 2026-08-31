"""Stable Market Target Outcome command and Authority failures."""

from market_regime_alpha.shared.errors import ConflictError, IntegrityError


class OutcomeAuthorityIntegrityError(IntegrityError):
    code = "OUTCOME_AUTHORITY_INTEGRITY_FAILED"


class OutcomeInputResolutionError(OutcomeAuthorityIntegrityError):
    code = "OUTCOME_INPUT_RESOLUTION_FAILED"


class OutcomeRevisionConflictError(ConflictError):
    code = "OUTCOME_REVISION_CONFLICT"


class OutcomeTransactionRetryExhaustedError(ConflictError):
    code = "OUTCOME_TRANSACTION_RETRY_EXHAUSTED"


class OutcomeRetryableTransactionError(RuntimeError):
    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate
        super().__init__(f"retryable Outcome transaction failure {sqlstate}")


class OutcomeCommitResultUnknownError(RuntimeError):
    """Connection loss made the transaction result unknowable."""


__all__ = [
    "OutcomeAuthorityIntegrityError",
    "OutcomeCommitResultUnknownError",
    "OutcomeInputResolutionError",
    "OutcomeRetryableTransactionError",
    "OutcomeRevisionConflictError",
    "OutcomeTransactionRetryExhaustedError",
]
