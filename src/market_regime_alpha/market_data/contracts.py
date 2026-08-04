"""Canonical point-in-time market-bar contracts.

These objects describe observable market data only.  They cannot produce a trading
decision, mutate a repository, fetch a provider, or invoke execution infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from math import isfinite
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)


MARKET_BAR_SCHEMA_VERSION = "canonical-market-bar-v1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class Exchange(str, Enum):
    SH = "SH"
    SZ = "SZ"
    BJ = "BJ"


class AssetType(str, Enum):
    A_SHARE = "A_SHARE"
    ETF = "ETF"
    INDEX = "INDEX"


class Timeframe(str, Enum):
    DAILY = "DAILY"
    MINUTE_1 = "MINUTE_1"
    MINUTE_5 = "MINUTE_5"
    MINUTE_15 = "MINUTE_15"
    MINUTE_30 = "MINUTE_30"
    MINUTE_60 = "MINUTE_60"

    @property
    def duration(self) -> timedelta | None:
        minutes = {
            Timeframe.MINUTE_1: 1,
            Timeframe.MINUTE_5: 5,
            Timeframe.MINUTE_15: 15,
            Timeframe.MINUTE_30: 30,
            Timeframe.MINUTE_60: 60,
        }.get(self)
        return timedelta(minutes=minutes) if minutes is not None else None


class AdjustmentMode(str, Enum):
    RAW = "RAW"
    PIT_ADJUSTED = "PIT_ADJUSTED"
    RESEARCH_BACK_ADJUSTED = "RESEARCH_BACK_ADJUSTED"


class TradingStatus(str, Enum):
    TRADING = "TRADING"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class PriceLimitState(str, Enum):
    NORMAL = "NORMAL"
    LIMIT_UP = "LIMIT_UP"
    LIMIT_DOWN = "LIMIT_DOWN"
    UNKNOWN = "UNKNOWN"


class VolumeUnit(str, Enum):
    SHARES = "SHARES"
    LOTS = "LOTS"


def require_utc_second(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    if value.microsecond != 0:
        raise ValueError(f"{label} must have whole-second precision")


def parse_utc_second(label: str, value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be canonical UTC RFC3339")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be canonical UTC RFC3339") from exc
    require_utc_second(label, parsed)
    if canonical_datetime(parsed) != value:
        raise ValueError(f"{label} is not canonical")
    return parsed


def require_decimal(
    label: str,
    value: Decimal,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not value.is_finite() or not isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")
    if non_negative and value < 0:
        raise ValueError(f"{label} must be non-negative")


def require_canonical_symbol(symbol: str, exchange: Exchange) -> None:
    if (
        not isinstance(symbol, str)
        or len(symbol) != 9
        or symbol[6] != "."
        or not symbol[:6].isdigit()
    ):
        raise ValueError("symbol must use canonical six-digit EXCHANGE suffix form")
    if symbol[7:] != exchange.value:
        raise ValueError("symbol exchange suffix does not match exchange")


def _optional_decimal(value: object, label: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a canonical decimal string or null")
    try:
        return Decimal(value)
    except Exception as exc:
        raise ValueError(f"{label} must be a canonical decimal string") from exc


@dataclass(frozen=True, slots=True)
class CanonicalMarketBar:
    schema_version: str
    bar_id: ArtifactId
    content_hash: str
    symbol: str
    exchange: Exchange
    asset_type: AssetType
    timeframe: Timeframe
    market_date: date
    event_start: datetime
    event_end: datetime
    available_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    previous_close: Decimal | None
    volume: Decimal
    volume_unit: VolumeUnit
    amount: Decimal | None
    turnover_rate: Decimal | None
    adjustment_mode: AdjustmentMode
    adjustment_factor: Decimal
    adjustment_factor_id: ArtifactId | None
    adjustment_factor_hash: str | None
    trading_status: TradingStatus
    price_limit_state: PriceLimitState
    source_artifact_id: ArtifactId
    source_content_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != MARKET_BAR_SCHEMA_VERSION:
            raise ValueError("unsupported Canonical Market Bar schema")
        require_sha256("content_hash", self.content_hash)
        require_canonical_symbol(self.symbol, self.exchange)
        for label, timestamp in (
            ("event_start", self.event_start),
            ("event_end", self.event_end),
            ("available_at", self.available_at),
        ):
            require_utc_second(label, timestamp)
        if self.event_start >= self.event_end:
            raise ValueError("event_start must precede event_end")
        if self.available_at < self.event_end:
            raise ValueError("available_at cannot precede event_end")
        if self.event_start.astimezone(_SHANGHAI).date() != self.market_date:
            raise ValueError("market_date must match event_start in Asia/Shanghai")
        duration = self.timeframe.duration
        if duration is not None and self.event_end - self.event_start != duration:
            raise ValueError("event interval does not match timeframe duration")
        for label, price in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            require_decimal(label, price, positive=True)
        if self.previous_close is not None:
            require_decimal("previous_close", self.previous_close, positive=True)
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("high is below another OHLC value")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("low exceeds another OHLC value")
        require_decimal("volume", self.volume, non_negative=True)
        if self.amount is not None:
            require_decimal("amount", self.amount, non_negative=True)
        if self.turnover_rate is not None:
            require_decimal("turnover_rate", self.turnover_rate, non_negative=True)
        require_decimal("adjustment_factor", self.adjustment_factor, positive=True)
        if self.adjustment_mode is AdjustmentMode.RAW:
            if self.adjustment_factor != Decimal("1"):
                raise ValueError("RAW adjustment factor must equal one")
            if self.adjustment_factor_id is not None or self.adjustment_factor_hash is not None:
                raise ValueError("RAW bars cannot bind adjustment factor evidence")
        elif self.adjustment_factor_id is None or self.adjustment_factor_hash is None:
            raise ValueError("adjusted bars require adjustment factor evidence")
        if (self.adjustment_factor_id is None) != (self.adjustment_factor_hash is None):
            raise ValueError("adjustment factor identity and hash must be paired")
        if self.adjustment_factor_hash is not None:
            require_sha256("adjustment_factor_hash", self.adjustment_factor_hash)
        require_sha256("source_content_hash", self.source_content_hash)

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        exchange: Exchange,
        asset_type: AssetType,
        timeframe: Timeframe,
        market_date: date,
        event_start: datetime,
        event_end: datetime,
        available_at: datetime,
        open: Decimal,
        high: Decimal,
        low: Decimal,
        close: Decimal,
        previous_close: Decimal | None,
        volume: Decimal,
        volume_unit: VolumeUnit,
        amount: Decimal | None,
        turnover_rate: Decimal | None,
        adjustment_mode: AdjustmentMode,
        adjustment_factor: Decimal,
        trading_status: TradingStatus,
        price_limit_state: PriceLimitState,
        source_artifact_id: ArtifactId,
        source_content_hash: str,
        adjustment_factor_id: ArtifactId | None = None,
        adjustment_factor_hash: str | None = None,
    ) -> CanonicalMarketBar:
        payload = cls._payload(
            symbol=symbol,
            exchange=exchange,
            asset_type=asset_type,
            timeframe=timeframe,
            market_date=market_date,
            event_start=event_start,
            event_end=event_end,
            available_at=available_at,
            open=open,
            high=high,
            low=low,
            close=close,
            previous_close=previous_close,
            volume=volume,
            volume_unit=volume_unit,
            amount=amount,
            turnover_rate=turnover_rate,
            adjustment_mode=adjustment_mode,
            adjustment_factor=adjustment_factor,
            adjustment_factor_id=adjustment_factor_id,
            adjustment_factor_hash=adjustment_factor_hash,
            trading_status=trading_status,
            price_limit_state=price_limit_state,
            source_artifact_id=source_artifact_id,
            source_content_hash=source_content_hash,
        )
        content_hash = canonical_hash(payload)
        result = cls(
            schema_version=MARKET_BAR_SCHEMA_VERSION,
            bar_id=ArtifactId(f"market-bar-{content_hash.split(':', 1)[1][:24]}"),
            content_hash=content_hash,
            symbol=symbol,
            exchange=exchange,
            asset_type=asset_type,
            timeframe=timeframe,
            market_date=market_date,
            event_start=event_start,
            event_end=event_end,
            available_at=available_at,
            open=open,
            high=high,
            low=low,
            close=close,
            previous_close=previous_close,
            volume=volume,
            volume_unit=volume_unit,
            amount=amount,
            turnover_rate=turnover_rate,
            adjustment_mode=adjustment_mode,
            adjustment_factor=adjustment_factor,
            adjustment_factor_id=adjustment_factor_id,
            adjustment_factor_hash=adjustment_factor_hash,
            trading_status=trading_status,
            price_limit_state=price_limit_state,
            source_artifact_id=source_artifact_id,
            source_content_hash=source_content_hash,
        )
        result.verify_identity()
        return result

    @staticmethod
    def _payload(**values: Any) -> dict[str, Any]:
        return {
            "schema_version": MARKET_BAR_SCHEMA_VERSION,
            "symbol": values["symbol"],
            "exchange": values["exchange"].value,
            "asset_type": values["asset_type"].value,
            "timeframe": values["timeframe"].value,
            "market_date": values["market_date"].isoformat(),
            "event_start": canonical_datetime(values["event_start"]),
            "event_end": canonical_datetime(values["event_end"]),
            "available_at": canonical_datetime(values["available_at"]),
            "open": str(values["open"]),
            "high": str(values["high"]),
            "low": str(values["low"]),
            "close": str(values["close"]),
            "previous_close": (
                str(values["previous_close"])
                if values["previous_close"] is not None
                else None
            ),
            "volume": str(values["volume"]),
            "volume_unit": values["volume_unit"].value,
            "amount": str(values["amount"]) if values["amount"] is not None else None,
            "turnover_rate": (
                str(values["turnover_rate"])
                if values["turnover_rate"] is not None
                else None
            ),
            "adjustment_mode": values["adjustment_mode"].value,
            "adjustment_factor": str(values["adjustment_factor"]),
            "adjustment_factor_id": (
                str(values["adjustment_factor_id"])
                if values["adjustment_factor_id"] is not None
                else None
            ),
            "adjustment_factor_hash": values["adjustment_factor_hash"],
            "trading_status": values["trading_status"].value,
            "price_limit_state": values["price_limit_state"].value,
            "source_artifact_id": str(values["source_artifact_id"]),
            "source_content_hash": values["source_content_hash"],
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self._payload(
            symbol=self.symbol,
            exchange=self.exchange,
            asset_type=self.asset_type,
            timeframe=self.timeframe,
            market_date=self.market_date,
            event_start=self.event_start,
            event_end=self.event_end,
            available_at=self.available_at,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            previous_close=self.previous_close,
            volume=self.volume,
            volume_unit=self.volume_unit,
            amount=self.amount,
            turnover_rate=self.turnover_rate,
            adjustment_mode=self.adjustment_mode,
            adjustment_factor=self.adjustment_factor,
            adjustment_factor_id=self.adjustment_factor_id,
            adjustment_factor_hash=self.adjustment_factor_hash,
            trading_status=self.trading_status,
            price_limit_state=self.price_limit_state,
            source_artifact_id=self.source_artifact_id,
            source_content_hash=self.source_content_hash,
        )

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Canonical Market Bar payload hash mismatch")
        expected_id = f"market-bar-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.bar_id) != expected_id:
            raise ValueError("Canonical Market Bar identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "bar_id": str(self.bar_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> CanonicalMarketBar:
        expected = {
            "bar_id",
            "content_hash",
            "schema_version",
            "symbol",
            "exchange",
            "asset_type",
            "timeframe",
            "market_date",
            "event_start",
            "event_end",
            "available_at",
            "open",
            "high",
            "low",
            "close",
            "previous_close",
            "volume",
            "volume_unit",
            "amount",
            "turnover_rate",
            "adjustment_mode",
            "adjustment_factor",
            "adjustment_factor_id",
            "adjustment_factor_hash",
            "trading_status",
            "price_limit_state",
            "source_artifact_id",
            "source_content_hash",
        }
        if set(payload) != expected:
            raise ValueError("Canonical Market Bar fields mismatch")
        factor_id = payload["adjustment_factor_id"]
        result = cls(
            schema_version=str(payload["schema_version"]),
            bar_id=ArtifactId(str(payload["bar_id"])),
            content_hash=str(payload["content_hash"]),
            symbol=str(payload["symbol"]),
            exchange=Exchange(str(payload["exchange"])),
            asset_type=AssetType(str(payload["asset_type"])),
            timeframe=Timeframe(str(payload["timeframe"])),
            market_date=date.fromisoformat(str(payload["market_date"])),
            event_start=parse_utc_second("event_start", payload["event_start"]),
            event_end=parse_utc_second("event_end", payload["event_end"]),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            open=Decimal(str(payload["open"])),
            high=Decimal(str(payload["high"])),
            low=Decimal(str(payload["low"])),
            close=Decimal(str(payload["close"])),
            previous_close=_optional_decimal(payload["previous_close"], "previous_close"),
            volume=Decimal(str(payload["volume"])),
            volume_unit=VolumeUnit(str(payload["volume_unit"])),
            amount=_optional_decimal(payload["amount"], "amount"),
            turnover_rate=_optional_decimal(payload["turnover_rate"], "turnover_rate"),
            adjustment_mode=AdjustmentMode(str(payload["adjustment_mode"])),
            adjustment_factor=Decimal(str(payload["adjustment_factor"])),
            adjustment_factor_id=(
                ArtifactId(str(factor_id)) if factor_id is not None else None
            ),
            adjustment_factor_hash=(
                str(payload["adjustment_factor_hash"])
                if payload["adjustment_factor_hash"] is not None
                else None
            ),
            trading_status=TradingStatus(str(payload["trading_status"])),
            price_limit_state=PriceLimitState(str(payload["price_limit_state"])),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            source_content_hash=str(payload["source_content_hash"]),
        )
        result.verify_identity()
        return result
