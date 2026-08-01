"""Manual intent and append-only Fill contracts; no broker execution API."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.core.identity import (
    ArtifactId,
    FillId,
    ManualTradeId,
    OpportunityId,
    PortfolioDecisionId,
    PositionBookId,
    RiskDecisionId,
    ThesisId,
)
from market_regime_alpha.evidence.canonical import require_sha256


MANUAL_TRADE_SCHEMA = "manual-trade-record-v1"
TRACEABLE_MANUAL_TRADE_SCHEMA = "manual-trade-record-v2-traceable"
FILL_SCHEMA = "manual-fill-v1"


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ManualOrderState(str, Enum):
    RECORDED = "RECORDED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class FillKind(str, Enum):
    EXECUTION = "EXECUTION"
    CORRECTION = "CORRECTION"


@dataclass(frozen=True, slots=True)
class ManualTradeRecord:
    schema_version: str
    manual_trade_id: ManualTradeId
    risk_decision_id: RiskDecisionId
    risk_decision_hash: str
    portfolio_decision_id: PortfolioDecisionId
    target_position_hash: str
    account_id: str
    symbol: str
    side: TradeSide
    intended_quantity: int
    expected_price_lower: float
    expected_price_upper: float
    state: ManualOrderState
    filled_quantity: int
    version: int
    actor: str
    reason: str
    created_at: datetime
    updated_at: datetime
    last_actor: str
    last_reason: str
    position_book_id: PositionBookId | None = None
    thesis_id: ThesisId | None = None
    opportunity_id: OpportunityId | None = None
    post_trade_snapshot_id: ArtifactId | None = None
    post_trade_snapshot_hash: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version not in {
            MANUAL_TRADE_SCHEMA,
            TRACEABLE_MANUAL_TRADE_SCHEMA,
        }:
            raise ValueError("unsupported ManualTradeRecord schema")
        require_sha256("risk_decision_hash", self.risk_decision_hash)
        require_sha256("target_position_hash", self.target_position_hash)
        for label, text_value in (
            ("account_id", self.account_id),
            ("symbol", self.symbol),
            ("actor", self.actor),
            ("reason", self.reason),
            ("last_actor", self.last_actor),
            ("last_reason", self.last_reason),
        ):
            _text(label, text_value)
        if self.intended_quantity <= 0 or self.filled_quantity < 0:
            raise ValueError("manual trade quantities are invalid")
        if (
            not isfinite(self.expected_price_lower)
            or not isfinite(self.expected_price_upper)
            or not 0.0 < self.expected_price_lower <= self.expected_price_upper
        ):
            raise ValueError("manual expected price range is invalid")
        if self.version < 0:
            raise ValueError("ManualTradeRecord version cannot be negative")
        if self.state is ManualOrderState.RECORDED and (
            self.version != 0 or self.filled_quantity != 0
        ):
            raise ValueError("RECORDED ManualTradeRecord must be initial version 0")
        if self.state is ManualOrderState.PARTIALLY_FILLED and not (
            0 < self.filled_quantity < self.intended_quantity
        ):
            raise ValueError("PARTIALLY_FILLED quantity mismatch")
        if self.state is ManualOrderState.FILLED and (
            self.filled_quantity != self.intended_quantity
        ):
            raise ValueError("FILLED quantity mismatch")
        if self.state is ManualOrderState.RECONCILIATION_REQUIRED and (
            self.filled_quantity <= self.intended_quantity
        ):
            raise ValueError("reconciliation state requires excess effective fill")
        for timestamp in (self.created_at, self.updated_at):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("manual trade timestamps must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("manual trade update cannot precede creation")
        trace_values = (
            self.position_book_id,
            self.thesis_id,
            self.opportunity_id,
            self.post_trade_snapshot_id,
            self.post_trade_snapshot_hash,
        )
        if self.schema_version == MANUAL_TRADE_SCHEMA:
            if any(value is not None for value in trace_values):
                raise ValueError("V1 ManualTradeRecord cannot carry V2 trace")
        elif any(value is None for value in trace_values):
            raise ValueError("traceable ManualTradeRecord requires complete trace")
        elif self.post_trade_snapshot_hash is not None:
            require_sha256(
                "post_trade_snapshot_hash", self.post_trade_snapshot_hash
            )

    def to_canonical_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "manual_trade_id": str(self.manual_trade_id),
            "risk_decision_id": str(self.risk_decision_id),
            "risk_decision_hash": self.risk_decision_hash,
            "portfolio_decision_id": str(self.portfolio_decision_id),
            "target_position_hash": self.target_position_hash,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "intended_quantity": self.intended_quantity,
            "expected_price_lower": self.expected_price_lower,
            "expected_price_upper": self.expected_price_upper,
            "state": self.state.value,
            "filled_quantity": self.filled_quantity,
            "version": self.version,
            "actor": self.actor,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_actor": self.last_actor,
            "last_reason": self.last_reason,
        }
        if self.schema_version == TRACEABLE_MANUAL_TRADE_SCHEMA:
            assert self.position_book_id is not None
            assert self.thesis_id is not None
            assert self.opportunity_id is not None
            assert self.post_trade_snapshot_id is not None
            assert self.post_trade_snapshot_hash is not None
            payload.update(
                {
                    "position_book_id": str(self.position_book_id),
                    "thesis_id": str(self.thesis_id),
                    "opportunity_id": str(self.opportunity_id),
                    "post_trade_snapshot_id": str(
                        self.post_trade_snapshot_id
                    ),
                    "post_trade_snapshot_hash": self.post_trade_snapshot_hash,
                }
            )
        return payload

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> ManualTradeRecord:
        expected = {
            "schema_version", "manual_trade_id", "risk_decision_id",
            "risk_decision_hash", "portfolio_decision_id", "target_position_hash",
            "account_id", "symbol", "side", "intended_quantity",
            "expected_price_lower", "expected_price_upper", "state",
            "filled_quantity", "version", "actor", "reason", "created_at",
            "updated_at", "last_actor", "last_reason",
        }
        schema = str(payload.get("schema_version"))
        trace_expected = {
            "position_book_id",
            "thesis_id",
            "opportunity_id",
            "post_trade_snapshot_id",
            "post_trade_snapshot_hash",
        }
        if schema == TRACEABLE_MANUAL_TRADE_SCHEMA:
            expected |= trace_expected
        if set(payload) != expected:
            raise ValueError("ManualTradeRecord fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            manual_trade_id=ManualTradeId(str(payload["manual_trade_id"])),
            risk_decision_id=RiskDecisionId(str(payload["risk_decision_id"])),
            risk_decision_hash=str(payload["risk_decision_hash"]),
            portfolio_decision_id=PortfolioDecisionId(str(payload["portfolio_decision_id"])),
            target_position_hash=str(payload["target_position_hash"]),
            account_id=str(payload["account_id"]),
            symbol=str(payload["symbol"]),
            side=TradeSide(str(payload["side"])),
            intended_quantity=int(payload["intended_quantity"]),
            expected_price_lower=float(payload["expected_price_lower"]),
            expected_price_upper=float(payload["expected_price_upper"]),
            state=ManualOrderState(str(payload["state"])),
            filled_quantity=int(payload["filled_quantity"]),
            version=int(payload["version"]),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            updated_at=datetime.fromisoformat(str(payload["updated_at"])),
            last_actor=str(payload["last_actor"]),
            last_reason=str(payload["last_reason"]),
            position_book_id=(
                PositionBookId(str(payload["position_book_id"]))
                if schema == TRACEABLE_MANUAL_TRADE_SCHEMA
                else None
            ),
            thesis_id=(
                ThesisId(str(payload["thesis_id"]))
                if schema == TRACEABLE_MANUAL_TRADE_SCHEMA
                else None
            ),
            opportunity_id=(
                OpportunityId(str(payload["opportunity_id"]))
                if schema == TRACEABLE_MANUAL_TRADE_SCHEMA
                else None
            ),
            post_trade_snapshot_id=(
                ArtifactId(str(payload["post_trade_snapshot_id"]))
                if schema == TRACEABLE_MANUAL_TRADE_SCHEMA
                else None
            ),
            post_trade_snapshot_hash=(
                str(payload["post_trade_snapshot_hash"])
                if schema == TRACEABLE_MANUAL_TRADE_SCHEMA
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class Fill:
    schema_version: str
    fill_id: FillId
    manual_trade_id: ManualTradeId
    account_id: str
    symbol: str
    side: TradeSide
    quantity: int
    price: float
    fees: float
    occurred_at: datetime
    recorded_at: datetime
    actor: str
    reason: str
    external_fill_id: str
    fill_kind: FillKind
    correction_of_fill_id: FillId | None

    def __post_init__(self) -> None:
        if self.schema_version != FILL_SCHEMA:
            raise ValueError("unsupported Fill schema")
        for label, text_value in (
            ("account_id", self.account_id),
            ("symbol", self.symbol),
            ("actor", self.actor),
            ("reason", self.reason),
            ("external_fill_id", self.external_fill_id),
        ):
            _text(label, text_value)
        if self.quantity <= 0 or not isfinite(self.price) or self.price <= 0.0:
            raise ValueError("Fill quantity and price must be positive")
        if not isfinite(self.fees) or self.fees < 0.0:
            raise ValueError("Fill fees must be non-negative and finite")
        if self.recorded_at < self.occurred_at:
            raise ValueError("Fill cannot be recorded before occurrence")
        for timestamp in (self.occurred_at, self.recorded_at):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("Fill timestamps must be timezone-aware")
        if self.fill_kind is FillKind.EXECUTION and self.correction_of_fill_id is not None:
            raise ValueError("execution Fill cannot reference a correction target")
        if self.fill_kind is FillKind.CORRECTION and self.correction_of_fill_id is None:
            raise ValueError("correction Fill requires correction_of_fill_id")
        if self.correction_of_fill_id == self.fill_id:
            raise ValueError("Fill cannot correct itself")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fill_id": str(self.fill_id),
            "manual_trade_id": str(self.manual_trade_id),
            "account_id": self.account_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "fees": self.fees,
            "occurred_at": self.occurred_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
            "actor": self.actor,
            "reason": self.reason,
            "external_fill_id": self.external_fill_id,
            "fill_kind": self.fill_kind.value,
            "correction_of_fill_id": (
                str(self.correction_of_fill_id)
                if self.correction_of_fill_id is not None
                else None
            ),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> Fill:
        expected = {
            "schema_version", "fill_id", "manual_trade_id", "account_id",
            "symbol", "side", "quantity", "price", "fees", "occurred_at",
            "recorded_at", "actor", "reason", "external_fill_id", "fill_kind",
            "correction_of_fill_id",
        }
        if set(payload) != expected:
            raise ValueError("Fill fields mismatch")
        correction = payload["correction_of_fill_id"]
        return cls(
            schema_version=str(payload["schema_version"]),
            fill_id=FillId(str(payload["fill_id"])),
            manual_trade_id=ManualTradeId(str(payload["manual_trade_id"])),
            account_id=str(payload["account_id"]),
            symbol=str(payload["symbol"]),
            side=TradeSide(str(payload["side"])),
            quantity=int(payload["quantity"]),
            price=float(payload["price"]),
            fees=float(payload["fees"]),
            occurred_at=datetime.fromisoformat(str(payload["occurred_at"])),
            recorded_at=datetime.fromisoformat(str(payload["recorded_at"])),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            external_fill_id=str(payload["external_fill_id"]),
            fill_kind=FillKind(str(payload["fill_kind"])),
            correction_of_fill_id=FillId(str(correction)) if correction is not None else None,
        )


@dataclass(frozen=True, slots=True)
class ExecutionDeviation:
    manual_trade_id: ManualTradeId
    intended_quantity: int
    effective_filled_quantity: int
    quantity_deviation: int
    volume_weighted_price: float | None
    expected_mid_price: float
    price_deviation: float | None

    def __post_init__(self) -> None:
        if self.intended_quantity <= 0 or self.effective_filled_quantity < 0:
            raise ValueError("ExecutionDeviation quantities are invalid")
        if self.quantity_deviation != (
            self.effective_filled_quantity - self.intended_quantity
        ):
            raise ValueError("ExecutionDeviation quantity mismatch")
        if not isfinite(self.expected_mid_price) or self.expected_mid_price <= 0.0:
            raise ValueError("ExecutionDeviation expected price is invalid")
        if (self.volume_weighted_price is None) is not (
            self.price_deviation is None
        ):
            raise ValueError("ExecutionDeviation price fields must align")
        if self.volume_weighted_price is not None:
            if (
                not isfinite(self.volume_weighted_price)
                or self.volume_weighted_price <= 0.0
                or not isfinite(self.price_deviation or 0.0)
            ):
                raise ValueError("ExecutionDeviation price fields are invalid")
            if self.price_deviation != (
                self.volume_weighted_price - self.expected_mid_price
            ):
                raise ValueError("ExecutionDeviation price mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "manual_trade_id": str(self.manual_trade_id),
            "intended_quantity": self.intended_quantity,
            "effective_filled_quantity": self.effective_filled_quantity,
            "quantity_deviation": self.quantity_deviation,
            "volume_weighted_price": self.volume_weighted_price,
            "expected_mid_price": self.expected_mid_price,
            "price_deviation": self.price_deviation,
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> ExecutionDeviation:
        expected = {
            "manual_trade_id",
            "intended_quantity",
            "effective_filled_quantity",
            "quantity_deviation",
            "volume_weighted_price",
            "expected_mid_price",
            "price_deviation",
        }
        if set(payload) != expected:
            raise ValueError("ExecutionDeviation fields mismatch")
        vwap = payload["volume_weighted_price"]
        price_deviation = payload["price_deviation"]
        return cls(
            manual_trade_id=ManualTradeId(str(payload["manual_trade_id"])),
            intended_quantity=int(payload["intended_quantity"]),
            effective_filled_quantity=int(payload["effective_filled_quantity"]),
            quantity_deviation=int(payload["quantity_deviation"]),
            volume_weighted_price=float(vwap) if vwap is not None else None,
            expected_mid_price=float(payload["expected_mid_price"]),
            price_deviation=(
                float(price_deviation) if price_deviation is not None else None
            ),
        )


def transition_manual_trade(
    record: ManualTradeRecord,
    *,
    state: ManualOrderState,
    filled_quantity: int,
    actor: str,
    reason: str,
    changed_at: datetime,
) -> ManualTradeRecord:
    if record.state in {ManualOrderState.CANCELLED, ManualOrderState.REJECTED}:
        raise ValueError("terminal ManualTradeRecord cannot transition")
    return replace(
        record,
        state=state,
        filled_quantity=filled_quantity,
        version=record.version + 1,
        updated_at=changed_at,
        last_actor=actor,
        last_reason=reason,
    )


def validate_manual_trade_transition(
    before: ManualTradeRecord, after: ManualTradeRecord
) -> None:
    expected = transition_manual_trade(
        before,
        state=after.state,
        filled_quantity=after.filled_quantity,
        actor=after.last_actor,
        reason=after.last_reason,
        changed_at=after.updated_at,
    )
    if expected != after:
        raise ValueError("invalid ManualTradeRecord transition")


def _text(label: str, value: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
