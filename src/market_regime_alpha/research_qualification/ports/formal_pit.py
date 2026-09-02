"""Campaign-bound exact Formal PIT source resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class FormalPitSourceKind(StrEnum):
    MARKET_BAR_REVISION = "MARKET_BAR_REVISION"
    INSTRUMENT_FACT_REVISION = "INSTRUMENT_FACT_REVISION"
    CLASSIFICATION_MEMBERSHIP_REVISION = "CLASSIFICATION_MEMBERSHIP_REVISION"
    TRADING_SESSION = "TRADING_SESSION"
    SOURCE_GAP = "SOURCE_GAP"


@dataclass(frozen=True, slots=True)
class FormalPitSource:
    formal_research_campaign_id: UUID
    provider_qualification_decision_id: UUID
    source_kind: FormalPitSourceKind
    source_identity: UUID
    capture_id: UUID
    source_content_sha256: str
    source_available_at: datetime
    qualified_decision_visible_at: datetime
    visibility_content_sha256: str


class FormalPitSourceReadPort(Protocol):
    def resolve_exact(
        self,
        *,
        formal_research_campaign_id: UUID,
        provider_qualification_decision_id: UUID,
        source_kind: FormalPitSourceKind,
        source_identity: UUID,
        requested_decision_time: datetime,
    ) -> FormalPitSource: ...


__all__ = ["FormalPitSource", "FormalPitSourceKind", "FormalPitSourceReadPort"]
