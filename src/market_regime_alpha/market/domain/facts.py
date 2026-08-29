"""Typed Market bar, instrument, lifecycle, and corporate-action facts."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.market.domain.vocabulary import (
    BarTimeframe,
    CorporateActionType,
    EvidenceScope,
    InstrumentFactKind,
    ListingStatus,
    NumericInstrumentFactKind,
    PriceBasis,
    SecurityStatus,
    SpecialTreatmentStatus,
)
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit, bounded_decimal
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import require_utc


@dataclass(frozen=True, slots=True)
class MarketBarRevision:
    bar_revision_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: InstrumentId
    session_id: TradingSessionId
    timeframe: BarTimeframe
    price_basis: PriceBasis
    event_start: datetime
    event_end: datetime
    revision: int
    supersedes_revision_id: UUID | None
    open: Money
    high: Money
    low: Money
    close: Money
    volume: Quantity
    turnover: Money | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        object.__setattr__(self, "session_id", TradingSessionId.parse(self.session_id))
        if not isinstance(self.timeframe, BarTimeframe):
            raise TypeError("timeframe must be BarTimeframe")
        if not isinstance(self.price_basis, PriceBasis):
            raise TypeError("price_basis must be PriceBasis")
        object.__setattr__(self, "event_start", require_utc(self.event_start, field="event_start"))
        object.__setattr__(self, "event_end", require_utc(self.event_end, field="event_end"))
        if self.event_end <= self.event_start:
            raise ValueError("bar event interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_revision_id is None):
            raise ValueError("market-bar revision chain is incomplete")
        if any(not isinstance(value, Money) for value in (self.open, self.high, self.low, self.close)):
            raise TypeError("bar OHLC values must be Money")
        if not isinstance(self.volume, Quantity):
            raise TypeError("bar volume must be Quantity")
        if self.turnover is not None and not isinstance(self.turnover, Money):
            raise TypeError("bar turnover must be Money when present")
        currencies = {value.currency for value in (self.open, self.high, self.low, self.close)}
        if len(currencies) != 1 or (self.turnover is not None and self.turnover.currency not in currencies):
            raise ValueError("bar money values must use one instrument currency")
        if self.volume.unit is not QuantityUnit.SHARES:
            raise ValueError("bar volume must use SHARES")
        prices = tuple(value.amount for value in (self.open, self.high, self.low, self.close))
        if min(prices) <= 0:
            raise ValueError("bar must contain positive legal OHLC")
        if self.high.amount < max(self.open.amount, self.close.amount, self.low.amount) or self.low.amount > min(
            self.open.amount, self.close.amount, self.high.amount
        ):
            raise ValueError("bar must contain legal OHLC")
        if self.volume.amount < 0 or (self.turnover is not None and self.turnover.amount < 0):
            raise ValueError("volume and turnover cannot be negative")

    @property
    def logical_series_key(
        self,
    ) -> tuple[UUID, InstrumentId, BarTimeframe, PriceBasis]:
        return (
            self.provider_product_id,
            self.instrument_id,
            self.timeframe,
            self.price_basis,
        )


@dataclass(frozen=True, slots=True)
class SecurityStatusFactRevision:
    fact_revision_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: InstrumentId
    session_id: TradingSessionId
    evidence_scope: EvidenceScope
    status: SecurityStatus
    event_start: datetime
    event_end: datetime
    revision: int
    supersedes_revision_id: UUID | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        object.__setattr__(self, "session_id", TradingSessionId.parse(self.session_id))
        if not isinstance(self.evidence_scope, EvidenceScope) or self.evidence_scope not in {
            EvidenceScope.DECISION_SESSION,
            EvidenceScope.PRIOR_SESSION,
        }:
            raise ValueError("security status scope must identify decision or prior session")
        if not isinstance(self.status, SecurityStatus):
            raise TypeError("status must be SecurityStatus")
        object.__setattr__(self, "event_start", require_utc(self.event_start, field="event_start"))
        object.__setattr__(self, "event_end", require_utc(self.event_end, field="event_end"))
        if self.event_end <= self.event_start:
            raise ValueError("fact event interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_revision_id is None):
            raise ValueError("security-status revision chain is incomplete")


@dataclass(frozen=True, slots=True)
class InstrumentFactRevision:
    fact_revision_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: InstrumentId
    session_id: TradingSessionId | None
    fact_kind: NumericInstrumentFactKind
    evidence_scope: EvidenceScope
    event_start: datetime
    event_end: datetime | None
    value: Money | Quantity
    revision: int
    supersedes_revision_id: UUID | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        if self.session_id is not None:
            object.__setattr__(
                self,
                "session_id",
                TradingSessionId.parse(self.session_id),
            )
        if not isinstance(self.fact_kind, NumericInstrumentFactKind):
            raise TypeError("fact_kind must be NumericInstrumentFactKind")
        if not isinstance(self.evidence_scope, EvidenceScope):
            raise TypeError("evidence_scope must be EvidenceScope")
        if self.evidence_scope is not EvidenceScope.EFFECTIVE_INTERVAL and self.session_id is None:
            raise ValueError("session-scoped fact requires session_id")
        object.__setattr__(self, "event_start", require_utc(self.event_start, field="event_start"))
        if self.event_end is not None:
            object.__setattr__(
                self,
                "event_end",
                require_utc(self.event_end, field="event_end"),
            )
        if self.event_end is not None and self.event_end <= self.event_start:
            raise ValueError("fact event interval must be positive")
        if self.fact_kind in {
            NumericInstrumentFactKind.TOTAL_SHARES,
            NumericInstrumentFactKind.FREE_FLOAT_SHARES,
        }:
            if (
                not isinstance(self.value, Quantity)
                or self.value.amount < 0
                or self.value.unit is not QuantityUnit.SHARES
                or self.evidence_scope is not EvidenceScope.EFFECTIVE_INTERVAL
                or self.session_id is not None
            ):
                raise ValueError("share facts require non-negative Quantity(SHARES) over an effective interval")
        elif self.fact_kind in {
            NumericInstrumentFactKind.LIMIT_UP_PRICE,
            NumericInstrumentFactKind.LIMIT_DOWN_PRICE,
            NumericInstrumentFactKind.REFERENCE_PRICE,
        }:
            if (
                not isinstance(self.value, Money)
                or self.value.amount <= 0
                or self.evidence_scope not in {EvidenceScope.DECISION_SESSION, EvidenceScope.PRIOR_SESSION}
                or self.session_id is None
                or self.event_end is None
            ):
                raise ValueError("price facts require positive Money and an exact Session scope")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_revision_id is None):
            raise ValueError("instrument-fact revision chain is incomplete")

    @property
    def numeric_value(self) -> Decimal:
        return self.value.amount

    @property
    def unit_code(self) -> str:
        if isinstance(self.value, Money):
            return self.value.currency
        return self.value.unit.value


@dataclass(frozen=True, slots=True)
class InstrumentLifecycleFactRevision:
    """Effective-dated listing or special-treatment Authority fact."""

    fact_revision_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: InstrumentId
    fact_kind: InstrumentFactKind
    status: ListingStatus | SpecialTreatmentStatus
    effective_from: datetime
    effective_to: datetime | None
    revision: int
    supersedes_revision_id: UUID | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        valid_status_type = {
            InstrumentFactKind.LISTING_STATUS: ListingStatus,
            InstrumentFactKind.SPECIAL_TREATMENT_STATUS: SpecialTreatmentStatus,
        }.get(self.fact_kind)
        if valid_status_type is None or not isinstance(self.status, valid_status_type):
            raise ValueError("lifecycle status does not match its instrument fact kind")
        object.__setattr__(
            self,
            "effective_from",
            require_utc(self.effective_from, field="effective_from"),
        )
        if self.effective_to is not None:
            object.__setattr__(
                self,
                "effective_to",
                require_utc(self.effective_to, field="effective_to"),
            )
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("lifecycle effective interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_revision_id is None):
            raise ValueError("lifecycle-status revision chain is incomplete")


@dataclass(frozen=True, slots=True)
class CorporateActionRevision:
    corporate_action_revision_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: InstrumentId
    action_key: str
    action_type: CorporateActionType
    ex_session_id: TradingSessionId
    record_session_id: TradingSessionId | None
    pay_session_id: TradingSessionId | None
    cash_amount_per_share: Money | None
    ratio_factor: Decimal | None
    subscription_price: Money | None
    revision: int
    supersedes_revision_id: UUID | None
    successor_instrument_id: InstrumentId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        object.__setattr__(
            self,
            "ex_session_id",
            TradingSessionId.parse(self.ex_session_id),
        )
        for field_name in ("record_session_id", "pay_session_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, TradingSessionId.parse(value))
        if self.successor_instrument_id is not None:
            object.__setattr__(
                self,
                "successor_instrument_id",
                InstrumentId.parse(self.successor_instrument_id),
            )
            if self.successor_instrument_id == self.instrument_id:
                raise ValueError("conversion successor must differ from source Instrument")
        if not self.action_key:
            raise ValueError("action_key is required")
        if not isinstance(self.action_type, CorporateActionType):
            raise TypeError("action_type must be CorporateActionType")
        if self.cash_amount_per_share is not None and not isinstance(
            self.cash_amount_per_share,
            Money,
        ):
            raise TypeError("cash_amount_per_share must be Money when present")
        if self.subscription_price is not None and not isinstance(
            self.subscription_price,
            Money,
        ):
            raise TypeError("subscription_price must be Money when present")
        if self.ratio_factor is not None:
            object.__setattr__(
                self,
                "ratio_factor",
                bounded_decimal(
                    self.ratio_factor,
                    field="ratio_factor",
                    precision=30,
                    scale=12,
                ),
            )
        if self.cash_amount_per_share is not None and self.cash_amount_per_share.amount < 0:
            raise ValueError("cash_amount_per_share cannot be negative")
        if self.ratio_factor is not None and self.ratio_factor <= 0:
            raise ValueError("ratio_factor must be positive")
        if self.subscription_price is not None and self.subscription_price.amount <= 0:
            raise ValueError("subscription_price must be positive")
        if (
            self.cash_amount_per_share is not None
            and self.subscription_price is not None
            and self.cash_amount_per_share.currency != self.subscription_price.currency
        ):
            raise ValueError("corporate-action money values must use one currency")
        valid_values = {
            CorporateActionType.CASH_DIVIDEND: (
                self.cash_amount_per_share is not None and self.ratio_factor is None and self.subscription_price is None
            ),
            CorporateActionType.STOCK_DIVIDEND: (
                self.cash_amount_per_share is None and self.ratio_factor is not None and self.subscription_price is None
            ),
            CorporateActionType.SPLIT: (
                self.cash_amount_per_share is None and self.ratio_factor is not None and self.subscription_price is None
            ),
            CorporateActionType.RIGHTS_ISSUE: (
                self.cash_amount_per_share is None
                and self.ratio_factor is not None
                and self.subscription_price is not None
                and self.successor_instrument_id is None
            ),
            CorporateActionType.CONVERSION: (
                self.cash_amount_per_share is None
                and self.ratio_factor is not None
                and self.subscription_price is None
                and self.successor_instrument_id is not None
            ),
            CorporateActionType.MERGER: (
                self.cash_amount_per_share is None
                and self.ratio_factor is not None
                and self.subscription_price is None
                and self.successor_instrument_id is not None
            ),
        }[self.action_type]
        if (
            self.action_type
            not in {
                CorporateActionType.CONVERSION,
                CorporateActionType.MERGER,
            }
            and self.successor_instrument_id is not None
        ):
            raise ValueError("only conversion or merger carries a successor Instrument")
        if not valid_values:
            raise ValueError("corporate-action values do not match action_type")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_revision_id is None):
            raise ValueError("corporate-action revision chain is incomplete")

    @property
    def currency(self) -> str | None:
        money = self.cash_amount_per_share or self.subscription_price
        return money.currency if money is not None else None
