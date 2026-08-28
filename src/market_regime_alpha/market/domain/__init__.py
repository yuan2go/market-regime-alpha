"""Market/PIT domain values and invariants with no infrastructure dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")


class AdjustmentBasis(StrEnum):
    RAW_UNADJUSTED = "RAW_UNADJUSTED"
    FORWARD_ADJUSTED = "FORWARD_ADJUSTED"
    BACKWARD_ADJUSTED = "BACKWARD_ADJUSTED"


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


class InstrumentFactValueKind(StrEnum):
    STATUS = "STATUS"
    DECIMAL = "DECIMAL"
    TEXT = "TEXT"


class DecisionReferenceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class Provider:
    provider_id: UUID
    provider_code: str
    display_name: str
    provider_kind: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}", self.provider_code):
            raise ValueError("provider_code has an invalid format")
        if not self.display_name:
            raise ValueError("display_name is required")
        if self.provider_kind not in {"PUBLIC_ENDPOINT", "DATA_VENDOR", "BROKER_FEED"}:
            raise ValueError("provider_kind is invalid")


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
    contract_sha256: str
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
        ContentHash(self.contract_sha256)


@dataclass(frozen=True, slots=True)
class Instrument:
    instrument_id: UUID
    canonical_code: str
    exchange: str
    instrument_type: str
    currency: str
    source_capture_id: UUID

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,31}", self.canonical_code):
            raise ValueError("canonical_code has an invalid format")
        if not re.fullmatch(r"[A-Z][A-Z0-9]{1,15}", self.exchange):
            raise ValueError("exchange has an invalid format")
        if self.instrument_type not in {"EQUITY", "ETF", "INDEX", "FUND", "BOND"}:
            raise ValueError("instrument_type is invalid")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("currency must be an ISO-style three-letter code")


@dataclass(frozen=True, slots=True)
class InstrumentIdentifier:
    instrument_identifier_id: UUID
    instrument_id: UUID
    identifier_scheme: str
    identifier_value: str
    effective_from: datetime
    effective_to: datetime | None
    revision: int
    supersedes_identifier_id: UUID | None
    source_capture_id: UUID

    def __post_init__(self) -> None:
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
    instrument_id: UUID
    source_capture_id: UUID
    membership_status: str
    effective_from: datetime
    effective_to: datetime | None
    revision: int
    supersedes_membership_revision_id: UUID | None

    def __post_init__(self) -> None:
        if self.membership_status not in {"MEMBER", "NOT_MEMBER"}:
            raise ValueError("membership_status is invalid")
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
class TemporalEnvelope:
    """Independent source/capture/knowledge axes for one immutable Capture."""

    provider_time: datetime | None
    source_availability_status: SourceAvailabilityStatus
    source_available_at: datetime | None
    capture_started_at: datetime
    capture_completed_at: datetime
    known_at: datetime
    decision_visible_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "provider_time",
            "source_available_at",
            "capture_started_at",
            "capture_completed_at",
            "known_at",
            "decision_visible_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    require_utc(value, field=field_name),
                )
        if self.source_availability_status is SourceAvailabilityStatus.UNKNOWN:
            if self.source_available_at is not None:
                raise ValueError("UNKNOWN source availability cannot carry a timestamp")
        elif self.source_available_at is None:
            raise ValueError("PROVIDER_REPORTED source availability needs a timestamp")
        if self.capture_completed_at < self.capture_started_at:
            raise ValueError("capture_completed_at cannot precede capture_started_at")
        if self.known_at < self.capture_completed_at:
            raise ValueError("known_at cannot precede completed capture")
        if self.decision_visible_at != self.known_at:
            raise ValueError(
                "unqualified Provider decision_visible_at must equal known_at"
            )


@dataclass(frozen=True, slots=True)
class ProviderCapture:
    capture_id: UUID
    provider_product_id: UUID
    capture_key: str
    request_hash: str
    status: CaptureStatus
    temporal: TemporalEnvelope
    artifact_id: UUID | None
    error_code: str | None
    limitation_code: str | None
    payload_encoding: str | None = None

    def __post_init__(self) -> None:
        if not self.capture_key or len(self.capture_key) > 200:
            raise ValueError("capture_key is required and limited to 200 characters")
        ContentHash(self.request_hash)
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
        elif self.error_code is None:
            raise ValueError("PROVIDER_FAILURE requires a typed error_code")


@dataclass(frozen=True, slots=True)
class TradingSession:
    session_id: UUID
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
        if not self.exchange:
            raise ValueError("exchange is required")
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


def _decimal(value: Decimal | None, field_name: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")


@dataclass(frozen=True, slots=True)
class MarketBarRevision:
    bar_revision_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: UUID
    session_id: UUID
    timeframe: BarTimeframe
    adjustment_basis: AdjustmentBasis
    event_start: datetime
    event_end: datetime
    revision: int
    supersedes_revision_id: UUID | None
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_start", require_utc(self.event_start, field="event_start"))
        object.__setattr__(self, "event_end", require_utc(self.event_end, field="event_end"))
        if self.event_end <= self.event_start:
            raise ValueError("bar event interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        for field_name in ("open", "high", "low", "close", "volume"):
            _decimal(getattr(self, field_name), field_name)
        _decimal(self.turnover, "turnover", optional=True)
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("bar must contain positive legal OHLC")
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close, self.high
        ):
            raise ValueError("bar must contain legal OHLC")
        if self.volume < 0 or (self.turnover is not None and self.turnover < 0):
            raise ValueError("volume and turnover cannot be negative")

    @property
    def logical_series_key(self) -> tuple[UUID, UUID, BarTimeframe, AdjustmentBasis]:
        return (
            self.provider_product_id,
            self.instrument_id,
            self.timeframe,
            self.adjustment_basis,
        )


@dataclass(frozen=True, slots=True)
class SecurityStatusFactRevision:
    fact_revision_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: UUID
    session_id: UUID
    evidence_scope: str
    status: SecurityStatus
    event_start: datetime
    event_end: datetime
    revision: int
    supersedes_revision_id: UUID | None

    def __post_init__(self) -> None:
        if self.evidence_scope not in {"DECISION_SESSION", "PRIOR_SESSION"}:
            raise ValueError("security status scope must identify decision or prior session")
        object.__setattr__(self, "event_start", require_utc(self.event_start, field="event_start"))
        object.__setattr__(self, "event_end", require_utc(self.event_end, field="event_end"))
        if self.event_end <= self.event_start:
            raise ValueError("fact event interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")


@dataclass(frozen=True, slots=True)
class InstrumentFactRevision:
    fact_revision_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: UUID
    session_id: UUID | None
    fact_kind: str
    evidence_scope: str
    event_start: datetime
    event_end: datetime
    value_kind: InstrumentFactValueKind
    status_value: str | None
    numeric_value: Decimal | None
    text_value: str | None
    unit_code: str | None
    revision: int
    supersedes_revision_id: UUID | None

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.fact_kind):
            raise ValueError("fact_kind has an invalid format")
        if self.evidence_scope not in {
            "DECISION_SESSION",
            "PRIOR_SESSION",
            "EFFECTIVE_INTERVAL",
        }:
            raise ValueError("evidence_scope is invalid")
        if self.evidence_scope != "EFFECTIVE_INTERVAL" and self.session_id is None:
            raise ValueError("session-scoped fact requires session_id")
        object.__setattr__(self, "event_start", require_utc(self.event_start, field="event_start"))
        object.__setattr__(self, "event_end", require_utc(self.event_end, field="event_end"))
        if self.event_end <= self.event_start:
            raise ValueError("fact event interval must be positive")
        present = sum(
            value is not None
            for value in (self.status_value, self.numeric_value, self.text_value)
        )
        if present != 1:
            raise ValueError("instrument fact requires exactly one typed value")
        expected_present = {
            InstrumentFactValueKind.STATUS: self.status_value is not None,
            InstrumentFactValueKind.DECIMAL: self.numeric_value is not None,
            InstrumentFactValueKind.TEXT: self.text_value is not None,
        }[self.value_kind]
        if not expected_present:
            raise ValueError("instrument fact value does not match value_kind")
        _decimal(self.numeric_value, "numeric_value", optional=True)
        if self.unit_code is not None and not re.fullmatch(
            r"[A-Z][A-Z0-9_]{0,31}", self.unit_code
        ):
            raise ValueError("unit_code has an invalid format")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_revision_id is None):
            raise ValueError("instrument-fact revision chain is incomplete")


@dataclass(frozen=True, slots=True)
class CorporateActionRevision:
    corporate_action_revision_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: UUID
    action_key: str
    action_type: str
    ex_session_id: UUID
    payable_at: datetime | None
    cash_amount: Decimal | None
    ratio_factor: Decimal | None
    currency: str | None
    revision: int
    supersedes_revision_id: UUID | None

    def __post_init__(self) -> None:
        if not self.action_key:
            raise ValueError("action_key is required")
        if self.action_type not in {
            "CASH_DIVIDEND",
            "STOCK_DIVIDEND",
            "SPLIT",
            "RIGHTS_ISSUE",
            "MERGER",
            "DELISTING",
        }:
            raise ValueError("action_type is invalid")
        if self.payable_at is not None:
            object.__setattr__(self, "payable_at", require_utc(self.payable_at, field="payable_at"))
        _decimal(self.cash_amount, "cash_amount", optional=True)
        _decimal(self.ratio_factor, "ratio_factor", optional=True)
        if self.cash_amount is not None and self.cash_amount < 0:
            raise ValueError("cash_amount cannot be negative")
        if self.ratio_factor is not None and self.ratio_factor <= 0:
            raise ValueError("ratio_factor must be positive")
        if self.cash_amount is not None and self.currency is None:
            raise ValueError("cash action requires currency")
        if self.currency is not None and not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("currency has an invalid format")
        if self.cash_amount is None and self.ratio_factor is None and self.action_type not in {"MERGER", "DELISTING"}:
            raise ValueError("corporate action requires a typed financial value")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_revision_id is None):
            raise ValueError("corporate-action revision chain is incomplete")


@dataclass(frozen=True, slots=True)
class SourceGap:
    gap_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: UUID | None
    session_id: UUID | None
    gap_kind: GapKind
    reason_code: str
    fact_kind: str
    timeframe: BarTimeframe | None
    adjustment_basis: AdjustmentBasis | None
    event_start: datetime | None
    event_end: datetime | None
    detail: str | None

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.reason_code):
            raise ValueError("reason_code has an invalid format")
        if not _CODE.fullmatch(self.fact_kind):
            raise ValueError("fact_kind has an invalid format")
        if (self.event_start is None) != (self.event_end is None):
            raise ValueError("gap event interval must be complete or absent")
        if self.event_start is not None and self.event_end is not None:
            object.__setattr__(self, "event_start", require_utc(self.event_start, field="event_start"))
            object.__setattr__(self, "event_end", require_utc(self.event_end, field="event_end"))
            if self.event_end <= self.event_start:
                raise ValueError("gap event interval must be positive")
        if (self.timeframe is None) != (self.adjustment_basis is None):
            raise ValueError("bar gaps require both timeframe and adjustment basis")


@dataclass(frozen=True, slots=True)
class NormalizationBatch:
    source_capture_id: UUID
    instruments: tuple[Instrument, ...] = ()
    instrument_identifiers: tuple[InstrumentIdentifier, ...] = ()
    trading_sessions: tuple[TradingSession, ...] = ()
    classifications: tuple[ClassificationRevision, ...] = ()
    classification_memberships: tuple[ClassificationMembershipRevision, ...] = ()
    bars: tuple[MarketBarRevision, ...] = ()
    instrument_facts: tuple[InstrumentFactRevision, ...] = ()
    security_status_facts: tuple[SecurityStatusFactRevision, ...] = ()
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
            *self.corporate_actions,
            *self.gaps,
        )
        if any(_evidence_capture_id(item) != self.source_capture_id for item in evidence):
            raise ValueError("normalization output must bind one exact Capture")


def _evidence_capture_id(item: object) -> UUID:
    for field_name in ("capture_id", "source_capture_id"):
        value = getattr(item, field_name, None)
        if isinstance(value, UUID):
            return value
    raise TypeError("normalization evidence has no Capture identity")


@dataclass(frozen=True, slots=True)
class DecisionReference:
    status: DecisionReferenceStatus
    reason_code: str
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
            reason_code="CURRENT_SESSION_SUSPENDED",
            bar=None,
        )
    if bar is None:
        return DecisionReference(
            status=DecisionReferenceStatus.UNAVAILABLE,
            reason_code="EXACT_RAW_1455_BAR_MISSING",
            bar=None,
        )
    exact = (
        bar.session_id == session.session_id
        and bar.timeframe is BarTimeframe.MINUTE_5
        and bar.adjustment_basis is AdjustmentBasis.RAW_UNADJUSTED
        and bar.event_end == session.decision_reference_at
        and bar.event_start == session.decision_reference_at - timedelta(minutes=5)
    )
    if not exact:
        return DecisionReference(
            status=DecisionReferenceStatus.FAILED,
            reason_code="DECISION_REFERENCE_NOT_EXACT_RAW_SAME_SESSION_1455",
            bar=None,
        )
    return DecisionReference(
        status=DecisionReferenceStatus.AVAILABLE,
        reason_code="EXACT_RAW_SAME_SESSION_1455",
        bar=bar,
    )


__all__ = [
    "AdjustmentBasis",
    "BarTimeframe",
    "CaptureStatus",
    "ClassificationMembershipRevision",
    "ClassificationRevision",
    "CorporateActionRevision",
    "DecisionReference",
    "DecisionReferenceStatus",
    "GapKind",
    "Instrument",
    "InstrumentFactRevision",
    "InstrumentFactValueKind",
    "InstrumentIdentifier",
    "MarketBarRevision",
    "NormalizationBatch",
    "ProviderCapture",
    "Provider",
    "ProviderProduct",
    "SecurityStatus",
    "SecurityStatusFactRevision",
    "SourceAvailabilityStatus",
    "SourceGap",
    "TemporalEnvelope",
    "TradingSession",
    "classify_decision_reference",
]
