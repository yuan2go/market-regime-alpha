"""Read-only due discovery, inspection, and reconciliation ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class DueOutcomeState(StrEnum):
    NOT_DUE = "NOT_DUE"
    DUE = "DUE"
    SETTLED = "SETTLED"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class DueOutcomeMember:
    research_partition_member_id: UUID
    research_partition_id: UUID
    commitment_id: UUID
    outcome_due_at: datetime
    database_now: datetime
    state: DueOutcomeState
    market_target_outcome_id: UUID | None
    terminal_revision_count: int


@dataclass(frozen=True, slots=True)
class FormalCampaignInspection:
    formal_research_campaign_id: UUID
    campaign_code: str
    revision: int
    campaign_class: str
    state: str
    provider_decision_status: str | None
    planned_partition_count: int
    bound_partition_count: int
    first_access_count: int
    evaluation_open_count: int
    evaluation_terminal_count: int
    due_count: int
    missing_count: int
    settled_count: int
    evidence_count: int
    assessment_count: int
    qualification_count: int
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormalCampaignVerification:
    formal_research_campaign_id: UUID
    matched: bool
    mismatch_count: int
    mismatches: tuple[str, ...]


class FormalCampaignQueryPort(Protocol):
    def discover_due_outcomes(
        self, formal_research_campaign_id: UUID
    ) -> tuple[DueOutcomeMember, ...]: ...

    def inspect(
        self, formal_research_campaign_id: UUID
    ) -> FormalCampaignInspection: ...

    def verify(
        self, formal_research_campaign_id: UUID
    ) -> FormalCampaignVerification: ...


__all__ = [
    "DueOutcomeMember",
    "DueOutcomeState",
    "FormalCampaignInspection",
    "FormalCampaignQueryPort",
    "FormalCampaignVerification",
]
