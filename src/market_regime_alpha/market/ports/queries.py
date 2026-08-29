"""Generic exact/as-of Market/PIT query ports."""

from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.market.domain import (
    BarTimeframe,
    ClassificationMembersResult,
    CorporateActionRevision,
    EvidenceScope,
    GapFactKind,
    InstrumentFactKind,
    InstrumentFactRevision,
    ListingStatus,
    MarketBarRevision,
    NumericInstrumentFactKind,
    PriceBasis,
    SecurityStatus,
    SourceGap,
    SpecialTreatmentStatus,
    TradingSession,
)
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import DecisionTime


class MarketQueries(Protocol):
    def exact_bar_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        timeframe: BarTimeframe,
        price_basis: PriceBasis,
        event_start: datetime,
        event_end: datetime,
        decision_time: DecisionTime,
    ) -> MarketBarRevision | None: ...

    def trading_session_as_of(self, *, exchange: str, session_date: date, decision_time: DecisionTime) -> TradingSession | None: ...

    def instrument_for_identifier_as_of(
        self, *, identifier_scheme: str, identifier_value: str, effective_time: datetime, decision_time: DecisionTime
    ) -> InstrumentId | None: ...

    def classification_members_as_of(
        self, *, classification_scheme: str, classification_code: str, effective_time: datetime, decision_time: DecisionTime
    ) -> ClassificationMembersResult: ...

    def security_status_as_of(
        self, *, instrument_id: InstrumentId, session_id: TradingSessionId, evidence_scope: EvidenceScope, decision_time: DecisionTime
    ) -> SecurityStatus | None: ...

    def instrument_fact_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        fact_kind: NumericInstrumentFactKind,
        evidence_scope: EvidenceScope,
        event_time: datetime,
        decision_time: DecisionTime,
        session_id: TradingSessionId | None = None,
    ) -> InstrumentFactRevision | None: ...

    def listing_status_as_of(
        self, *, instrument_id: InstrumentId, effective_time: datetime, decision_time: DecisionTime
    ) -> ListingStatus | None: ...

    def special_treatment_status_as_of(
        self, *, instrument_id: InstrumentId, effective_time: datetime, decision_time: DecisionTime
    ) -> SpecialTreatmentStatus | None: ...

    def corporate_actions_as_of(
        self, *, instrument_id: InstrumentId, ex_session_id: TradingSessionId, decision_time: DecisionTime
    ) -> tuple[CorporateActionRevision, ...]: ...

    def source_gaps_as_of(
        self,
        *,
        decision_time: DecisionTime,
        capture_id: UUID | None = None,
        fact_kind: GapFactKind | None = None,
        instrument_id: InstrumentId | None = None,
        session_id: TradingSessionId | None = None,
        instrument_code: str | None = None,
        identifier_scheme: str | None = None,
        identifier_value: str | None = None,
        exchange: str | None = None,
        session_date: date | None = None,
        classification_scheme: str | None = None,
        classification_code: str | None = None,
        instrument_fact_kind: InstrumentFactKind | None = None,
        evidence_scope: EvidenceScope | None = None,
        action_key: str | None = None,
    ) -> tuple[SourceGap, ...]: ...


class MarketQueryProvider(Protocol):
    def for_provider_product(self, provider_product_id: UUID) -> MarketQueries: ...
