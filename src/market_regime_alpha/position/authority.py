"""Authoritative PositionSnapshot rebuilt solely from append-only Fill events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import (
    ArtifactId,
    FillId,
    ManualTradeId,
    OpportunityId,
    PositionBookId,
    PositionSnapshotId,
    ThesisId,
)
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.execution.manual import (
    TRACEABLE_MANUAL_TRADE_SCHEMA,
    Fill,
    FillKind,
    ManualTradeRecord,
    TradeSide,
)
from market_regime_alpha.execution.position_book import PositionBook


POSITION_SNAPSHOT_SCHEMA = "position-snapshot-v1"
TRACEABLE_POSITION_SNAPSHOT_SCHEMA = "position-snapshot-v2-traceable"
T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA = "position-snapshot-v3-a-share-t-plus-one"
SYMBOL_TRADING_SESSION_STATUS_SCHEMA = "symbol-trading-session-status-v1"


class PositionState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class LotSettlementState(str, Enum):
    FROZEN_T_PLUS_ONE = "FROZEN_T_PLUS_ONE"
    SELLABLE = "SELLABLE"
    FROZEN_MARKET_CONSTRAINT = "FROZEN_MARKET_CONSTRAINT"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class PositionSellabilityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIALLY_AVAILABLE = "PARTIALLY_AVAILABLE"
    T_PLUS_ONE_FROZEN = "T_PLUS_ONE_FROZEN"
    SUSPENDED = "SUSPENDED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    CLOSED = "CLOSED"


class SymbolTradingState(str, Enum):
    TRADABLE = "TRADABLE"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SymbolTradingSessionStatus:
    schema_version: str
    status_id: ArtifactId
    symbol: str
    session_date: date
    state: SymbolTradingState
    source_artifact_id: ArtifactId
    source_artifact_hash: str
    availability_time: datetime
    reason_code: str
    content_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != SYMBOL_TRADING_SESSION_STATUS_SCHEMA:
            raise ValueError("unsupported symbol trading session status schema")
        if not self.symbol or self.symbol != self.symbol.strip():
            raise ValueError("symbol must be a non-empty trimmed string")
        if not self.reason_code or self.reason_code != self.reason_code.strip():
            raise ValueError("reason_code must be a non-empty trimmed string")
        if self.availability_time.tzinfo is None:
            raise ValueError("status availability_time must be timezone-aware")
        require_sha256("source_artifact_hash", self.source_artifact_hash)
        require_sha256("content_hash", self.content_hash)
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("symbol trading session status hash mismatch")
        digest = self.content_hash.split(":", 1)[1]
        if self.status_id != ArtifactId(f"symbol-session-status-{digest[:24]}"):
            raise ValueError("symbol trading session status identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "session_date": self.session_date.isoformat(),
            "state": self.state.value,
            "source_artifact_id": str(self.source_artifact_id),
            "source_artifact_hash": self.source_artifact_hash,
            "availability_time": self.availability_time.isoformat(),
            "reason_code": self.reason_code,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "status_id": str(self.status_id),
            **self.semantic_payload(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        session_date: date,
        state: SymbolTradingState,
        source_artifact_id: ArtifactId,
        source_artifact_hash: str,
        availability_time: datetime,
        reason_code: str,
    ) -> SymbolTradingSessionStatus:
        semantic = {
            "schema_version": SYMBOL_TRADING_SESSION_STATUS_SCHEMA,
            "symbol": symbol,
            "session_date": session_date.isoformat(),
            "state": state.value,
            "source_artifact_id": str(source_artifact_id),
            "source_artifact_hash": source_artifact_hash,
            "availability_time": availability_time.isoformat(),
            "reason_code": reason_code,
        }
        digest = canonical_hash(semantic)
        return cls(
            schema_version=SYMBOL_TRADING_SESSION_STATUS_SCHEMA,
            status_id=ArtifactId(
                f"symbol-session-status-{digest.split(':', 1)[1][:24]}"
            ),
            symbol=symbol,
            session_date=session_date,
            state=state,
            source_artifact_id=source_artifact_id,
            source_artifact_hash=source_artifact_hash,
            availability_time=availability_time,
            reason_code=reason_code,
            content_hash=digest,
        )

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> SymbolTradingSessionStatus:
        expected = {
            "schema_version",
            "status_id",
            "symbol",
            "session_date",
            "state",
            "source_artifact_id",
            "source_artifact_hash",
            "availability_time",
            "reason_code",
            "content_hash",
        }
        if set(payload) != expected:
            raise ValueError("SymbolTradingSessionStatus fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            status_id=ArtifactId(str(payload["status_id"])),
            symbol=str(payload["symbol"]),
            session_date=date.fromisoformat(str(payload["session_date"])),
            state=SymbolTradingState(str(payload["state"])),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            source_artifact_hash=str(payload["source_artifact_hash"]),
            availability_time=datetime.fromisoformat(
                str(payload["availability_time"])
            ),
            reason_code=str(payload["reason_code"]),
            content_hash=str(payload["content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class PositionLot:
    source_fill_id: FillId
    symbol: str
    quantity_remaining: int
    unit_cost: float
    acquired_at: datetime
    trade_date: date | None = None
    available_quantity: int | None = None
    frozen_quantity: int | None = None
    sellable_from_session: date | None = None
    settlement_state: LotSettlementState | None = None

    def __post_init__(self) -> None:
        if self.quantity_remaining <= 0 or self.unit_cost <= 0.0:
            raise ValueError("PositionLot quantity and cost must be positive")
        if self.acquired_at.tzinfo is None:
            raise ValueError("PositionLot acquired_at must be timezone-aware")
        settlement = (
            self.trade_date,
            self.available_quantity,
            self.frozen_quantity,
            self.sellable_from_session,
            self.settlement_state,
        )
        if any(item is not None for item in settlement):
            if any(item is None for item in settlement):
                raise ValueError("settled PositionLot requires complete settlement fields")
            assert self.available_quantity is not None
            assert self.frozen_quantity is not None
            assert self.trade_date is not None
            assert self.sellable_from_session is not None
            if self.available_quantity + self.frozen_quantity != self.quantity_remaining:
                raise ValueError("PositionLot available/frozen quantity mismatch")
            if self.sellable_from_session <= self.trade_date:
                raise ValueError("PositionLot sellable session must follow trade date")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_fill_id": str(self.source_fill_id),
            "symbol": self.symbol,
            "quantity_remaining": self.quantity_remaining,
            "unit_cost": self.unit_cost,
            "acquired_at": self.acquired_at.isoformat(),
        }
        if self.trade_date is not None:
            assert self.available_quantity is not None
            assert self.frozen_quantity is not None
            assert self.sellable_from_session is not None
            assert self.settlement_state is not None
            payload.update(
                {
                    "trade_date": self.trade_date.isoformat(),
                    "available_quantity": self.available_quantity,
                    "frozen_quantity": self.frozen_quantity,
                    "sellable_from_session": self.sellable_from_session.isoformat(),
                    "settlement_state": self.settlement_state.value,
                }
            )
        return payload

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> PositionLot:
        expected = {
            "source_fill_id",
            "symbol",
            "quantity_remaining",
            "unit_cost",
            "acquired_at",
        }
        settled = {
            "trade_date",
            "available_quantity",
            "frozen_quantity",
            "sellable_from_session",
            "settlement_state",
        }
        is_settled = set(payload) == expected | settled
        if set(payload) != expected and not is_settled:
            raise ValueError("PositionLot fields mismatch")
        return cls(
            source_fill_id=FillId(str(payload["source_fill_id"])),
            symbol=str(payload["symbol"]),
            quantity_remaining=int(payload["quantity_remaining"]),
            unit_cost=float(payload["unit_cost"]),
            acquired_at=datetime.fromisoformat(str(payload["acquired_at"])),
            trade_date=(
                date.fromisoformat(str(payload["trade_date"])) if is_settled else None
            ),
            available_quantity=(int(payload["available_quantity"]) if is_settled else None),
            frozen_quantity=(int(payload["frozen_quantity"]) if is_settled else None),
            sellable_from_session=(
                date.fromisoformat(str(payload["sellable_from_session"]))
                if is_settled
                else None
            ),
            settlement_state=(
                LotSettlementState(str(payload["settlement_state"]))
                if is_settled
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    schema_version: str
    snapshot_id: PositionSnapshotId
    account_id: str
    symbol: str
    as_of: datetime
    state: PositionState
    total_quantity: int
    average_cost: float | None
    realized_pnl: float
    lots: tuple[PositionLot, ...]
    source_fill_ids: tuple[FillId, ...]
    effective_fill_ids: tuple[FillId, ...]
    version: int
    reason_codes: tuple[str, ...]
    position_book_id: PositionBookId | None = None
    thesis_id: ThesisId | None = None
    opportunity_id: OpportunityId | None = None
    source_manual_trade_ids: tuple[ManualTradeId, ...] = ()
    available_quantity: int | None = None
    frozen_quantity: int | None = None
    today_acquired_quantity: int | None = None
    sellability_state: PositionSellabilityState | None = None
    as_of_session_date: date | None = None
    calendar_artifact_id: ArtifactId | None = None
    calendar_content_hash: str | None = None
    source_trading_status_ids: tuple[ArtifactId, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version not in {
            POSITION_SNAPSHOT_SCHEMA,
            TRACEABLE_POSITION_SNAPSHOT_SCHEMA,
            T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
        }:
            raise ValueError("unsupported PositionSnapshot schema")
        if not self.source_fill_ids or self.version != len(self.source_fill_ids):
            raise ValueError("PositionSnapshot version must equal source Fill count")
        if self.total_quantity != sum(item.quantity_remaining for item in self.lots):
            raise ValueError("PositionSnapshot lot quantity mismatch")
        if self.total_quantity == 0 and self.average_cost is not None:
            raise ValueError("closed Position cannot carry average cost")
        if self.total_quantity > 0 and self.average_cost is None:
            raise ValueError("open Position requires average cost")
        if self.state is PositionState.RECONCILIATION_REQUIRED and not self.reason_codes:
            raise ValueError("reconciliation Position requires reason_codes")
        trace_values = (
            self.position_book_id,
            self.thesis_id,
            self.opportunity_id,
        )
        settlement_values = (
            self.available_quantity,
            self.frozen_quantity,
            self.today_acquired_quantity,
            self.sellability_state,
            self.as_of_session_date,
            self.calendar_artifact_id,
            self.calendar_content_hash,
        )
        if self.schema_version == POSITION_SNAPSHOT_SCHEMA:
            if any(value is not None for value in trace_values) or self.source_manual_trade_ids:
                raise ValueError("V1 PositionSnapshot cannot carry V2 trace")
            if any(value is not None for value in settlement_values) or self.source_trading_status_ids:
                raise ValueError("V1 PositionSnapshot cannot carry T+1 authority")
        elif self.schema_version == TRACEABLE_POSITION_SNAPSHOT_SCHEMA:
            if any(value is None for value in trace_values):
                raise ValueError("traceable PositionSnapshot requires complete trace")
            if not self.source_manual_trade_ids:
                raise ValueError("traceable PositionSnapshot requires ManualTrade IDs")
            if self.source_manual_trade_ids != tuple(
                sorted(set(self.source_manual_trade_ids), key=str)
            ):
                raise ValueError("Position ManualTrade IDs must be sorted and unique")
            if any(value is not None for value in settlement_values) or self.source_trading_status_ids:
                raise ValueError("V2 PositionSnapshot cannot carry V3 T+1 authority")
        else:
            if any(value is None for value in trace_values):
                raise ValueError("T+1 PositionSnapshot requires complete trace")
            if not self.source_manual_trade_ids:
                raise ValueError("T+1 PositionSnapshot requires ManualTrade IDs")
            if self.source_manual_trade_ids != tuple(
                sorted(set(self.source_manual_trade_ids), key=str)
            ):
                raise ValueError("Position ManualTrade IDs must be sorted and unique")
            if any(value is None for value in settlement_values):
                raise ValueError("T+1 PositionSnapshot requires settlement authority")
            if not self.source_trading_status_ids:
                raise ValueError("T+1 PositionSnapshot requires session status evidence")
            if self.source_trading_status_ids != tuple(
                sorted(set(self.source_trading_status_ids), key=str)
            ):
                raise ValueError("Position status IDs must be sorted and unique")
            assert self.available_quantity is not None
            assert self.frozen_quantity is not None
            assert self.today_acquired_quantity is not None
            assert self.calendar_content_hash is not None
            if self.available_quantity + self.frozen_quantity != self.total_quantity:
                raise ValueError("Position available/frozen quantity mismatch")
            if not 0 <= self.today_acquired_quantity <= self.frozen_quantity:
                raise ValueError("Position today-acquired quantity mismatch")
            require_sha256("calendar_content_hash", self.calendar_content_hash)
            if any(item.trade_date is None for item in self.lots):
                raise ValueError("T+1 Position requires settled lots")
            if self.total_quantity == 0 and self.sellability_state is not PositionSellabilityState.CLOSED:
                raise ValueError("closed Position requires CLOSED sellability")
        expected = _snapshot_id(self.semantic_payload())
        if self.snapshot_id != expected:
            raise ValueError("PositionSnapshot content identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "state": self.state.value,
            "total_quantity": self.total_quantity,
            "average_cost": self.average_cost,
            "realized_pnl": self.realized_pnl,
            "lots": [item.to_canonical_dict() for item in self.lots],
            "source_fill_ids": [str(item) for item in self.source_fill_ids],
            "effective_fill_ids": [str(item) for item in self.effective_fill_ids],
            "version": self.version,
            "reason_codes": list(self.reason_codes),
        }
        if self.schema_version in {
            TRACEABLE_POSITION_SNAPSHOT_SCHEMA,
            T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
        }:
            assert self.position_book_id is not None
            assert self.thesis_id is not None
            assert self.opportunity_id is not None
            payload.update(
                {
                    "position_book_id": str(self.position_book_id),
                    "thesis_id": str(self.thesis_id),
                    "opportunity_id": str(self.opportunity_id),
                    "source_manual_trade_ids": [
                        str(item) for item in self.source_manual_trade_ids
                    ],
                }
            )
        if self.schema_version == T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA:
            assert self.available_quantity is not None
            assert self.frozen_quantity is not None
            assert self.today_acquired_quantity is not None
            assert self.sellability_state is not None
            assert self.as_of_session_date is not None
            assert self.calendar_artifact_id is not None
            assert self.calendar_content_hash is not None
            payload.update(
                {
                    "available_quantity": self.available_quantity,
                    "frozen_quantity": self.frozen_quantity,
                    "today_acquired_quantity": self.today_acquired_quantity,
                    "sellability_state": self.sellability_state.value,
                    "as_of_session_date": self.as_of_session_date.isoformat(),
                    "calendar_artifact_id": str(self.calendar_artifact_id),
                    "calendar_content_hash": self.calendar_content_hash,
                    "source_trading_status_ids": [
                        str(item) for item in self.source_trading_status_ids
                    ],
                }
            )
        return payload

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"snapshot_id": str(self.snapshot_id), **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> PositionSnapshot:
        expected = {
            "schema_version",
            "snapshot_id",
            "account_id",
            "symbol",
            "as_of",
            "state",
            "total_quantity",
            "average_cost",
            "realized_pnl",
            "lots",
            "source_fill_ids",
            "effective_fill_ids",
            "version",
            "reason_codes",
        }
        schema = str(payload.get("schema_version"))
        if schema in {
            TRACEABLE_POSITION_SNAPSHOT_SCHEMA,
            T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
        }:
            expected |= {
                "position_book_id",
                "thesis_id",
                "opportunity_id",
                "source_manual_trade_ids",
            }
        if schema == T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA:
            expected |= {
                "available_quantity",
                "frozen_quantity",
                "today_acquired_quantity",
                "sellability_state",
                "as_of_session_date",
                "calendar_artifact_id",
                "calendar_content_hash",
                "source_trading_status_ids",
            }
        if set(payload) != expected:
            raise ValueError("PositionSnapshot fields mismatch")
        lots = payload["lots"]
        source_ids = payload["source_fill_ids"]
        effective_ids = payload["effective_fill_ids"]
        reasons = payload["reason_codes"]
        manual_ids = payload.get("source_manual_trade_ids", [])
        status_ids = payload.get("source_trading_status_ids", [])
        if not all(
            isinstance(value, list)
            for value in (
                lots,
                source_ids,
                effective_ids,
                reasons,
                manual_ids,
                status_ids,
            )
        ):
            raise ValueError("PositionSnapshot array field mismatch")
        average_cost = payload["average_cost"]
        return cls(
            schema_version=str(payload["schema_version"]),
            snapshot_id=PositionSnapshotId(str(payload["snapshot_id"])),
            account_id=str(payload["account_id"]),
            symbol=str(payload["symbol"]),
            as_of=datetime.fromisoformat(str(payload["as_of"])),
            state=PositionState(str(payload["state"])),
            total_quantity=int(payload["total_quantity"]),
            average_cost=(
                float(average_cost) if average_cost is not None else None
            ),
            realized_pnl=float(payload["realized_pnl"]),
            lots=tuple(
                PositionLot.from_canonical_dict(_object(item)) for item in lots
            ),
            source_fill_ids=tuple(FillId(str(item)) for item in source_ids),
            effective_fill_ids=tuple(FillId(str(item)) for item in effective_ids),
            version=int(payload["version"]),
            reason_codes=tuple(str(item) for item in reasons),
            position_book_id=(
                PositionBookId(str(payload["position_book_id"]))
                if schema in {
                    TRACEABLE_POSITION_SNAPSHOT_SCHEMA,
                    T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
                }
                else None
            ),
            thesis_id=(
                ThesisId(str(payload["thesis_id"]))
                if schema in {
                    TRACEABLE_POSITION_SNAPSHOT_SCHEMA,
                    T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
                }
                else None
            ),
            opportunity_id=(
                OpportunityId(str(payload["opportunity_id"]))
                if schema in {
                    TRACEABLE_POSITION_SNAPSHOT_SCHEMA,
                    T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
                }
                else None
            ),
            source_manual_trade_ids=tuple(
                ManualTradeId(str(item)) for item in manual_ids
            ),
            available_quantity=(
                int(payload["available_quantity"])
                if schema == T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA
                else None
            ),
            frozen_quantity=(
                int(payload["frozen_quantity"])
                if schema == T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA
                else None
            ),
            today_acquired_quantity=(
                int(payload["today_acquired_quantity"])
                if schema == T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA
                else None
            ),
            sellability_state=(
                PositionSellabilityState(str(payload["sellability_state"]))
                if schema == T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA
                else None
            ),
            as_of_session_date=(
                date.fromisoformat(str(payload["as_of_session_date"]))
                if schema == T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA
                else None
            ),
            calendar_artifact_id=(
                ArtifactId(str(payload["calendar_artifact_id"]))
                if schema == T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA
                else None
            ),
            calendar_content_hash=(
                str(payload["calendar_content_hash"])
                if schema == T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA
                else None
            ),
            source_trading_status_ids=tuple(
                ArtifactId(str(item)) for item in status_ids
            ),
        )


@dataclass(slots=True)
class _MutableLot:
    source_fill_id: FillId
    symbol: str
    quantity_remaining: int
    unit_cost: float
    acquired_at: datetime
    trade_date: date | None = None
    sellable_from_session: date | None = None


class PositionProjector:
    """Pure projector. Its only state-changing evidence input is Fill."""

    def project(
        self,
        *,
        account_id: str,
        symbol: str,
        fills: tuple[Fill, ...],
        as_of: datetime,
    ) -> PositionSnapshot:
        if not fills:
            raise ValueError("PositionSnapshot requires at least one Fill")
        ordered_fills = tuple(
            sorted(fills, key=lambda item: (item.recorded_at, str(item.fill_id)))
        )
        source_ids = tuple(item.fill_id for item in ordered_fills)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate FillId cannot enter Position projection")
        if any(
            item.account_id != account_id or item.symbol != symbol
            for item in ordered_fills
        ):
            raise ValueError("Position Fill scope mismatch")
        if any(item.recorded_at > as_of for item in ordered_fills):
            raise ValueError("Position projection cannot consume future recorded Fill")
        effective = _effective_fills(ordered_fills)
        lots: list[_MutableLot] = []
        realized_pnl = 0.0
        reconciliation = False
        for fill in effective:
            if fill.side is TradeSide.BUY:
                lots.append(
                    _MutableLot(
                        source_fill_id=fill.fill_id,
                        symbol=symbol,
                        quantity_remaining=fill.quantity,
                        unit_cost=(fill.price * fill.quantity + fill.fees) / fill.quantity,
                        acquired_at=fill.occurred_at,
                    )
                )
                continue
            remaining = fill.quantity
            sell_fee_remaining = fill.fees
            for lot in lots:
                if remaining == 0:
                    break
                consumed = min(remaining, lot.quantity_remaining)
                allocated_fee = fill.fees * consumed / fill.quantity
                sell_fee_remaining -= allocated_fee
                realized_pnl += consumed * (fill.price - lot.unit_cost) - allocated_fee
                lot.quantity_remaining -= consumed
                remaining -= consumed
            realized_pnl -= max(0.0, sell_fee_remaining)
            lots = [item for item in lots if item.quantity_remaining > 0]
            if remaining > 0:
                reconciliation = True
        frozen_lots = tuple(
            PositionLot(
                source_fill_id=item.source_fill_id,
                symbol=item.symbol,
                quantity_remaining=item.quantity_remaining,
                unit_cost=item.unit_cost,
                acquired_at=item.acquired_at,
            )
            for item in lots
        )
        total = sum(item.quantity_remaining for item in frozen_lots)
        average = (
            sum(item.quantity_remaining * item.unit_cost for item in frozen_lots) / total
            if total
            else None
        )
        state = (
            PositionState.RECONCILIATION_REQUIRED
            if reconciliation
            else PositionState.OPEN if total else PositionState.CLOSED
        )
        reasons = (
            ("SELL_QUANTITY_EXCEEDS_AUTHORITATIVE_LOTS",)
            if reconciliation
            else ("POSITION_REBUILT_FROM_APPEND_ONLY_FILLS",)
        )
        semantic = {
            "schema_version": POSITION_SNAPSHOT_SCHEMA,
            "account_id": account_id,
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "state": state.value,
            "total_quantity": total,
            "average_cost": average,
            "realized_pnl": realized_pnl,
            "lots": [item.to_canonical_dict() for item in frozen_lots],
            "source_fill_ids": [str(item) for item in source_ids],
            "effective_fill_ids": [str(item.fill_id) for item in effective],
            "version": len(source_ids),
            "reason_codes": list(reasons),
        }
        return PositionSnapshot(
            schema_version=POSITION_SNAPSHOT_SCHEMA,
            snapshot_id=_snapshot_id(semantic),
            account_id=account_id,
            symbol=symbol,
            as_of=as_of,
            state=state,
            total_quantity=total,
            average_cost=average,
            realized_pnl=realized_pnl,
            lots=frozen_lots,
            source_fill_ids=source_ids,
            effective_fill_ids=tuple(item.fill_id for item in effective),
            version=len(source_ids),
            reason_codes=reasons,
        )

    def project_book(
        self,
        *,
        book: PositionBook,
        trades: tuple[ManualTradeRecord, ...],
        fills: tuple[Fill, ...],
        as_of: datetime,
    ) -> PositionSnapshot:
        """Project one Thesis book and reject any cross-book Fill."""

        if not trades:
            raise ValueError("traceable Position requires ManualTrade records")
        trade_by_id = {item.manual_trade_id: item for item in trades}
        if len(trade_by_id) != len(trades):
            raise ValueError("duplicate ManualTrade identity in Position book")
        for trade in trades:
            if (
                trade.schema_version != TRACEABLE_MANUAL_TRADE_SCHEMA
                or trade.position_book_id != book.position_book_id
                or trade.thesis_id != book.thesis_id
                or trade.opportunity_id != book.opportunity_id
                or trade.account_id != book.account_id
                or trade.symbol != book.symbol
            ):
                raise ValueError("ManualTrade does not belong to Position book")
        fill_trade_ids = {item.manual_trade_id for item in fills}
        if not fill_trade_ids or not fill_trade_ids.issubset(trade_by_id):
            raise ValueError("Fill does not belong to Position book ManualTrade")
        base = self.project(
            account_id=book.account_id,
            symbol=book.symbol,
            fills=fills,
            as_of=as_of,
        )
        manual_ids = tuple(sorted(fill_trade_ids, key=str))
        semantic = {
            **base.semantic_payload(),
            "schema_version": TRACEABLE_POSITION_SNAPSHOT_SCHEMA,
            "position_book_id": str(book.position_book_id),
            "thesis_id": str(book.thesis_id),
            "opportunity_id": str(book.opportunity_id),
            "source_manual_trade_ids": [str(item) for item in manual_ids],
        }
        return PositionSnapshot(
            schema_version=TRACEABLE_POSITION_SNAPSHOT_SCHEMA,
            snapshot_id=_snapshot_id(semantic),
            account_id=base.account_id,
            symbol=base.symbol,
            as_of=base.as_of,
            state=base.state,
            total_quantity=base.total_quantity,
            average_cost=base.average_cost,
            realized_pnl=base.realized_pnl,
            lots=base.lots,
            source_fill_ids=base.source_fill_ids,
            effective_fill_ids=base.effective_fill_ids,
            version=base.version,
            reason_codes=base.reason_codes,
            position_book_id=book.position_book_id,
            thesis_id=book.thesis_id,
            opportunity_id=book.opportunity_id,
            source_manual_trade_ids=manual_ids,
        )

    def project_book_t_plus_one(
        self,
        *,
        book: PositionBook,
        trades: tuple[ManualTradeRecord, ...],
        fills: tuple[Fill, ...],
        calendar: TradingCalendarArtifact,
        symbol_session_statuses: tuple[SymbolTradingSessionStatus, ...],
        as_of: datetime,
    ) -> PositionSnapshot:
        """Rebuild A-share sellability from Fill and explicit session evidence."""

        _validate_traceable_book_inputs(book, trades, fills)
        if calendar.market != "CN_A_SHARE":
            raise ValueError("T+1 Position requires CN_A_SHARE calendar authority")
        if as_of.tzinfo is None:
            raise ValueError("Position as_of must be timezone-aware")
        zone = ZoneInfo(calendar.timezone_name)
        as_of_session = as_of.astimezone(zone).date()
        if not calendar.contains(as_of_session):
            raise LookupError("Position assessment date is absent from calendar authority")
        statuses = tuple(
            sorted(
                symbol_session_statuses,
                key=lambda item: (item.session_date, str(item.status_id)),
            )
        )
        status_by_date = {item.session_date: item for item in statuses}
        if len(status_by_date) != len(statuses):
            raise ValueError("symbol session status dates must be unique")
        if any(item.symbol != book.symbol for item in statuses):
            raise ValueError("symbol session status scope mismatch")
        if any(not calendar.contains(item.session_date) for item in statuses):
            raise ValueError("symbol status references a non-calendar session")
        current_status = status_by_date.get(as_of_session)
        if current_status is None:
            raise ValueError("symbol session status evidence is required for as_of")
        if any(item.availability_time > as_of for item in statuses):
            raise ValueError("unavailable symbol session status cannot enter Position")

        ordered_fills = tuple(
            sorted(fills, key=lambda item: (item.recorded_at, str(item.fill_id)))
        )
        if any(item.recorded_at > as_of for item in ordered_fills):
            raise ValueError("Position projection cannot consume future recorded Fill")
        effective = _effective_fills(ordered_fills)
        lots: list[_MutableLot] = []
        realized_pnl = 0.0
        reconciliation_reasons: set[str] = set()
        for fill in effective:
            trade_date = fill.occurred_at.astimezone(zone).date()
            if not calendar.contains(trade_date):
                raise LookupError("Fill trade date is absent from calendar authority")
            if fill.side is TradeSide.BUY:
                sellable_session = calendar.resolve_next_session_date(
                    DecisionTime(fill.occurred_at)
                )
                lots.append(
                    _MutableLot(
                        source_fill_id=fill.fill_id,
                        symbol=book.symbol,
                        quantity_remaining=fill.quantity,
                        unit_cost=(
                            fill.price * fill.quantity + fill.fees
                        )
                        / fill.quantity,
                        acquired_at=fill.occurred_at,
                        trade_date=trade_date,
                        sellable_from_session=sellable_session,
                    )
                )
                continue

            sell_status = status_by_date.get(trade_date)
            if sell_status is None:
                raise ValueError(
                    "symbol session status evidence is required for sell Fill"
                )
            if sell_status.state is not SymbolTradingState.TRADABLE:
                reconciliation_reasons.add("SELL_RECORDED_WHILE_SYMBOL_NOT_TRADABLE")
            remaining = fill.quantity
            sell_fee_remaining = fill.fees
            for lot in lots:
                if remaining == 0:
                    break
                assert lot.sellable_from_session is not None
                if lot.sellable_from_session > trade_date:
                    continue
                consumed = min(remaining, lot.quantity_remaining)
                allocated_fee = fill.fees * consumed / fill.quantity
                sell_fee_remaining -= allocated_fee
                realized_pnl += consumed * (fill.price - lot.unit_cost) - allocated_fee
                lot.quantity_remaining -= consumed
                remaining -= consumed
            realized_pnl -= max(0.0, sell_fee_remaining)
            lots = [item for item in lots if item.quantity_remaining > 0]
            if remaining > 0:
                reconciliation_reasons.add("T_PLUS_ONE_SELL_EXCEEDS_AVAILABLE")

        settled_lots: list[PositionLot] = []
        for lot in lots:
            assert lot.trade_date is not None
            assert lot.sellable_from_session is not None
            legally_settled = lot.sellable_from_session <= as_of_session
            if not legally_settled:
                available = 0
                settlement_state = LotSettlementState.FROZEN_T_PLUS_ONE
            elif current_status.state is SymbolTradingState.TRADABLE:
                available = lot.quantity_remaining
                settlement_state = LotSettlementState.SELLABLE
            elif current_status.state is SymbolTradingState.SUSPENDED:
                available = 0
                settlement_state = LotSettlementState.FROZEN_MARKET_CONSTRAINT
            else:
                available = 0
                settlement_state = LotSettlementState.DATA_INSUFFICIENT
            settled_lots.append(
                PositionLot(
                    source_fill_id=lot.source_fill_id,
                    symbol=lot.symbol,
                    quantity_remaining=lot.quantity_remaining,
                    unit_cost=lot.unit_cost,
                    acquired_at=lot.acquired_at,
                    trade_date=lot.trade_date,
                    available_quantity=available,
                    frozen_quantity=lot.quantity_remaining - available,
                    sellable_from_session=lot.sellable_from_session,
                    settlement_state=settlement_state,
                )
            )
        frozen_lots = tuple(settled_lots)
        total = sum(item.quantity_remaining for item in frozen_lots)
        available_quantity = sum(
            item.available_quantity or 0 for item in frozen_lots
        )
        frozen_quantity = total - available_quantity
        today_acquired = sum(
            item.quantity_remaining
            for item in frozen_lots
            if item.trade_date == as_of_session
        )
        average = (
            sum(item.quantity_remaining * item.unit_cost for item in frozen_lots)
            / total
            if total
            else None
        )
        reasons = {"POSITION_REBUILT_FROM_APPEND_ONLY_FILLS_AND_CALENDAR"}
        reasons.update(reconciliation_reasons)
        if reconciliation_reasons:
            state = PositionState.RECONCILIATION_REQUIRED
            sellability = PositionSellabilityState.RECONCILIATION_REQUIRED
        elif total == 0:
            state = PositionState.CLOSED
            sellability = PositionSellabilityState.CLOSED
        elif current_status.state is SymbolTradingState.SUSPENDED:
            state = PositionState.OPEN
            sellability = PositionSellabilityState.SUSPENDED
            reasons.add("SYMBOL_SUSPENDED")
        elif current_status.state is SymbolTradingState.UNKNOWN:
            state = PositionState.OPEN
            sellability = PositionSellabilityState.DATA_INSUFFICIENT
            reasons.add("SYMBOL_TRADING_STATE_UNKNOWN")
        elif available_quantity == 0:
            state = PositionState.OPEN
            sellability = PositionSellabilityState.T_PLUS_ONE_FROZEN
            reasons.add("T_PLUS_ONE_POSITION_FROZEN")
        elif available_quantity < total:
            state = PositionState.OPEN
            sellability = PositionSellabilityState.PARTIALLY_AVAILABLE
            reasons.add("POSITION_PARTIALLY_SELLABLE")
        else:
            state = PositionState.OPEN
            sellability = PositionSellabilityState.AVAILABLE
            reasons.add("POSITION_FULLY_SELLABLE")
        source_ids = tuple(item.fill_id for item in ordered_fills)
        effective_ids = tuple(item.fill_id for item in effective)
        manual_ids = tuple(
            sorted({item.manual_trade_id for item in fills}, key=str)
        )
        status_ids = tuple(sorted((item.status_id for item in statuses), key=str))
        semantic = {
            "schema_version": T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
            "account_id": book.account_id,
            "symbol": book.symbol,
            "as_of": as_of.isoformat(),
            "state": state.value,
            "total_quantity": total,
            "average_cost": average,
            "realized_pnl": realized_pnl,
            "lots": [item.to_canonical_dict() for item in frozen_lots],
            "source_fill_ids": [str(item) for item in source_ids],
            "effective_fill_ids": [str(item) for item in effective_ids],
            "version": len(source_ids),
            "reason_codes": sorted(reasons),
            "position_book_id": str(book.position_book_id),
            "thesis_id": str(book.thesis_id),
            "opportunity_id": str(book.opportunity_id),
            "source_manual_trade_ids": [str(item) for item in manual_ids],
            "available_quantity": available_quantity,
            "frozen_quantity": frozen_quantity,
            "today_acquired_quantity": today_acquired,
            "sellability_state": sellability.value,
            "as_of_session_date": as_of_session.isoformat(),
            "calendar_artifact_id": str(calendar.artifact_id),
            "calendar_content_hash": calendar.content_hash,
            "source_trading_status_ids": [str(item) for item in status_ids],
        }
        return PositionSnapshot(
            schema_version=T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
            snapshot_id=_snapshot_id(semantic),
            account_id=book.account_id,
            symbol=book.symbol,
            as_of=as_of,
            state=state,
            total_quantity=total,
            average_cost=average,
            realized_pnl=realized_pnl,
            lots=frozen_lots,
            source_fill_ids=source_ids,
            effective_fill_ids=effective_ids,
            version=len(source_ids),
            reason_codes=tuple(sorted(reasons)),
            position_book_id=book.position_book_id,
            thesis_id=book.thesis_id,
            opportunity_id=book.opportunity_id,
            source_manual_trade_ids=manual_ids,
            available_quantity=available_quantity,
            frozen_quantity=frozen_quantity,
            today_acquired_quantity=today_acquired,
            sellability_state=sellability,
            as_of_session_date=as_of_session,
            calendar_artifact_id=calendar.artifact_id,
            calendar_content_hash=calendar.content_hash,
            source_trading_status_ids=status_ids,
        )


def _validate_traceable_book_inputs(
    book: PositionBook,
    trades: tuple[ManualTradeRecord, ...],
    fills: tuple[Fill, ...],
) -> None:
    if not trades:
        raise ValueError("traceable Position requires ManualTrade records")
    trade_by_id = {item.manual_trade_id: item for item in trades}
    if len(trade_by_id) != len(trades):
        raise ValueError("duplicate ManualTrade identity in Position book")
    for trade in trades:
        if (
            trade.schema_version != TRACEABLE_MANUAL_TRADE_SCHEMA
            or trade.position_book_id != book.position_book_id
            or trade.thesis_id != book.thesis_id
            or trade.opportunity_id != book.opportunity_id
            or trade.account_id != book.account_id
            or trade.symbol != book.symbol
        ):
            raise ValueError("ManualTrade does not belong to Position book")
    fill_trade_ids = {item.manual_trade_id for item in fills}
    if not fill_trade_ids or not fill_trade_ids.issubset(trade_by_id):
        raise ValueError("Fill does not belong to Position book ManualTrade")
    if len({item.fill_id for item in fills}) != len(fills):
        raise ValueError("duplicate FillId cannot enter Position projection")
    if any(
        item.account_id != book.account_id or item.symbol != book.symbol
        for item in fills
    ):
        raise ValueError("Position Fill scope mismatch")


def _effective_fills(fills: tuple[Fill, ...]) -> tuple[Fill, ...]:
    executions: dict[FillId, Fill] = {}
    corrections: dict[FillId, Fill] = {}
    for fill in sorted(fills, key=lambda item: (item.recorded_at, str(item.fill_id))):
        if fill.fill_kind is FillKind.EXECUTION:
            executions[fill.fill_id] = fill
            continue
        assert fill.correction_of_fill_id is not None
        original = executions.get(fill.correction_of_fill_id)
        if original is None:
            raise ValueError("correction Fill references unknown execution Fill")
        if fill.correction_of_fill_id in corrections:
            raise ValueError("execution Fill cannot have multiple corrections")
        if (
            fill.manual_trade_id != original.manual_trade_id
            or fill.account_id != original.account_id
            or fill.symbol != original.symbol
        ):
            raise ValueError("correction Fill scope mismatch")
        corrections[fill.correction_of_fill_id] = fill
    effective = tuple(corrections.get(fill_id, fill) for fill_id, fill in executions.items())
    return tuple(sorted(effective, key=lambda item: (item.occurred_at, str(item.fill_id))))


def _snapshot_id(payload: dict[str, Any]) -> PositionSnapshotId:
    digest = canonical_hash(payload).split(":", 1)[1]
    return PositionSnapshotId(f"position-snapshot-{digest[:24]}")


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Position value must be an object")
    return value
