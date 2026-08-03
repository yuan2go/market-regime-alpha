"""SQLite authority for immutable H4 reducing-risk decision bundles."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.portfolio.risk_routes import (
    ReducingExecutionObservation,
    RiskReducingDecision,
    RiskReducingExecutionGate,
    RiskReducingGateConfiguration,
)
from market_regime_alpha.position.authority import PositionSnapshot


_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
RISK_ROUTE_UP_MIGRATION = _MIGRATION_ROOT / "007_risk_routes_up.sql"
RISK_ROUTE_DOWN_MIGRATION = _MIGRATION_ROOT / "007_risk_routes_down.sql"

_REQUIRED_COLUMNS = {
    "risk_reducing_decisions": {
        "decision_id",
        "position_snapshot_id",
        "position_book_id",
        "thesis_id",
        "action",
        "state",
        "content_hash",
        "position_json",
        "observation_json",
        "configuration_json",
        "decision_json",
        "assessed_at",
    },
    "risk_reducing_commands": {
        "idempotency_key",
        "command_hash",
        "decision_id",
        "created_at",
    },
}
_REQUIRED_TRIGGERS = {
    "risk_reducing_decisions_no_update",
    "risk_reducing_decisions_no_delete",
    "risk_reducing_commands_no_update",
    "risk_reducing_commands_no_delete",
}


class SQLiteRiskRouteRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                RISK_ROUTE_UP_MIGRATION.read_text(encoding="utf-8")
            )
            _validate_schema(connection)

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

    def save_reducing_decision(
        self,
        decision: RiskReducingDecision,
        *,
        position: PositionSnapshot,
        execution_observation: ReducingExecutionObservation,
        configuration: RiskReducingGateConfiguration,
        idempotency_key: str,
        command_hash: str,
    ) -> RiskReducingDecision:
        _key(idempotency_key)
        require_sha256("command_hash", command_hash)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay = _resolve_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                )
                if replay is not None:
                    connection.commit()
                    return replay
                existing = connection.execute(
                    """
                    SELECT * FROM risk_reducing_decisions
                    WHERE decision_id = ? OR content_hash = ?
                    """,
                    (str(decision.decision_id), decision.content_hash),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO risk_reducing_decisions(
                            decision_id, position_snapshot_id, position_book_id,
                            thesis_id, action, state, content_hash, position_json,
                            observation_json, configuration_json, decision_json,
                            assessed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(decision.decision_id),
                            str(decision.position_snapshot_id),
                            str(decision.position_book_id),
                            str(decision.thesis_id),
                            decision.action.value,
                            decision.state.value,
                            decision.content_hash,
                            _json(position.to_canonical_dict()),
                            _json(execution_observation.to_canonical_dict()),
                            _json(configuration.to_canonical_dict()),
                            _json(decision.to_canonical_dict()),
                            decision.assessed_at.isoformat(),
                        ),
                    )
                else:
                    stored = _restore_bundle(existing)
                    if stored != (
                        position,
                        execution_observation,
                        configuration,
                        decision,
                    ):
                        raise ValueError("risk-reducing decision identity conflict")
                connection.execute(
                    """
                    INSERT INTO risk_reducing_commands(
                        idempotency_key, command_hash, decision_id, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        idempotency_key,
                        command_hash,
                        str(decision.decision_id),
                        decision.assessed_at.isoformat(),
                    ),
                )
                stored_decision = _load_reducing_decision(
                    connection, decision.decision_id
                )
                connection.commit()
                return stored_decision
            except Exception:
                connection.rollback()
                raise

    def resolve_reducing_command(
        self, *, idempotency_key: str, command_hash: str
    ) -> RiskReducingDecision | None:
        _key(idempotency_key)
        require_sha256("command_hash", command_hash)
        with self._connect() as connection:
            return _resolve_command(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
            )

    def get_reducing_decision(
        self, decision_id: ArtifactId
    ) -> RiskReducingDecision:
        with self._connect() as connection:
            return _load_reducing_decision(connection, decision_id)


