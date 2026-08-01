"""SQLite adapter for Thesis-scoped manual execution traceability."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from market_regime_alpha.core.identity import ManualTradeId, PositionBookId
from market_regime_alpha.decision.opportunity import OpportunityState, TradingOpportunity
from market_regime_alpha.decision.thesis import ThesisState, TradingThesis
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    TRACEABLE_MANUAL_TRADE_SCHEMA,
    Fill,
    ManualOrderState,
    ManualTradeRecord,
    TradeSide,
)
from market_regime_alpha.execution.position_book import (
    PositionBook,
    PositionBookState,
)
from market_regime_alpha.execution.sqlite_repository import (
    ExecutionVersionConflictError,
    SQLiteManualExecutionRepository,
    _command,
    _insert_command,
    _insert_trade_event,
    _json,
    _load_trade,
    _object_json,
    _validate_command,
)
from market_regime_alpha.portfolio.account_authority import (
    CompleteAccountPortfolioDecision,
    CompleteAccountRiskDecision,
    CompleteAccountRiskService,
    ProposedTradeDelta,
)
from market_regime_alpha.portfolio.lifecycle import RiskDecisionState


_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
EXECUTION_TRACEABILITY_UP_MIGRATION = (
    _MIGRATION_ROOT / "006_execution_traceability_up.sql"
)
EXECUTION_TRACEABILITY_DOWN_MIGRATION = (
    _MIGRATION_ROOT / "006_execution_traceability_down.sql"
)


class SQLiteTraceableManualExecutionRepository(SQLiteManualExecutionRepository):
    """One Fill ledger plus an immutable authority-chain index."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        with self._connect() as connection:
            connection.executescript(
                EXECUTION_TRACEABILITY_UP_MIGRATION.read_text(encoding="utf-8")
            )

    def create_traceable_trade(
        self,
        record: ManualTradeRecord,
        *,
        book: PositionBook,
        opportunity: TradingOpportunity,
        thesis: TradingThesis,
        risk_decision: CompleteAccountRiskDecision,
        portfolio_decision: CompleteAccountPortfolioDecision,
        trade_delta: ProposedTradeDelta,
        idempotency_key: str,
        command_hash: str,
    ) -> tuple[PositionBook, ManualTradeRecord]:
        _validate_trace_authority(
            record,
            book=book,
            opportunity=opportunity,
            thesis=thesis,
            risk=risk_decision,
            portfolio=portfolio_decision,
            delta=trade_delta,
        )
        if record.state is not ManualOrderState.RECORDED or record.version != 0:
            raise ValueError("new traceable ManualTradeRecord must be RECORDED version 0")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash, record.manual_trade_id)
                    stored_trade = _load_trade(
                        connection,
                        record.manual_trade_id,
                        int(command["result_version"]),
                    )
                    stored_book = _load_book(connection, book.position_book_id)
                    connection.commit()
                    return stored_book, stored_trade

                stored_book = _open_or_validate_book(connection, book, idempotency_key)
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
                    binding = connection.execute(
                        "SELECT position_book_id FROM traceable_manual_trade_bindings "
                        "WHERE manual_trade_id = ?",
                        (str(record.manual_trade_id),),
                    ).fetchone()
                    if binding is None or binding["position_book_id"] != str(
                        book.position_book_id
                    ):
                        raise ValueError("ManualTradeRecord trace binding conflict")
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
                    connection.execute(
                        """
                        INSERT INTO traceable_manual_trade_bindings(
                            manual_trade_id, position_book_id, opportunity_id,
                            thesis_id, portfolio_decision_id, risk_decision_id,
                            post_trade_snapshot_id, post_trade_snapshot_hash,
                            target_delta_hash, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(record.manual_trade_id),
                            str(book.position_book_id),
                            str(opportunity.opportunity_id),
                            str(thesis.thesis_id),
                            str(portfolio_decision.decision_id),
                            str(risk_decision.risk_decision_id),
                            str(portfolio_decision.post_trade.snapshot_id),
                            portfolio_decision.post_trade.content_hash,
                            canonical_hash(trade_delta.to_canonical_dict()),
                            record.created_at.isoformat(),
                        ),
                    )
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    record=record,
                    fill=None,
                )
                connection.commit()
                return stored_book, record
            except Exception:
                connection.rollback()
                raise

    def get_position_book(self, book_id: PositionBookId) -> PositionBook:
        with self._connect() as connection:
            return _load_book(connection, book_id)

    def get_trade(self, trade_id: ManualTradeId) -> ManualTradeRecord:
        with self._connect() as connection:
            record = _load_trade(connection, trade_id)
            if record.schema_version == TRACEABLE_MANUAL_TRADE_SCHEMA:
                _validate_stored_binding(connection, record)
            return record

    def trades_for_book(
        self, book_id: PositionBookId
    ) -> tuple[ManualTradeRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record.aggregate_json
                FROM traceable_manual_trade_bindings AS binding
                JOIN manual_trade_records AS record
                  ON record.manual_trade_id = binding.manual_trade_id
                WHERE binding.position_book_id = ?
                ORDER BY binding.created_at, binding.manual_trade_id
                """,
                (str(book_id),),
            ).fetchall()
            records = tuple(
                ManualTradeRecord.from_canonical_dict(
                    _object_json(str(row["aggregate_json"]))
                )
                for row in rows
            )
            for record in records:
                _validate_stored_binding(connection, record)
            return records

    def fills_for_book(self, book_id: PositionBookId) -> tuple[Fill, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT fill.fill_json
                FROM traceable_manual_trade_bindings AS binding
                JOIN manual_fills AS fill
                  ON fill.manual_trade_id = binding.manual_trade_id
                WHERE binding.position_book_id = ?
                ORDER BY fill.recorded_at, fill.fill_id
                """,
                (str(book_id),),
            ).fetchall()
            return tuple(
                Fill.from_canonical_dict(_object_json(str(row["fill_json"])))
                for row in rows
            )

    def close_position_book(
        self,
        book: PositionBook,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> PositionBook:
        if book.state is not PositionBookState.CLOSED:
            raise ValueError("PositionBook close repository requires CLOSED aggregate")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                duplicate = connection.execute(
                    "SELECT position_book_id, aggregate_json FROM position_book_events "
                    "WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if duplicate is not None:
                    if duplicate["position_book_id"] != str(book.position_book_id):
                        raise ValueError("PositionBook idempotency key reused")
                    result = PositionBook.from_canonical_dict(
                        _object_json(str(duplicate["aggregate_json"]))
                    )
                    if result != book:
                        raise ValueError("PositionBook idempotency semantics conflict")
                    connection.commit()
                    return result
                current = _load_book(connection, book.position_book_id)
                if current.version != expected_version:
                    raise ExecutionVersionConflictError("PositionBook CAS conflict")
                if (
                    current.state is not PositionBookState.OPEN
                    or book.version != current.version + 1
                    or book.account_id != current.account_id
                    or book.symbol != current.symbol
                    or book.thesis_id != current.thesis_id
                    or book.opportunity_id != current.opportunity_id
                    or book.opened_at != current.opened_at
                ):
                    raise ValueError("invalid PositionBook close transition")
                updated = connection.execute(
                    """
                    UPDATE position_books
                    SET state = ?, version = ?, aggregate_json = ?, closed_at = ?
                    WHERE position_book_id = ? AND version = ? AND state = 'OPEN'
                    """,
                    (
                        book.state.value,
                        book.version,
                        _json(book.to_canonical_dict()),
                        book.closed_at.isoformat() if book.closed_at else None,
                        str(book.position_book_id),
                        expected_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise ExecutionVersionConflictError(
                        "PositionBook compare-and-swap failed"
                    )
                _insert_book_event(connection, book, idempotency_key)
                connection.commit()
                return book
            except Exception:
                connection.rollback()
                raise


def _validate_trace_authority(
    record: ManualTradeRecord,
    *,
    book: PositionBook,
    opportunity: TradingOpportunity,
    thesis: TradingThesis,
    risk: CompleteAccountRiskDecision,
    portfolio: CompleteAccountPortfolioDecision,
    delta: ProposedTradeDelta,
) -> None:
    if risk.state is not RiskDecisionState.APPROVED:
        raise ValueError("traceable manual trade requires approved RiskDecision")
    expected_risk = CompleteAccountRiskService().assess(
        portfolio,
        actor=risk.actor,
        reason=risk.reason,
        started_at=risk.started_at,
        completed_at=risk.completed_at,
    )
    if expected_risk != risk:
        raise ValueError("traceable manual trade requires recomputable RiskDecision")
    if (
        opportunity.state is not OpportunityState.CONFIRMED_TO_THESIS
        or opportunity.opportunity_id != thesis.opportunity_id
        or opportunity.symbol != thesis.symbol
        or record.created_at > opportunity.valid_until
        or thesis.state is not ThesisState.APPROVED
        or record.created_at >= thesis.time_invalidation
    ):
        raise ValueError("traceable manual trade Opportunity/Thesis is not active")
    if delta not in portfolio.post_trade.proposed_deltas:
        raise ValueError("traceable manual trade delta is absent from PortfolioDecision")
    expected_side = TradeSide.BUY if delta.trade_quantity > 0 else TradeSide.SELL
    if delta.trade_quantity == 0:
        raise ValueError("zero trade delta cannot create manual trade")
    if (
        risk.portfolio_decision_id != portfolio.decision_id
        or risk.post_trade_snapshot_id != portfolio.post_trade.snapshot_id
        or risk.post_trade_content_hash != portfolio.post_trade.content_hash
        or delta.thesis_id != thesis.thesis_id
        or delta.symbol != thesis.symbol
        or book.account_id != record.account_id
        or book.symbol != thesis.symbol
        or book.opportunity_id != opportunity.opportunity_id
        or book.thesis_id != thesis.thesis_id
        or book.thesis_version != thesis.version
        or record.position_book_id != book.position_book_id
        or record.opportunity_id != opportunity.opportunity_id
        or record.thesis_id != thesis.thesis_id
        or record.risk_decision_id != risk.risk_decision_id
        or record.risk_decision_hash != canonical_hash(risk.to_canonical_dict())
        or record.portfolio_decision_id != portfolio.decision_id
        or record.post_trade_snapshot_id != portfolio.post_trade.snapshot_id
        or record.post_trade_snapshot_hash != portfolio.post_trade.content_hash
        or record.target_position_hash != canonical_hash(delta.to_canonical_dict())
        or record.symbol != delta.symbol
        or record.side is not expected_side
        or record.intended_quantity != abs(delta.trade_quantity)
    ):
        raise ValueError("traceable manual trade authority binding mismatch")


def _open_or_validate_book(
    connection: sqlite3.Connection,
    book: PositionBook,
    idempotency_key: str,
) -> PositionBook:
    existing_scope = connection.execute(
        "SELECT position_book_id FROM position_books "
        "WHERE account_id = ? AND symbol = ? AND state = 'OPEN'",
        (book.account_id, book.symbol),
    ).fetchone()
    if existing_scope is not None:
        existing = _load_book(
            connection, PositionBookId(str(existing_scope["position_book_id"]))
        )
        if existing.position_book_id != book.position_book_id:
            raise ValueError(
                "account and symbol already have an ACTIVE Thesis PositionBook"
            )
        return existing
    if book.state is not PositionBookState.OPEN or book.version != 0:
        raise ValueError("new PositionBook must be OPEN version 0")
    connection.execute(
        """
        INSERT INTO position_books(
            position_book_id, account_id, symbol, opportunity_id, thesis_id,
            state, version, aggregate_json, opened_at, closed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            str(book.position_book_id),
            book.account_id,
            book.symbol,
            str(book.opportunity_id),
            str(book.thesis_id),
            book.state.value,
            book.version,
            _json(book.to_canonical_dict()),
            book.opened_at.isoformat(),
        ),
    )
    _insert_book_event(connection, book, f"{idempotency_key}:book-open")
    return book


