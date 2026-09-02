"""Narrow canonical Selection/Market lineage reads for Research datasets."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain import (
    DatasetSource,
    DatasetSourceRole,
)
from market_regime_alpha.shared.time import DecisionTime


@dataclass(frozen=True, slots=True)
class DatasetPopulationMember:
    instrument_id: UUID
    universe_member_id: UUID
    eligibility_assessment_id: UUID


@dataclass(frozen=True, slots=True)
class DatasetMarketSourceObservation:
    dataset_source_id: UUID
    role: DatasetSourceRole
    source_identity: UUID
    instrument_id: UUID | None
    decision_visible_at: datetime
    foundation_integrity: bool


class ResearchSourceQueries(Protocol):
    def expected_population(
        self,
        *,
        universe_revision_id: UUID,
        eligibility_policy_id: UUID,
        decision_time: DecisionTime,
        lock: bool,
    ) -> tuple[DatasetPopulationMember, ...]: ...

    def market_source_observations(
        self,
        sources: tuple[DatasetSource, ...],
        *,
        lock: bool,
    ) -> tuple[DatasetMarketSourceObservation, ...]: ...

    def formal_market_source_observations(
        self,
        sources: tuple[DatasetSource, ...],
        *,
        formal_research_campaign_id: UUID,
        provider_qualification_decision_id: UUID,
        lock: bool,
    ) -> tuple[DatasetMarketSourceObservation, ...]: ...


__all__ = [
    "DatasetMarketSourceObservation",
    "DatasetPopulationMember",
    "ResearchSourceQueries",
]
