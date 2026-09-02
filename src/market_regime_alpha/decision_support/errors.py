"""Stable Decision Support command and Authority failures."""

from market_regime_alpha.shared.errors import ConflictError, IntegrityError


class CandidateSetAlreadyCommittedError(ConflictError):
    code = "CANDIDATE_SET_ALREADY_COMMITTED"


class DecisionAuthorityIntegrityError(IntegrityError):
    code = "DECISION_AUTHORITY_INTEGRITY_FAILED"


class DecisionReferenceResolutionError(DecisionAuthorityIntegrityError):
    code = "DECISION_REFERENCE_RESOLUTION_FAILED"


class DecisionQualificationResolutionError(DecisionAuthorityIntegrityError):
    code = "DECISION_QUALIFICATION_RESOLUTION_FAILED"


class ContextAuthorityIntegrityError(DecisionAuthorityIntegrityError):
    code = "CONTEXT_AUTHORITY_INTEGRITY_FAILED"


class ContextAlreadyAssessedError(ConflictError):
    code = "CONTEXT_ALREADY_ASSESSED"


class StrategyAuthorityIntegrityError(DecisionAuthorityIntegrityError):
    code = "STRATEGY_AUTHORITY_INTEGRITY_FAILED"


class StrategyAlreadyRegisteredError(ConflictError):
    code = "STRATEGY_ALREADY_REGISTERED"


class InferenceAuthorityIntegrityError(DecisionAuthorityIntegrityError):
    code = "INFERENCE_AUTHORITY_INTEGRITY_FAILED"


class InferenceAlreadyProducedError(ConflictError):
    code = "INFERENCE_ALREADY_PRODUCED"


class DecisionTransactionRetryExhaustedError(ConflictError):
    code = "DECISION_TRANSACTION_RETRY_EXHAUSTED"


class DecisionRetryableTransactionError(RuntimeError):
    """One whole PostgreSQL transaction may be retried with frozen inputs."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate
        super().__init__(f"retryable Decision transaction failure {sqlstate}")


class DecisionCommitOutcomeUnknownError(RuntimeError):
    """Connection loss prevented determining whether COMMIT reached PostgreSQL."""


__all__ = [
    "CandidateSetAlreadyCommittedError",
    "ContextAlreadyAssessedError",
    "ContextAuthorityIntegrityError",
    "DecisionAuthorityIntegrityError",
    "DecisionCommitOutcomeUnknownError",
    "DecisionRetryableTransactionError",
    "DecisionReferenceResolutionError",
    "DecisionQualificationResolutionError",
    "DecisionTransactionRetryExhaustedError",
    "InferenceAlreadyProducedError",
    "InferenceAuthorityIntegrityError",
    "StrategyAlreadyRegisteredError",
    "StrategyAuthorityIntegrityError",
]
