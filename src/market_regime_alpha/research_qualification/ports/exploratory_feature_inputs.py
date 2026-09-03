"""Narrow dual-clock feature observations for exploratory Dataset construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.exploratory import (
    ExploratoryRetrospectiveDatasetScope,
)
from market_regime_alpha.shared.identity import ContentHash, InstrumentId, TradingSessionId


@dataclass(frozen=True, slots=True)
class ExploratoryIntradayFeatureObservation:
    bar_revision_id: UUID
    capture_id: UUID
    instrument_id: InstrumentId
    session_id: TradingSessionId
    event_start: datetime
    event_end: datetime
    known_at: datetime
    open_value: Decimal
    close_value: Decimal
    intraday_move: Decimal
    content_sha256: ContentHash


@dataclass(frozen=True, slots=True)
class ExploratoryIntradayFeatureGap:
    gap_id: UUID
    capture_id: UUID
    instrument_id: InstrumentId
    session_id: TradingSessionId
    event_start: datetime
    event_end: datetime
    known_at: datetime
    gap_kind: str
    reason_code: str
    content_sha256: ContentHash


ExploratoryIntradayFeatureInput = (
    ExploratoryIntradayFeatureObservation | ExploratoryIntradayFeatureGap
)


class ExploratoryFeatureInputReadPort(Protocol):
    def exact_intraday_move(
        self,
        *,
        scope: ExploratoryRetrospectiveDatasetScope,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        feature_event_end: datetime,
    ) -> ExploratoryIntradayFeatureInput: ...


__all__ = [
    "ExploratoryFeatureInputReadPort",
    "ExploratoryIntradayFeatureGap",
    "ExploratoryIntradayFeatureInput",
    "ExploratoryIntradayFeatureObservation",
]
