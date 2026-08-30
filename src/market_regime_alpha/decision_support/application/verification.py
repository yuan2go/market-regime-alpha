"""Public read-only Decision Run replay verification facade."""

from uuid import UUID

from market_regime_alpha.decision_support.domain import DecisionRunVerification
from market_regime_alpha.decision_support.ports import DecisionRunVerificationProvider


class DecisionRunVerifier:
    def __init__(self, provider: DecisionRunVerificationProvider) -> None:
        self._provider = provider

    def verify(self, decision_run_id: UUID) -> DecisionRunVerification:
        return self._provider.verify(decision_run_id)


__all__ = ["DecisionRunVerifier"]
