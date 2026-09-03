"""Read-only exact input and in-transaction revalidation ports."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.outcome.domain import PreparedOutcomeInputs
from market_regime_alpha.runtime.ports import AttemptClaim


class OutcomeSettlementRequest(Protocol):
    @property
    def commitment_id(self) -> UUID: ...

    @property
    def observation_cutoff(self) -> datetime: ...

    @property
    def knowledge_cutoff(self) -> datetime: ...

    @property
    def expected_current_revision_id(self) -> UUID | None: ...


class OutcomeInputPreparationProvider(Protocol):
    def prepare(
        self,
        request: OutcomeSettlementRequest,
        runtime_claim: AttemptClaim,
    ) -> PreparedOutcomeInputs: ...

    def prepare_exploratory_retrospective(
        self,
        request: OutcomeSettlementRequest,
        runtime_claim: AttemptClaim,
    ) -> PreparedOutcomeInputs: ...


class OutcomeDependencyRepository(Protocol):
    def lock_and_revalidate(self, prepared: PreparedOutcomeInputs) -> None: ...


__all__ = [
    "OutcomeDependencyRepository",
    "OutcomeInputPreparationProvider",
    "OutcomeSettlementRequest",
]
