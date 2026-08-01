"""SQLite manual execution ledger with append-only Fill enforcement."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from market_regime_alpha.core.identity import FillId, ManualTradeId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    Fill,
    FillKind,
    ManualOrderState,
    ManualTradeRecord,
    TradeSide,
    validate_manual_trade_transition,
)
from market_regime_alpha.portfolio.lifecycle import (
    PortfolioDecision,
    RiskDecision,
    RiskDecisionState,
    TargetPosition,
)
from market_regime_alpha.portfolio.services import IndependentRiskService


_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
MANUAL_EXECUTION_UP_MIGRATION = _MIGRATION_ROOT / "004_manual_execution_up.sql"
MANUAL_EXECUTION_DOWN_MIGRATION = _MIGRATION_ROOT / "004_manual_execution_down.sql"


class ExecutionVersionConflictError(RuntimeError):
    pass


class SQLiteManualExecutionRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                MANUAL_EXECUTION_UP_MIGRATION.read_text(encoding="utf-8")
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    def create_trade(
        self,
        record: ManualTradeRecord,
        *,
        risk_decision: RiskDecision,
        portfolio_decision: PortfolioDecision,
        target_position: TargetPosition,
        idempotency_key: str,
        command_hash: str,
    ) -> ManualTradeRecord:
        _validate_authority(record, risk_decision, portfolio_decision, target_position)
        if record.state is not ManualOrderState.RECORDED or record.version != 0:
            raise ValueError("new ManualTradeRecord must be RECORDED version 0")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash, record.manual_trade_id)
                    result = _load_trade(
                        connection,
                        record.manual_trade_id,
                        int(command["result_version"]),
                    )
                    connection.commit()
                    return result
                existing = connection.execute(
                    "SELECT aggregate_json FROM manual_trade_records WHERE manual_trade_id = ?",
                    (str(record.manual_trade_id),),
                ).fetchone()
                if existing is not None:
                    current = ManualTradeRecord.from_canonical_dict(
                        _object_json(str(existing["aggregate_json"]))
                    )
                    if current != record:
                        raise ValueError("ManualTradeRecord identity conflict")
                else:
                    connection.execute(
                        """
                        INSERT INTO manual_trade_records(
                            manual_trade_id, risk_decision_id, account_id, symbol,
                            side, state, filled_quantity, aggregate_json, version
                        ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, 0)
                        """,
                        (
                            str(record.manual_trade_id),
                            str(record.risk_decision_id),
                            record.account_id,
                            record.symbol,
                            record.side.value,
                            record.state.value,
                            _json(record.to_canonical_dict()),
                        ),
                    )
                    _insert_trade_event(connection, record, idempotency_key)
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    record=record,
                    fill=None,
                )
                connection.commit()
                return record
            except Exception:
                connection.rollback()
                raise

    def append_fill(
        self,
        fill: Fill,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> tuple[ManualTradeRecord, Fill]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash, fill.manual_trade_id)
                    stored_fill = _load_fill(connection, FillId(str(command["fill_id"])))
                    record = _load_trade(
                        connection,
                        fill.manual_trade_id,
                        int(command["result_version"]),
                    )
                    connection.commit()
                    return record, stored_fill
                current = _load_trade(connection, fill.manual_trade_id)
                if fill.account_id != current.account_id or fill.symbol != current.symbol:
                    raise ValueError("Fill scope does not match ManualTradeRecord")
                if fill.side is not current.side:
                    raise ValueError("Fill side does not match ManualTradeRecord")
                if current.state in {ManualOrderState.CANCELLED, ManualOrderState.REJECTED}:
                    raise ValueError("terminal cancelled/rejected trade cannot accept Fill")
                if current.state is ManualOrderState.FILLED and fill.fill_kind is FillKind.EXECUTION:
                    raise ValueError("filled trade accepts correction records only")
                existing_fill = connection.execute(
                    "SELECT fill_json FROM manual_fills WHERE fill_id = ? OR external_fill_id = ?",
                    (str(fill.fill_id), fill.external_fill_id),
                ).fetchone()
                if existing_fill is not None:
                    stored = Fill.from_canonical_dict(
                        _object_json(str(existing_fill["fill_json"]))
                    )
                    if stored != fill:
                        raise ValueError("duplicate Fill identity has conflicting semantics")
                    raise ValueError("Fill already exists under a different idempotency key")
                existing_fills = _fills_for_trade(connection, fill.manual_trade_id)
                if fill.fill_kind is FillKind.CORRECTION:
                    assert fill.correction_of_fill_id is not None
                    originals = {item.fill_id: item for item in existing_fills}
                    original = originals.get(fill.correction_of_fill_id)
                    if original is None or original.fill_kind is not FillKind.EXECUTION:
                        raise ValueError("correction target must be an execution Fill")
                    if any(
                        item.correction_of_fill_id == fill.correction_of_fill_id
                        for item in existing_fills
                    ):
                        raise ValueError("execution Fill already has a correction")
                connection.execute(
                    """
                    INSERT INTO manual_fills(
                        fill_id, external_fill_id, manual_trade_id, account_id,
                        symbol, fill_kind, correction_of_fill_id, fill_json,
                        recorded_at, idempotency_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(fill.fill_id),
                        fill.external_fill_id,
                        str(fill.manual_trade_id),
                        fill.account_id,
                        fill.symbol,
                        fill.fill_kind.value,
                        (
                            str(fill.correction_of_fill_id)
                            if fill.correction_of_fill_id is not None
                            else None
                        ),
                        _json(fill.to_canonical_dict()),
                        fill.recorded_at.isoformat(),
                        idempotency_key,
                    ),
                )
                all_fills = (*existing_fills, fill)
                effective_quantity = _effective_quantity(all_fills)
                if effective_quantity < current.intended_quantity:
                    state = ManualOrderState.PARTIALLY_FILLED
                elif effective_quantity == current.intended_quantity:
                    state = ManualOrderState.FILLED
                else:
                    state = ManualOrderState.RECONCILIATION_REQUIRED
                updated = ManualTradeRecord.from_canonical_dict(
                    {
                        **current.to_canonical_dict(),
                        "state": state.value,
                        "filled_quantity": effective_quantity,
                        "version": current.version + 1,
                        "updated_at": fill.recorded_at.isoformat(),
                        "last_actor": fill.actor,
                        "last_reason": fill.reason,
                    }
                )
                validate_manual_trade_transition(current, updated)
                _update_trade(connection, updated, current.version)
                _insert_trade_event(
                    connection, updated, f"{idempotency_key}:trade"
                )
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    record=updated,
                    fill=fill,
                )
                connection.commit()
                return updated, fill
            except Exception:
                connection.rollback()
                raise

    def transition_trade(
        self,
        record: ManualTradeRecord,
        *,
        expected_version: int,
        idempotency_key: str,
        command_hash: str,
    ) -> ManualTradeRecord:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash, record.manual_trade_id)
                    result = _load_trade(
                        connection,
                        record.manual_trade_id,
                        int(command["result_version"]),
                    )
                    connection.commit()
                    return result
                current = _load_trade(connection, record.manual_trade_id)
                if current.version != expected_version:
                    raise ExecutionVersionConflictError("manual trade CAS conflict")
                validate_manual_trade_transition(current, record)
                _update_trade(connection, record, expected_version)
                _insert_trade_event(connection, record, idempotency_key)
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    record=record,
                    fill=None,
                )
                connection.commit()
                return record
            except Exception:
                connection.rollback()
                raise

    def get_trade(self, trade_id: ManualTradeId) -> ManualTradeRecord:
        with self._connect() as connection:
            return _load_trade(connection, trade_id)

    def fills_for_trade(self, trade_id: ManualTradeId) -> tuple[Fill, ...]:
        with self._connect() as connection:
            return _fills_for_trade(connection, trade_id)

    def all_fills(self, account_id: str, symbol: str) -> tuple[Fill, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT fill_json FROM manual_fills
                WHERE account_id = ? AND symbol = ? ORDER BY recorded_at, fill_id
                """,
                (account_id, symbol),
            ).fetchall()
            return tuple(
                Fill.from_canonical_dict(_object_json(str(item["fill_json"])))
                for item in rows
            )


def _validate_authority(
    record: ManualTradeRecord,
    risk: RiskDecision,
    portfolio: PortfolioDecision,
    target: TargetPosition,
) -> None:
    if risk.state is not RiskDecisionState.APPROVED:
        raise ValueError("ManualTradeRecord requires approved RiskDecision")
    if risk.portfolio_decision_id != portfolio.decision_id:
        raise ValueError("RiskDecision and PortfolioDecision mismatch")
    expected_risk = IndependentRiskService().assess(
        portfolio,
        actor=risk.actor,
        reason=risk.reason,
        started_at=risk.started_at,
        completed_at=risk.completed_at,
    )
    if expected_risk != risk:
        raise ValueError("ManualTradeRecord requires independently valid RiskDecision")
    if target not in portfolio.target_positions:
        raise ValueError("ManualTradeRecord TargetPosition is not in PortfolioDecision")
    expected_side = TradeSide.BUY if target.trade_quantity > 0 else TradeSide.SELL
    if target.trade_quantity == 0:
        raise ValueError("zero TargetPosition delta cannot create ManualTradeRecord")
    if (
        record.risk_decision_id != risk.risk_decision_id
        or record.risk_decision_hash != canonical_hash(risk.to_canonical_dict())
        or record.portfolio_decision_id != portfolio.decision_id
        or record.target_position_hash != canonical_hash(target.to_canonical_dict())
        or record.symbol != target.symbol
        or record.side is not expected_side
        or record.intended_quantity != abs(target.trade_quantity)
    ):
        raise ValueError("ManualTradeRecord authority binding mismatch")


def _effective_quantity(fills: tuple[Fill, ...]) -> int:
    executions = {item.fill_id: item for item in fills if item.fill_kind is FillKind.EXECUTION}
    corrections = {
        item.correction_of_fill_id: item
        for item in fills
        if item.fill_kind is FillKind.CORRECTION
    }
    return sum(corrections.get(fill_id, fill).quantity for fill_id, fill in executions.items())


def _load_trade(
    connection: sqlite3.Connection,
    trade_id: ManualTradeId,
    version: int | None = None,
) -> ManualTradeRecord:
    row = connection.execute(
        "SELECT * FROM manual_trade_records WHERE manual_trade_id = ?",
        (str(trade_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown ManualTradeRecord: {trade_id}")
    current_version = int(row["version"])
    requested = current_version if version is None else version
    events = connection.execute(
        """
        SELECT aggregate_json FROM manual_trade_events
        WHERE manual_trade_id = ? AND sequence <= ? ORDER BY sequence
        """,
        (str(trade_id), requested),
    ).fetchall()
    if requested < 0 or requested > current_version or len(events) != requested + 1:
        raise ValueError("ManualTradeRecord history is not contiguous")
    history = tuple(
        ManualTradeRecord.from_canonical_dict(_object_json(str(item["aggregate_json"])))
        for item in events
    )
    for before, after in zip(history, history[1:]):
        validate_manual_trade_transition(before, after)
    result = history[-1]
    if requested == current_version:
        stored = ManualTradeRecord.from_canonical_dict(
            _object_json(str(row["aggregate_json"]))
        )
        if stored != result or row["state"] != result.state.value:
            raise ValueError("ManualTradeRecord projection is not reconstructible")
    return result


def _load_fill(connection: sqlite3.Connection, fill_id: FillId) -> Fill:
    row = connection.execute(
        "SELECT fill_json FROM manual_fills WHERE fill_id = ?", (str(fill_id),)
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown Fill: {fill_id}")
    return Fill.from_canonical_dict(_object_json(str(row["fill_json"])))


def _fills_for_trade(
    connection: sqlite3.Connection, trade_id: ManualTradeId
) -> tuple[Fill, ...]:
    rows = connection.execute(
        """
        SELECT fill_json FROM manual_fills
        WHERE manual_trade_id = ? ORDER BY recorded_at, fill_id
        """,
        (str(trade_id),),
    ).fetchall()
    return tuple(
        Fill.from_canonical_dict(_object_json(str(item["fill_json"])))
        for item in rows
    )


def _update_trade(
    connection: sqlite3.Connection, record: ManualTradeRecord, expected_version: int
) -> None:
    updated = connection.execute(
        """
        UPDATE manual_trade_records
        SET state = ?, filled_quantity = ?, aggregate_json = ?, version = ?
        WHERE manual_trade_id = ? AND version = ?
        """,
        (
            record.state.value,
            record.filled_quantity,
            _json(record.to_canonical_dict()),
            record.version,
            str(record.manual_trade_id),
            expected_version,
        ),
    )
    if updated.rowcount != 1:
        raise ExecutionVersionConflictError("manual trade compare-and-swap failed")


def _insert_trade_event(
    connection: sqlite3.Connection, record: ManualTradeRecord, idempotency_key: str
) -> None:
    connection.execute(
        """
        INSERT INTO manual_trade_events(
            manual_trade_id, sequence, state, aggregate_json,
            idempotency_key, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(record.manual_trade_id),
            record.version,
            record.state.value,
            _json(record.to_canonical_dict()),
            idempotency_key,
            record.updated_at.isoformat(),
        ),
    )


def _command(connection: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM execution_commands WHERE idempotency_key = ?", (key,)
    ).fetchone()


def _validate_command(
    row: sqlite3.Row, command_hash: str, trade_id: ManualTradeId
) -> None:
    if row["command_hash"] != command_hash or row["manual_trade_id"] != str(trade_id):
        raise ValueError("idempotency key reused for different execution command")


def _insert_command(
    connection: sqlite3.Connection,
    *,
    idempotency_key: str,
    command_hash: str,
    record: ManualTradeRecord,
    fill: Fill | None,
) -> None:
    connection.execute(
        """
        INSERT INTO execution_commands(
            idempotency_key, command_hash, manual_trade_id,
            fill_id, result_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            idempotency_key,
            command_hash,
            str(record.manual_trade_id),
            str(fill.fill_id) if fill is not None else None,
            record.version,
            datetime.now(UTC).isoformat(),
        ),
    )


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _object_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("manual execution JSON must be an object")
    return payload
