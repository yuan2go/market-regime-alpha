"""Relational verification facts required by the Outcome replay verifier."""

from typing import Protocol
from uuid import UUID

from market_regime_alpha.outcome.domain import OutcomeMismatch


class OutcomeVerificationProvider(Protocol):
    def inspect(self, revision_id: UUID) -> tuple[OutcomeMismatch, ...]: ...


__all__ = ["OutcomeVerificationProvider"]
