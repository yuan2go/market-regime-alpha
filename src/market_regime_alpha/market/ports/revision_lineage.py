"""Narrow read-only lineage port for repeated Market observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.market.domain.vocabulary import (
    BarTimeframe,
    EvidenceScope,
    InstrumentFactKind,
    PriceBasis,
)
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId


@dataclass(frozen=True, slots=True)
class MarketBarRevisionHead:
    bar_revision_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class InstrumentFactRevisionHead:
    fact_revision_id: UUID
    revision: int


class MarketRevisionLineageReadPort(Protocol):
    def market_bar_head(
        self,
        *,
        provider_product_id: UUID,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        timeframe: BarTimeframe,
        price_basis: PriceBasis,
        event_start: datetime,
        event_end: datetime,
    ) -> MarketBarRevisionHead | None: ...

    def instrument_fact_head(
        self,
        *,
        provider_product_id: UUID,
        instrument_id: InstrumentId,
        session_id: TradingSessionId | None,
        fact_kind: InstrumentFactKind,
        evidence_scope: EvidenceScope,
        event_start: datetime,
    ) -> InstrumentFactRevisionHead | None: ...


__all__ = [
    "InstrumentFactRevisionHead",
    "MarketBarRevisionHead",
    "MarketRevisionLineageReadPort",
]
