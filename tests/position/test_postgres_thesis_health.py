from __future__ import annotations

from datetime import timedelta, timezone
import json
import psycopg
from tests.postgres_path_repositories import postgres_connection

import pytest

from market_regime_alpha.evidence.canonical import canonical_hash
import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.position import ThesisHealthObservationBuilder
from market_regime_alpha.position.thesis_health import thesis_health_command_hash
from tests.postgres_path_repositories import (
    PostgresThesisHealthRepository,
)

from tests.position.test_thesis_health_builder import _bundle
from tests.position.thesis_health_fixtures import make_h5_fixture


def _command_hash(bundle) -> str:
    return thesis_health_command_hash(bundle)


def _different_command_hash(label: str) -> str:
    return canonical_hash({"different-command": label})


def _stored(tmp_path):
    repository = PostgresThesisHealthRepository(tmp_path / "thesis-health.postgres-scope")
    bundle = _bundle(make_h5_fixture())
    observation = ThesisHealthObservationBuilder().build(bundle)
    stored = repository.save_observation(
        observation,
        input_bundle=bundle,
        idempotency_key="stored-health",
        command_hash=_command_hash(bundle),
    )
    return repository, bundle, stored


def test_repository_saves_reads_replays_and_restarts(tmp_path) -> None:
    repository, bundle, observation = _stored(tmp_path)

    assert repository.get_observation(observation.observation_id) == observation
    verified = repository.get_verified_thesis_health_bundle(
        observation.observation_id
    )
    assert verified.observation == observation
    assert verified.input_bundle == bundle
    assert verified.is_latest
    assert repository.resolve_command(
        idempotency_key="stored-health",
        command_hash=_command_hash(bundle),
    ) == observation
    restarted = PostgresThesisHealthRepository(repository.path)
    assert restarted.get_observation(observation.observation_id) == observation


def test_repository_rejects_idempotency_semantic_conflict(tmp_path) -> None:
    repository, _, _ = _stored(tmp_path)

    with pytest.raises(ValueError, match="idempotency key reused"):
        repository.resolve_command(
            idempotency_key="stored-health",
            command_hash=_different_command_hash("different-health"),
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
    with postgres_connection(repository.path) as connection:
        connection.execute(
            "DROP TRIGGER thesis_health_observations_no_update "
            "ON thesis_health_observations"
        )
        payload = json.loads(
            connection.execute(
                f"SELECT {column} FROM thesis_health_observations WHERE observation_id = %s",
                (str(observation.observation_id),),
            ).fetchone()[0]
        )
        payload[field] = replacement
        connection.execute(
            f"UPDATE thesis_health_observations SET {column} = %s WHERE observation_id = %s",
            (json.dumps(payload), str(observation.observation_id)),
        )

    with pytest.raises(ValueError):
        repository.get_observation(observation.observation_id)


def test_repository_rejects_tampered_projection_and_builder_replay(tmp_path) -> None:
    repository, _, observation = _stored(tmp_path)
    with postgres_connection(repository.path) as connection:
        connection.execute(
            "DROP TRIGGER thesis_health_observations_no_update "
            "ON thesis_health_observations"
        )
        connection.execute(
            "UPDATE thesis_health_observations SET effective_health_state = %s WHERE observation_id = %s",
            ("WEAKENING", str(observation.observation_id)),
        )

    with pytest.raises(ValueError, match="projection"):
        repository.get_observation(observation.observation_id)


def test_repository_transaction_rolls_back_on_command_failure(tmp_path) -> None:
    repository = PostgresThesisHealthRepository(tmp_path / "thesis-health.postgres-scope")
    bundle = _bundle(make_h5_fixture())
    observation = ThesisHealthObservationBuilder().build(bundle)
    with postgres_connection(repository.path) as connection:
        connection.execute(
            """
            CREATE FUNCTION reject_thesis_health_command_fn()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'injected H5 command failure';
            END;
            $$;
            CREATE TRIGGER reject_thesis_health_command
            BEFORE INSERT ON thesis_health_commands
            FOR EACH ROW EXECUTE FUNCTION reject_thesis_health_command_fn();
            """,
            prepare=False,
        )

    with pytest.raises(psycopg.Error, match="injected H5 command failure"):
        repository.save_observation(
            observation,
            input_bundle=bundle,
            idempotency_key="rollback-health",
            command_hash=_command_hash(bundle),
        )

    with postgres_connection(repository.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM thesis_health_observations"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM thesis_health_commands"
        ).fetchone()[0] == 0


def test_migration_repeat_safe_and_tables_append_only(tmp_path) -> None:
    repository, _, observation = _stored(tmp_path)
    PostgresThesisHealthRepository(repository.path)
    with postgres_connection(repository.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 8"
        ).fetchone()[0] == 1
        for statement in (
            "UPDATE thesis_health_observations SET observed_health_state = observed_health_state",
            "DELETE FROM thesis_health_observations",
            "UPDATE thesis_health_commands SET command_hash = command_hash",
            "DELETE FROM thesis_health_commands",
        ):
            with pytest.raises(psycopg.Error, match="append-only"):
                with connection.transaction():
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
        command_hash=_command_hash(current_bundle),
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
            command_hash=_command_hash(fork_bundle),
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
        command_hash=_command_hash(current_bundle),
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
        command_hash=_command_hash(successor_bundle),
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
        command_hash=_command_hash(current_bundle),
    )
    with postgres_connection(repository.path) as connection:
        connection.execute(
            "DROP TRIGGER thesis_health_observations_no_update "
            "ON thesis_health_observations"
        )
        payload = json.loads(
            connection.execute(
                "SELECT observation_json FROM thesis_health_observations WHERE observation_id = %s",
                (str(prior.observation_id),),
            ).fetchone()[0]
        )
        payload["reason"] = "tampered stored prior"
        connection.execute(
            "UPDATE thesis_health_observations SET observation_json = %s WHERE observation_id = %s",
            (json.dumps(payload), str(prior.observation_id)),
        )

    with pytest.raises(ValueError):
        repository.get_observation(current.observation_id)


@pytest.mark.parametrize("tamper", ("observation_id", "created_at"))
def test_repository_rejects_tampered_command_projection(tmp_path, tamper: str) -> None:
    repository, prior_bundle, prior = _stored(tmp_path)
    fixture = make_h5_fixture()
    current_bundle = _bundle(
        fixture,
        prior_observation=prior,
        assessed_at=prior.assessed_at + timedelta(minutes=1),
    )
    current = ThesisHealthObservationBuilder().build(current_bundle)
    repository.save_observation(
        current,
        input_bundle=current_bundle,
        idempotency_key="command-successor",
        command_hash=_command_hash(current_bundle),
    )
    with postgres_connection(repository.path) as connection:
        connection.execute(
            "DROP TRIGGER thesis_health_commands_no_update "
            "ON thesis_health_commands"
        )
        if tamper == "observation_id":
            connection.execute(
                """
                UPDATE thesis_health_commands SET observation_id = %s
                WHERE idempotency_key = 'stored-health'
                """,
                (str(current.observation_id),),
            )
        else:
            connection.execute(
                """
                UPDATE thesis_health_commands SET created_at = %s
                WHERE idempotency_key = 'stored-health'
                """,
                (current.assessed_at.isoformat(),),
            )

    with pytest.raises(ValueError, match="command projection mismatch"):
        repository.resolve_command(
            idempotency_key="stored-health",
            command_hash=_command_hash(prior_bundle),
        )
