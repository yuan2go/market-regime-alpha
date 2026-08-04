"""Versioned price-adjustment evidence and policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.market_data.contracts import (
    AdjustmentMode,
    Exchange,
    parse_utc_second,
    require_canonical_symbol,
    require_decimal,
    require_utc_second,
)


ADJUSTMENT_FACTOR_SCHEMA_VERSION = "adjustment-factor-evidence-v1"
ADJUSTMENT_POLICY_SCHEMA_VERSION = "price-adjustment-policy-v1"


@dataclass(frozen=True, slots=True)
class AdjustmentFactorEvidence:
    schema_version: str
    factor_id: ArtifactId
    content_hash: str
    symbol: str
    exchange: Exchange
    effective_date: date
    available_at: datetime
    factor: Decimal
    source_artifact_id: ArtifactId
    source_content_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != ADJUSTMENT_FACTOR_SCHEMA_VERSION:
            raise ValueError("unsupported Adjustment Factor Evidence schema")
        require_sha256("content_hash", self.content_hash)
        require_canonical_symbol(self.symbol, self.exchange)
        require_utc_second("available_at", self.available_at)
        require_decimal("factor", self.factor, positive=True)
        require_sha256("source_content_hash", self.source_content_hash)

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        exchange: Exchange,
        effective_date: date,
        available_at: datetime,
        factor: Decimal,
        source_artifact_id: ArtifactId,
        source_content_hash: str,
    ) -> AdjustmentFactorEvidence:
        payload = {
            "schema_version": ADJUSTMENT_FACTOR_SCHEMA_VERSION,
            "symbol": symbol,
            "exchange": exchange.value,
            "effective_date": effective_date.isoformat(),
            "available_at": canonical_datetime(available_at),
            "factor": str(factor),
            "source_artifact_id": str(source_artifact_id),
            "source_content_hash": source_content_hash,
        }
        content_hash = canonical_hash(payload)
        result = cls(
            schema_version=ADJUSTMENT_FACTOR_SCHEMA_VERSION,
            factor_id=ArtifactId(
                f"adjustment-factor-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            symbol=symbol,
            exchange=exchange,
            effective_date=effective_date,
            available_at=available_at,
            factor=factor,
            source_artifact_id=source_artifact_id,
            source_content_hash=source_content_hash,
        )
        result.verify_identity()
        return result
    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "exchange": self.exchange.value,
            "effective_date": self.effective_date.isoformat(),
            "available_at": canonical_datetime(self.available_at),
            "factor": str(self.factor),
            "source_artifact_id": str(self.source_artifact_id),
            "source_content_hash": self.source_content_hash,
        }

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Adjustment Factor Evidence payload hash mismatch")
        expected_id = f"adjustment-factor-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.factor_id) != expected_id:
            raise ValueError("Adjustment Factor Evidence identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "factor_id": str(self.factor_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> AdjustmentFactorEvidence:
        expected = {
            "schema_version",
            "factor_id",
            "content_hash",
            "symbol",
            "exchange",
            "effective_date",
            "available_at",
            "factor",
            "source_artifact_id",
            "source_content_hash",
        }
        if set(payload) != expected:
            raise ValueError("Adjustment Factor Evidence fields mismatch")
        result = cls(
            schema_version=str(payload["schema_version"]),
            factor_id=ArtifactId(str(payload["factor_id"])),
            content_hash=str(payload["content_hash"]),
            symbol=str(payload["symbol"]),
            exchange=Exchange(str(payload["exchange"])),
            effective_date=date.fromisoformat(str(payload["effective_date"])),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            factor=Decimal(str(payload["factor"])),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            source_content_hash=str(payload["source_content_hash"]),
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class PriceAdjustmentPolicy:
    schema_version: str
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    mode: AdjustmentMode
    factors: tuple[AdjustmentFactorEvidence, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != ADJUSTMENT_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported Price Adjustment Policy schema")
        require_sha256("policy_hash", self.policy_hash)
        require_text("policy_version", self.policy_version)
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("limitations must be sorted")
        keys = tuple((item.symbol, item.effective_date) for item in self.factors)
        if keys != tuple(sorted(keys)):
            raise ValueError("adjustment factors must be sorted")
        if len(keys) != len(set(keys)):
            raise ValueError("adjustment factors must be unique by symbol/effective date")
        for item in self.factors:
            item.verify_identity()
        if self.mode is AdjustmentMode.RAW and self.factors:
            raise ValueError("RAW policy cannot contain adjustment factors")
        if self.mode is AdjustmentMode.PIT_ADJUSTED and not self.factors:
            raise ValueError("PIT_ADJUSTED policy requires factor evidence")
        if self.mode is AdjustmentMode.RESEARCH_BACK_ADJUSTED and (
            "RESEARCH_BACK_ADJUSTED_NOT_DECISION_RUNTIME_ELIGIBLE"
            not in self.limitations
        ):
            raise ValueError("research back-adjusted policy must declare runtime limitation")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        mode: AdjustmentMode,
        factors: tuple[AdjustmentFactorEvidence, ...],
        limitations: tuple[str, ...],
    ) -> PriceAdjustmentPolicy:
        ordered_factors = tuple(
            sorted(factors, key=lambda item: (item.symbol, item.effective_date))
        )
        ordered_limitations = tuple(sorted(limitations))
        payload = {
            "schema_version": ADJUSTMENT_POLICY_SCHEMA_VERSION,
            "policy_version": policy_version,
            "mode": mode.value,
            "factors": [item.to_canonical_dict() for item in ordered_factors],
            "limitations": list(ordered_limitations),
        }
        policy_hash = canonical_hash(payload)
        result = cls(
            schema_version=ADJUSTMENT_POLICY_SCHEMA_VERSION,
            policy_id=ArtifactId(
                f"price-adjustment-policy-{policy_hash.split(':', 1)[1][:24]}"
            ),
            policy_hash=policy_hash,
            policy_version=policy_version,
            mode=mode,
            factors=ordered_factors,
            limitations=ordered_limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "mode": self.mode.value,
            "factors": [item.to_canonical_dict() for item in self.factors],
            "limitations": list(self.limitations),
        }

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.policy_hash != expected_hash:
            raise ValueError("Price Adjustment Policy payload hash mismatch")
        expected_id = (
            f"price-adjustment-policy-{expected_hash.split(':', 1)[1][:24]}"
        )
        if str(self.policy_id) != expected_id:
            raise ValueError("Price Adjustment Policy identity mismatch")

    def validate_for_decision_runtime(self) -> None:
        self.verify_identity()
        if self.mode is AdjustmentMode.RESEARCH_BACK_ADJUSTED:
            raise ValueError("RESEARCH_BACK_ADJUSTED cannot enter Decision Runtime")

    def factor_for(
        self,
        *,
        symbol: str,
        market_date: date,
        decision_time: datetime,
    ) -> AdjustmentFactorEvidence:
        require_utc_second("decision_time", decision_time)
        matches = tuple(
            item
            for item in self.factors
            if item.symbol == symbol and item.effective_date <= market_date
        )
        if not matches:
            raise ValueError("adjustment factor is not established for symbol/date")
        available = tuple(item for item in matches if item.available_at <= decision_time)
        if not available:
            raise ValueError("adjustment factor became available after DecisionTime")
        return max(available, key=lambda item: item.effective_date)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> PriceAdjustmentPolicy:
        expected = {
            "schema_version",
            "policy_id",
            "policy_hash",
            "policy_version",
            "mode",
            "factors",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Price Adjustment Policy fields mismatch")
        raw_factors = payload["factors"]
        raw_limitations = payload["limitations"]
        if not isinstance(raw_factors, list) or not all(
            isinstance(item, dict) for item in raw_factors
        ):
            raise ValueError("factors must be an array of objects")
        if not isinstance(raw_limitations, list) or not all(
            isinstance(item, str) for item in raw_limitations
        ):
            raise ValueError("limitations must be an array of strings")
        result = cls(
            schema_version=str(payload["schema_version"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            policy_version=str(payload["policy_version"]),
            mode=AdjustmentMode(str(payload["mode"])),
            factors=tuple(
                AdjustmentFactorEvidence.from_canonical_dict(item)
                for item in raw_factors
            ),
            limitations=tuple(raw_limitations),
        )
        result.verify_identity()
        return result
