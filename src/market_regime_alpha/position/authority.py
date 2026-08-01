"""Authoritative PositionSnapshot rebuilt solely from append-only Fill events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import FillId, PositionSnapshotId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import Fill, FillKind, TradeSide


POSITION_SNAPSHOT_SCHEMA = "position-snapshot-v1"


class PositionState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class PositionLot:
    source_fill_id: FillId
    symbol: str
    quantity_remaining: int
    unit_cost: float
    acquired_at: datetime

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "source_fill_id": str(self.source_fill_id),
            "symbol": self.symbol,
            "quantity_remaining": self.quantity_remaining,
            "unit_cost": self.unit_cost,
            "acquired_at": self.acquired_at.isoformat(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> PositionLot:
        expected = {
            "source_fill_id",
            "symbol",
            "quantity_remaining",
            "unit_cost",
            "acquired_at",
        }
        if set(payload) != expected:
            raise ValueError("PositionLot fields mismatch")
        return cls(
            source_fill_id=FillId(str(payload["source_fill_id"])),
            symbol=str(payload["symbol"]),
            quantity_remaining=int(payload["quantity_remaining"]),
            unit_cost=float(payload["unit_cost"]),
            acquired_at=datetime.fromisoformat(str(payload["acquired_at"])),
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

    def __post_init__(self) -> None:
        if self.schema_version != POSITION_SNAPSHOT_SCHEMA:
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
        expected = _snapshot_id(self.semantic_payload())
        if self.snapshot_id != expected:
            raise ValueError("PositionSnapshot content identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
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
        if set(payload) != expected:
            raise ValueError("PositionSnapshot fields mismatch")
        lots = payload["lots"]
        source_ids = payload["source_fill_ids"]
        effective_ids = payload["effective_fill_ids"]
        reasons = payload["reason_codes"]
        if not all(
            isinstance(value, list)
            for value in (lots, source_ids, effective_ids, reasons)
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
        )


@dataclass(slots=True)
class _MutableLot:
    source_fill_id: FillId
    symbol: str
    quantity_remaining: int
    unit_cost: float
    acquired_at: datetime


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
