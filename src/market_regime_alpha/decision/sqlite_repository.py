"""SQLite durable adapter for decision aggregates and append-only histories."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from market_regime_alpha.core.identity import OpportunityId, ThesisId
from market_regime_alpha.decision.opportunity import (
    OpportunityState,
    TradingOpportunity,
    validate_opportunity_transition,
)
from market_regime_alpha.decision.repositories import (
    DecisionCommandResult,
    DecisionVersionConflictError,
)
from market_regime_alpha.decision.thesis import (
    ThesisState,
    TradingThesis,
    validate_thesis_transition,
)


_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
DECISION_UP_MIGRATION = _MIGRATION_ROOT / "002_decision_lifecycle_up.sql"
DECISION_DOWN_MIGRATION = _MIGRATION_ROOT / "002_decision_lifecycle_down.sql"


class SQLiteDecisionLifecycleRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(DECISION_UP_MIGRATION.read_text(encoding="utf-8"))

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

    def resolve_command(
        self, *, idempotency_key: str, command_hash: str
    ) -> DecisionCommandResult | None:
        _key(idempotency_key)
        with self._connect() as connection:
            row = _command(connection, idempotency_key)
            if row is None:
                return None
            _validate_command(row, command_hash)
            return self._result_from_command(connection, row)

    def get_opportunity(self, opportunity_id: OpportunityId) -> TradingOpportunity:
        with self._connect() as connection:
            return _load_opportunity(connection, opportunity_id)

    def get_thesis(self, thesis_id: ThesisId) -> TradingThesis:
        with self._connect() as connection:
            return _load_thesis(connection, thesis_id)

    def create_opportunity(
        self,
        opportunity: TradingOpportunity,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> DecisionCommandResult:
        _key(idempotency_key)
        if opportunity.state is not OpportunityState.OPEN or opportunity.version != 0:
            raise ValueError("new Opportunity must be OPEN version 0")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash)
                    result = self._result_from_command(connection, command)
                    connection.commit()
                    return result
                existing = connection.execute(
                    "SELECT aggregate_json FROM trading_opportunities WHERE opportunity_id = ?",
                    (str(opportunity.opportunity_id),),
                ).fetchone()
                if existing is not None:
                    current = TradingOpportunity.from_canonical_dict(
                        _object_json(str(existing["aggregate_json"]))
                    )
                    if current != opportunity:
                        raise ValueError("Opportunity identity conflict")
                else:
                    payload = _json(opportunity.to_canonical_dict())
                    connection.execute(
                        """
                        INSERT INTO trading_opportunities(
                            opportunity_id, symbol, state, valid_until,
                            aggregate_json, version
                        ) VALUES (?, ?, ?, ?, ?, 0)
                        """,
                        (
                            str(opportunity.opportunity_id),
                            opportunity.symbol,
                            opportunity.state.value,
                            opportunity.valid_until.isoformat(),
                            payload,
                        ),
                    )
                    _insert_opportunity_event(
                        connection,
                        opportunity,
                        event_type="CREATED",
                        idempotency_key=idempotency_key,
                    )
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    opportunity=opportunity,
                    thesis=None,
                )
                connection.commit()
                return DecisionCommandResult(opportunity, None)
            except Exception:
                connection.rollback()
                raise

    def transition_opportunity(
        self,
        opportunity: TradingOpportunity,
        *,
        expected_version: int,
        idempotency_key: str,
        command_hash: str,
    ) -> DecisionCommandResult:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash)
                    result = self._result_from_command(connection, command)
                    connection.commit()
                    return result
                current = _load_opportunity(connection, opportunity.opportunity_id)
                if current.version != expected_version:
                    raise DecisionVersionConflictError("Opportunity compare-and-swap conflict")
                validate_opportunity_transition(current, opportunity)
                _update_opportunity(connection, opportunity, expected_version)
                _insert_opportunity_event(
                    connection,
                    opportunity,
                    event_type=opportunity.state.value,
                    idempotency_key=idempotency_key,
                )
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    opportunity=opportunity,
                    thesis=None,
                )
                connection.commit()
                return DecisionCommandResult(opportunity, None)
            except Exception:
                connection.rollback()
                raise

    def confirm_opportunity(
        self,
        opportunity: TradingOpportunity,
        thesis: TradingThesis,
        *,
        expected_version: int,
        idempotency_key: str,
        command_hash: str,
    ) -> DecisionCommandResult:
        if opportunity.state is not OpportunityState.CONFIRMED_TO_THESIS:
            raise ValueError("confirmation requires confirmed Opportunity state")
        if thesis.state is not ThesisState.APPROVED or thesis.version != 0:
            raise ValueError("confirmation requires initial APPROVED Thesis")
        if thesis.opportunity_id != opportunity.opportunity_id:
            raise ValueError("Opportunity and Thesis identity mismatch")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash)
                    result = self._result_from_command(connection, command)
                    connection.commit()
                    return result
                current = _load_opportunity(connection, opportunity.opportunity_id)
                if current.version != expected_version:
                    raise DecisionVersionConflictError("Opportunity compare-and-swap conflict")
                validate_opportunity_transition(current, opportunity)
                _validate_confirmation(current, opportunity, thesis)
                if connection.execute(
                    "SELECT 1 FROM trading_theses WHERE opportunity_id = ?",
                    (str(opportunity.opportunity_id),),
                ).fetchone() is not None:
                    raise ValueError("Opportunity already owns a Thesis")
                _update_opportunity(connection, opportunity, expected_version)
                _insert_opportunity_event(
                    connection,
                    opportunity,
                    event_type=opportunity.state.value,
                    idempotency_key=f"{idempotency_key}:opportunity",
                )
                connection.execute(
                    """
                    INSERT INTO trading_theses(
                        thesis_id, opportunity_id, symbol, state,
                        time_invalidation, aggregate_json, version
                    ) VALUES (?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        str(thesis.thesis_id),
                        str(thesis.opportunity_id),
                        thesis.symbol,
                        thesis.state.value,
                        thesis.time_invalidation.isoformat(),
                        _json(thesis.to_canonical_dict()),
                    ),
                )
                _insert_thesis_event(
                    connection,
                    thesis,
                    event_type="APPROVED",
                    idempotency_key=f"{idempotency_key}:thesis",
                )
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    opportunity=opportunity,
                    thesis=thesis,
                )
                connection.commit()
                return DecisionCommandResult(opportunity, thesis)
            except Exception:
                connection.rollback()
                raise

    def transition_thesis(
        self,
        thesis: TradingThesis,
        *,
        expected_version: int,
        idempotency_key: str,
        command_hash: str,
    ) -> DecisionCommandResult:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash)
                    result = self._result_from_command(connection, command)
                    connection.commit()
                    return result
                current = _load_thesis(connection, thesis.thesis_id)
                if current.version != expected_version:
                    raise DecisionVersionConflictError("Thesis compare-and-swap conflict")
                validate_thesis_transition(current, thesis)
                updated = connection.execute(
                    """
                    UPDATE trading_theses
                    SET state = ?, aggregate_json = ?, version = ?
                    WHERE thesis_id = ? AND version = ?
                    """,
                    (
                        thesis.state.value,
                        _json(thesis.to_canonical_dict()),
                        thesis.version,
                        str(thesis.thesis_id),
                        expected_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise DecisionVersionConflictError("Thesis compare-and-swap failed")
                _insert_thesis_event(
                    connection,
                    thesis,
                    event_type=thesis.state.value,
                    idempotency_key=idempotency_key,
                )
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    opportunity=None,
                    thesis=thesis,
                )
                connection.commit()
                return DecisionCommandResult(None, thesis)
            except Exception:
                connection.rollback()
                raise

    def _result_from_command(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> DecisionCommandResult:
        opportunity = (
            _load_opportunity(
                connection,
                OpportunityId(str(row["opportunity_id"])),
                version=int(row["opportunity_version"]),
            )
            if row["opportunity_id"] is not None
            else None
        )
        thesis = (
            _load_thesis(
                connection,
                ThesisId(str(row["thesis_id"])),
                version=int(row["thesis_version"]),
            )
            if row["thesis_id"] is not None
            else None
        )
        return DecisionCommandResult(opportunity, thesis)


def _load_opportunity(
    connection: sqlite3.Connection,
    opportunity_id: OpportunityId,
    version: int | None = None,
) -> TradingOpportunity:
    row = connection.execute(
        "SELECT * FROM trading_opportunities WHERE opportunity_id = ?",
        (str(opportunity_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown Opportunity: {opportunity_id}")
    current_version = int(row["version"])
    requested = current_version if version is None else version
    if requested < 0 or requested > current_version:
        raise ValueError("Opportunity command references invalid version")
    event_rows = connection.execute(
        """
        SELECT aggregate_json FROM opportunity_events
        WHERE opportunity_id = ? AND sequence <= ? ORDER BY sequence
        """,
        (str(opportunity_id), requested),
    ).fetchall()
    if len(event_rows) != requested + 1:
        raise ValueError("Opportunity event history is not contiguous")
    history = tuple(
        TradingOpportunity.from_canonical_dict(
            _object_json(str(item["aggregate_json"]))
        )
        for item in event_rows
    )
    if history[0].state is not OpportunityState.OPEN or history[0].version != 0:
        raise ValueError("Opportunity history must begin OPEN version 0")
    for before, after in zip(history, history[1:]):
        validate_opportunity_transition(before, after)
    result = history[-1]
    if requested == current_version:
        stored = TradingOpportunity.from_canonical_dict(
            _object_json(str(row["aggregate_json"]))
        )
        if result != stored or row["state"] != result.state.value:
            raise ValueError("Opportunity current projection is not reconstructible")
    return result


def _load_thesis(
    connection: sqlite3.Connection,
    thesis_id: ThesisId,
    version: int | None = None,
) -> TradingThesis:
    row = connection.execute(
        "SELECT * FROM trading_theses WHERE thesis_id = ?", (str(thesis_id),)
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown Thesis: {thesis_id}")
    current_version = int(row["version"])
    requested = current_version if version is None else version
    if requested < 0 or requested > current_version:
        raise ValueError("Thesis command references invalid version")
    event_rows = connection.execute(
        """
        SELECT aggregate_json FROM thesis_events
        WHERE thesis_id = ? AND sequence <= ? ORDER BY sequence
        """,
        (str(thesis_id), requested),
    ).fetchall()
    if len(event_rows) != requested + 1:
        raise ValueError("Thesis event history is not contiguous")
    history = tuple(
        TradingThesis.from_canonical_dict(_object_json(str(item["aggregate_json"])))
        for item in event_rows
    )
    if history[0].state is not ThesisState.APPROVED or history[0].version != 0:
        raise ValueError("Thesis history must begin APPROVED version 0")
    for before, after in zip(history, history[1:]):
        validate_thesis_transition(before, after)
    result = history[-1]
    if requested == current_version:
        stored = TradingThesis.from_canonical_dict(
            _object_json(str(row["aggregate_json"]))
        )
        if result != stored or row["state"] != result.state.value:
            raise ValueError("Thesis current projection is not reconstructible")
    return result


def _update_opportunity(
    connection: sqlite3.Connection,
    opportunity: TradingOpportunity,
    expected_version: int,
) -> None:
    updated = connection.execute(
        """
        UPDATE trading_opportunities
        SET state = ?, aggregate_json = ?, version = ?
        WHERE opportunity_id = ? AND version = ?
        """,
        (
            opportunity.state.value,
            _json(opportunity.to_canonical_dict()),
            opportunity.version,
            str(opportunity.opportunity_id),
            expected_version,
        ),
    )
    if updated.rowcount != 1:
        raise DecisionVersionConflictError("Opportunity compare-and-swap failed")


def _validate_confirmation(
    before: TradingOpportunity,
    after: TradingOpportunity,
    thesis: TradingThesis,
) -> None:
    if thesis.source_opportunity_version != before.version:
        raise ValueError("Thesis source Opportunity version mismatch")
    if thesis.symbol != before.symbol:
        raise ValueError("Thesis and Opportunity symbol mismatch")
    if thesis.created_at != after.updated_at or thesis.created_at > before.valid_until:
        raise ValueError("Thesis approval time is outside Opportunity validity")
    required = {
        (before.candidate_set.artifact_id, before.candidate_set.content_hash),
        (before.signal_snapshot.artifact_id, before.signal_snapshot.content_hash),
        (before.path_forecast.artifact_id, before.path_forecast.content_hash),
    }
    provided = {
        (item.artifact_id, item.content_hash) for item in thesis.supporting_evidence
    }
    if not required.issubset(provided):
        raise ValueError("Thesis omits required Opportunity evidence")


def _insert_opportunity_event(
    connection: sqlite3.Connection,
    opportunity: TradingOpportunity,
    *,
    event_type: str,
    idempotency_key: str,
) -> None:
    connection.execute(
        """
        INSERT INTO opportunity_events(
            opportunity_id, sequence, event_type, actor, reason,
            aggregate_json, idempotency_key, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(opportunity.opportunity_id),
            opportunity.version,
            event_type,
            opportunity.last_actor,
            opportunity.last_reason,
            _json(opportunity.to_canonical_dict()),
            idempotency_key,
            opportunity.updated_at.isoformat(),
        ),
    )


def _insert_thesis_event(
    connection: sqlite3.Connection,
    thesis: TradingThesis,
    *,
    event_type: str,
    idempotency_key: str,
) -> None:
    connection.execute(
        """
        INSERT INTO thesis_events(
            thesis_id, sequence, event_type, actor, reason,
            aggregate_json, idempotency_key, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(thesis.thesis_id),
            thesis.version,
            event_type,
            thesis.last_actor,
            thesis.last_reason,
            _json(thesis.to_canonical_dict()),
            idempotency_key,
            thesis.updated_at.isoformat(),
        ),
    )


def _command(connection: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM decision_commands WHERE idempotency_key = ?", (key,)
    ).fetchone()


def _validate_command(row: sqlite3.Row, command_hash: str) -> None:
    if row["command_hash"] != command_hash:
        raise ValueError("idempotency key reused for different decision command")


def _insert_command(
    connection: sqlite3.Connection,
    *,
    idempotency_key: str,
    command_hash: str,
    opportunity: TradingOpportunity | None,
    thesis: TradingThesis | None,
) -> None:
    connection.execute(
        """
        INSERT INTO decision_commands(
            idempotency_key, command_hash, opportunity_id,
            opportunity_version, thesis_id, thesis_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            idempotency_key,
            command_hash,
            str(opportunity.opportunity_id) if opportunity is not None else None,
            opportunity.version if opportunity is not None else None,
            str(thesis.thesis_id) if thesis is not None else None,
            thesis.version if thesis is not None else None,
            datetime.now(UTC).isoformat(),
        ),
    )


def _key(value: str) -> None:
    if not value or value != value.strip():
        raise ValueError("idempotency_key must be a non-empty trimmed string")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _object_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("decision aggregate JSON must be an object")
    return payload
