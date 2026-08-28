"""Market/PIT domain values and invariants with no infrastructure dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from market_regime_alpha.shared.identity import (
    ContentHash,
    InstrumentId,
    TradingSessionId,
)
from market_regime_alpha.shared.financial import (
    Money,
    Quantity,
    QuantityUnit,
    bounded_decimal,
)
from market_regime_alpha.shared.time import DecisionTime, KnownTime, require_utc


_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")
_CAPTURE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class PriceBasis(StrEnum):
    RAW_UNADJUSTED = "RAW_UNADJUSTED"
    FORWARD_ADJUSTED = "FORWARD_ADJUSTED"
    BACKWARD_ADJUSTED = "BACKWARD_ADJUSTED"


class ProviderKind(StrEnum):
    PUBLIC_ENDPOINT = "PUBLIC_ENDPOINT"
    DATA_VENDOR = "DATA_VENDOR"
    BROKER_FEED = "BROKER_FEED"


class InstrumentType(StrEnum):
    EQUITY = "EQUITY"
    ETF = "ETF"
    INDEX = "INDEX"
    FUND = "FUND"
    BOND = "BOND"


class MembershipStatus(StrEnum):
    MEMBER = "MEMBER"
    NOT_MEMBER = "NOT_MEMBER"


class ClassificationEvidenceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"


class EvidenceScope(StrEnum):
    DECISION_SESSION = "DECISION_SESSION"
    PRIOR_SESSION = "PRIOR_SESSION"
    EFFECTIVE_INTERVAL = "EFFECTIVE_INTERVAL"


class CorporateActionType(StrEnum):
    CASH_DIVIDEND = "CASH_DIVIDEND"
    STOCK_DIVIDEND = "STOCK_DIVIDEND"
    SPLIT = "SPLIT"
    RIGHTS_ISSUE = "RIGHTS_ISSUE"
    CONVERSION = "CONVERSION"
    MERGER = "MERGER"


class MarketFactKind(StrEnum):
    INSTRUMENT = "INSTRUMENT"
    INSTRUMENT_IDENTIFIER = "INSTRUMENT_IDENTIFIER"
    TRADING_SESSION = "TRADING_SESSION"
    CLASSIFICATION = "CLASSIFICATION"
    CLASSIFICATION_MEMBERSHIP = "CLASSIFICATION_MEMBERSHIP"
    MARKET_BAR = "MARKET_BAR"
    INSTRUMENT_FACT = "INSTRUMENT_FACT"
    CORPORATE_ACTION = "CORPORATE_ACTION"


class InstrumentFactKind(StrEnum):
    SECURITY_STATUS = "SECURITY_STATUS"
    LISTING_STATUS = "LISTING_STATUS"
    SPECIAL_TREATMENT_STATUS = "SPECIAL_TREATMENT_STATUS"
    TOTAL_SHARES = "TOTAL_SHARES"
    FREE_FLOAT_SHARES = "FREE_FLOAT_SHARES"
    LIMIT_UP_PRICE = "LIMIT_UP_PRICE"
    LIMIT_DOWN_PRICE = "LIMIT_DOWN_PRICE"
    REFERENCE_PRICE = "REFERENCE_PRICE"


class NumericInstrumentFactKind(StrEnum):
    TOTAL_SHARES = "TOTAL_SHARES"
    FREE_FLOAT_SHARES = "FREE_FLOAT_SHARES"
    LIMIT_UP_PRICE = "LIMIT_UP_PRICE"
    LIMIT_DOWN_PRICE = "LIMIT_DOWN_PRICE"
    REFERENCE_PRICE = "REFERENCE_PRICE"


class GapFactKind(StrEnum):
    DATA_CAPTURE = "DATA_CAPTURE"
    INSTRUMENT = "INSTRUMENT"
    INSTRUMENT_IDENTIFIER = "INSTRUMENT_IDENTIFIER"
    TRADING_SESSION = "TRADING_SESSION"
    CLASSIFICATION = "CLASSIFICATION"
    CLASSIFICATION_MEMBERSHIP = "CLASSIFICATION_MEMBERSHIP"
    MARKET_BAR = "MARKET_BAR"
    INSTRUMENT_FACT = "INSTRUMENT_FACT"
    CORPORATE_ACTION = "CORPORATE_ACTION"


class GapReasonCode(StrEnum):
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    NO_ROWS_RETURNED = "NO_ROWS_RETURNED"
    EXPECTED_OBSERVATION_MISSING = "EXPECTED_OBSERVATION_MISSING"
    EXACT_BAR_MISSING = "EXACT_BAR_MISSING"
    NULL_OHLC_PLACEHOLDER = "NULL_OHLC_PLACEHOLDER"
    CONFLICTING_SOURCE_REVISIONS = "CONFLICTING_SOURCE_REVISIONS"
    INVALID_OHLC = "INVALID_OHLC"


class BarTimeframe(StrEnum):
    MINUTE_1 = "MINUTE_1"
    MINUTE_5 = "MINUTE_5"
    MINUTE_15 = "MINUTE_15"
    MINUTE_30 = "MINUTE_30"
    MINUTE_60 = "MINUTE_60"
    DAILY = "DAILY"


class CaptureStatus(StrEnum):
    CAPTURED = "CAPTURED"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"


class SourceAvailabilityStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    PROVIDER_REPORTED = "PROVIDER_REPORTED"


class GapKind(StrEnum):
    MISSING = "MISSING"
    PLACEHOLDER = "PLACEHOLDER"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    CONFLICT = "CONFLICT"
    INVALID_OHLC = "INVALID_OHLC"


class SecurityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class ListingStatus(StrEnum):
    PRE_LISTING = "PRE_LISTING"
    LISTED = "LISTED"
    DELISTED = "DELISTED"
    UNKNOWN = "UNKNOWN"


class SpecialTreatmentStatus(StrEnum):
    NORMAL = "NORMAL"
    ST = "ST"
    STAR_ST = "STAR_ST"
    UNKNOWN = "UNKNOWN"


class DecisionReferenceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class DecisionReferenceReason(StrEnum):
    TRADING_SESSION_MISSING = "TRADING_SESSION_MISSING"
    CURRENT_SESSION_SUSPENDED = "CURRENT_SESSION_SUSPENDED"
    EXACT_RAW_1455_BAR_MISSING = "EXACT_RAW_1455_BAR_MISSING"
    DECISION_REFERENCE_NOT_EXACT_RAW_SAME_SESSION_1455 = (
        "DECISION_REFERENCE_NOT_EXACT_RAW_SAME_SESSION_1455"
    )
    EXACT_RAW_SAME_SESSION_1455 = "EXACT_RAW_SAME_SESSION_1455"


@dataclass(frozen=True, slots=True)
class Provider:
    provider_id: UUID
    provider_code: str
    display_name: str
    provider_kind: ProviderKind

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}", self.provider_code):
            raise ValueError("provider_code has an invalid format")
        if not self.display_name:
            raise ValueError("display_name is required")
        if not isinstance(self.provider_kind, ProviderKind):
            raise TypeError("provider_kind must be ProviderKind")


@dataclass(frozen=True, slots=True)
class ProviderProduct:
    provider_product_id: UUID
    provider_id: UUID
    product_code: str
    revision: int
    payload_family: str
    media_type: str
    payload_encoding: str
    source_availability_policy: SourceAvailabilityStatus
    fact_kinds: tuple[MarketFactKind, ...]
    instrument_fact_kinds: tuple[InstrumentFactKind, ...]
    bar_timeframes: tuple[BarTimeframe, ...]
    price_bases: tuple[PriceBasis, ...]
    supersedes_provider_product_id: UUID | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", self.product_code):
            raise ValueError("product_code has an invalid format")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_provider_product_id is None):
            raise ValueError("product revision chain is incomplete")
        if not _CODE.fullmatch(self.payload_family):
            raise ValueError("payload_family has an invalid format")
        if not self.media_type or not self.payload_encoding:
            raise ValueError("payload media type and encoding are required")
        if not isinstance(
            self.source_availability_policy,
            SourceAvailabilityStatus,
        ):
            raise TypeError(
                "source_availability_policy must be SourceAvailabilityStatus"
            )
        if not self.fact_kinds or any(
            not isinstance(item, MarketFactKind) for item in self.fact_kinds
        ):
            raise TypeError("fact_kinds must contain typed MarketFactKind values")
        if len(set(self.fact_kinds)) != len(self.fact_kinds):
            raise ValueError("fact_kinds cannot contain duplicates")
        if any(
            not isinstance(item, InstrumentFactKind)
            for item in self.instrument_fact_kinds
        ):
            raise TypeError(
                "instrument_fact_kinds must contain typed InstrumentFactKind values"
            )
        if len(set(self.instrument_fact_kinds)) != len(self.instrument_fact_kinds):
            raise ValueError("instrument_fact_kinds cannot contain duplicates")
        if any(not isinstance(item, BarTimeframe) for item in self.bar_timeframes):
            raise TypeError("bar_timeframes must contain typed BarTimeframe values")
        if len(set(self.bar_timeframes)) != len(self.bar_timeframes):
            raise ValueError("bar_timeframes cannot contain duplicates")
        if any(not isinstance(item, PriceBasis) for item in self.price_bases):
            raise TypeError("price_bases must contain typed PriceBasis values")
        if len(set(self.price_bases)) != len(self.price_bases):
            raise ValueError("price_bases cannot contain duplicates")
        carries_bars = MarketFactKind.MARKET_BAR in self.fact_kinds
        if carries_bars != bool(self.bar_timeframes) or carries_bars != bool(
            self.price_bases
        ):
            raise ValueError(
                "MARKET_BAR products require explicit timeframe and price-basis capabilities"
            )
        carries_instrument_facts = MarketFactKind.INSTRUMENT_FACT in self.fact_kinds
        if carries_instrument_facts != bool(self.instrument_fact_kinds):
            raise ValueError(
                "INSTRUMENT_FACT products require explicit fact-kind capabilities"
            )


@dataclass(frozen=True, slots=True)
class Instrument:
    instrument_id: InstrumentId
    canonical_code: str
    exchange: str
    instrument_type: InstrumentType
    currency: str
    source_capture_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,31}", self.canonical_code):
            raise ValueError("canonical_code has an invalid format")
        if not re.fullmatch(r"[A-Z][A-Z0-9]{1,15}", self.exchange):
            raise ValueError("exchange has an invalid format")
        if not isinstance(self.instrument_type, InstrumentType):
            raise TypeError("instrument_type must be InstrumentType")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("currency must be an ISO-style three-letter code")


@dataclass(frozen=True, slots=True)
class InstrumentIdentifier:
    instrument_identifier_id: UUID
    instrument_id: InstrumentId
    identifier_scheme: str
    identifier_value: str
    effective_from: datetime
    effective_to: datetime | None
    revision: int
    supersedes_identifier_id: UUID | None
    source_capture_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", self.identifier_scheme):
            raise ValueError("identifier_scheme has an invalid format")
        if not self.identifier_value:
            raise ValueError("identifier_value is required")
        object.__setattr__(self, "effective_from", require_utc(self.effective_from, field="effective_from"))
        if self.effective_to is not None:
            object.__setattr__(self, "effective_to", require_utc(self.effective_to, field="effective_to"))
            if self.effective_to <= self.effective_from:
                raise ValueError("identifier effective interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_identifier_id is None):
            raise ValueError("identifier revision chain is incomplete")


@dataclass(frozen=True, slots=True)
class ClassificationRevision:
    classification_id: UUID
    classification_scheme: str
    classification_code: str
    display_name: str
    revision: int
    effective_from: datetime
    effective_to: datetime | None
    supersedes_classification_id: UUID | None
    source_capture_id: UUID

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", self.classification_scheme):
            raise ValueError("classification_scheme has an invalid format")
        if not self.classification_code or not self.display_name:
            raise ValueError("classification code and name are required")
        object.__setattr__(self, "effective_from", require_utc(self.effective_from, field="effective_from"))
        if self.effective_to is not None:
            object.__setattr__(self, "effective_to", require_utc(self.effective_to, field="effective_to"))
            if self.effective_to <= self.effective_from:
                raise ValueError("classification effective interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_classification_id is None):
            raise ValueError("classification revision chain is incomplete")


@dataclass(frozen=True, slots=True)
class ClassificationMembershipRevision:
    membership_revision_id: UUID
    classification_id: UUID
    instrument_id: InstrumentId
    source_capture_id: UUID
    membership_status: MembershipStatus
    effective_from: datetime
    effective_to: datetime | None
    revision: int
    supersedes_membership_revision_id: UUID | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        if not isinstance(self.membership_status, MembershipStatus):
            raise TypeError("membership_status must be MembershipStatus")
        object.__setattr__(self, "effective_from", require_utc(self.effective_from, field="effective_from"))
        if self.effective_to is not None:
            object.__setattr__(self, "effective_to", require_utc(self.effective_to, field="effective_to"))
            if self.effective_to <= self.effective_from:
                raise ValueError("membership effective interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_membership_revision_id is None):
            raise ValueError("membership revision chain is incomplete")


@dataclass(frozen=True, slots=True)
class ClassificationMembersResult:
    """Distinguish verified empty membership from absent Classification evidence."""

    status: ClassificationEvidenceStatus
    members: tuple[InstrumentId, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, ClassificationEvidenceStatus):
            raise TypeError("status must be ClassificationEvidenceStatus")
        object.__setattr__(
            self,
            "members",
            tuple(InstrumentId.parse(item) for item in self.members),
        )
        if self.status is ClassificationEvidenceStatus.MISSING and self.members:
            raise ValueError("missing Classification evidence cannot contain members")


def require_capture_key(value: str) -> str:
    """Validate the canonical Provider observation correlation key."""

    if not _CAPTURE_KEY.fullmatch(value):
        raise ValueError("capture_key has an invalid format")
    return value


@dataclass(frozen=True, slots=True)
class TemporalEnvelope:
    """Independent source/capture/knowledge axes for one immutable Capture."""

    provider_time: datetime | None
    source_availability_status: SourceAvailabilityStatus
    source_available_at: datetime | None
    capture_started_at: datetime
    capture_completed_at: datetime
    known_at: KnownTime
    decision_visible_at: DecisionTime

    def __post_init__(self) -> None:
        if not isinstance(self.source_availability_status, SourceAvailabilityStatus):
            raise TypeError(
                "source_availability_status must be SourceAvailabilityStatus"
            )
        for field_name in (
            "provider_time",
            "source_available_at",
            "capture_started_at",
            "capture_completed_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    require_utc(value, field=field_name),
                )
        object.__setattr__(
            self,
            "known_at",
            self.known_at
            if isinstance(self.known_at, KnownTime)
            else KnownTime(self.known_at),
        )
        object.__setattr__(
            self,
            "decision_visible_at",
            self.decision_visible_at
            if isinstance(self.decision_visible_at, DecisionTime)
            else DecisionTime(self.decision_visible_at),
        )
        if self.source_availability_status is SourceAvailabilityStatus.UNKNOWN:
            if self.source_available_at is not None:
                raise ValueError("UNKNOWN source availability cannot carry a timestamp")
        elif self.source_available_at is None:
            raise ValueError("PROVIDER_REPORTED source availability needs a timestamp")
        if (
            self.source_available_at is not None
            and self.source_available_at > self.known_at.value
        ):
            raise ValueError("source_available_at cannot follow known_at")
        if self.capture_completed_at < self.capture_started_at:
            raise ValueError("capture_completed_at cannot precede capture_started_at")
        if self.known_at.value < self.capture_completed_at:
            raise ValueError("known_at cannot precede completed capture")
        if self.decision_visible_at.value != self.known_at.value:
            raise ValueError(
                "unqualified Provider decision_visible_at must equal known_at"
            )


@dataclass(frozen=True, slots=True)
class ProviderCapture:
    capture_id: UUID
    provider_product_id: UUID
    capture_key: str
    request_hash: ContentHash
    status: CaptureStatus
    temporal: TemporalEnvelope
    artifact_id: UUID | None
    error_code: str | None
    limitation_code: str | None
    payload_encoding: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, CaptureStatus):
            raise TypeError("status must be CaptureStatus")
        require_capture_key(self.capture_key)
        object.__setattr__(
            self,
            "request_hash",
            self.request_hash
            if isinstance(self.request_hash, ContentHash)
            else ContentHash(self.request_hash),
        )
        for field_name in ("error_code", "limitation_code"):
            value = getattr(self, field_name)
            if value is not None and not _CODE.fullmatch(value):
                raise ValueError(f"{field_name} has an invalid format")
        if self.status is CaptureStatus.CAPTURED:
            if (
                self.artifact_id is None
                or self.error_code is not None
                or not self.payload_encoding
            ):
                raise ValueError("CAPTURED requires an Artifact, encoding, and no error")
        else:
            if self.error_code is None:
                raise ValueError("PROVIDER_FAILURE requires a typed error_code")
            if (
                self.temporal.source_availability_status
                is not SourceAvailabilityStatus.UNKNOWN
                or self.temporal.source_available_at is not None
            ):
                raise ValueError(
                    "PROVIDER_FAILURE cannot assert source availability evidence"
                )


@dataclass(frozen=True, slots=True)
class TradingSession:
    session_id: TradingSessionId
    exchange: str
    session_date: date
    timezone_name: str
    open_at: datetime
    break_start_at: datetime | None
    break_end_at: datetime | None
    close_at: datetime
    decision_reference_at: datetime
    source_capture_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", TradingSessionId.parse(self.session_id))
        if not self.exchange:
            raise ValueError("exchange is required")
        if self.timezone_name != "Asia/Shanghai":
            raise ValueError("A-share TradingSession timezone must be Asia/Shanghai")
        try:
            exchange_zone = ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone_name is not an IANA timezone") from exc
        for field_name in (
            "open_at",
            "break_start_at",
            "break_end_at",
            "close_at",
            "decision_reference_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, require_utc(value, field=field_name))
        if (self.break_start_at is None) != (self.break_end_at is None):
            raise ValueError("session break boundaries must both be present or absent")
        boundaries = [self.open_at]
        if self.break_start_at is not None and self.break_end_at is not None:
            boundaries.extend((self.break_start_at, self.break_end_at))
        boundaries.append(self.close_at)
        if boundaries != sorted(boundaries) or len(set(boundaries)) != len(boundaries):
            raise ValueError("session boundaries must be strictly ordered")
        if not self.open_at < self.decision_reference_at <= self.close_at:
            raise ValueError("decision reference must fall within the same session")
        if any(
            boundary.astimezone(exchange_zone).date() != self.session_date
            for boundary in (self.open_at, self.close_at, self.decision_reference_at)
        ):
            raise ValueError("session boundaries must resolve to session_date")
        if self.decision_reference_at.astimezone(exchange_zone).time() != time(14, 55):
            raise ValueError("A-share decision_reference_at must be exact local 14:55")


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
        if any(
            not isinstance(value, Money)
            for value in (self.open, self.high, self.low, self.close)
        ):
            raise TypeError("bar OHLC values must be Money")
        if not isinstance(self.volume, Quantity):
            raise TypeError("bar volume must be Quantity")
        if self.turnover is not None and not isinstance(self.turnover, Money):
            raise TypeError("bar turnover must be Money when present")
        currencies = {value.currency for value in (self.open, self.high, self.low, self.close)}
        if len(currencies) != 1 or (
            self.turnover is not None and self.turnover.currency not in currencies
        ):
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
        if self.volume.amount < 0 or (
            self.turnover is not None and self.turnover.amount < 0
        ):
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
                raise ValueError(
                    "share facts require non-negative Quantity(SHARES) over an effective interval"
                )
        elif self.fact_kind in {
            NumericInstrumentFactKind.LIMIT_UP_PRICE,
            NumericInstrumentFactKind.LIMIT_DOWN_PRICE,
            NumericInstrumentFactKind.REFERENCE_PRICE,
        }:
            if (
                not isinstance(self.value, Money)
                or self.value.amount <= 0
                or self.evidence_scope
                not in {EvidenceScope.DECISION_SESSION, EvidenceScope.PRIOR_SESSION}
                or self.session_id is None
                or self.event_end is None
            ):
                raise ValueError(
                    "price facts require positive Money and an exact Session scope"
                )
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
        if (
            self.cash_amount_per_share is not None
            and self.cash_amount_per_share.amount < 0
        ):
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
                self.cash_amount_per_share is not None
                and self.ratio_factor is None
                and self.subscription_price is None
            ),
            CorporateActionType.STOCK_DIVIDEND: (
                self.cash_amount_per_share is None
                and self.ratio_factor is not None
                and self.subscription_price is None
            ),
            CorporateActionType.SPLIT: (
                self.cash_amount_per_share is None
                and self.ratio_factor is not None
                and self.subscription_price is None
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
        if self.action_type not in {
            CorporateActionType.CONVERSION,
            CorporateActionType.MERGER,
        } and self.successor_instrument_id is not None:
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


@dataclass(frozen=True, slots=True)
class SourceGap:
    gap_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: InstrumentId | None
    session_id: TradingSessionId | None
    gap_kind: GapKind
    reason_code: GapReasonCode
    fact_kind: GapFactKind
    instrument_fact_kind: InstrumentFactKind | None
    timeframe: BarTimeframe | None
    price_basis: PriceBasis | None
    event_start: datetime | None
    event_end: datetime | None
    detail: str | None
    evidence_scope: EvidenceScope | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    instrument_code: str | None = None
    identifier_scheme: str | None = None
    identifier_value: str | None = None
    exchange: str | None = None
    session_date: date | None = None
    classification_scheme: str | None = None
    classification_code: str | None = None
    action_key: str | None = None

    def __post_init__(self) -> None:
        if self.instrument_id is not None:
            object.__setattr__(
                self,
                "instrument_id",
                InstrumentId.parse(self.instrument_id),
            )
        if self.session_id is not None:
            object.__setattr__(
                self,
                "session_id",
                TradingSessionId.parse(self.session_id),
            )
        if not isinstance(self.gap_kind, GapKind):
            raise TypeError("gap_kind must be GapKind")
        if not isinstance(self.reason_code, GapReasonCode):
            raise TypeError("reason_code must be GapReasonCode")
        allowed_reasons = {
            GapKind.MISSING: {
                GapReasonCode.NO_ROWS_RETURNED,
                GapReasonCode.EXPECTED_OBSERVATION_MISSING,
                GapReasonCode.EXACT_BAR_MISSING,
            },
            GapKind.PLACEHOLDER: {GapReasonCode.NULL_OHLC_PLACEHOLDER},
            GapKind.PROVIDER_FAILURE: {GapReasonCode.PROVIDER_FAILURE},
            GapKind.CONFLICT: {GapReasonCode.CONFLICTING_SOURCE_REVISIONS},
            GapKind.INVALID_OHLC: {GapReasonCode.INVALID_OHLC},
        }[self.gap_kind]
        if self.reason_code not in allowed_reasons:
            raise ValueError("reason_code is incompatible with gap_kind")
        if not isinstance(self.fact_kind, GapFactKind):
            raise TypeError("fact_kind must be GapFactKind")
        if self.instrument_fact_kind is not None and not isinstance(
            self.instrument_fact_kind,
            InstrumentFactKind,
        ):
            raise TypeError(
                "instrument_fact_kind must be InstrumentFactKind when present"
            )
        if (self.fact_kind is GapFactKind.INSTRUMENT_FACT) != (
            self.instrument_fact_kind is not None
        ):
            raise ValueError(
                "instrument-fact gaps require one exact instrument_fact_kind"
            )
        if self.timeframe is not None and not isinstance(self.timeframe, BarTimeframe):
            raise TypeError("timeframe must be BarTimeframe when present")
        if self.price_basis is not None and not isinstance(
            self.price_basis,
            PriceBasis,
        ):
            raise TypeError("price_basis must be PriceBasis when present")
        if self.event_start is None and self.event_end is not None:
            raise ValueError("gap event_end requires event_start")
        if self.event_start is not None:
            object.__setattr__(
                self,
                "event_start",
                require_utc(self.event_start, field="event_start"),
            )
        if self.event_end is not None:
            object.__setattr__(
                self,
                "event_end",
                require_utc(self.event_end, field="event_end"),
            )
        if self.event_start is not None and self.event_end is not None:
            if self.event_end <= self.event_start:
                raise ValueError("gap event interval must be positive")
        if self.effective_from is None and self.effective_to is not None:
            raise ValueError("gap effective_to requires effective_from")
        if self.effective_from is not None:
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
        if self.effective_from is not None and self.effective_to is not None:
            if self.effective_to <= self.effective_from:
                raise ValueError("gap effective interval must be positive")
        if self.evidence_scope is not None and not isinstance(
            self.evidence_scope,
            EvidenceScope,
        ):
            raise TypeError("evidence_scope must be EvidenceScope when present")
        if (self.timeframe is None) != (self.price_basis is None):
            raise ValueError("bar gaps require both timeframe and price basis")
        if (self.fact_kind is GapFactKind.MARKET_BAR) != (
            self.timeframe is not None
        ):
            raise ValueError("only MARKET_BAR gaps carry timeframe and price basis")
        if self.fact_kind is GapFactKind.MARKET_BAR and (
            self.instrument_id is None
            or self.session_id is None
            or self.event_start is None
            or self.event_end is None
        ):
            raise ValueError(
                "MARKET_BAR gaps require exact Instrument, Session, and event interval"
            )
        if self.reason_code in {
            GapReasonCode.EXACT_BAR_MISSING,
            GapReasonCode.NULL_OHLC_PLACEHOLDER,
            GapReasonCode.INVALID_OHLC,
        } and self.fact_kind is not GapFactKind.MARKET_BAR:
            raise ValueError("OHLC and exact-bar reasons require a MARKET_BAR gap")
        for field_name, pattern in (
            ("instrument_code", r"[A-Z0-9][A-Z0-9._-]{0,31}"),
            ("identifier_scheme", r"[A-Z][A-Z0-9_]{0,31}"),
            ("exchange", r"[A-Z][A-Z0-9]{1,15}"),
            ("classification_scheme", r"[A-Z][A-Z0-9_]{0,31}"),
        ):
            value = getattr(self, field_name)
            if value is not None and not re.fullmatch(pattern, value):
                raise ValueError(f"{field_name} has an invalid format")
        for field_name in (
            "identifier_value",
            "classification_code",
            "action_key",
        ):
            value = getattr(self, field_name)
            if value is not None and not value:
                raise ValueError(f"{field_name} cannot be empty")
        session_fact_kinds = {
            InstrumentFactKind.SECURITY_STATUS,
            InstrumentFactKind.LIMIT_UP_PRICE,
            InstrumentFactKind.LIMIT_DOWN_PRICE,
            InstrumentFactKind.REFERENCE_PRICE,
        }
        effective_fact_kinds = {
            InstrumentFactKind.LISTING_STATUS,
            InstrumentFactKind.SPECIAL_TREATMENT_STATUS,
            InstrumentFactKind.TOTAL_SHARES,
            InstrumentFactKind.FREE_FLOAT_SHARES,
        }
        exact_scope = {
            GapFactKind.DATA_CAPTURE: not any(
                (
                    self.instrument_id,
                    self.session_id,
                    self.evidence_scope,
                    self.instrument_code,
                    self.identifier_scheme,
                    self.identifier_value,
                    self.exchange,
                    self.session_date,
                    self.classification_scheme,
                    self.classification_code,
                    self.action_key,
                    self.event_start,
                    self.effective_from,
                )
            ),
            GapFactKind.INSTRUMENT: (
                self.instrument_code is not None
                and self.instrument_id is None
                and self.session_id is None
                and self.evidence_scope is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.action_key is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is None
                and self.effective_to is None
            ),
            GapFactKind.INSTRUMENT_IDENTIFIER: (
                self.identifier_scheme is not None
                and self.identifier_value is not None
                and self.session_id is None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.exchange is None
                and self.session_date is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.action_key is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is not None
            ),
            GapFactKind.TRADING_SESSION: (
                self.exchange is not None
                and self.session_date is not None
                and self.session_id is None
                and self.instrument_id is None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.action_key is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is None
                and self.effective_to is None
            ),
            GapFactKind.CLASSIFICATION: (
                self.classification_scheme is not None
                and self.classification_code is not None
                and self.instrument_id is None
                and self.session_id is None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.action_key is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is not None
            ),
            GapFactKind.CLASSIFICATION_MEMBERSHIP: (
                self.classification_scheme is not None
                and self.classification_code is not None
                and self.instrument_id is not None
                and self.session_id is None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.action_key is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is not None
            ),
            GapFactKind.MARKET_BAR: (
                self.instrument_id is not None
                and self.session_id is not None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.action_key is None
                and self.event_start is not None
                and self.event_end is not None
                and self.effective_from is None
                and self.effective_to is None
            ),
            GapFactKind.INSTRUMENT_FACT: (
                self.instrument_id is not None
                and self.instrument_fact_kind is not None
                and self.evidence_scope is not None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.action_key is None
                and (
                    (
                        self.instrument_fact_kind in session_fact_kinds
                        and self.session_id is not None
                        and self.evidence_scope
                        in {
                            EvidenceScope.DECISION_SESSION,
                            EvidenceScope.PRIOR_SESSION,
                        }
                        and self.event_start is not None
                        and self.event_end is not None
                        and self.effective_from is None
                        and self.effective_to is None
                    )
                    or (
                        self.instrument_fact_kind in effective_fact_kinds
                        and self.session_id is None
                        and self.evidence_scope is EvidenceScope.EFFECTIVE_INTERVAL
                        and self.event_start is None
                        and self.event_end is None
                        and self.effective_from is not None
                    )
                )
            ),
            GapFactKind.CORPORATE_ACTION: (
                self.instrument_id is not None
                and self.session_id is not None
                and self.action_key is not None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is None
                and self.effective_to is None
            ),
        }[self.fact_kind]
        if not exact_scope:
            raise ValueError(f"{self.fact_kind.value} gap requires its exact typed scope")

    @property
    def disposition_key(self) -> tuple[object, ...]:
        """One Capture has one disposition for one exact expected fact."""

        return (
            self.capture_id,
            self.fact_kind,
            self.instrument_id,
            self.session_id,
            self.instrument_fact_kind,
            self.evidence_scope,
            self.timeframe,
            self.price_basis,
            self.event_start,
            self.event_end,
            self.effective_from,
            self.effective_to,
            self.instrument_code,
            self.identifier_scheme,
            self.identifier_value,
            self.exchange,
            self.session_date,
            self.classification_scheme,
            self.classification_code,
            self.action_key,
        )


class MarketEvidenceGapError(RuntimeError):
    """The current PIT disposition is a typed gap, not an older fact."""

    def __init__(self, gap: SourceGap) -> None:
        self.gap = gap
        super().__init__(
            f"{gap.fact_kind.value} evidence is {gap.gap_kind.value}: "
            f"{gap.reason_code.value}"
        )


@dataclass(frozen=True, slots=True)
class NormalizationBatch:
    source_capture_id: UUID
    source_provider_product_id: UUID
    instruments: tuple[Instrument, ...] = ()
    instrument_identifiers: tuple[InstrumentIdentifier, ...] = ()
    trading_sessions: tuple[TradingSession, ...] = ()
    classifications: tuple[ClassificationRevision, ...] = ()
    classification_memberships: tuple[ClassificationMembershipRevision, ...] = ()
    bars: tuple[MarketBarRevision, ...] = ()
    instrument_facts: tuple[InstrumentFactRevision, ...] = ()
    security_status_facts: tuple[SecurityStatusFactRevision, ...] = ()
    lifecycle_status_facts: tuple[InstrumentLifecycleFactRevision, ...] = ()
    corporate_actions: tuple[CorporateActionRevision, ...] = ()
    gaps: tuple[SourceGap, ...] = ()

    def __post_init__(self) -> None:
        evidence = (
            *self.instruments,
            *self.instrument_identifiers,
            *self.trading_sessions,
            *self.classifications,
            *self.classification_memberships,
            *self.bars,
            *self.instrument_facts,
            *self.security_status_facts,
            *self.lifecycle_status_facts,
            *self.corporate_actions,
            *self.gaps,
        )
        if not evidence:
            raise ValueError("normalization must record a fact revision or typed SourceGap")
        if any(_evidence_capture_id(item) != self.source_capture_id for item in evidence):
            raise ValueError("normalization output must bind one exact Capture")
        products = tuple(
            item.provider_product_id
            for item in evidence
            if hasattr(item, "provider_product_id")
        )
        if any(item != self.source_provider_product_id for item in products):
            raise ValueError("normalization output must bind the Capture's ProviderProduct")
        gap_keys = tuple(item.disposition_key for item in self.gaps)
        if len(gap_keys) != len(set(gap_keys)):
            raise ValueError(
                "one Capture must have one SourceGap disposition per expected fact"
            )
        if any(_gap_conflicts_with_batch_fact(self, gap) for gap in self.gaps):
            raise ValueError(
                "one Capture cannot assert both a canonical fact and a SourceGap "
                "for the same expected observation"
            )

    @property
    def required_fact_kinds(self) -> frozenset[MarketFactKind]:
        required: set[MarketFactKind] = set()
        for values, kind in (
            (self.instruments, MarketFactKind.INSTRUMENT),
            (self.instrument_identifiers, MarketFactKind.INSTRUMENT_IDENTIFIER),
            (self.trading_sessions, MarketFactKind.TRADING_SESSION),
            (self.classifications, MarketFactKind.CLASSIFICATION),
            (
                self.classification_memberships,
                MarketFactKind.CLASSIFICATION_MEMBERSHIP,
            ),
            (self.bars, MarketFactKind.MARKET_BAR),
            (
                (
                    *self.instrument_facts,
                    *self.security_status_facts,
                    *self.lifecycle_status_facts,
                ),
                MarketFactKind.INSTRUMENT_FACT,
            ),
            (self.corporate_actions, MarketFactKind.CORPORATE_ACTION),
        ):
            if values:
                required.add(kind)
        for gap in self.gaps:
            try:
                required.add(MarketFactKind(gap.fact_kind.value))
            except ValueError:
                # Capture-level gaps do not invent a Market fact.
                pass
        return frozenset(required)

    @property
    def required_instrument_fact_kinds(self) -> frozenset[InstrumentFactKind]:
        required = {
            InstrumentFactKind(item.fact_kind.value) for item in self.instrument_facts
        }
        if self.security_status_facts:
            required.add(InstrumentFactKind.SECURITY_STATUS)
        required.update(item.fact_kind for item in self.lifecycle_status_facts)
        required.update(
            item.instrument_fact_kind
            for item in self.gaps
            if item.instrument_fact_kind is not None
        )
        return frozenset(required)


def _gap_conflicts_with_batch_fact(
    batch: NormalizationBatch,
    gap: SourceGap,
) -> bool:
    if gap.fact_kind is GapFactKind.DATA_CAPTURE:
        return False
    if gap.fact_kind is GapFactKind.INSTRUMENT:
        return any(item.canonical_code == gap.instrument_code for item in batch.instruments)
    if gap.fact_kind is GapFactKind.INSTRUMENT_IDENTIFIER:
        return any(
            item.identifier_scheme == gap.identifier_scheme
            and item.identifier_value == gap.identifier_value
            and (gap.instrument_id is None or item.instrument_id == gap.instrument_id)
            and item.effective_from == gap.effective_from
            and item.effective_to == gap.effective_to
            for item in batch.instrument_identifiers
        )
    if gap.fact_kind is GapFactKind.TRADING_SESSION:
        return any(
            item.exchange == gap.exchange and item.session_date == gap.session_date
            for item in batch.trading_sessions
        )
    if gap.fact_kind is GapFactKind.CLASSIFICATION:
        return any(
            item.classification_scheme == gap.classification_scheme
            and item.classification_code == gap.classification_code
            and item.effective_from == gap.effective_from
            and item.effective_to == gap.effective_to
            for item in batch.classifications
        )
    if gap.fact_kind is GapFactKind.CLASSIFICATION_MEMBERSHIP:
        classification_by_id = {
            item.classification_id: item for item in batch.classifications
        }
        return any(
            item.instrument_id == gap.instrument_id
            and item.effective_from == gap.effective_from
            and item.effective_to == gap.effective_to
            and (
                classification := classification_by_id.get(item.classification_id)
            )
            is not None
            and classification.classification_scheme == gap.classification_scheme
            and classification.classification_code == gap.classification_code
            for item in batch.classification_memberships
        )
    if gap.fact_kind is GapFactKind.MARKET_BAR:
        return any(
            item.instrument_id == gap.instrument_id
            and item.session_id == gap.session_id
            and item.timeframe == gap.timeframe
            and item.price_basis == gap.price_basis
            and item.event_start == gap.event_start
            and item.event_end == gap.event_end
            for item in batch.bars
        )
    if gap.fact_kind is GapFactKind.CORPORATE_ACTION:
        return any(
            item.instrument_id == gap.instrument_id
            and item.ex_session_id == gap.session_id
            and item.action_key == gap.action_key
            for item in batch.corporate_actions
        )
    if gap.instrument_fact_kind is None:
        raise AssertionError("INSTRUMENT_FACT SourceGap lost its typed fact kind")
    if gap.evidence_scope is not EvidenceScope.EFFECTIVE_INTERVAL:
        numeric_conflict = any(
            item.instrument_id == gap.instrument_id
            and item.fact_kind.value == gap.instrument_fact_kind.value
            and item.session_id == gap.session_id
            and item.evidence_scope == gap.evidence_scope
            and item.event_start == gap.event_start
            and item.event_end == gap.event_end
            for item in batch.instrument_facts
        )
        security_conflict = any(
            gap.instrument_fact_kind is InstrumentFactKind.SECURITY_STATUS
            and item.instrument_id == gap.instrument_id
            and item.session_id == gap.session_id
            and item.evidence_scope == gap.evidence_scope
            and item.event_start == gap.event_start
            and item.event_end == gap.event_end
            for item in batch.security_status_facts
        )
        return numeric_conflict or security_conflict
    numeric_conflict = any(
        item.instrument_id == gap.instrument_id
        and item.fact_kind.value == gap.instrument_fact_kind.value
        and item.evidence_scope is EvidenceScope.EFFECTIVE_INTERVAL
        and item.event_start == gap.effective_from
        and item.event_end == gap.effective_to
        for item in batch.instrument_facts
    )
    lifecycle_conflict = any(
        item.instrument_id == gap.instrument_id
        and item.fact_kind == gap.instrument_fact_kind
        and item.effective_from == gap.effective_from
        and item.effective_to == gap.effective_to
        for item in batch.lifecycle_status_facts
    )
    return numeric_conflict or lifecycle_conflict


def _evidence_capture_id(item: object) -> UUID:
    for field_name in ("capture_id", "source_capture_id"):
        value = getattr(item, field_name, None)
        if isinstance(value, UUID):
            return value
    raise TypeError("normalization evidence has no Capture identity")


@dataclass(frozen=True, slots=True)
class DecisionReference:
    status: DecisionReferenceStatus
    reason_code: DecisionReferenceReason | GapReasonCode
    bar: MarketBarRevision | None


def classify_decision_reference(
    *,
    session: TradingSession,
    bar: MarketBarRevision | None,
    current_session_status: SecurityStatus | None,
    gap: SourceGap | None,
) -> DecisionReference:
    """Fail closed around the exact same-session RAW five-minute 14:55 fact."""

    if gap is not None:
        unavailable = gap.gap_kind in {GapKind.MISSING, GapKind.PLACEHOLDER}
        return DecisionReference(
            status=(
                DecisionReferenceStatus.UNAVAILABLE
                if unavailable
                else DecisionReferenceStatus.FAILED
            ),
            reason_code=gap.reason_code,
            bar=None,
        )
    if current_session_status is SecurityStatus.SUSPENDED:
        return DecisionReference(
            status=DecisionReferenceStatus.UNAVAILABLE,
            reason_code=DecisionReferenceReason.CURRENT_SESSION_SUSPENDED,
            bar=None,
        )
    if bar is None:
        return DecisionReference(
            status=DecisionReferenceStatus.UNAVAILABLE,
            reason_code=DecisionReferenceReason.EXACT_RAW_1455_BAR_MISSING,
            bar=None,
        )
    exact = (
        bar.session_id == session.session_id
        and bar.timeframe is BarTimeframe.MINUTE_5
        and bar.price_basis is PriceBasis.RAW_UNADJUSTED
        and bar.event_end == session.decision_reference_at
        and bar.event_start == session.decision_reference_at - timedelta(minutes=5)
    )
    if not exact:
        return DecisionReference(
            status=DecisionReferenceStatus.FAILED,
            reason_code=(
                DecisionReferenceReason.DECISION_REFERENCE_NOT_EXACT_RAW_SAME_SESSION_1455
            ),
            bar=None,
        )
    return DecisionReference(
        status=DecisionReferenceStatus.AVAILABLE,
        reason_code=DecisionReferenceReason.EXACT_RAW_SAME_SESSION_1455,
        bar=bar,
    )


__all__ = [
    "BarTimeframe",
    "CaptureStatus",
    "ClassificationEvidenceStatus",
    "ClassificationMembersResult",
    "ClassificationMembershipRevision",
    "ClassificationRevision",
    "CorporateActionType",
    "CorporateActionRevision",
    "DecisionReference",
    "DecisionReferenceStatus",
    "DecisionReferenceReason",
    "GapFactKind",
    "GapKind",
    "GapReasonCode",
    "EvidenceScope",
    "Instrument",
    "InstrumentFactRevision",
    "InstrumentFactKind",
    "InstrumentLifecycleFactRevision",
    "InstrumentIdentifier",
    "InstrumentType",
    "MarketFactKind",
    "MarketEvidenceGapError",
    "MarketBarRevision",
    "NormalizationBatch",
    "NumericInstrumentFactKind",
    "ProviderCapture",
    "Provider",
    "ProviderKind",
    "ProviderProduct",
    "PriceBasis",
    "MembershipStatus",
    "ListingStatus",
    "SecurityStatus",
    "SecurityStatusFactRevision",
    "SourceAvailabilityStatus",
    "SourceGap",
    "SpecialTreatmentStatus",
    "TemporalEnvelope",
    "TradingSession",
    "classify_decision_reference",
    "require_capture_key",
]
