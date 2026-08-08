from __future__ import annotations

import json
import psycopg
from tests.postgres_path_repositories import postgres_connection

import pytest

from market_regime_alpha.evidence.canonical import canonical_hash
from tests.postgres_path_repositories import (
    PostgresRiskRouteRepository,
)
from tests.portfolio.risk_route_test_support import make_decision, sha


def test_repository_saves_reads_replays_and_restarts(tmp_path) -> None:
    database = tmp_path / "risk-routes.postgres-scope"
    repository = PostgresRiskRouteRepository(database)
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
    verified = repository.get_verified_reducing_decision_bundle(
        decision.decision_id
    )
    assert verified.position == position
    assert verified.execution_observation == observation
    assert verified.configuration == configuration
    assert verified.decision == decision
    assert (
        repository.resolve_reducing_command(
            idempotency_key="repository-save-replay",
            command_hash=command_hash,
        )
        == decision
    )
    restarted = PostgresRiskRouteRepository(database)
    assert restarted.get_reducing_decision(decision.decision_id) == decision


def test_repository_rejects_idempotency_key_semantic_conflict(tmp_path) -> None:
    repository = PostgresRiskRouteRepository(tmp_path / "risk-routes.postgres-scope")
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
    with postgres_connection(repository.path) as connection:
        connection.execute(
            "DROP TRIGGER risk_reducing_decisions_no_update "
            "ON risk_reducing_decisions"
        )
        payload = json.loads(
            connection.execute(
                f"SELECT {column} FROM risk_reducing_decisions WHERE decision_id = %s",
                (str(decision.decision_id),),
            ).fetchone()[0]
        )
        payload[field] = replacement
        connection.execute(
            f"UPDATE risk_reducing_decisions SET {column} = %s WHERE decision_id = %s",
            (json.dumps(payload), str(decision.decision_id)),
        )

    with pytest.raises(ValueError):
        repository.get_reducing_decision(decision.decision_id)


def test_repository_rejects_tampered_projection_content_hash(tmp_path) -> None:
    repository, decision = _stored_decision(tmp_path)
    with postgres_connection(repository.path) as connection:
        connection.execute(
            "DROP TRIGGER risk_reducing_decisions_no_update "
            "ON risk_reducing_decisions"
        )
        connection.execute(
            "UPDATE risk_reducing_decisions SET content_hash = %s WHERE decision_id = %s",
            (sha("f"), str(decision.decision_id)),
        )

    with pytest.raises(ValueError):
        repository.get_reducing_decision(decision.decision_id)


def test_repository_rolls_back_decision_when_command_insert_fails(tmp_path) -> None:
    repository = PostgresRiskRouteRepository(tmp_path / "risk-routes.postgres-scope")
    position, observation, configuration, decision = make_decision(
        reason="atomic rollback fixture"
    )
    with postgres_connection(repository.path) as connection:
        connection.execute(
            """
            CREATE FUNCTION reject_risk_reducing_command_fn()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'injected command failure';
            END;
            $$;
            CREATE TRIGGER reject_risk_reducing_command
            BEFORE INSERT ON risk_reducing_commands
            FOR EACH ROW EXECUTE FUNCTION reject_risk_reducing_command_fn();
            """,
            prepare=False,
        )

    with pytest.raises(psycopg.Error, match="injected command failure"):
        repository.save_reducing_decision(
            decision,
            position=position,
            execution_observation=observation,
            configuration=configuration,
            idempotency_key="atomic-rollback",
            command_hash=canonical_hash({"command": "ATOMIC_ROLLBACK"}),
        )

    with postgres_connection(repository.path) as connection:
        decision_count = connection.execute(
            "SELECT COUNT(*) FROM risk_reducing_decisions WHERE decision_id = %s",
            (str(decision.decision_id),),
        ).fetchone()[0]
        command_count = connection.execute(
            "SELECT COUNT(*) FROM risk_reducing_commands WHERE idempotency_key = %s",
            ("atomic-rollback",),
        ).fetchone()[0]
    assert decision_count == 0
    assert command_count == 0


def test_migration_is_repeatable_and_decisions_are_append_only(tmp_path) -> None:
    repository, decision = _stored_decision(tmp_path)
    PostgresRiskRouteRepository(repository.path)
    with postgres_connection(repository.path) as connection:
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 7"
        ).fetchone()[0]
        rejected = (
            (
                "UPDATE risk_reducing_decisions SET state = state "
                "WHERE decision_id = %s",
                (str(decision.decision_id),),
            ),
            (
                "DELETE FROM risk_reducing_decisions WHERE decision_id = %s",
                (str(decision.decision_id),),
            ),
            (
                "UPDATE risk_reducing_commands SET command_hash = command_hash "
                "WHERE idempotency_key = %s",
                ("stored-decision",),
            ),
            (
                "DELETE FROM risk_reducing_commands WHERE idempotency_key = %s",
                ("stored-decision",),
            ),
        )
        for statement, parameters in rejected:
            with pytest.raises(psycopg.Error, match="append-only"):
                with connection.transaction():
                    connection.execute(statement, parameters)
    assert migration_count == 1


def test_repository_rejects_same_decision_id_with_different_content(
    tmp_path,
) -> None:
    repository, decision = _stored_decision(tmp_path)
    _, _, _, conflicting = make_decision(reason="different semantic content")
    with postgres_connection(repository.path) as connection:
        connection.execute(
            "DROP TRIGGER risk_reducing_decisions_no_update "
            "ON risk_reducing_decisions"
        )
        connection.execute(
            "UPDATE risk_reducing_decisions SET decision_json = %s WHERE decision_id = %s",
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


def _stored_decision(tmp_path):
    repository = PostgresRiskRouteRepository(tmp_path / "risk-routes.postgres-scope")
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
