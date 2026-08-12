"""Owner-bound inputs for automatic Strategy and Portfolio Shadow observations.

The builders in this module do not call providers.  They accept values reloaded
from immutable owners (or a frozen policy), reject future/missing facts, and
produce one content-addressed receipt that can be replayed before a Shadow
operator consumes its payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeCheckpoint,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
    ShadowPortfolioTradeSession,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)


class ObservationKind(str, Enum):
    STRATEGY = "STRATEGY"
    PORTFOLIO = "PORTFOLIO"


class ObservationBuildStatus(str, Enum):
    READY = "READY"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


_STRATEGY_VALUE_NAMES = frozenset(
    {
        "intended_quantity",
        "decision_reference_price",
        "observed_fill_price",
        "fillability",
        "slippage_bps",
        "impact_bps",
        "commission_bps",
        "sessions_held",
        "current_price",
        "signal_reversed",
        "market_deteriorated",
        "theme_deteriorated",
        "capital_deteriorated",
        "exit_cost",
        "mfe",
        "mae",
    }
)

_PORTFOLIO_VALUE_SUFFIXES = frozenset(
    {
        "reference_price",
        "mark_price",
        "average_daily_amount",
        "trading_status",
        "price_limit_state",
        "trade_session",
    }
)


ObservationScalar = str | int | bool | None


@dataclass(frozen=True, slots=True)
class ShadowOwnerLineageRequest:
    """Exact references used to reload the existing Phase D owner chain."""

    decision_reference: ValidationArtifactReference
    panel_reference: ValidationArtifactReference
    candidate_reference: ValidationArtifactReference
    target_protocol_reference: ValidationArtifactReference
    outcome_reference: ValidationArtifactReference
    enrichment_reference: ValidationArtifactReference

    def __post_init__(self) -> None:
        expected = (
            (self.decision_reference, "SHADOW_DECISION"),
            (self.panel_reference, "RESEARCH_PANEL_V2"),
            (self.candidate_reference, "CANDIDATE_SET"),
            (self.target_protocol_reference, "OUTCOME_TARGET_PROTOCOL"),
            (self.outcome_reference, "TARGETED_SHADOW_OUTCOME"),
            (self.enrichment_reference, "PANEL_ENRICHMENT"),
        )
        for reference, kind in expected:
            if reference.artifact_kind != kind:
                raise ValueError(f"Shadow lineage requires {kind}")

    @property
    def references(self) -> tuple[ValidationArtifactReference, ...]:
        return _references(
            (
                self.decision_reference,
                self.panel_reference,
                self.candidate_reference,
                self.target_protocol_reference,
                self.outcome_reference,
                self.enrichment_reference,
            )
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_reference": self.decision_reference.to_canonical_dict(),
            "panel_reference": self.panel_reference.to_canonical_dict(),
            "candidate_reference": self.candidate_reference.to_canonical_dict(),
            "target_protocol_reference": (
                self.target_protocol_reference.to_canonical_dict()
            ),
            "outcome_reference": self.outcome_reference.to_canonical_dict(),
            "enrichment_reference": self.enrichment_reference.to_canonical_dict(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ShadowOwnerLineageRequest:
        expected = {
            "decision_reference",
            "panel_reference",
            "candidate_reference",
            "target_protocol_reference",
            "outcome_reference",
            "enrichment_reference",
        }
        if set(payload) != expected:
            raise ValueError("Shadow lineage fields mismatch")
        return cls(
            decision_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["decision_reference"])
            ),
            panel_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["panel_reference"])
            ),
            candidate_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["candidate_reference"])
            ),
            target_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["target_protocol_reference"])
            ),
            outcome_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["outcome_reference"])
            ),
            enrichment_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["enrichment_reference"])
            ),
        )


@dataclass(frozen=True, slots=True)
class OwnerObservationValue:
    """One value plus the exact owner or policy source that establishes it."""

    name: str
    value: ObservationScalar
    provenance: ShadowParameterProvenance
    source_reference: ValidationArtifactReference | None
    effective_at: datetime
    available_at: datetime
    source_value_path: str

    def __post_init__(self) -> None:
        require_text("Observation value name", self.name)
        require_text("Observation source value path", self.source_value_path)
        _aware("Observation effective_at", self.effective_at)
        _aware("Observation available_at", self.available_at)
        if (
            self.provenance is ShadowParameterProvenance.OBSERVED_FACT
            and self.source_reference is None
        ):
            raise ValueError("Observed Fact requires an owner reference")
        if self.source_reference is None:
            raise ValueError("Observation value requires a policy or owner reference")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "provenance": self.provenance.value,
            "source_reference": (
                None
                if self.source_reference is None
                else self.source_reference.to_canonical_dict()
            ),
            "effective_at": canonical_datetime(self.effective_at),
            "available_at": canonical_datetime(self.available_at),
            "source_value_path": self.source_value_path,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> OwnerObservationValue:
        reference_payload = payload["source_reference"]
        if reference_payload is not None and not isinstance(
            reference_payload, Mapping
        ):
            raise ValueError("Observation source reference must be an object")
        value = payload["value"]
        if value is not None and not isinstance(value, (str, int, bool)):
            raise ValueError("Observation value must be canonical scalar data")
        return cls(
            name=str(payload["name"]),
            value=value,
            provenance=ShadowParameterProvenance(str(payload["provenance"])),
            source_reference=(
                None
                if reference_payload is None
                else ValidationArtifactReference.from_canonical_dict(
                    reference_payload
                )
            ),
            effective_at=datetime.fromisoformat(str(payload["effective_at"])),
            available_at=datetime.fromisoformat(str(payload["available_at"])),
            source_value_path=str(payload["source_value_path"]),
        )


@dataclass(frozen=True, slots=True)
class ShadowObservationPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    intended_quantity: Decimal
    fill_checkpoint: OutcomeCheckpoint
    mark_checkpoint: OutcomeCheckpoint
    trade_session: ShadowPortfolioTradeSession
    fillability: Decimal
    slippage_bps: Decimal
    impact_bps: Decimal
    commission_bps: Decimal
    exit_cost_bps: Decimal
    created_at: datetime
    schema_version: str = "shadow-observation-policy/v1"

    def __post_init__(self) -> None:
        require_sha256("Shadow Observation policy hash", self.policy_hash)
        require_text("Shadow Observation policy version", self.policy_version)
        _aware("Shadow Observation policy created_at", self.created_at)
        if self.intended_quantity <= 0:
            raise ValueError("Shadow Observation intended quantity must be positive")
        if self.fill_checkpoint is self.mark_checkpoint:
            raise ValueError("Shadow Observation fill and mark checkpoints must differ")
        if self.trade_session is ShadowPortfolioTradeSession.UNKNOWN:
            raise ValueError("Shadow Observation trade session cannot be UNKNOWN")
        if not Decimal("0") <= self.fillability <= Decimal("1"):
            raise ValueError("Shadow Observation fillability must be within [0, 1]")
        for value in (
            self.slippage_bps,
            self.impact_bps,
            self.commission_bps,
            self.exit_cost_bps,
        ):
            if not value.is_finite() or value < 0:
                raise ValueError("Shadow Observation cost assumptions must be finite")
        if canonical_hash(self.identity_payload()) != self.policy_hash:
            raise ValueError("Shadow Observation policy hash mismatch")
        if str(self.policy_id) != f"shadow-observation-policy:{self.policy_hash[7:]}":
            raise ValueError("Shadow Observation policy id mismatch")

    @classmethod
    def create(cls, **values: Any) -> ShadowObservationPolicy:
        payload = _policy_payload(**values)
        digest = canonical_hash(payload)
        return cls(
            policy_id=ArtifactId(f"shadow-observation-policy:{digest[7:]}"),
            policy_hash=digest,
            **values,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _policy_payload(
            policy_version=self.policy_version,
            intended_quantity=self.intended_quantity,
            fill_checkpoint=self.fill_checkpoint,
            mark_checkpoint=self.mark_checkpoint,
            trade_session=self.trade_session,
            fillability=self.fillability,
            slippage_bps=self.slippage_bps,
            impact_bps=self.impact_bps,
            commission_bps=self.commission_bps,
            exit_cost_bps=self.exit_cost_bps,
            created_at=self.created_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ShadowObservationPolicy:
        return cls(
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            policy_version=str(payload["policy_version"]),
            intended_quantity=Decimal(str(payload["intended_quantity"])),
            fill_checkpoint=OutcomeCheckpoint(str(payload["fill_checkpoint"])),
            mark_checkpoint=OutcomeCheckpoint(str(payload["mark_checkpoint"])),
            trade_session=ShadowPortfolioTradeSession(
                str(payload["trade_session"])
            ),
            fillability=Decimal(str(payload["fillability"])),
            slippage_bps=Decimal(str(payload["slippage_bps"])),
            impact_bps=Decimal(str(payload["impact_bps"])),
            commission_bps=Decimal(str(payload["commission_bps"])),
            exit_cost_bps=Decimal(str(payload["exit_cost_bps"])),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ShadowObservationReceipt:
    receipt_id: ArtifactId
    receipt_hash: str
    kind: ObservationKind
    status: ObservationBuildStatus
    research_trading_date: date
    trading_date: date
    observed_at: datetime
    symbol: str | None
    policy_reference: ValidationArtifactReference
    values: tuple[OwnerObservationValue, ...]
    source_references: tuple[ValidationArtifactReference, ...]
    observation_payload: Mapping[str, Any] | None
    reason_codes: tuple[str, ...]
    formal_pit: bool = False
    formal_oos: bool = False
    calibrated: bool = False
    schema_version: str = "shadow-observation-receipt/v1"

    def __post_init__(self) -> None:
        require_sha256("Shadow Observation receipt hash", self.receipt_hash)
        _aware("Shadow Observation observed_at", self.observed_at)
        if self.trading_date < self.research_trading_date:
            raise ValueError("Shadow Observation cannot precede its Research date")
        if self.values != tuple(sorted(self.values, key=lambda item: item.name)):
            raise ValueError("Shadow Observation values must be sorted")
        if len({item.name for item in self.values}) != len(self.values):
            raise ValueError("Shadow Observation values must be unique")
        if self.source_references != _references(self.source_references):
            raise ValueError("Shadow Observation source references must be sorted")
        bound_references = set(self.source_references)
        if self.policy_reference not in bound_references:
            raise ValueError("Shadow Observation Policy is not source-bound")
        if any(item.source_reference not in bound_references for item in self.values):
            raise ValueError("Shadow Observation value owner is not source-bound")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Shadow Observation reasons must be sorted")
        if (self.status is ObservationBuildStatus.READY) != (
            self.observation_payload is not None
        ):
            raise ValueError("Shadow Observation status/payload mismatch")
        if self.formal_pit or self.formal_oos or self.calibrated:
            raise ValueError("Free Shadow Observation cannot claim Formal evidence")
        if canonical_hash(self.identity_payload()) != self.receipt_hash:
            raise ValueError("Shadow Observation receipt hash mismatch")
        if str(self.receipt_id) != f"shadow-observation:{self.receipt_hash[7:]}":
            raise ValueError("Shadow Observation receipt id mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "status": self.status.value,
            "research_trading_date": self.research_trading_date.isoformat(),
            "trading_date": self.trading_date.isoformat(),
            "observed_at": canonical_datetime(self.observed_at),
            "symbol": self.symbol,
            "policy_reference": self.policy_reference.to_canonical_dict(),
            "values": [item.to_canonical_dict() for item in self.values],
            "source_references": [
                item.to_canonical_dict() for item in self.source_references
            ],
            "observation_payload": self.observation_payload,
            "reason_codes": list(self.reason_codes),
            "formal_pit": self.formal_pit,
            "formal_oos": self.formal_oos,
            "calibrated": self.calibrated,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "receipt_hash": self.receipt_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ShadowObservationReceipt:
        raw_payload = payload["observation_payload"]
        if raw_payload is not None and not isinstance(raw_payload, Mapping):
            raise ValueError("Shadow Observation payload must be an object")
        return cls(
            receipt_id=ArtifactId(str(payload["receipt_id"])),
            receipt_hash=str(payload["receipt_hash"]),
            kind=ObservationKind(str(payload["kind"])),
            status=ObservationBuildStatus(str(payload["status"])),
            research_trading_date=date.fromisoformat(
                str(payload["research_trading_date"])
            ),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            observed_at=datetime.fromisoformat(str(payload["observed_at"])),
            symbol=None if payload["symbol"] is None else str(payload["symbol"]),
            policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["policy_reference"])
            ),
            values=tuple(
                OwnerObservationValue.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["values"])
            ),
            source_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["source_references"])
            ),
            observation_payload=raw_payload,
            reason_codes=tuple(str(item) for item in _sequence(payload["reason_codes"])),
            formal_pit=_boolean(payload["formal_pit"]),
            formal_oos=_boolean(payload["formal_oos"]),
            calibrated=_boolean(payload["calibrated"]),
            schema_version=str(payload["schema_version"]),
        )


def build_observation_receipt(
    *,
    kind: ObservationKind,
    research_trading_date: date,
    trading_date: date,
    observed_at: datetime,
    symbol: str | None,
    policy: ShadowObservationPolicy,
    values: tuple[OwnerObservationValue, ...],
    source_references: tuple[ValidationArtifactReference, ...],
) -> ShadowObservationReceipt:
    """Validate owner values and freeze a READY or NOT_ESTIMABLE receipt."""

    _aware("Shadow Observation observed_at", observed_at)
    ordered = tuple(sorted(values, key=lambda item: item.name))
    by_name = {item.name: item for item in ordered}
    reasons: set[str] = set()
    required = _STRATEGY_VALUE_NAMES if kind is ObservationKind.STRATEGY else frozenset()
    for name in sorted(required - set(by_name)):
        reasons.add(f"REQUIRED_VALUE_MISSING:{name}")
    for value in ordered:
        if value.available_at > observed_at or value.effective_at > observed_at:
            reasons.add(f"FUTURE_VALUE_REJECTED:{value.name}")
        if value.name in required and value.value is None and value.name not in {
            "mfe",
            "mae",
            "observed_fill_price",
        }:
            reasons.add(f"REQUIRED_VALUE_UNAVAILABLE:{value.name}")
    fillability = by_name.get("fillability")
    observed_fill = by_name.get("observed_fill_price")
    if (
        fillability is not None
        and fillability.value is not None
        and Decimal(str(fillability.value)) > 0
        and (observed_fill is None or observed_fill.value is None)
    ):
        reasons.add("REQUIRED_VALUE_UNAVAILABLE:observed_fill_price")
    if kind is ObservationKind.STRATEGY and symbol is None:
        reasons.add("STRATEGY_SYMBOL_MISSING")

    policy_reference = ValidationArtifactReference(
        "SHADOW_OBSERVATION_POLICY",
        policy.policy_id,
        policy.policy_hash,
    )
    all_references = _references(
        (
            *source_references,
            policy_reference,
            *(
                item.source_reference
                for item in ordered
                if item.source_reference is not None
            ),
        )
    )
    payload: Mapping[str, Any] | None = None
    status = ObservationBuildStatus.NOT_ESTIMABLE
    if not reasons:
        status = ObservationBuildStatus.READY
        payload = _strategy_payload(
            trading_date=research_trading_date,
            observed_at=observed_at,
            symbol=symbol,
            values=by_name,
        )
        reasons.add("OWNER_RESOLVED_OBSERVATION_READY")
    else:
        reasons.add("OWNER_RESOLVED_OBSERVATION_NOT_ESTIMABLE")

    identity = {
        "schema_version": "shadow-observation-receipt/v1",
        "kind": kind.value,
        "status": status.value,
        "research_trading_date": research_trading_date.isoformat(),
        "trading_date": trading_date.isoformat(),
        "observed_at": canonical_datetime(observed_at),
        "symbol": symbol,
        "policy_reference": policy_reference.to_canonical_dict(),
        "values": [item.to_canonical_dict() for item in ordered],
        "source_references": [item.to_canonical_dict() for item in all_references],
        "observation_payload": payload,
        "reason_codes": sorted(reasons),
        "formal_pit": False,
        "formal_oos": False,
        "calibrated": False,
    }
    digest = canonical_hash(identity)
    return ShadowObservationReceipt(
        receipt_id=ArtifactId(f"shadow-observation:{digest[7:]}"),
        receipt_hash=digest,
        kind=kind,
        status=status,
        research_trading_date=research_trading_date,
        trading_date=trading_date,
        observed_at=observed_at,
        symbol=symbol,
        policy_reference=policy_reference,
        values=ordered,
        source_references=all_references,
        observation_payload=payload,
        reason_codes=tuple(sorted(reasons)),
    )


def build_portfolio_observation_receipt(
    *,
    research_trading_date: date,
    trading_date: date,
    observed_at: datetime,
    policy: ShadowObservationPolicy,
    values: tuple[OwnerObservationValue, ...],
    source_references: tuple[ValidationArtifactReference, ...],
    observation_payload: Mapping[str, Any],
) -> ShadowObservationReceipt:
    """Freeze automatic Portfolio inputs or a typed missing-fact result."""

    _aware("Portfolio Observation observed_at", observed_at)
    ordered = tuple(sorted(values, key=lambda item: item.name))
    names = {item.name for item in ordered}
    prefixes = {
        item.name.rsplit(".", 1)[0]
        for item in ordered
        if "." in item.name
    }
    reasons: set[str] = set()
    for prefix in sorted(prefixes):
        for suffix in sorted(_PORTFOLIO_VALUE_SUFFIXES):
            name = f"{prefix}.{suffix}"
            if name not in names:
                reasons.add(f"REQUIRED_VALUE_MISSING:{name}")
    if not prefixes:
        reasons.add("PORTFOLIO_OBSERVATION_SYMBOLS_MISSING")
    for value in ordered:
        if value.available_at > observed_at or value.effective_at > observed_at:
            reasons.add(f"FUTURE_VALUE_REJECTED:{value.name}")
        if value.name.rsplit(".", 1)[-1] in _PORTFOLIO_VALUE_SUFFIXES and value.value is None:
            reasons.add(f"REQUIRED_VALUE_UNAVAILABLE:{value.name}")

    policy_reference = ValidationArtifactReference(
        "SHADOW_OBSERVATION_POLICY",
        policy.policy_id,
        policy.policy_hash,
    )
    all_references = _references(
        (
            *source_references,
            policy_reference,
            *(
                item.source_reference
                for item in ordered
                if item.source_reference is not None
            ),
        )
    )
    status = (
        ObservationBuildStatus.READY
        if not reasons
        else ObservationBuildStatus.NOT_ESTIMABLE
    )
    if status is ObservationBuildStatus.READY:
        reasons.add("OWNER_RESOLVED_OBSERVATION_READY")
        payload: Mapping[str, Any] | None = dict(observation_payload)
    else:
        reasons.add("OWNER_RESOLVED_OBSERVATION_NOT_ESTIMABLE")
        payload = None
    identity = {
        "schema_version": "shadow-observation-receipt/v1",
        "kind": ObservationKind.PORTFOLIO.value,
        "status": status.value,
        "research_trading_date": research_trading_date.isoformat(),
        "trading_date": trading_date.isoformat(),
        "observed_at": canonical_datetime(observed_at),
        "symbol": None,
        "policy_reference": policy_reference.to_canonical_dict(),
        "values": [item.to_canonical_dict() for item in ordered],
        "source_references": [item.to_canonical_dict() for item in all_references],
        "observation_payload": payload,
        "reason_codes": sorted(reasons),
        "formal_pit": False,
        "formal_oos": False,
        "calibrated": False,
    }
    digest = canonical_hash(identity)
    return ShadowObservationReceipt(
        receipt_id=ArtifactId(f"shadow-observation:{digest[7:]}"),
        receipt_hash=digest,
        kind=ObservationKind.PORTFOLIO,
        status=status,
        research_trading_date=research_trading_date,
        trading_date=trading_date,
        observed_at=observed_at,
        symbol=None,
        policy_reference=policy_reference,
        values=ordered,
        source_references=all_references,
        observation_payload=payload,
        reason_codes=tuple(sorted(reasons)),
    )


def _strategy_payload(
    *,
    trading_date: date,
    observed_at: datetime,
    symbol: str | None,
    values: Mapping[str, OwnerObservationValue],
) -> dict[str, Any]:
    return {
        "trading_date": trading_date.isoformat(),
        "observed_at": canonical_datetime(observed_at),
        "symbol": symbol,
        **{name: values[name].value for name in sorted(_STRATEGY_VALUE_NAMES)},
        "value_provenance": {
            name: values[name].provenance.value
            for name in sorted(_STRATEGY_VALUE_NAMES)
        },
    }


def _policy_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "shadow-observation-policy/v1",
        "policy_version": str(values["policy_version"]),
        "intended_quantity": str(values["intended_quantity"]),
        "fill_checkpoint": values["fill_checkpoint"].value,
        "mark_checkpoint": values["mark_checkpoint"].value,
        "trade_session": values["trade_session"].value,
        "fillability": str(values["fillability"]),
        "slippage_bps": str(values["slippage_bps"]),
        "impact_bps": str(values["impact_bps"]),
        "commission_bps": str(values["commission_bps"]),
        "exit_cost_bps": str(values["exit_cost_bps"]),
        "created_at": canonical_datetime(values["created_at"]),
    }


def _references(
    values: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    return tuple(
        sorted(
            set(values),
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return tuple(value)


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("expected boolean")
    return value


__all__ = [
    "ObservationBuildStatus",
    "ObservationKind",
    "OwnerObservationValue",
    "ShadowObservationPolicy",
    "ShadowObservationReceipt",
    "build_observation_receipt",
    "build_portfolio_observation_receipt",
]
