"""Row-to-domain mapping for PostgreSQL Market queries."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from market_regime_alpha.market.domain import (
    BarTimeframe,
    EvidenceScope,
    GapFactKind,
    GapKind,
    GapReasonCode,
    InstrumentFactKind,
    MarketBarRevision,
    PriceBasis,
    SourceGap,
    TradingSession,
)
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import DecisionTime


def _bar(row: tuple[Any, ...]) -> MarketBarRevision:
    return MarketBarRevision(
        bar_revision_id=UUID(str(row[0])),
        provider_product_id=UUID(str(row[1])),
        capture_id=UUID(str(row[2])),
        instrument_id=InstrumentId.parse(row[3]),
        session_id=TradingSessionId.parse(row[4]),
        timeframe=BarTimeframe(str(row[5])),
        price_basis=PriceBasis(str(row[6])),
        event_start=row[7],
        event_end=row[8],
        revision=int(row[9]),
        supersedes_revision_id=UUID(str(row[10])) if row[10] is not None else None,
        open=Money(Decimal(row[11]), str(row[17])),
        high=Money(Decimal(row[12]), str(row[17])),
        low=Money(Decimal(row[13]), str(row[17])),
        close=Money(Decimal(row[14]), str(row[17])),
        volume=Quantity(Decimal(row[15]), QuantityUnit.SHARES),
        turnover=Money(Decimal(row[16]), str(row[17])) if row[16] is not None else None,
    )


def _session(row: tuple[Any, ...]) -> TradingSession:
    return TradingSession(
        session_id=TradingSessionId.parse(row[0]),
        exchange=str(row[1]),
        session_date=row[2],
        timezone_name=str(row[3]),
        open_at=row[4],
        break_start_at=row[5],
        break_end_at=row[6],
        close_at=row[7],
        decision_reference_at=row[8],
        source_capture_id=UUID(str(row[9])),
    )


def _source_gap(row: tuple[Any, ...]) -> SourceGap:
    return SourceGap(
        gap_id=UUID(str(row[0])),
        provider_product_id=UUID(str(row[1])),
        capture_id=UUID(str(row[2])),
        instrument_id=InstrumentId.parse(row[3]) if row[3] is not None else None,
        session_id=TradingSessionId.parse(row[4]) if row[4] is not None else None,
        instrument_code=str(row[5]) if row[5] is not None else None,
        identifier_scheme=str(row[6]) if row[6] is not None else None,
        identifier_value=str(row[7]) if row[7] is not None else None,
        exchange=str(row[8]) if row[8] is not None else None,
        session_date=row[9],
        classification_scheme=str(row[10]) if row[10] is not None else None,
        classification_code=str(row[11]) if row[11] is not None else None,
        action_key=str(row[12]) if row[12] is not None else None,
        gap_kind=GapKind(str(row[13])),
        reason_code=GapReasonCode(str(row[14])),
        fact_kind=GapFactKind(str(row[15])),
        instrument_fact_kind=InstrumentFactKind(str(row[16])) if row[16] is not None else None,
        evidence_scope=EvidenceScope(str(row[17])) if row[17] is not None else None,
        timeframe=BarTimeframe(str(row[18])) if row[18] is not None else None,
        price_basis=PriceBasis(str(row[19])) if row[19] is not None else None,
        event_start=row[20],
        event_end=row[21],
        effective_from=row[22],
        effective_to=row[23],
        detail=str(row[24]) if row[24] is not None else None,
    )


def _decision_time(value: DecisionTime | datetime) -> DecisionTime:
    return value if isinstance(value, DecisionTime) else DecisionTime(value)
