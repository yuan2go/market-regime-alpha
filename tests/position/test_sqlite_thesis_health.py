from __future__ import annotations

from datetime import timedelta, timezone
import json
import sqlite3

import pytest

from market_regime_alpha.evidence.canonical import canonical_hash
import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.position import ThesisHealthObservationBuilder
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
    THESIS_HEALTH_DOWN_MIGRATION,
)

from tests.position.test_thesis_health_builder import _bundle
from tests.position.thesis_health_fixtures import make_h5_fixture


def _command_hash(label: str) -> str:
    return canonical_hash({"command": label})


def _stored(tmp_path):
    repository = SQLiteThesisHealthRepository(tmp_path / "thesis-health.sqlite3")
    bundle = _bundle(make_h5_fixture())
    observation = ThesisHealthObservationBuilder().build(bundle)
    stored = repository.save_observation(
        observation,
        input_bundle=bundle,
        idempotency_key="stored-health",
        command_hash=_command_hash("stored-health"),
    )
    return repository, bundle, stored


def test_repository_saves_reads_replays_and_restarts(tmp_path) -> None:
    repository, _, observation = _stored(tmp_path)

    assert repository.get_observation(observation.observation_id) == observation
    assert repository.resolve_command(
        idempotency_key="stored-health",
        command_hash=_command_hash("stored-health"),
    ) == observation
    restarted = SQLiteThesisHealthRepository(repository.path)
    assert restarted.get_observation(observation.observation_id) == observation


def test_repository_rejects_idempotency_semantic_conflict(tmp_path) -> None:
    repository, _, _ = _stored(tmp_path)

    with pytest.raises(ValueError, match="idempotency key reused"):
        repository.resolve_command(
            idempotency_key="stored-health",
            command_hash=_command_hash("different-health"),
        )


@pytest.mark.parametrize(
    ("column", "field", "replacement"),
    (
        ("observation_json", "reason", "tampered reason"),
        ("input_bundle_json", "actor", "tampered actor"),
        ("configuration_json", "profile_id", "tampered-profile"),
        ("rule_set_json", "thesis_version", 99),
    ),
)
def test_repository_rejects_tampered_replay_json(
    tmp_path, column: str, field: str, replacement: object
) -> None:
    repository, _, observation = _stored(tmp_path)
    with sqlite3.connect(repository.path) as connection:
        connection.execute("DROP TRIGGER thesis_health_observations_no_update")
        payload = json.loads(
            connection.execute(
                f"SELECT {column} FROM thesis_health_observations WHERE observation_id = ?",
                (str(observation.observation_id),),
            ).fetchone()[0]
        )
        payload[field] = replacement
        connection.execute(
            f"UPDATE thesis_health_observations SET {column} = ? WHERE observation_id = ?",
            (json.dumps(payload), str(observation.observation_id)),
        )

    with pytest.raises(ValueError):
        repository.get_observation(observation.observation_id)


def test_repository_rejects_tampered_projection_and_builder_replay(tmp_path) -> None:
    repository, _, observation = _stored(tmp_path)
    with sqlite3.connect(repository.path) as connection:
        connection.execute("DROP TRIGGER thesis_health_observations_no_update")
        connection.execute(
            "UPDATE thesis_health_observations SET effective_health_state = ? WHERE observation_id = ?",
            ("WEAKENING", str(observation.observation_id)),
        )

    with pytest.raises(ValueError, match="projection"):
        repository.get_observation(observation.observation_id)


