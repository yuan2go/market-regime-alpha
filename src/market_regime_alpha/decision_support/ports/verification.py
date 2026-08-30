"""Read-only Decision Run replay/reconciliation verification port."""

from typing import Protocol
from uuid import UUID

from market_regime_alpha.decision_support.domain import DecisionRunVerification


class DecisionRunVerificationProvider(Protocol):
    def verify(self, decision_run_id: UUID) -> DecisionRunVerification: ...


__all__ = ["DecisionRunVerificationProvider"]
