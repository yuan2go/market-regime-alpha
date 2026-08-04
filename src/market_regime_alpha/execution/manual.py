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
    PositionSnapshotId,
    RiskDecisionId,
    ThesisId,
)
from market_regime_alpha.evidence.canonical import require_sha256


MANUAL_TRADE_SCHEMA = "manual-trade-record-v1"
TRACEABLE_MANUAL_TRADE_SCHEMA = "manual-trade-record-v2-traceable"
ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA = (
    "manual-trade-record-v3-route-authorized"
)
FILL_SCHEMA = "manual-fill-v1"


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ManualTradeAuthorityRoute(str, Enum):
    INCREASING = "INCREASING"
    REDUCING = "REDUCING"


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
    risk_decision_id: RiskDecisionId | None
    risk_decision_hash: str | None
    portfolio_decision_id: PortfolioDecisionId | None
    target_position_hash: str | None
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
    authority_route: ManualTradeAuthorityRoute | None = None
    risk_reducing_decision_id: ArtifactId | None = None
    risk_reducing_decision_hash: str | None = None
    risk_reduction_confirmation_id: ArtifactId | None = None
    risk_reduction_confirmation_hash: str | None = None
    source_position_snapshot_id: PositionSnapshotId | None = None
    source_position_snapshot_hash: str | None = None
    source_position_snapshot_version: int | None = None
    target_quantity: int | None = None
    order_quantity: int | None = None

    def __post_init__(self) -> None:
        if self.schema_version not in {
            MANUAL_TRADE_SCHEMA,
            TRACEABLE_MANUAL_TRADE_SCHEMA,
            ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
        }:
            raise ValueError("unsupported ManualTradeRecord schema")
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
        increasing_authority = (
            self.risk_decision_id,
            self.risk_decision_hash,
            self.portfolio_decision_id,
            self.target_position_hash,
            self.post_trade_snapshot_id,
            self.post_trade_snapshot_hash,
        )
        common_trace = (
            self.position_book_id,
            self.thesis_id,
            self.opportunity_id,
        )
        reducing_authority = (
            self.risk_reducing_decision_id,
            self.risk_reducing_decision_hash,
            self.risk_reduction_confirmation_id,
            self.risk_reduction_confirmation_hash,
            self.source_position_snapshot_id,
            self.source_position_snapshot_hash,
            self.source_position_snapshot_version,
            self.target_quantity,
            self.order_quantity,
        )
        if self.schema_version in {
            MANUAL_TRADE_SCHEMA,
            TRACEABLE_MANUAL_TRADE_SCHEMA,
        }:
            if any(value is None for value in increasing_authority[:4]):
                raise ValueError(
                    "V1/V2 ManualTradeRecord requires increasing authority"
                )
            assert self.risk_decision_hash is not None
            assert self.target_position_hash is not None
            require_sha256("risk_decision_hash", self.risk_decision_hash)
            require_sha256("target_position_hash", self.target_position_hash)
            if self.authority_route is not None or any(
                value is not None for value in reducing_authority
            ):
                raise ValueError("V1/V2 ManualTradeRecord cannot carry V3 authority")
        if self.schema_version == MANUAL_TRADE_SCHEMA:
            if any(value is not None for value in (*common_trace, *increasing_authority[4:])):
                raise ValueError("V1 ManualTradeRecord cannot carry V2 trace")
        elif self.schema_version == TRACEABLE_MANUAL_TRADE_SCHEMA and any(
            value is None for value in (*common_trace, *increasing_authority[4:])
        ):
            raise ValueError("traceable ManualTradeRecord requires complete trace")
        elif self.schema_version == TRACEABLE_MANUAL_TRADE_SCHEMA:
            assert self.post_trade_snapshot_hash is not None
            require_sha256(
                "post_trade_snapshot_hash", self.post_trade_snapshot_hash
            )
        elif self.schema_version == ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA:
            self._validate_v3_route(
                common_trace=common_trace,
                increasing_authority=increasing_authority,
                reducing_authority=reducing_authority,
            )

    def _validate_v3_route(
        self,
        *,
        common_trace: tuple[object | None, ...],
        increasing_authority: tuple[object | None, ...],
        reducing_authority: tuple[object | None, ...],
    ) -> None:
        if any(value is None for value in common_trace):
            raise ValueError("V3 ManualTradeRecord requires complete book trace")
        if self.authority_route is ManualTradeAuthorityRoute.INCREASING:
            if any(value is None for value in increasing_authority):
                raise ValueError(
                    "INCREASING route requires complete increasing authority"
                )
            if any(value is not None for value in reducing_authority):
                raise ValueError(
                    "INCREASING route cannot carry reducing authority"
                )
            assert self.risk_decision_hash is not None
            assert self.target_position_hash is not None
            assert self.post_trade_snapshot_hash is not None
            require_sha256("risk_decision_hash", self.risk_decision_hash)
            require_sha256("target_position_hash", self.target_position_hash)
            require_sha256(
                "post_trade_snapshot_hash", self.post_trade_snapshot_hash
            )
            if self.side is not TradeSide.BUY:
                raise ValueError("INCREASING route requires BUY")
            return
        if self.authority_route is ManualTradeAuthorityRoute.REDUCING:
            if any(value is not None for value in increasing_authority):
                raise ValueError("REDUCING route cannot carry increasing authority")
            if any(value is None for value in reducing_authority):
                raise ValueError("REDUCING route requires complete reducing authority")
            assert self.risk_reducing_decision_hash is not None
            assert self.risk_reduction_confirmation_hash is not None
            assert self.source_position_snapshot_hash is not None
            assert self.source_position_snapshot_version is not None
            assert self.target_quantity is not None
            assert self.order_quantity is not None
            require_sha256(
                "risk_reducing_decision_hash",
                self.risk_reducing_decision_hash,
            )
            require_sha256(
                "risk_reduction_confirmation_hash",
                self.risk_reduction_confirmation_hash,
            )
            require_sha256(
                "source_position_snapshot_hash",
                self.source_position_snapshot_hash,
            )
            if (
                self.source_position_snapshot_version < 0
                or self.target_quantity < 0
                or self.order_quantity <= 0
                or self.side is not TradeSide.SELL
                or self.intended_quantity != self.order_quantity
            ):
                raise ValueError(
                    "reducing ManualTradeRecord has invalid SELL order semantics"
                )
            return
        raise ValueError("V3 ManualTradeRecord requires an authority route")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "manual_trade_id": str(self.manual_trade_id),
            "risk_decision_id": (
                str(self.risk_decision_id)
                if self.risk_decision_id is not None
                else None
            ),
            "risk_decision_hash": self.risk_decision_hash,
            "portfolio_decision_id": (
                str(self.portfolio_decision_id)
                if self.portfolio_decision_id is not None
                else None
            ),
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
        if self.schema_version in {
            TRACEABLE_MANUAL_TRADE_SCHEMA,
            ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
        }:
            assert self.position_book_id is not None
            assert self.thesis_id is not None
            assert self.opportunity_id is not None
            payload.update(
                {
                    "position_book_id": str(self.position_book_id),
                    "thesis_id": str(self.thesis_id),
                    "opportunity_id": str(self.opportunity_id),
                    "post_trade_snapshot_id": (
                        str(self.post_trade_snapshot_id)
                        if self.post_trade_snapshot_id is not None
                        else None
                    ),
                    "post_trade_snapshot_hash": self.post_trade_snapshot_hash,
                }
            )
        if self.schema_version == ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA:
            assert self.authority_route is not None
            payload.update(
                {
                    "authority_route": self.authority_route.value,
                    "risk_reducing_decision_id": (
                        str(self.risk_reducing_decision_id)
                        if self.risk_reducing_decision_id is not None
                        else None
                    ),
                    "risk_reducing_decision_hash": (
                        self.risk_reducing_decision_hash
                    ),
                    "risk_reduction_confirmation_id": (
                        str(self.risk_reduction_confirmation_id)
                        if self.risk_reduction_confirmation_id is not None
                        else None
                    ),
                    "risk_reduction_confirmation_hash": (
                        self.risk_reduction_confirmation_hash
                    ),
                    "source_position_snapshot_id": (
                        str(self.source_position_snapshot_id)
                        if self.source_position_snapshot_id is not None
                        else None
                    ),
                    "source_position_snapshot_hash": (
                        self.source_position_snapshot_hash
                    ),
                    "source_position_snapshot_version": (
                        self.source_position_snapshot_version
                    ),
                    "target_quantity": self.target_quantity,
                    "order_quantity": self.order_quantity,
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
        if schema in {
            TRACEABLE_MANUAL_TRADE_SCHEMA,
            ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
        }:
            expected |= trace_expected
        route_expected = {
            "authority_route",
            "risk_reducing_decision_id",
            "risk_reducing_decision_hash",
            "risk_reduction_confirmation_id",
            "risk_reduction_confirmation_hash",
            "source_position_snapshot_id",
            "source_position_snapshot_hash",
            "source_position_snapshot_version",
            "target_quantity",
            "order_quantity",
        }
        if schema == ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA:
            expected |= route_expected
        if set(payload) != expected:
            raise ValueError("ManualTradeRecord fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            manual_trade_id=ManualTradeId(str(payload["manual_trade_id"])),
            risk_decision_id=(
                RiskDecisionId(str(payload["risk_decision_id"]))
                if payload["risk_decision_id"] is not None
                else None
            ),
            risk_decision_hash=(
                str(payload["risk_decision_hash"])
                if payload["risk_decision_hash"] is not None
                else None
            ),
            portfolio_decision_id=(
                PortfolioDecisionId(str(payload["portfolio_decision_id"]))
                if payload["portfolio_decision_id"] is not None
                else None
            ),
            target_position_hash=(
                str(payload["target_position_hash"])
                if payload["target_position_hash"] is not None
                else None
            ),
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
                if schema
                in {
                    TRACEABLE_MANUAL_TRADE_SCHEMA,
                    ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
                }
                else None
            ),
            thesis_id=(
                ThesisId(str(payload["thesis_id"]))
                if schema
                in {
                    TRACEABLE_MANUAL_TRADE_SCHEMA,
                    ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
                }
                else None
            ),
            opportunity_id=(
                OpportunityId(str(payload["opportunity_id"]))
                if schema
                in {
                    TRACEABLE_MANUAL_TRADE_SCHEMA,
                    ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
                }
                else None
            ),
            post_trade_snapshot_id=(
                ArtifactId(str(payload["post_trade_snapshot_id"]))
                if schema
                in {
                    TRACEABLE_MANUAL_TRADE_SCHEMA,
                    ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
                }
                and payload["post_trade_snapshot_id"] is not None
                else None
            ),
            post_trade_snapshot_hash=(
                str(payload["post_trade_snapshot_hash"])
                if schema
                in {
                    TRACEABLE_MANUAL_TRADE_SCHEMA,
                    ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
                }
                and payload["post_trade_snapshot_hash"] is not None
                else None
            ),
            authority_route=(
                ManualTradeAuthorityRoute(str(payload["authority_route"]))
                if schema == ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA
                else None
            ),
            risk_reducing_decision_id=_optional_artifact_id(
                payload, "risk_reducing_decision_id", schema
            ),
            risk_reducing_decision_hash=_optional_route_string(
                payload, "risk_reducing_decision_hash", schema
            ),
            risk_reduction_confirmation_id=_optional_artifact_id(
                payload, "risk_reduction_confirmation_id", schema
            ),
            risk_reduction_confirmation_hash=_optional_route_string(
                payload, "risk_reduction_confirmation_hash", schema
            ),
            source_position_snapshot_id=(
                PositionSnapshotId(str(payload["source_position_snapshot_id"]))
                if schema == ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA
                and payload["source_position_snapshot_id"] is not None
                else None
            ),
            source_position_snapshot_hash=_optional_route_string(
                payload, "source_position_snapshot_hash", schema
            ),
            source_position_snapshot_version=_optional_route_int(
                payload, "source_position_snapshot_version", schema
            ),
            target_quantity=_optional_route_int(
                payload, "target_quantity", schema
            ),
            order_quantity=_optional_route_int(payload, "order_quantity", schema),
        )


def _optional_artifact_id(
    payload: dict[str, Any], key: str, schema: str
) -> ArtifactId | None:
    if schema != ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA or payload[key] is None:
        return None
    return ArtifactId(str(payload[key]))


def _optional_route_string(
    payload: dict[str, Any], key: str, schema: str
) -> str | None:
    if schema != ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA or payload[key] is None:
        return None
    return str(payload[key])


def _optional_route_int(
    payload: dict[str, Any], key: str, schema: str
) -> int | None:
    if schema != ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA or payload[key] is None:
        return None
    return int(payload[key])


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
