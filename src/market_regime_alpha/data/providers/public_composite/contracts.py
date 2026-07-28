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


PUBLIC_COMPOSITE_LIVE_PROFILE_ID = "public-composite-live-v1"
PUBLIC_COMPOSITE_REPLAY_PROFILE_ID = "public-composite-replay-v1"
BAOSTOCK_PUBLIC_PROVIDER_ID = ProviderId("provider-baostock-public")
TENCENT_PUBLIC_PROVIDER_ID = ProviderId("provider-tencent-public")


class TradingStatus(str, Enum):
    TRADING = "TRADING"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


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
class AcquiredSourcePayload:
    """Exact provider bytes before normalization."""

    provider_id: ProviderId
    product: str
    locator: str
    raw_payload: bytes
    retrieved_time: RetrievedAt
    limitations: tuple[str, ...]
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
        raw_hash = f"sha256:{sha256(self.raw_payload).hexdigest()}"
        object.__setattr__(self, "raw_hash", raw_hash)
        semantic = {
            "provider_id": str(self.provider_id),
            "product": self.product,
            "locator": self.locator,
            "raw_hash": raw_hash,
            "retrieved_time": self.retrieved_time.isoformat(),
            "limitations": list(self.limitations),
        }
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
        return payload

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> AcquiredSourcePayload:
        from base64 import b64decode

        expected = {
            "provider_id",
            "product",
            "locator",
            "retrieved_time",
            "limitations",
            "raw_hash",
            "source_artifact_id",
            "raw_payload_base64",
        }
        if set(payload) != expected:
            raise ValueError("AcquiredSourcePayload fields mismatch")
        item = cls(
            provider_id=ProviderId(str(payload["provider_id"])),
            product=str(payload["product"]),
            locator=str(payload["locator"]),
            raw_payload=b64decode(str(payload["raw_payload_base64"]), validate=True),
            retrieved_time=RetrievedAt(
                datetime.fromisoformat(str(payload["retrieved_time"]))
            ),
            limitations=tuple(str(value) for value in payload["limitations"]),
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

    def __post_init__(self) -> None:
        _require_text("symbol", self.symbol)
        if self.event_time is not None:
            _require_aware("event_time", self.event_time)
        if self.price is not None:
            _require_number("price", self.price, positive=True)
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
        )


@dataclass(frozen=True, slots=True)
class PublicCompositeBatch:
    raw_payloads: tuple[AcquiredSourcePayload, ...]
    bars: tuple[PublicBar, ...]
    quotes: tuple[PublicQuote, ...]
    source_conflicts: tuple[str, ...]
    limitations: tuple[str, ...]


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
        }:
            raise ValueError("unsupported public composite profile")
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        if not self.raw_payloads:
            raise ValueError("raw_payloads must not be empty")
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
