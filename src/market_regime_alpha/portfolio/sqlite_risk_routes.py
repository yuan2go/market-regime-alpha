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
    VerifiedRiskReducingDecisionBundle,
)
from market_regime_alpha.position.authority import PositionSnapshot


_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
RISK_ROUTE_UP_MIGRATION = _MIGRATION_ROOT / "007_risk_routes_up.sql"
RISK_ROUTE_DOWN_MIGRATION = _MIGRATION_ROOT / "007_risk_routes_down.sql"

_REQUIRED_TABLE_INFO = {
    "risk_reducing_decisions": (
        ("decision_id", "TEXT", 0, 1),
        ("position_snapshot_id", "TEXT", 1, 0),
        ("position_book_id", "TEXT", 1, 0),
        ("thesis_id", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0),
        ("state", "TEXT", 1, 0),
        ("content_hash", "TEXT", 1, 0),
        ("position_json", "TEXT", 1, 0),
        ("observation_json", "TEXT", 1, 0),
        ("configuration_json", "TEXT", 1, 0),
        ("decision_json", "TEXT", 1, 0),
        ("assessed_at", "TEXT", 1, 0),
    ),
    "risk_reducing_commands": (
        ("idempotency_key", "TEXT", 0, 1),
        ("command_hash", "TEXT", 1, 0),
        ("decision_id", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0),
    ),
}
_REQUIRED_UNIQUE_COLUMNS = {
    "risk_reducing_decisions": {("content_hash",)},
    "risk_reducing_commands": set(),
}
_REQUIRED_FOREIGN_KEYS = {
    "risk_reducing_decisions": set(),
    "risk_reducing_commands": {
        (
            "risk_reducing_decisions",
            "decision_id",
            "decision_id",
            "NO ACTION",
            "NO ACTION",
            "NONE",
        )
    },
}
_REQUIRED_TABLE_CHECKS = {
    "risk_reducing_decisions": {
        "check(actionin('reduce','exit'))",
        "check(statein('permitted_for_manual_confirmation','blocked','data_insufficient'))",
    },
    "risk_reducing_commands": set(),
}
_REQUIRED_TRIGGER_SQL = {
    "risk_reducing_decisions_no_update": """
        CREATE TRIGGER risk_reducing_decisions_no_update
        BEFORE UPDATE ON risk_reducing_decisions
        BEGIN
            SELECT RAISE(ABORT, 'risk reducing decisions are append-only');
        END
    """,
    "risk_reducing_decisions_no_delete": """
        CREATE TRIGGER risk_reducing_decisions_no_delete
        BEFORE DELETE ON risk_reducing_decisions
        BEGIN
            SELECT RAISE(ABORT, 'risk reducing decisions are append-only');
        END
    """,
    "risk_reducing_commands_no_update": """
        CREATE TRIGGER risk_reducing_commands_no_update
        BEFORE UPDATE ON risk_reducing_commands
        BEGIN
            SELECT RAISE(ABORT, 'risk reducing commands are append-only');
        END
    """,
    "risk_reducing_commands_no_delete": """
        CREATE TRIGGER risk_reducing_commands_no_delete
        BEFORE DELETE ON risk_reducing_commands
        BEGIN
            SELECT RAISE(ABORT, 'risk reducing commands are append-only');
        END
    """,
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

    def get_verified_reducing_decision_bundle(
        self, decision_id: ArtifactId
    ) -> VerifiedRiskReducingDecisionBundle:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM risk_reducing_decisions WHERE decision_id = ?",
                (str(decision_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown RiskReducingDecision: {decision_id}")
            position, observation, configuration, decision = _restore_bundle(row)
            return VerifiedRiskReducingDecisionBundle(
                position=position,
                execution_observation=observation,
                configuration=configuration,
                decision=decision,
            )


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
    for table, required in _REQUIRED_TABLE_INFO.items():
        actual = tuple(
            (
                str(row["name"]),
                str(row["type"]).upper(),
                int(row["notnull"]),
                int(row["pk"]),
            )
            for row in connection.execute(f"PRAGMA table_info({table})")
        )
        if actual != required:
            raise ValueError(f"risk-route table schema mismatch: {table}")
        unique_columns = {
            tuple(
                str(column["name"])
                for column in connection.execute(
                    f"PRAGMA index_info('{index['name']}')"
                )
            )
            for index in connection.execute(f"PRAGMA index_list({table})")
            if int(index["unique"]) == 1 and str(index["origin"]) == "u"
        }
        if unique_columns != _REQUIRED_UNIQUE_COLUMNS[table]:
            raise ValueError(f"risk-route unique constraint mismatch: {table}")
        foreign_keys = {
            (
                str(row["table"]),
                str(row["from"]),
                str(row["to"]),
                str(row["on_update"]),
                str(row["on_delete"]),
                str(row["match"]),
            )
            for row in connection.execute(f"PRAGMA foreign_key_list({table})")
        }
        if foreign_keys != _REQUIRED_FOREIGN_KEYS[table]:
            raise ValueError(f"risk-route foreign key mismatch: {table}")
        table_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if table_row is None:
            raise ValueError(f"risk-route table schema mismatch: {table}")
        compact_table_sql = _compact_sql(str(table_row["sql"]))
        if any(
            item not in compact_table_sql
            for item in _REQUIRED_TABLE_CHECKS[table]
        ):
            raise ValueError(f"risk-route check constraint mismatch: {table}")
    triggers = {
        str(row["name"]): str(row["sql"])
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    for name, expected_sql in _REQUIRED_TRIGGER_SQL.items():
        actual_sql = triggers.get(name)
        if actual_sql is None:
            raise ValueError("risk-route append-only triggers are missing")
        if _compact_sql(actual_sql) != _compact_sql(expected_sql):
            raise ValueError(f"risk-route append-only trigger mismatch: {name}")


def _key(value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
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


def _compact_sql(value: str) -> str:
    return "".join(value.lower().split())
