"""Content-addressed Decision Price Snapshot for Phase D plumbing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite import (
    PublicCompositeProviderResult,
    TradingStatus,
)
from market_regime_alpha.data.source_manifest import (
    SourceFieldQualityStatus,
    SourceManifest,
)
from market_regime_alpha.daily_decision._support import (
    canonical_hash,
    require_finite,
    require_strings,
    require_text,
)


class DecisionPriceQuality(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class DecisionPriceObservation:
    symbol: str
    provider_id: ProviderId
    source_artifact_id: ArtifactId
    event_time: datetime | None
    available_time: AvailabilityTime | None
    price: float | None
    quality: DecisionPriceQuality
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if self.event_time is not None and (
            self.event_time.tzinfo is None
            or self.event_time.utcoffset() is None
        ):
            raise ValueError("event_time must be timezone-aware")
        if self.price is not None:
            value = require_finite("price", self.price)
            if value <= 0:
                raise ValueError("price must be positive")
            object.__setattr__(self, "price", value)
        if not isinstance(self.quality, DecisionPriceQuality):
            raise TypeError("quality must be a DecisionPriceQuality")
        require_strings("reason_codes", self.reason_codes)
        if self.quality is DecisionPriceQuality.AVAILABLE:
            if (
                self.price is None
                or self.event_time is None
                or self.available_time is None
                or self.reason_codes
            ):
                raise ValueError("AVAILABLE Decision Price requires complete evidence")
        elif not self.reason_codes:
            raise ValueError("INSUFFICIENT Decision Price requires reasons")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "provider_id": str(self.provider_id),
            "source_artifact_id": str(self.source_artifact_id),
            "event_time": (
                self.event_time.isoformat() if self.event_time is not None else None
            ),
            "available_time": (
                self.available_time.isoformat()
                if self.available_time is not None
                else None
            ),
            "price": self.price,
            "quality": self.quality.value,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> DecisionPriceObservation:
        expected = {
            "symbol",
            "provider_id",
            "source_artifact_id",
            "event_time",
            "available_time",
            "price",
            "quality",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("Decision Price Observation fields mismatch")
        event = payload["event_time"]
        available = payload["available_time"]
        price = payload["price"]
        return cls(
            symbol=str(payload["symbol"]),
            provider_id=ProviderId(str(payload["provider_id"])),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            event_time=(
                datetime.fromisoformat(str(event)) if event is not None else None
            ),
            available_time=(
                AvailabilityTime(datetime.fromisoformat(str(available)))
                if available is not None
                else None
            ),
            price=float(price) if price is not None else None,
            quality=DecisionPriceQuality(str(payload["quality"])),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class DecisionPriceSnapshot:
    SCHEMA_VERSION = "phase-d-decision-price-snapshot-v1"

    source_manifest_id: ArtifactId
    decision_time: DecisionTime
    observations: tuple[DecisionPriceObservation, ...]
    data_eligibility: DataEligibility
    content_hash: str = field(init=False)
    decision_snapshot_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        if tuple(item.symbol for item in self.observations) != tuple(
            sorted(item.symbol for item in self.observations)
        ):
            raise ValueError("Decision Price observations must be ordered")
        symbols = tuple(item.symbol for item in self.observations)
        if len(symbols) != len(set(symbols)):
            raise ValueError("Decision Price observations must be unique")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Decision Price Snapshot is EXPLORATORY-only")
        content_hash = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "decision_snapshot_id",
            ArtifactId(f"decision-price-{content_hash.split(':', 1)[1][:24]}"),
        )

    def observation_for(
        self,
        symbol: str,
    ) -> DecisionPriceObservation | None:
        return next(
            (item for item in self.observations if item.symbol == symbol),
            None,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "source_manifest_id": str(self.source_manifest_id),
            "decision_time": self.decision_time.isoformat(),
            "observations": [
                item.to_canonical_dict() for item in self.observations
            ],
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "decision_snapshot_id": str(self.decision_snapshot_id),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> DecisionPriceSnapshot:
        expected = {
            "schema_version",
            "source_manifest_id",
            "decision_time",
            "observations",
            "data_eligibility",
            "content_hash",
            "decision_snapshot_id",
        }
        if set(payload) != expected or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("Decision Price Snapshot schema mismatch")
        snapshot = cls(
            source_manifest_id=ArtifactId(str(payload["source_manifest_id"])),
            decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["decision_time"]))
            ),
            observations=tuple(
                DecisionPriceObservation.from_canonical_dict(item)
                for item in payload["observations"]
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if (
            snapshot.content_hash != payload["content_hash"]
            or str(snapshot.decision_snapshot_id)
            != payload["decision_snapshot_id"]
        ):
            raise ValueError("Decision Price Snapshot identity mismatch")
        return snapshot


def build_decision_price_snapshot(
    *,
    provider_result: PublicCompositeProviderResult,
    source_manifest: SourceManifest,
) -> DecisionPriceSnapshot:
    if provider_result.decision_time != source_manifest.decision_time:
        raise ValueError("Decision Price source Decision Time mismatch")
    if not {
        item.source_artifact_id for item in provider_result.raw_payloads
    }.issubset({item.artifact_id for item in source_manifest.source_artifacts}):
        raise ValueError("SourceManifest omits Decision Price source evidence")
    payload_by_id = {
        item.source_artifact_id: item for item in provider_result.raw_payloads
    }
    observations: list[DecisionPriceObservation] = []
    for quote in sorted(provider_result.quotes, key=lambda item: item.symbol):
        reasons: list[str] = []
        if quote.price is None:
            reasons.append("PRICE_UNAVAILABLE")
        if quote.event_time is None:
            reasons.append("QUOTE_EVENT_TIME_UNKNOWN")
        elif quote.event_time > provider_result.decision_time.value:
            reasons.append("EVENT_AFTER_DECISION")
        if quote.available_time is None:
            reasons.append("AVAILABLE_TIME_UNKNOWN")
        elif quote.available_time.as_utc() > provider_result.decision_time.as_utc():
            reasons.append("AVAILABLE_AFTER_DECISION")
        if quote.trading_status is not TradingStatus.TRADING:
            reasons.append("TRADING_STATUS_NOT_CONFIRMED")
        manifest_price = next(
            (
                item
                for item in source_manifest.fields
                if item.symbol == quote.symbol
                and item.field_id == "price"
            ),
            None,
        )
        if manifest_price is None:
            reasons.append("PRICE_LINEAGE_MISSING")
        elif (
            manifest_price.quality_status
            is SourceFieldQualityStatus.INSUFFICIENT
        ):
            reasons.extend(manifest_price.reason_codes or ("PRICE_INSUFFICIENT",))
        source = payload_by_id[quote.source_artifact_id]
        observations.append(
            DecisionPriceObservation(
                symbol=quote.symbol,
                provider_id=source.provider_id,
                source_artifact_id=source.source_artifact_id,
                event_time=quote.event_time,
                available_time=quote.available_time,
                price=quote.price,
                quality=(
                    DecisionPriceQuality.AVAILABLE
                    if not reasons
                    else DecisionPriceQuality.INSUFFICIENT
                ),
                reason_codes=tuple(dict.fromkeys(reasons)),
            )
        )
    return DecisionPriceSnapshot(
        source_manifest_id=source_manifest.source_manifest_id,
        decision_time=provider_result.decision_time,
        observations=tuple(observations),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
