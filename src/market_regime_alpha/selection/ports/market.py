"""Narrow read-only Market/PIT port consumed by Selection."""

from typing import Protocol
from uuid import UUID

from market_regime_alpha.selection.domain import (
    CriterionEvidence,
    EligibilityRule,
    MembershipEvidence,
    UniverseScopeSpecification,
    ExploratoryRetrospectiveSelectionScope,
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

    def membership_for_exploratory_retrospective(
        self,
        *,
        scope: UniverseScopeSpecification,
        instrument_id: InstrumentId,
        retrospective: ExploratoryRetrospectiveSelectionScope,
    ) -> MembershipEvidence: ...

    def criterion_evidence_for_exploratory_retrospective(
        self,
        *,
        market_provider_product_id: UUID,
        rule: EligibilityRule,
        instrument_id: InstrumentId,
        retrospective: ExploratoryRetrospectiveSelectionScope,
    ) -> CriterionEvidence: ...


__all__ = ["SelectionMarketQueries"]
