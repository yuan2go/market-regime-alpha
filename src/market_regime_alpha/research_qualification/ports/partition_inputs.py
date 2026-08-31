"""Typed ex-ante inputs used to derive an exact Partition roster."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.partition import ResearchPartitionPlan


@dataclass(frozen=True, slots=True)
class PartitionCalendarBounds:
    decision_start_date: date
    decision_end_date: date
    protected_start_session_id: UUID
    protected_end_session_id: UUID
    protected_start_date: date
    protected_end_date: date
    outcome_horizon_sessions: int


@dataclass(frozen=True, slots=True)
class DerivedPartitionMember:
    commitment_id: UUID
    decision_reference_observation_id: UUID
    target_definition_id: UUID
    decision_time: datetime
    candidate_disposition: str
    commitment_recorded_at: datetime
    runtime_mode: str
    decision_session_id: UUID
    earliest_outcome_event_at: datetime
    outcome_due_at: datetime


class PartitionInputQueries(Protocol):
    def lock_target_and_calendar(
        self, plan: ResearchPartitionPlan
    ) -> PartitionCalendarBounds: ...

    def derive_complete_roster(
        self, plan: ResearchPartitionPlan
    ) -> tuple[DerivedPartitionMember, ...]: ...

    def require_canonical_live_clock(
        self, members: tuple[DerivedPartitionMember, ...]
    ) -> None: ...


__all__ = [
    "DerivedPartitionMember",
    "PartitionCalendarBounds",
    "PartitionInputQueries",
]