def _resolve_command(
    connection: sqlite3.Connection,
    *,
    idempotency_key: str,
    command_hash: str,
) -> RiskReducingDecision | None:
    row = connection.execute(
        """
        SELECT command_hash, decision_id FROM risk_reducing_commands
        WHERE idempotency_key = ?
        """,
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if row["command_hash"] != command_hash:
        raise ValueError("idempotency key reused for different risk-route command")
    return _load_reducing_decision(
        connection, ArtifactId(str(row["decision_id"]))
    )


def _load_reducing_decision(
    connection: sqlite3.Connection, decision_id: ArtifactId
) -> RiskReducingDecision:
    row = connection.execute(
        "SELECT * FROM risk_reducing_decisions WHERE decision_id = ?",
        (str(decision_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown RiskReducingDecision: {decision_id}")
    return _restore_bundle(row)[3]


def _restore_bundle(
    row: sqlite3.Row,
) -> tuple[
    PositionSnapshot,
    ReducingExecutionObservation,
    RiskReducingGateConfiguration,
    RiskReducingDecision,
]:
    position = PositionSnapshot.from_canonical_dict(
        _object_json(str(row["position_json"]))
    )
    observation = ReducingExecutionObservation.from_canonical_dict(
        _object_json(str(row["observation_json"]))
    )
    configuration = RiskReducingGateConfiguration.from_canonical_dict(
        _object_json(str(row["configuration_json"]))
    )
    decision = RiskReducingDecision.from_canonical_dict(
        _object_json(str(row["decision_json"]))
    )
    position_hash = canonical_hash(position.to_canonical_dict())
    if (
        row["decision_id"] != str(decision.decision_id)
        or row["position_snapshot_id"] != str(decision.position_snapshot_id)
        or row["position_book_id"] != str(decision.position_book_id)
        or row["thesis_id"] != str(decision.thesis_id)
        or row["action"] != decision.action.value
        or row["state"] != decision.state.value
        or row["content_hash"] != decision.content_hash
        or row["assessed_at"] != decision.assessed_at.isoformat()
    ):
        raise ValueError("risk-reducing decision projection is invalid")
    if (
        decision.position_snapshot_id != position.snapshot_id
        or decision.position_snapshot_hash != position_hash
        or decision.position_snapshot_version != position.version
        or decision.position_book_id != position.position_book_id
        or decision.thesis_id != position.thesis_id
        or decision.symbol != position.symbol
        or decision.current_quantity != position.total_quantity
        or decision.available_quantity != (position.available_quantity or 0)
        or decision.observation_id != observation.observation_id
        or decision.observation_hash != observation.content_hash
        or decision.configuration_id != configuration.configuration_id
        or decision.configuration_hash != configuration.configuration_hash
    ):
        raise ValueError("risk-reducing decision evidence references are invalid")
    expected = RiskReducingExecutionGate().assess(
        action=decision.action,
        position=position,
        target_quantity=decision.target_quantity,
        order_quantity=decision.order_quantity,
        execution_observation=observation,
        configuration=configuration,
        actor=decision.actor,
        reason=decision.reason,
        assessed_at=decision.assessed_at,
    )
    if expected != decision:
        raise ValueError("risk-reducing decision is not reconstructible")
    return position, observation, configuration, decision


def _validate_schema(connection: sqlite3.Connection) -> None:
    migration = connection.execute(
        "SELECT 1 FROM pdl_schema_migrations WHERE version = 7"
    ).fetchone()
    if migration is None:
        raise ValueError("risk-route migration 007 is not applied")
    for table, required in _REQUIRED_COLUMNS.items():
        actual = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if actual != required:
            raise ValueError(f"risk-route table schema mismatch: {table}")
    triggers = {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    if not _REQUIRED_TRIGGERS.issubset(triggers):
        raise ValueError("risk-route append-only triggers are missing")


def _key(value: str) -> None:
    if not value or value != value.strip():
        raise ValueError("idempotency key must be a non-empty trimmed string")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _object_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("risk-route repository JSON must be an object")
    return payload
