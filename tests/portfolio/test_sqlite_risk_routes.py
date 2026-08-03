from __future__ import annotations

import json
import sqlite3

import pytest

from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.portfolio.sqlite_risk_routes import (
    SQLiteRiskRouteRepository,
)
from tests.portfolio.risk_route_test_support import make_decision, sha


def test_repository_saves_reads_replays_and_restarts(tmp_path) -> None:
    database = tmp_path / "risk-routes.sqlite3"
    repository = SQLiteRiskRouteRepository(database)
    position, observation, configuration, decision = make_decision()
    command_hash = canonical_hash(
        {
            "command": "TEST_RISK_REDUCTION",
            "decision": decision.to_canonical_dict(),
        }
    )

    stored = repository.save_reducing_decision(
        decision,
        position=position,
        execution_observation=observation,
        configuration=configuration,
        idempotency_key="repository-save-replay",
        command_hash=command_hash,
    )

    assert stored == decision
    assert repository.get_reducing_decision(decision.decision_id) == decision
    assert (
        repository.resolve_reducing_command(
            idempotency_key="repository-save-replay",
            command_hash=command_hash,
        )
        == decision
    )
    restarted = SQLiteRiskRouteRepository(database)
    assert restarted.get_reducing_decision(decision.decision_id) == decision


def test_repository_rejects_idempotency_key_semantic_conflict(tmp_path) -> None:
    repository = SQLiteRiskRouteRepository(tmp_path / "risk-routes.sqlite3")
    position, observation, configuration, decision = make_decision()
    command_hash = canonical_hash({"command": "ORIGINAL"})
    repository.save_reducing_decision(
        decision,
        position=position,
        execution_observation=observation,
        configuration=configuration,
        idempotency_key="conflicting-command",
        command_hash=command_hash,
    )

    with pytest.raises(ValueError, match="idempotency key reused"):
        repository.resolve_reducing_command(
            idempotency_key="conflicting-command",
            command_hash=canonical_hash({"command": "DIFFERENT"}),
        )


@pytest.mark.parametrize(
    ("column", "field", "replacement"),
    (
        ("decision_json", "reason", "tampered decision reason"),
        ("configuration_json", "profile_id", "tampered-profile"),
    ),
)
def test_repository_rejects_tampered_canonical_json(
    tmp_path, column: str, field: str, replacement: str
) -> None:
    repository, decision = _stored_decision(tmp_path)
    with sqlite3.connect(repository.path) as connection:
        connection.execute("DROP TRIGGER risk_reducing_decisions_no_update")
        payload = json.loads(
            connection.execute(
                f"SELECT {column} FROM risk_reducing_decisions WHERE decision_id = ?",
                (str(decision.decision_id),),
            ).fetchone()[0]
        )
        payload[field] = replacement
        connection.execute(
            f"UPDATE risk_reducing_decisions SET {column} = ? WHERE decision_id = ?",
            (json.dumps(payload), str(decision.decision_id)),
        )

    with pytest.raises(ValueError):
        repository.get_reducing_decision(decision.decision_id)


def test_repository_rejects_tampered_projection_content_hash(tmp_path) -> None:
    repository, decision = _stored_decision(tmp_path)
    with sqlite3.connect(repository.path) as connection:
        connection.execute("DROP TRIGGER risk_reducing_decisions_no_update")
        connection.execute(
            "UPDATE risk_reducing_decisions SET content_hash = ? WHERE decision_id = ?",
            (sha("f"), str(decision.decision_id)),
        )

    with pytest.raises(ValueError):
        repository.get_reducing_decision(decision.decision_id)