def test_repository_transaction_rolls_back_on_command_failure(tmp_path) -> None:
    repository = SQLiteThesisHealthRepository(tmp_path / "thesis-health.sqlite3")
    bundle = _bundle(make_h5_fixture())
    observation = ThesisHealthObservationBuilder().build(bundle)
    with sqlite3.connect(repository.path) as connection:
        connection.executescript(
            """
            CREATE TRIGGER reject_thesis_health_command
            BEFORE INSERT ON thesis_health_commands
            BEGIN
                SELECT RAISE(ABORT, 'injected H5 command failure');
            END;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected H5 command failure"):
        repository.save_observation(
            observation,
            input_bundle=bundle,
            idempotency_key="rollback-health",
            command_hash=_command_hash("rollback-health"),
        )

    with sqlite3.connect(repository.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM thesis_health_observations"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM thesis_health_commands"
        ).fetchone()[0] == 0


def test_migration_repeat_safe_and_tables_append_only(tmp_path) -> None:
    repository, _, observation = _stored(tmp_path)
    SQLiteThesisHealthRepository(repository.path)
    with sqlite3.connect(repository.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM pdl_schema_migrations WHERE version = 8"
        ).fetchone()[0] == 1
        for statement in (
            "UPDATE thesis_health_observations SET observed_health_state = observed_health_state",
            "DELETE FROM thesis_health_observations",
            "UPDATE thesis_health_commands SET command_hash = command_hash",
            "DELETE FROM thesis_health_commands",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(statement)
    assert repository.get_observation(observation.observation_id) == observation


def test_repository_rejects_forked_prior(tmp_path) -> None:
    repository, _, prior = _stored(tmp_path)
    fixture = make_h5_fixture()
    from datetime import timedelta

    current_bundle = _bundle(
        fixture,
        prior_observation=prior,
        assessed_at=prior.assessed_at + timedelta(minutes=1),
    )
    current = ThesisHealthObservationBuilder().build(current_bundle)
    repository.save_observation(
        current,
        input_bundle=current_bundle,
        idempotency_key="second-health",
        command_hash=_command_hash("second-health"),
    )

    fork_bundle = _bundle(
        fixture,
        prior_observation=prior,
        assessed_at=prior.assessed_at + timedelta(minutes=2),
    )
    fork = ThesisHealthObservationBuilder().build(fork_bundle)
    with pytest.raises(ValueError, match="latest prior"):
        repository.save_observation(
            fork,
            input_bundle=fork_bundle,
            idempotency_key="forked-health",
            command_hash=_command_hash("forked-health"),
        )


def test_latest_observation_follows_successor_chain_across_timezone_offsets(
    tmp_path,
) -> None:
    repository, _, prior = _stored(tmp_path)
    fixture = make_h5_fixture()
    current_bundle = _bundle(
        fixture,
        prior_observation=prior,
        assessed_at=(prior.assessed_at + timedelta(minutes=11)).astimezone(
            timezone.utc
        ),
    )
    current = ThesisHealthObservationBuilder().build(current_bundle)
    repository.save_observation(
        current,
        input_bundle=current_bundle,
        idempotency_key="timezone-current",
        command_hash=_command_hash("timezone-current"),
    )

    assert repository.get_latest_observation(prior.thesis_id) == current

    successor_bundle = _bundle(
        fixture,
        prior_observation=current,
        assessed_at=current.assessed_at + timedelta(minutes=1),
    )
    successor = ThesisHealthObservationBuilder().build(successor_bundle)
    assert repository.save_observation(
        successor,
        input_bundle=successor_bundle,
        idempotency_key="timezone-successor",
        command_hash=_command_hash("timezone-successor"),
    ) == successor


def test_repository_recursively_revalidates_stored_prior_observation(tmp_path) -> None:
    repository, _, prior = _stored(tmp_path)
    fixture = make_h5_fixture()
    from datetime import timedelta

    current_bundle = _bundle(
        fixture,
        prior_observation=prior,
        assessed_at=prior.assessed_at + timedelta(minutes=1),
    )
    current = ThesisHealthObservationBuilder().build(current_bundle)
    repository.save_observation(
        current,
        input_bundle=current_bundle,
        idempotency_key="recursive-prior",
        command_hash=_command_hash("recursive-prior"),
    )
    with sqlite3.connect(repository.path) as connection:
        connection.execute("DROP TRIGGER thesis_health_observations_no_update")
        payload = json.loads(
            connection.execute(
                "SELECT observation_json FROM thesis_health_observations WHERE observation_id = ?",
                (str(prior.observation_id),),
            ).fetchone()[0]
        )
        payload["reason"] = "tampered stored prior"
        connection.execute(
            "UPDATE thesis_health_observations SET observation_json = ? WHERE observation_id = ?",
            (json.dumps(payload), str(prior.observation_id)),
        )

    with pytest.raises(ValueError):
        repository.get_observation(current.observation_id)


def test_down_migration_is_isolated(tmp_path) -> None:
    repository = SQLiteThesisHealthRepository(tmp_path / "thesis-health.sqlite3")
    with sqlite3.connect(repository.path) as connection:
        connection.executescript(THESIS_HEALTH_DOWN_MIGRATION.read_text(encoding="utf-8"))
        assert connection.execute(
            "SELECT COUNT(*) FROM pdl_schema_migrations WHERE version = 8"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM pdl_schema_migrations WHERE version = 7"
        ).fetchone()[0] in {0, 1}
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'thesis_health_observations'"
        ).fetchone() is None


def test_repository_rejects_spoofed_append_only_trigger(tmp_path) -> None:
    database = tmp_path / "spoofed-trigger.sqlite3"
    SQLiteThesisHealthRepository(database)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            DROP TRIGGER thesis_health_observations_no_update;
            CREATE TRIGGER thesis_health_observations_no_update
            BEFORE UPDATE ON thesis_health_observations BEGIN SELECT 1; END;
            """
        )

    with pytest.raises(ValueError, match="append-only trigger mismatch"):
        SQLiteThesisHealthRepository(database)


def test_repository_rejects_same_name_tables_with_weak_schema(tmp_path) -> None:
    database = tmp_path / "weak-health.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE thesis_health_observations (
                observation_id TEXT, thesis_id TEXT, thesis_version INTEGER,
                observed_health_state TEXT, effective_health_state TEXT,
                content_hash TEXT, input_bundle_id TEXT, input_bundle_hash TEXT,
                configuration_id TEXT, configuration_hash TEXT,
                rule_set_id TEXT, rule_set_hash TEXT, prior_observation_id TEXT,
                prior_observation_hash TEXT, observation_json TEXT,
                input_bundle_json TEXT, configuration_json TEXT,
                rule_set_json TEXT, prior_observation_json TEXT, assessed_at TEXT
            );
            CREATE TABLE thesis_health_commands (
                idempotency_key TEXT, command_hash TEXT,
                observation_id TEXT, created_at TEXT
            );
            """
        )

    with pytest.raises(ValueError, match="schema mismatch"):
        SQLiteThesisHealthRepository(database)