def _load_book(
    connection: sqlite3.Connection, book_id: PositionBookId
) -> PositionBook:
    row = connection.execute(
        "SELECT aggregate_json, version FROM position_books WHERE position_book_id = ?",
        (str(book_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown PositionBook: {book_id}")
    version = int(row["version"])
    events = connection.execute(
        "SELECT aggregate_json FROM position_book_events "
        "WHERE position_book_id = ? ORDER BY sequence",
        (str(book_id),),
    ).fetchall()
    if len(events) != version + 1:
        raise ValueError("PositionBook history is not contiguous")
    history = tuple(
        PositionBook.from_canonical_dict(_object_json(str(item["aggregate_json"])))
        for item in events
    )
    if history[0].state is not PositionBookState.OPEN or history[0].version != 0:
        raise ValueError("PositionBook history does not start OPEN")
    if len(history) == 2:
        before, after = history
        if (
            after.state is not PositionBookState.CLOSED
            or after.version != before.version + 1
            or after.position_book_id != before.position_book_id
        ):
            raise ValueError("PositionBook close history is invalid")
    elif len(history) != 1:
        raise ValueError("PositionBook V1 supports one close transition")
    projected = PositionBook.from_canonical_dict(
        _object_json(str(row["aggregate_json"]))
    )
    if projected != history[-1]:
        raise ValueError("PositionBook projection is not reconstructible")
    return projected


def _insert_book_event(
    connection: sqlite3.Connection, book: PositionBook, idempotency_key: str
) -> None:
    created_at = book.closed_at or book.opened_at
    connection.execute(
        """
        INSERT INTO position_book_events(
            position_book_id, sequence, state, aggregate_json,
            idempotency_key, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(book.position_book_id),
            book.version,
            book.state.value,
            _json(book.to_canonical_dict()),
            idempotency_key,
            created_at.isoformat(),
        ),
    )


def trace_binding_payload(
    connection: sqlite3.Connection, trade_id: ManualTradeId
) -> dict[str, Any]:
    """Return the immutable trace index for diagnostics and contract tests."""

    row = connection.execute(
        "SELECT * FROM traceable_manual_trade_bindings WHERE manual_trade_id = ?",
        (str(trade_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown trace binding: {trade_id}")
    return {key: row[key] for key in row.keys()}


def _validate_stored_binding(
    connection: sqlite3.Connection, record: ManualTradeRecord
) -> None:
    row = connection.execute(
        "SELECT * FROM traceable_manual_trade_bindings WHERE manual_trade_id = ?",
        (str(record.manual_trade_id),),
    ).fetchone()
    if row is None or (
        row["position_book_id"] != str(record.position_book_id)
        or row["opportunity_id"] != str(record.opportunity_id)
        or row["thesis_id"] != str(record.thesis_id)
        or row["portfolio_decision_id"] != str(record.portfolio_decision_id)
        or row["risk_decision_id"] != str(record.risk_decision_id)
        or row["post_trade_snapshot_id"] != str(record.post_trade_snapshot_id)
        or row["post_trade_snapshot_hash"] != record.post_trade_snapshot_hash
        or row["target_delta_hash"] != record.target_position_hash
    ):
        raise ValueError("ManualTradeRecord immutable trace index mismatch")
