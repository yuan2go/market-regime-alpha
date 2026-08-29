"""Narrow read-only Market/PIT port consumed by Selection."""

from typing import Protocol
from uuid import UUID

from market_regime_alpha.selection.domain import (
    CriterionEvidence,
    EligibilityRule,
    MembershipEvidence,
    UniverseScopeSpecification,
)
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.time import DecisionTime


class SelectionMarketQueries(Protocol):
    def membership_as_of(
        self,
        *,
        scope: UniverseScopeSpecification,
        instrument_id: InstrumentId,
        decision_time: DecisionTime,
    ) -> MembershipEvidence: ...

    def criterion_evidence_as_of(
        self,
        *,
        market_provider_product_id: UUID,
        rule: EligibilityRule,
        instrument_id: InstrumentId,
        decision_time: DecisionTime,
    ) -> CriterionEvidence: ...


__all__ = ["SelectionMarketQueries"]
