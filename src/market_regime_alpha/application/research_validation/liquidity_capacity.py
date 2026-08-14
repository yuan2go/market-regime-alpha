"""Liquidity and capacity engineering with explicit evidence provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from statistics import median
from typing import Any, Iterable, Mapping

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ValidationArtifactReference,
    content_identity,
    decimal_text,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text
from market_regime_alpha.market_data import CanonicalMarketBar, PriceLimitState, TradingStatus


class CapacityValueProvenance(str, Enum):
    OBSERVED_FACT = "OBSERVED_FACT"
    ENGINEERING_ASSUMPTION = "ENGINEERING_ASSUMPTION"
    CALIBRATED_PARAMETER = "CALIBRATED_PARAMETER"


@dataclass(frozen=True, slots=True)
class CapacityParameter:
    name: str
    value: Decimal
    provenance: CapacityValueProvenance
    evidence_reference: ValidationArtifactReference | None = None

    def __post_init__(self) -> None:
        require_text("name", self.name)
        if self.provenance is CapacityValueProvenance.CALIBRATED_PARAMETER and self.evidence_reference is None:
            raise ValueError("calibrated Capacity parameter requires evidence")
        if (
            self.provenance is CapacityValueProvenance.CALIBRATED_PARAMETER
            and self.evidence_reference is not None
            and self.evidence_reference.artifact_kind != "CALIBRATION_ARTIFACT"
        ):
            raise ValueError("calibrated Capacity parameter requires Calibration Artifact")
        if self.provenance is CapacityValueProvenance.OBSERVED_FACT:
            raise ValueError("configuration parameter cannot masquerade as observed fact")


@dataclass(frozen=True, slots=True)
class LiquidityCapacityProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    protocol_version: str
    parameters: tuple[CapacityParameter, ...]
    adv_short_sessions: int
    adv_long_sessions: int
    created_at: datetime
    schema_version: str = "liquidity-capacity-protocol/v1"

    def __post_init__(self) -> None:
        require_sha256("protocol_hash", self.protocol_hash)
        require_text("protocol_version", self.protocol_version)
        if self.schema_version != "liquidity-capacity-protocol/v1":
            raise ValueError("unsupported Liquidity/Capacity Protocol schema")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("Liquidity/Capacity Protocol time must be timezone-aware")
        if self.parameters != tuple(sorted(self.parameters, key=lambda item: item.name)):
            raise ValueError("Liquidity/Capacity Protocol parameters must be sorted")
        if len({item.name for item in self.parameters}) != len(self.parameters):
            raise ValueError("Liquidity/Capacity parameters must be unique")
        if self.adv_short_sessions != 5 or self.adv_long_sessions != 20:
            raise ValueError("Current Liquidity/Capacity contract requires ADV5 and ADV20")
        if canonical_hash(self.identity_payload()) != self.protocol_hash:
            raise ValueError("Liquidity/Capacity Protocol hash mismatch")
        if self.protocol_id != ArtifactId(
            f"liquidity-capacity-protocol:{self.protocol_hash[7:]}"
        ):
            raise ValueError("Liquidity/Capacity Protocol identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        parameters: tuple[CapacityParameter, ...],
        created_at: datetime,
        adv_short_sessions: int = 5,
        adv_long_sessions: int = 20,
    ) -> LiquidityCapacityProtocol:
        ordered = tuple(sorted(parameters, key=lambda item: item.name))
        if len({item.name for item in ordered}) != len(ordered):
            raise ValueError("Liquidity/Capacity parameters must be unique")
        if adv_short_sessions != 5 or adv_long_sessions != 20:
            raise ValueError("Current Liquidity/Capacity contract requires ADV5 and ADV20")
        payload = _protocol_payload(
            protocol_version=protocol_version,
            parameters=ordered,
            adv_short_sessions=adv_short_sessions,
            adv_long_sessions=adv_long_sessions,
            created_at=created_at,
        )
        artifact_id, digest = content_identity("liquidity-capacity-protocol", payload)
        return cls(artifact_id, digest, protocol_version, ordered, adv_short_sessions, adv_long_sessions, created_at)

    def identity_payload(self) -> dict[str, Any]:
        return _protocol_payload(
            protocol_version=self.protocol_version,
            parameters=self.parameters,
            adv_short_sessions=self.adv_short_sessions,
            adv_long_sessions=self.adv_long_sessions,
            created_at=self.created_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": str(self.protocol_id),
            "protocol_hash": self.protocol_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> LiquidityCapacityProtocol:
        raw_parameters = value.get("parameters")
        if not isinstance(raw_parameters, (list, tuple)):
            raise ValueError("Liquidity/Capacity parameters are malformed")
        return cls(
            protocol_id=ArtifactId(str(value["protocol_id"])),
            protocol_hash=str(value["protocol_hash"]),
            protocol_version=str(value["protocol_version"]),
            parameters=tuple(
                CapacityParameter(
                    name=str(_mapping(item)["name"]),
                    value=Decimal(str(_mapping(item)["value"])),
                    provenance=CapacityValueProvenance(
                        str(_mapping(item)["provenance"])
                    ),
                    evidence_reference=(
                        None
                        if _mapping(item).get("evidence_reference") is None
                        else ValidationArtifactReference.from_canonical_dict(
                            _mapping(_mapping(item)["evidence_reference"])
                        )
                    ),
                )
                for item in raw_parameters
            ),
            adv_short_sessions=int(value["adv_short_sessions"]),
            adv_long_sessions=int(value["adv_long_sessions"]),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            schema_version=str(value["schema"]),
        )


@dataclass(frozen=True, slots=True)
class LiquidityCapacityAssessment:
    assessment_id: ArtifactId
    assessment_hash: str
    symbol: str
    as_of_date: date
    market_data_reference: ValidationArtifactReference
    protocol_reference: ValidationArtifactReference
    adv5: Decimal | None
    adv20: Decimal | None
    median_amount: Decimal | None
    turnover_rate: Decimal | None
    requested_position: Decimal
    requested_order: Decimal
    participation_rate: Decimal | None
    position_adv_ratio: Decimal | None
    order_adv_ratio: Decimal | None
    limit_state: str
    suspended: bool
    estimated_slippage_bps: Decimal | None
    estimated_market_impact_bps: Decimal | None
    fillability: Decimal
    capacity_ceiling: Decimal | None
    parameters: tuple[CapacityParameter, ...]
    observed_fields: tuple[str, ...]
    assumption_fields: tuple[str, ...]
    calibrated_fields: tuple[str, ...]
    reason_codes: tuple[str, ...]
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "liquidity-capacity-assessment/v1"

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_sha256("assessment_hash", self.assessment_hash)
        if not Decimal("0") <= self.fillability <= Decimal("1"):
            raise ValueError("fillability must be within [0, 1]")
        if self.requested_position < 0 or self.requested_order < 0:
            raise ValueError("requested values must be non-negative")
        if self.parameters != tuple(sorted(self.parameters, key=lambda item: item.name)):
            raise ValueError("Capacity parameters must be unique and sorted")
        for values in (self.observed_fields, self.assumption_fields, self.calibrated_fields, self.reason_codes, self.limitations):
            if values != tuple(sorted(set(values))):
                raise ValueError("Capacity evidence fields must be unique and sorted")
        if set(self.observed_fields) & (set(self.assumption_fields) | set(self.calibrated_fields)):
            raise ValueError("observed and modeled Capacity fields cannot overlap")
        if canonical_hash(self.identity_payload()) != self.assessment_hash:
            raise ValueError("Liquidity Capacity assessment hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        as_of_date: date,
        market_data_reference: ValidationArtifactReference,
        bars: tuple[CanonicalMarketBar, ...],
        requested_position: Decimal,
        requested_order: Decimal,
        protocol: LiquidityCapacityProtocol,
        created_at: datetime,
    ) -> LiquidityCapacityAssessment:
        parameters = protocol.parameters
        protocol_reference = ValidationArtifactReference("LIQUIDITY_CAPACITY_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
        scoped = tuple(
            sorted((item for item in bars if item.symbol == symbol and item.market_date <= as_of_date), key=lambda item: item.market_date)
        )
        amounts = [item.amount for item in scoped if item.amount is not None]
        adv5 = _mean(amounts[-5:])
        adv20 = _mean(amounts[-20:])
        median_amount = None if not amounts else Decimal(str(median(amounts[-20:])))
        latest = scoped[-1] if scoped else None
        turnover = None if latest is None else latest.turnover_rate
        parameter_map = {item.name: item for item in parameters}
        participation = parameter_map.get("participation_rate")
        impact = parameter_map.get("impact_coefficient_bps")
        slippage = parameter_map.get("slippage_bps")
        capacity = None if adv20 is None or participation is None else adv20 * participation.value
        position_adv = None if adv20 is None or adv20 == 0 else requested_position / adv20
        order_adv = None if adv20 is None or adv20 == 0 else requested_order / adv20
        suspended = latest is None or latest.trading_status is not TradingStatus.TRADING
        limit_state = "UNKNOWN" if latest is None else latest.price_limit_state.value
        limit_blocked = latest is not None and latest.price_limit_state is not PriceLimitState.NORMAL
        if suspended or limit_blocked or adv20 in (None, Decimal("0")):
            fillability = Decimal("0")
        else:
            ratio_penalty = min(Decimal("1"), order_adv or Decimal("0"))
            fillability = max(Decimal("0"), Decimal("1") - ratio_penalty)
        reasons = set()
        if latest is None:
            reasons.add("LIQUIDITY_OBSERVATION_MISSING")
        if suspended:
            reasons.add("SUSPENDED_OR_NOT_NORMAL")
        if limit_blocked:
            reasons.add("PRICE_LIMIT_FILLABILITY_BLOCKED")
        if impact is not None and impact.provenance is CapacityValueProvenance.ENGINEERING_ASSUMPTION:
            reasons.add("IMPACT_PARAMETER_UNCALIBRATED")
        if slippage is not None and slippage.provenance is CapacityValueProvenance.ENGINEERING_ASSUMPTION:
            reasons.add("SLIPPAGE_PARAMETER_UNCALIBRATED")
        calibrated = tuple(sorted(item.name for item in parameters if item.provenance is CapacityValueProvenance.CALIBRATED_PARAMETER))
        assumptions = tuple(sorted(item.name for item in parameters if item.provenance is CapacityValueProvenance.ENGINEERING_ASSUMPTION))
        observed = tuple(sorted(("adv5", "adv20", "limit_state", "median_amount", "suspended", "turnover_rate")))
        values: dict[str, Any] = {
            "symbol": symbol,
            "as_of_date": as_of_date.isoformat(),
            "market_data_reference": market_data_reference.to_canonical_dict(),
            "protocol_reference": protocol_reference.to_canonical_dict(),
            "adv5": decimal_text(adv5),
            "adv20": decimal_text(adv20),
            "median_amount": decimal_text(median_amount),
            "turnover_rate": decimal_text(turnover),
            "requested_position": str(requested_position),
            "requested_order": str(requested_order),
            "participation_rate": None if participation is None else str(participation.value),
            "position_adv_ratio": decimal_text(position_adv),
            "order_adv_ratio": decimal_text(order_adv),
            "limit_state": limit_state,
            "suspended": suspended,
            "estimated_slippage_bps": None if slippage is None else str(slippage.value),
            "estimated_market_impact_bps": None if impact is None or order_adv is None else str(impact.value * order_adv),
            "fillability": str(fillability),
            "capacity_ceiling": decimal_text(capacity),
            "parameters": [_parameter_payload(item) for item in sorted(parameters, key=lambda item: item.name)],
            "observed_fields": list(observed),
            "assumption_fields": list(assumptions),
            "calibrated_fields": list(calibrated),
            "reason_codes": sorted(reasons),
            "created_at": timestamp(created_at),
            "limitations": list(tuple(sorted({*ENGINEERING_LIMITATIONS, "IMPACT_AND_SLIPPAGE_NOT_VALIDATED"}))),
            "schema_version": "liquidity-capacity-assessment/v1",
        }
        artifact_id, digest = content_identity("liquidity-capacity", values)
        return cls(
            artifact_id,
            digest,
            symbol,
            as_of_date,
            market_data_reference,
            protocol_reference,
            adv5,
            adv20,
            median_amount,
            turnover,
            requested_position,
            requested_order,
            None if participation is None else participation.value,
            position_adv,
            order_adv,
            limit_state,
            suspended,
            None if slippage is None else slippage.value,
            None if impact is None or order_adv is None else impact.value * order_adv,
            fillability,
            capacity,
            tuple(sorted(parameters, key=lambda item: item.name)),
            observed,
            assumptions,
            calibrated,
            tuple(sorted(reasons)),
            created_at,
            tuple(sorted({*ENGINEERING_LIMITATIONS, "IMPACT_AND_SLIPPAGE_NOT_VALIDATED"})),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of_date": self.as_of_date.isoformat(),
            "market_data_reference": self.market_data_reference.to_canonical_dict(),
            "protocol_reference": self.protocol_reference.to_canonical_dict(),
            "adv5": decimal_text(self.adv5),
            "adv20": decimal_text(self.adv20),
            "median_amount": decimal_text(self.median_amount),
            "turnover_rate": decimal_text(self.turnover_rate),
            "requested_position": str(self.requested_position),
            "requested_order": str(self.requested_order),
            "participation_rate": decimal_text(self.participation_rate),
            "position_adv_ratio": decimal_text(self.position_adv_ratio),
            "order_adv_ratio": decimal_text(self.order_adv_ratio),
            "limit_state": self.limit_state,
            "suspended": self.suspended,
            "estimated_slippage_bps": decimal_text(self.estimated_slippage_bps),
            "estimated_market_impact_bps": decimal_text(self.estimated_market_impact_bps),
            "fillability": str(self.fillability),
            "capacity_ceiling": decimal_text(self.capacity_ceiling),
            "parameters": [_parameter_payload(item) for item in self.parameters],
            "observed_fields": list(self.observed_fields),
            "assumption_fields": list(self.assumption_fields),
            "calibrated_fields": list(self.calibrated_fields),
            "reason_codes": list(self.reason_codes),
            "created_at": timestamp(self.created_at),
            "limitations": list(self.limitations),
            "schema_version": self.schema_version,
        }


def _parameter_payload(item: CapacityParameter) -> dict[str, Any]:
    return {
        "name": item.name,
        "value": str(item.value),
        "provenance": item.provenance.value,
        "evidence_reference": None if item.evidence_reference is None else item.evidence_reference.to_canonical_dict(),
    }


def _protocol_payload(
    *,
    protocol_version: str,
    parameters: tuple[CapacityParameter, ...],
    adv_short_sessions: int,
    adv_long_sessions: int,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "schema": "liquidity-capacity-protocol/v1",
        "protocol_version": protocol_version,
        "parameters": [_parameter_payload(item) for item in parameters],
        "adv_short_sessions": adv_short_sessions,
        "adv_long_sessions": adv_long_sessions,
        "created_at": timestamp(created_at),
    }


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Liquidity/Capacity payload is not an object")
    return value


def _mean(values: Iterable[Decimal]) -> Decimal | None:
    collected = tuple(values)
    return None if not collected else sum(collected, Decimal("0")) / Decimal(len(collected))