def test_repository_rolls_back_decision_when_command_insert_fails(tmp_path) -> None:
    repository = SQLiteRiskRouteRepository(tmp_path / "risk-routes.sqlite3")
    position, observation, configuration, decision = make_decision(
        reason="atomic rollback fixture"
    )
    with sqlite3.connect(repository.path) as connection:
        connection.executescript(
            """
            CREATE TRIGGER reject_risk_reducing_command
            BEFORE INSERT ON risk_reducing_commands
            BEGIN
                SELECT RAISE(ABORT, 'injected command failure');
            END;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected command failure"):
        repository.save_reducing_decision(
            decision,
            position=position,
            execution_observation=observation,
            configuration=configuration,
            idempotency_key="atomic-rollback",
            command_hash=canonical_hash({"command": "ATOMIC_ROLLBACK"}),
        )

    with sqlite3.connect(repository.path) as connection:
        decision_count = connection.execute(
            "SELECT COUNT(*) FROM risk_reducing_decisions WHERE decision_id = ?",
            (str(decision.decision_id),),
        ).fetchone()[0]
        command_count = connection.execute(
            "SELECT COUNT(*) FROM risk_reducing_commands WHERE idempotency_key = ?",
            ("atomic-rollback",),
        ).fetchone()[0]
    assert decision_count == 0
    assert command_count == 0


def test_migration_is_repeatable_and_decisions_are_append_only(tmp_path) -> None:
    repository, decision = _stored_decision(tmp_path)
    SQLiteRiskRouteRepository(repository.path)
    with sqlite3.connect(repository.path) as connection:
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM pdl_schema_migrations WHERE version = 7"
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE risk_reducing_decisions SET state = state WHERE decision_id = ?",
                (str(decision.decision_id),),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM risk_reducing_decisions WHERE decision_id = ?",
                (str(decision.decision_id),),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE risk_reducing_commands SET command_hash = command_hash "
                "WHERE idempotency_key = ?",
                ("stored-decision",),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM risk_reducing_commands WHERE idempotency_key = ?",
                ("stored-decision",),
            )
    assert migration_count == 1


def test_repository_rejects_same_decision_id_with_different_content(
    tmp_path,
) -> None:
    repository, decision = _stored_decision(tmp_path)
    _, _, _, conflicting = make_decision(reason="different semantic content")
    with sqlite3.connect(repository.path) as connection:
        connection.execute("DROP TRIGGER risk_reducing_decisions_no_update")
        connection.execute(
            "UPDATE risk_reducing_decisions SET decision_json = ? WHERE decision_id = ?",
            (json.dumps(conflicting.to_canonical_dict()), str(decision.decision_id)),
        )

    position, observation, configuration, _ = make_decision()
    with pytest.raises(ValueError):
        repository.save_reducing_decision(
            decision,
            position=position,
            execution_observation=observation,
            configuration=configuration,
            idempotency_key="identity-conflict",
            command_hash=canonical_hash({"command": "IDENTITY_CONFLICT"}),
        )


def test_repository_rejects_same_name_tables_with_weakened_constraints(
    tmp_path,
) -> None:
    database = tmp_path / "weak-schema.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE risk_reducing_decisions (
                decision_id TEXT, position_snapshot_id TEXT,
                position_book_id TEXT, thesis_id TEXT, action TEXT,
                state TEXT, content_hash TEXT, position_json TEXT,
                observation_json TEXT, configuration_json TEXT,
                decision_json TEXT, assessed_at TEXT
            );
            CREATE TABLE risk_reducing_commands (
                idempotency_key TEXT, command_hash TEXT,
                decision_id TEXT, created_at TEXT
            );
            CREATE TRIGGER risk_reducing_decisions_no_update
            BEFORE UPDATE ON risk_reducing_decisions BEGIN SELECT 1; END;
            CREATE TRIGGER risk_reducing_decisions_no_delete
            BEFORE DELETE ON risk_reducing_decisions BEGIN SELECT 1; END;
            CREATE TRIGGER risk_reducing_commands_no_update
            BEFORE UPDATE ON risk_reducing_commands BEGIN SELECT 1; END;
            CREATE TRIGGER risk_reducing_commands_no_delete
            BEFORE DELETE ON risk_reducing_commands BEGIN SELECT 1; END;
            """
        )

    with pytest.raises(ValueError, match="table schema mismatch"):
        SQLiteRiskRouteRepository(database)


def test_repository_rejects_spoofed_append_only_trigger(tmp_path) -> None:
    database = tmp_path / "spoofed-trigger.sqlite3"
    SQLiteRiskRouteRepository(database)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            DROP TRIGGER risk_reducing_decisions_no_update;
            CREATE TRIGGER risk_reducing_decisions_no_update
            BEFORE UPDATE ON risk_reducing_decisions BEGIN SELECT 1; END;
            """
        )

    with pytest.raises(ValueError, match="append-only trigger mismatch"):
        SQLiteRiskRouteRepository(database)


def _stored_decision(tmp_path):
    repository = SQLiteRiskRouteRepository(tmp_path / "risk-routes.sqlite3")
    position, observation, configuration, decision = make_decision()
    repository.save_reducing_decision(
        decision,
        position=position,
        execution_observation=observation,
        configuration=configuration,
        idempotency_key="stored-decision",
        command_hash=canonical_hash({"command": "STORED_DECISION"}),
    )
    return repository, decision
