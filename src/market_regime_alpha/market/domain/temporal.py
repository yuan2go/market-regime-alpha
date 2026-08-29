"""Capture and exchange-session temporal facts."""

from dataclasses import dataclass
from datetime import date, datetime, time
import re
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from market_regime_alpha.market.domain.vocabulary import CaptureStatus, SourceAvailabilityStatus
from market_regime_alpha.shared.identity import ContentHash, TradingSessionId
from market_regime_alpha.shared.time import DecisionTime, KnownTime, require_utc

_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")
_CAPTURE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


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
            raise TypeError("source_availability_status must be SourceAvailabilityStatus")
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
            self.known_at if isinstance(self.known_at, KnownTime) else KnownTime(self.known_at),
        )
        object.__setattr__(
            self,
            "decision_visible_at",
            self.decision_visible_at if isinstance(self.decision_visible_at, DecisionTime) else DecisionTime(self.decision_visible_at),
        )
        if self.source_availability_status is SourceAvailabilityStatus.UNKNOWN:
            if self.source_available_at is not None:
                raise ValueError("UNKNOWN source availability cannot carry a timestamp")
        elif self.source_available_at is None:
            raise ValueError("PROVIDER_REPORTED source availability needs a timestamp")
        if self.source_available_at is not None and self.source_available_at > self.known_at.value:
            raise ValueError("source_available_at cannot follow known_at")
        if self.capture_completed_at < self.capture_started_at:
            raise ValueError("capture_completed_at cannot precede capture_started_at")
        if self.known_at.value < self.capture_completed_at:
            raise ValueError("known_at cannot precede completed capture")
        if self.decision_visible_at.value != self.known_at.value:
            raise ValueError("unqualified Provider decision_visible_at must equal known_at")


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
            self.request_hash if isinstance(self.request_hash, ContentHash) else ContentHash(self.request_hash),
        )
        for field_name in ("error_code", "limitation_code"):
            value = getattr(self, field_name)
            if value is not None and not _CODE.fullmatch(value):
                raise ValueError(f"{field_name} has an invalid format")
        if self.status is CaptureStatus.CAPTURED:
            if self.artifact_id is None or self.error_code is not None or not self.payload_encoding:
                raise ValueError("CAPTURED requires an Artifact, encoding, and no error")
        else:
            if self.error_code is None:
                raise ValueError("PROVIDER_FAILURE requires a typed error_code")
            if (
                self.temporal.source_availability_status is not SourceAvailabilityStatus.UNKNOWN
                or self.temporal.source_available_at is not None
            ):
                raise ValueError("PROVIDER_FAILURE cannot assert source availability evidence")


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
