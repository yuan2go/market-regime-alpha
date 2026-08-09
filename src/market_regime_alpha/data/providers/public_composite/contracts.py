"""Provider-only contracts for public composite acquisition and replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any, Mapping, Protocol

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import (
    DataEligibility,
    SourceArtifactReference,
)
from market_regime_alpha.data.source_manifest import SourceFieldFinality
from market_regime_alpha.data.source_manifest import (
    SourceAuthorityKind,
    SourceFieldQualityStatus,
)


PUBLIC_COMPOSITE_LIVE_PROFILE_ID = "public-composite-live-v1"
PUBLIC_COMPOSITE_REPLAY_PROFILE_ID = "public-composite-replay-v1"
TENCENT_FREE_OPERATIONAL_PROFILE_ID = "TENCENT_FREE_OPERATIONAL_V1"
BAOSTOCK_PUBLIC_PROVIDER_ID = ProviderId("provider-baostock-public")
TENCENT_PUBLIC_PROVIDER_ID = ProviderId("provider-tencent-public")
HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1 = (
    "HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1"
)


class TradingStatus(str, Enum):
    TRADING = "TRADING"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class STStatus(str, Enum):
    ST = "ST"
    NOT_ST = "NOT_ST"
    UNKNOWN = "UNKNOWN"


class ListingStatus(str, Enum):
    LISTED = "LISTED"
    DELISTED = "DELISTED"
    UNKNOWN = "UNKNOWN"


class SecurityStatusFactType(str, Enum):
    TRADING_STATUS = "TRADING_STATUS"
    ST_STATUS = "ST_STATUS"
    LISTING_STATUS = "LISTING_STATUS"


class SecurityStatusEvidenceScope(str, Enum):
    PRIOR_SESSION_STATUS = "PRIOR_SESSION_STATUS"
    CURRENT_DECISION_SESSION = "CURRENT_DECISION_SESSION"


SecurityStatusValue = TradingStatus | STStatus | ListingStatus


def _require_text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_aware(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _require_number(label: str, value: float, *, positive: bool = False) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or (positive and float(value) <= 0.0)
        or (not positive and float(value) < 0.0)
    ):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{label} must be a finite {qualifier} number")


def _require_finite_number(label: str, value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{label} must be a finite number")


def _optional_payload_float(
    payload: Mapping[str, Any], key: str
) -> float | None:
    value = payload.get(key)
    return float(value) if value is not None else None


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class PublicCompositeRequest:
    symbols: tuple[str, ...]
    decision_time: DecisionTime
    history_start: date
    minimum_history_sessions: int

    def __post_init__(self) -> None:
        if not self.symbols or tuple(sorted(set(self.symbols))) != self.symbols:
            raise ValueError("symbols must be non-empty, unique, and ordered")
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        if not isinstance(self.history_start, date):
            raise TypeError("history_start must be a date")
        if (
            isinstance(self.minimum_history_sessions, bool)
            or self.minimum_history_sessions < 1
        ):
            raise ValueError("minimum_history_sessions must be a positive integer")


@dataclass(frozen=True, slots=True)
class RawSourceRequestMetadata:
    """Request/response facts bound to new raw source payloads."""

    provider_profile_id: str
    endpoint: str
    request_parameters: tuple[tuple[str, str], ...]
    requested_at: datetime
    provider_timestamp: datetime | None
    event_time: datetime | None
    available_at: datetime | None
    decision_time: datetime
    http_status: int | None
    content_type: str | None
    response_size: int
    encoding: str
    symbol_scope: tuple[str, ...]
    field_scope: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text("provider_profile_id", self.provider_profile_id)
        _require_text("endpoint", self.endpoint)
        keys: list[str] = []
        for key, value in self.request_parameters:
            _require_text("request parameter key", key)
            _require_text("request parameter value", value)
            keys.append(key)
        if tuple(sorted(set(keys))) != tuple(keys):
            raise ValueError("request_parameters must have unique ordered keys")
        _require_aware("requested_at", self.requested_at)
        _require_aware("decision_time", self.decision_time)
        optional_times: tuple[tuple[str, datetime | None], ...] = (
            ("provider_timestamp", self.provider_timestamp),
            ("event_time", self.event_time),
            ("available_at", self.available_at),
        )
        for label, optional_time in optional_times:
            if optional_time is not None:
                _require_aware(label, optional_time)
        if self.http_status is not None and (
            isinstance(self.http_status, bool) or not 100 <= self.http_status <= 599
        ):
            raise ValueError("http_status must be between 100 and 599")
        if self.content_type is not None:
            _require_text("content_type", self.content_type)
        if isinstance(self.response_size, bool) or self.response_size < 1:
            raise ValueError("response_size must be a positive integer")
        _require_text("encoding", self.encoding)
        for label, values in (
            ("symbol_scope", self.symbol_scope),
            ("field_scope", self.field_scope),
        ):
            if not values or tuple(sorted(set(values))) != values:
                raise ValueError(f"{label} must be non-empty, unique, and ordered")
            for value in values:
                _require_text(label, value)

    def to_canonical_dict(self) -> dict[str, Any]:
        def instant(value: datetime | None) -> str | None:
            return value.isoformat() if value is not None else None

        return {
            "provider_profile_id": self.provider_profile_id,
            "endpoint": self.endpoint,
            "request_parameters": [list(item) for item in self.request_parameters],
            "requested_at": self.requested_at.isoformat(),
            "provider_timestamp": instant(self.provider_timestamp),
            "event_time": instant(self.event_time),
            "available_at": instant(self.available_at),
            "decision_time": self.decision_time.isoformat(),
            "http_status": self.http_status,
            "content_type": self.content_type,
            "response_size": self.response_size,
            "encoding": self.encoding,
            "symbol_scope": list(self.symbol_scope),
            "field_scope": list(self.field_scope),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> RawSourceRequestMetadata:
        expected = {
            "provider_profile_id",
            "endpoint",
            "request_parameters",
            "requested_at",
            "provider_timestamp",
            "event_time",
            "available_at",
            "decision_time",
            "http_status",
            "content_type",
            "response_size",
            "encoding",
            "symbol_scope",
            "field_scope",
        }
        if set(payload) != expected:
            raise ValueError("RawSourceRequestMetadata fields mismatch")

        def optional_instant(key: str) -> datetime | None:
            value = payload[key]
            return datetime.fromisoformat(str(value)) if value is not None else None

        parameters = payload["request_parameters"]
        if not isinstance(parameters, list) or any(
            not isinstance(item, list) or len(item) != 2 for item in parameters
        ):
            raise TypeError("request_parameters must be a list")
        return cls(
            provider_profile_id=str(payload["provider_profile_id"]),
            endpoint=str(payload["endpoint"]),
            request_parameters=tuple(
                (str(item[0]), str(item[1])) for item in parameters
            ),
            requested_at=datetime.fromisoformat(str(payload["requested_at"])),
            provider_timestamp=optional_instant("provider_timestamp"),
            event_time=optional_instant("event_time"),
            available_at=optional_instant("available_at"),
            decision_time=datetime.fromisoformat(str(payload["decision_time"])),
            http_status=(
                int(payload["http_status"])
                if payload["http_status"] is not None
                else None
            ),
            content_type=(
                str(payload["content_type"])
                if payload["content_type"] is not None
                else None
            ),
            response_size=int(payload["response_size"]),
            encoding=str(payload["encoding"]),
            symbol_scope=tuple(str(value) for value in payload["symbol_scope"]),
            field_scope=tuple(str(value) for value in payload["field_scope"]),
        )


@dataclass(frozen=True, slots=True)
class AcquiredSourcePayload:
    """Exact provider bytes before normalization."""

    provider_id: ProviderId
    product: str
    locator: str
    raw_payload: bytes
    retrieved_time: RetrievedAt
    limitations: tuple[str, ...]
    request_metadata: RawSourceRequestMetadata | None = None
    raw_hash: str = field(init=False)
    source_artifact_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        _require_text("product", self.product)
        _require_text("locator", self.locator)
        if not isinstance(self.raw_payload, bytes) or not self.raw_payload:
            raise ValueError("raw_payload must be non-empty bytes")
        if not isinstance(self.retrieved_time, RetrievedAt):
            raise TypeError("retrieved_time must be a RetrievedAt")
        for value in self.limitations:
            _require_text("limitation", value)
        if self.request_metadata is not None:
            if not isinstance(self.request_metadata, RawSourceRequestMetadata):
                raise TypeError("request_metadata must be RawSourceRequestMetadata")
            if self.request_metadata.response_size != len(self.raw_payload):
                raise ValueError(
                    "request metadata response_size does not match raw bytes"
                )
            if self.request_metadata.available_at is not None and (
                self.request_metadata.available_at != self.retrieved_time.value
            ):
                raise ValueError(
                    "request metadata available_at must equal retrieved_time"
                )
            if self.request_metadata.requested_at > self.retrieved_time.value:
                raise ValueError("request metadata requested_at exceeds retrieved_time")
        raw_hash = f"sha256:{sha256(self.raw_payload).hexdigest()}"
        object.__setattr__(self, "raw_hash", raw_hash)
        semantic: dict[str, Any] = {
            "provider_id": str(self.provider_id),
            "product": self.product,
            "locator": self.locator,
            "raw_hash": raw_hash,
            "retrieved_time": self.retrieved_time.isoformat(),
            "limitations": list(self.limitations),
        }
        if self.request_metadata is not None:
            semantic["request_metadata"] = self.request_metadata.to_canonical_dict()
        identity_hash = _canonical_hash(semantic)
        object.__setattr__(
            self,
            "source_artifact_id",
            ArtifactId(f"source-{identity_hash.split(':', 1)[1][:24]}"),
        )

    @property
    def reference(self) -> SourceArtifactReference:
        return SourceArtifactReference(
            artifact_id=self.source_artifact_id,
            provider_id=self.provider_id,
            retrieved_at=self.retrieved_time,
            content_hash=self.raw_hash,
            locator=self.locator,
        )

    def to_canonical_dict(self, *, include_payload: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider_id": str(self.provider_id),
            "product": self.product,
            "locator": self.locator,
            "retrieved_time": self.retrieved_time.isoformat(),
            "limitations": list(self.limitations),
            "raw_hash": self.raw_hash,
            "source_artifact_id": str(self.source_artifact_id),
        }
        if include_payload:
            from base64 import b64encode

            payload["raw_payload_base64"] = b64encode(self.raw_payload).decode("ascii")
        if self.request_metadata is not None:
            payload["request_metadata"] = self.request_metadata.to_canonical_dict()
        return payload

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> AcquiredSourcePayload:
        from base64 import b64decode

        legacy_expected = {
            "provider_id",
            "product",
            "locator",
            "retrieved_time",
            "limitations",
            "raw_hash",
            "source_artifact_id",
            "raw_payload_base64",
        }
        expected = legacy_expected | {"request_metadata"}
        if frozenset(payload) not in {
            frozenset(legacy_expected),
            frozenset(expected),
        }:
            raise ValueError("AcquiredSourcePayload fields mismatch")
        metadata_payload = payload.get("request_metadata")
        if "request_metadata" in payload and not isinstance(
            metadata_payload, Mapping
        ):
            raise TypeError("request_metadata must be an object")
        item = cls(
            provider_id=ProviderId(str(payload["provider_id"])),
            product=str(payload["product"]),
            locator=str(payload["locator"]),
            raw_payload=b64decode(str(payload["raw_payload_base64"]), validate=True),
            retrieved_time=RetrievedAt(
                datetime.fromisoformat(str(payload["retrieved_time"]))
            ),
            limitations=tuple(str(value) for value in payload["limitations"]),
            request_metadata=(
                RawSourceRequestMetadata.from_canonical_dict(metadata_payload)
                if isinstance(metadata_payload, Mapping)
                else None
            ),
        )
        if (
            item.raw_hash != payload["raw_hash"]
            or str(item.source_artifact_id) != payload["source_artifact_id"]
        ):
            raise ValueError("source payload identity mismatch")
        return item


@dataclass(frozen=True, slots=True)
class PublicBar:
    symbol: str
    event_time: datetime
    available_time: AvailabilityTime | None
    source_artifact_id: ArtifactId
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    unit: str
    adjustment_basis: str
    finality: SourceFieldFinality

    def __post_init__(self) -> None:
        _require_text("symbol", self.symbol)
        _require_aware("event_time", self.event_time)
        for label, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            _require_number(label, value, positive=True)
        for label, value in (("volume", self.volume), ("amount", self.amount)):
            _require_number(label, value)
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low exceeds OHLC values")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high is below OHLC values")
        _require_text("unit", self.unit)
        _require_text("adjustment_basis", self.adjustment_basis)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "event_time": self.event_time.isoformat(),
            "available_time": (
                self.available_time.isoformat()
                if self.available_time is not None
                else None
            ),
            "source_artifact_id": str(self.source_artifact_id),
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
            "amount": float(self.amount),
            "unit": self.unit,
            "adjustment_basis": self.adjustment_basis,
            "finality": self.finality.value,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PublicBar:
        available = payload["available_time"]
        return cls(
            symbol=str(payload["symbol"]),
            event_time=datetime.fromisoformat(str(payload["event_time"])),
            available_time=(
                AvailabilityTime(datetime.fromisoformat(str(available)))
                if available is not None
                else None
            ),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            volume=float(payload["volume"]),
            amount=float(payload["amount"]),
            unit=str(payload["unit"]),
            adjustment_basis=str(payload["adjustment_basis"]),
            finality=SourceFieldFinality(str(payload["finality"])),
        )


@dataclass(frozen=True, slots=True)
class PublicQuote:
    symbol: str
    event_time: datetime | None
    available_time: AvailabilityTime | None
    source_artifact_id: ArtifactId
    price: float | None
    trading_status: TradingStatus
    unit: str
    finality: SourceFieldFinality
    previous_close: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    change_fraction: float | None = None

    def __post_init__(self) -> None:
        _require_text("symbol", self.symbol)
        if self.event_time is not None:
            _require_aware("event_time", self.event_time)
        if self.price is not None:
            _require_number("price", self.price, positive=True)
        for label, value in (
            ("previous_close", self.previous_close),
            ("open_price", self.open_price),
            ("high_price", self.high_price),
            ("low_price", self.low_price),
        ):
            if value is not None:
                _require_number(label, value, positive=True)
        if self.change_fraction is not None:
            _require_finite_number("change_fraction", self.change_fraction)
        if (
            self.high_price is not None
            and self.low_price is not None
            and self.high_price < self.low_price
        ):
            raise ValueError("quote high_price cannot be below low_price")
        if not isinstance(self.trading_status, TradingStatus):
            raise TypeError("trading_status must be a TradingStatus")
        _require_text("unit", self.unit)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "event_time": (
                self.event_time.isoformat() if self.event_time is not None else None
            ),
            "available_time": (
                self.available_time.isoformat()
                if self.available_time is not None
                else None
            ),
            "source_artifact_id": str(self.source_artifact_id),
            "price": float(self.price) if self.price is not None else None,
            "trading_status": self.trading_status.value,
            "unit": self.unit,
            "finality": self.finality.value,
            "previous_close": self.previous_close,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "change_fraction": self.change_fraction,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PublicQuote:
        event = payload["event_time"]
        available = payload["available_time"]
        price = payload["price"]
        return cls(
            symbol=str(payload["symbol"]),
            event_time=(
                datetime.fromisoformat(str(event)) if event is not None else None
            ),
            available_time=(
                AvailabilityTime(datetime.fromisoformat(str(available)))
                if available is not None
                else None
            ),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            price=float(price) if price is not None else None,
            trading_status=TradingStatus(str(payload["trading_status"])),
            unit=str(payload["unit"]),
            finality=SourceFieldFinality(str(payload["finality"])),
            previous_close=_optional_payload_float(payload, "previous_close"),
            open_price=_optional_payload_float(payload, "open_price"),
            high_price=_optional_payload_float(payload, "high_price"),
            low_price=_optional_payload_float(payload, "low_price"),
            change_fraction=_optional_payload_float(payload, "change_fraction"),
        )


@dataclass(frozen=True, slots=True)
class PublicSecurityStatusObservation:
    """One Provider-declared status fact with explicit temporal scope."""

    symbol: str
    fact_type: SecurityStatusFactType
    value: SecurityStatusValue
    scope: SecurityStatusEvidenceScope
    event_time: datetime | None
    available_time: AvailabilityTime | None
    retrieved_time: RetrievedAt
    decision_time: DecisionTime
    policy_effective_time: datetime | None
    provider_id: ProviderId
    source_artifact_id: ArtifactId
    authority_kind: SourceAuthorityKind
    quality_status: SourceFieldQualityStatus
    reason_codes: tuple[str, ...]
    finality: SourceFieldFinality
    data_eligibility: DataEligibility

    def __post_init__(self) -> None:
        _require_text("symbol", self.symbol)
        if not isinstance(self.fact_type, SecurityStatusFactType):
            raise TypeError("fact_type must be a SecurityStatusFactType")
        value_matches_fact = (
            self.fact_type is SecurityStatusFactType.TRADING_STATUS
            and isinstance(self.value, TradingStatus)
        ) or (
            self.fact_type is SecurityStatusFactType.ST_STATUS
            and isinstance(self.value, STStatus)
        ) or (
            self.fact_type is SecurityStatusFactType.LISTING_STATUS
            and isinstance(self.value, ListingStatus)
        )
        if not value_matches_fact:
            raise TypeError("status value does not match fact_type")
        if not isinstance(self.scope, SecurityStatusEvidenceScope):
            raise TypeError("scope must be a SecurityStatusEvidenceScope")
        if self.event_time is not None:
            _require_aware("event_time", self.event_time)
        if self.policy_effective_time is not None:
            _require_aware("policy_effective_time", self.policy_effective_time)
        if not isinstance(self.retrieved_time, RetrievedAt):
            raise TypeError("retrieved_time must be a RetrievedAt")
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        if self.authority_kind is not SourceAuthorityKind.PROVIDER:
            raise ValueError("security status must use Provider authority")
        if not isinstance(self.quality_status, SourceFieldQualityStatus):
            raise TypeError("quality_status must be a SourceFieldQualityStatus")
        if not isinstance(self.finality, SourceFieldFinality):
            raise TypeError("finality must be a SourceFieldFinality")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("public security status must remain EXPLORATORY")
        for reason in self.reason_codes:
            _require_text("reason_code", reason)
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes must be unique")
        if (
            self.quality_status is SourceFieldQualityStatus.COMPLETE
            and self.reason_codes
        ):
            raise ValueError("COMPLETE status observation cannot carry reason_codes")
        if self.value.value == "UNKNOWN" and (
            self.quality_status is SourceFieldQualityStatus.COMPLETE
            or not self.reason_codes
        ):
            raise ValueError("UNKNOWN status must be explicit and incomplete")
        if (
            self.scope is SecurityStatusEvidenceScope.CURRENT_DECISION_SESSION
            and self.value.value != "UNKNOWN"
            and self.available_time is None
        ):
            raise ValueError("known current status requires available_time")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "fact_type": self.fact_type.value,
            "value": self.value.value,
            "scope": self.scope.value,
            "event_time": (
                self.event_time.isoformat() if self.event_time is not None else None
            ),
            "available_time": (
                self.available_time.isoformat()
                if self.available_time is not None
                else None
            ),
            "retrieved_time": self.retrieved_time.isoformat(),
            "decision_time": self.decision_time.isoformat(),
            "policy_effective_time": (
                self.policy_effective_time.isoformat()
                if self.policy_effective_time is not None
                else None
            ),
            "provider_id": str(self.provider_id),
            "source_artifact_id": str(self.source_artifact_id),
            "authority_kind": self.authority_kind.value,
            "quality_status": self.quality_status.value,
            "reason_codes": list(self.reason_codes),
            "finality": self.finality.value,
            "data_eligibility": self.data_eligibility.value,
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> PublicSecurityStatusObservation:
        expected = {
            "symbol",
            "fact_type",
            "value",
            "scope",
            "event_time",
            "available_time",
            "retrieved_time",
            "decision_time",
            "policy_effective_time",
            "provider_id",
            "source_artifact_id",
            "authority_kind",
            "quality_status",
            "reason_codes",
            "finality",
            "data_eligibility",
        }
        if set(payload) != expected:
            raise ValueError("PublicSecurityStatusObservation fields mismatch")
        fact_type = SecurityStatusFactType(str(payload["fact_type"]))
        raw_value = str(payload["value"])
        if fact_type is SecurityStatusFactType.TRADING_STATUS:
            value: SecurityStatusValue = TradingStatus(raw_value)
        elif fact_type is SecurityStatusFactType.ST_STATUS:
            value = STStatus(raw_value)
        else:
            value = ListingStatus(raw_value)
        event_time = payload["event_time"]
        available_time = payload["available_time"]
        policy_effective_time = payload["policy_effective_time"]
        return cls(
            symbol=str(payload["symbol"]),
            fact_type=fact_type,
            value=value,
            scope=SecurityStatusEvidenceScope(str(payload["scope"])),
            event_time=(
                datetime.fromisoformat(str(event_time))
                if event_time is not None
                else None
            ),
            available_time=(
                AvailabilityTime(datetime.fromisoformat(str(available_time)))
                if available_time is not None
                else None
            ),
            retrieved_time=RetrievedAt(
                datetime.fromisoformat(str(payload["retrieved_time"]))
            ),
            decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["decision_time"]))
            ),
            policy_effective_time=(
                datetime.fromisoformat(str(policy_effective_time))
                if policy_effective_time is not None
                else None
            ),
            provider_id=ProviderId(str(payload["provider_id"])),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            authority_kind=SourceAuthorityKind(str(payload["authority_kind"])),
            quality_status=SourceFieldQualityStatus(str(payload["quality_status"])),
            reason_codes=tuple(str(value) for value in payload["reason_codes"]),
            finality=SourceFieldFinality(str(payload["finality"])),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )


@dataclass(frozen=True, slots=True)
class PublicCompositeBatch:
    raw_payloads: tuple[AcquiredSourcePayload, ...]
    bars: tuple[PublicBar, ...]
    quotes: tuple[PublicQuote, ...]
    source_conflicts: tuple[str, ...]
    limitations: tuple[str, ...]
    security_status_observations: tuple[PublicSecurityStatusObservation, ...] = ()


class PublicAcquisitionClient(Protocol):
    def acquire(self, request: PublicCompositeRequest) -> PublicCompositeBatch: ...


@dataclass(frozen=True, slots=True)
class PublicCompositeProviderResult:
    SCHEMA_VERSION = "public-composite-provider-result-v1"

    profile_id: str
    decision_time: DecisionTime
    raw_payloads: tuple[AcquiredSourcePayload, ...]
    bars: tuple[PublicBar, ...]
    quotes: tuple[PublicQuote, ...]
    source_conflicts: tuple[str, ...]
    limitations: tuple[str, ...]
    data_eligibility: DataEligibility = field(
        init=False,
        default=DataEligibility.EXPLORATORY,
    )
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.profile_id not in {
            PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
            PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
            TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        }:
            raise ValueError("unsupported public composite profile")
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        if not self.raw_payloads:
            raise ValueError("raw_payloads must not be empty")
        if any(
            item.request_metadata is not None
            and item.request_metadata.provider_profile_id != self.profile_id
            for item in self.raw_payloads
        ):
            raise ValueError("raw payload provider profile does not match result profile")
        source_ids = tuple(item.source_artifact_id for item in self.raw_payloads)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("raw_payloads must be unique")
        known = set(source_ids)
        if any(item.source_artifact_id not in known for item in self.bars):
            raise ValueError("normalized data references an unarchived source payload")
        if any(item.source_artifact_id not in known for item in self.quotes):
            raise ValueError("normalized data references an unarchived source payload")
        bar_keys = tuple((item.symbol, item.event_time) for item in self.bars)
        quote_symbols = tuple(item.symbol for item in self.quotes)
        if len(bar_keys) != len(set(bar_keys)):
            raise ValueError("bars must be unique by symbol and event_time")
        if len(quote_symbols) != len(set(quote_symbols)):
            raise ValueError("quotes must be unique by symbol")
        for values in (self.source_conflicts, self.limitations):
            for value in values:
                _require_text("provider declaration", value)
            if len(values) != len(set(values)):
                raise ValueError("provider declarations must be unique")
        object.__setattr__(self, "content_hash", _canonical_hash(self.semantic_payload()))

    @property
    def source_artifact_references(self) -> tuple[SourceArtifactReference, ...]:
        return tuple(item.reference for item in self.raw_payloads)

    def semantic_payload(self, *, include_raw_payloads: bool = False) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "profile_id": self.profile_id,
            "decision_time": self.decision_time.isoformat(),
            "raw_payloads": [
                item.to_canonical_dict(include_payload=include_raw_payloads)
                for item in self.raw_payloads
            ],
            "bars": [item.to_canonical_dict() for item in self.bars],
            "quotes": [item.to_canonical_dict() for item in self.quotes],
            "source_conflicts": list(self.source_conflicts),
            "limitations": list(self.limitations),
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self, *, include_raw_payloads: bool) -> dict[str, Any]:
        return {
            **self.semantic_payload(include_raw_payloads=include_raw_payloads),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> PublicCompositeProviderResult:
        expected = {
            "schema_version",
            "profile_id",
            "decision_time",
            "raw_payloads",
            "bars",
            "quotes",
            "source_conflicts",
            "limitations",
            "data_eligibility",
            "content_hash",
        }
        if set(payload) != expected:
            raise ValueError("PublicCompositeProviderResult fields mismatch")
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported PublicCompositeProviderResult schema")
        if payload["data_eligibility"] != DataEligibility.EXPLORATORY.value:
            raise ValueError("public provider result may not inflate eligibility")
        result = cls(
            profile_id=str(payload["profile_id"]),
            decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["decision_time"]))
            ),
            raw_payloads=tuple(
                AcquiredSourcePayload.from_canonical_dict(item)
                for item in payload["raw_payloads"]
            ),
            bars=tuple(PublicBar.from_canonical_dict(item) for item in payload["bars"]),
            quotes=tuple(
                PublicQuote.from_canonical_dict(item) for item in payload["quotes"]
            ),
            source_conflicts=tuple(str(item) for item in payload["source_conflicts"]),
            limitations=tuple(str(item) for item in payload["limitations"]),
        )
        if result.content_hash != payload["content_hash"]:
            raise ValueError("provider result identity mismatch")
        return result
