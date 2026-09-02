"""Market-owned transaction failures exposed by narrow persistence adapters."""

from market_regime_alpha.shared.errors import ConflictError


class MarketRetryableTransactionError(RuntimeError):
    """One complete Market transaction may be retried with frozen inputs."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate
        super().__init__(f"retryable Market transaction failure {sqlstate}")


class MarketCommitOutcomeUnknownError(RuntimeError):
    """The connection failed while PostgreSQL's COMMIT result was unknowable."""


class MarketTransactionRetryExhaustedError(ConflictError):
    code = "MARKET_TRANSACTION_RETRY_EXHAUSTED"


__all__ = [
    "MarketCommitOutcomeUnknownError",
    "MarketRetryableTransactionError",
    "MarketTransactionRetryExhaustedError",
]
