from __future__ import annotations

from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor

import pytest

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import (
    PostgresMigration,
    PostgresMigrationChecksumError,
    PostgresMigrationSequenceError,
    PostgresMigrator,
    load_packaged_migrations,
)


def test_packaged_migrations_are_contiguous_and_checksummed() -> None:
    migrations = load_packaged_migrations()

    assert tuple(item.version for item in migrations) == tuple(range(1, 27))
    assert len({item.name for item in migrations}) == 26
    assert all(item.checksum == sha256(item.sql.encode("utf-8")).hexdigest() for item in migrations)


def test_missing_migration_version_is_rejected() -> None:
    migrations = (
        PostgresMigration.create(1, "one", "SELECT 1;"),
        PostgresMigration.create(3, "three", "SELECT 3;"),
    )

    with pytest.raises(PostgresMigrationSequenceError, match="contiguous"):
        PostgresMigrator(migrations=migrations)


def test_apply_all_is_idempotent(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrator = PostgresMigrator()

    first = migrator.apply_all(postgres_factory)
    second = migrator.apply_all(postgres_factory)

    assert tuple(item.version for item in first) == tuple(range(1, 27))
    assert second == ()
    with postgres_factory.connection(read_only=True) as connection:
        rows = connection.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version").fetchall()
    assert len(rows) == 26


def test_applied_checksum_drift_is_rejected(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = (PostgresMigration.create(1, "one", "SELECT 1;"),)
    PostgresMigrator(migrations=migrations).apply_all(postgres_factory)
    changed = (PostgresMigration.create(1, "one", "SELECT 2;"),)

    with pytest.raises(PostgresMigrationChecksumError, match="checksum"):
        PostgresMigrator(migrations=changed).apply_all(postgres_factory)


def test_failed_migration_does_not_record_version(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = (
        PostgresMigration.create(1, "one", "CREATE TABLE durable_one(id bigint PRIMARY KEY);"),
        PostgresMigration.create(2, "broken", "CREATE TABL invalid syntax;"),
    )

    with pytest.raises(Exception):
        PostgresMigrator(migrations=migrations).apply_all(postgres_factory)
    with postgres_factory.connection(read_only=True) as connection:
        rows = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        durable = connection.execute("SELECT to_regclass('durable_one')").fetchone()
    assert rows == [(1,)]
    assert durable == ("durable_one",)


def test_concurrent_migrators_are_serialized(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = (
        PostgresMigration.create(
            1,
            "serialized",
            "SELECT pg_sleep(0.05); CREATE TABLE serialized_once(id bigint PRIMARY KEY);",
        ),
    )
    migrator = PostgresMigrator(migrations=migrations)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: migrator.apply_all(postgres_factory), range(2)))

    assert sorted(len(result) for result in results) == [0, 1]


def test_migration_021_upgrades_an_existing_020_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:20]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (21, "continuous_runtime_schedule"),
        (22, "state_system_dynamic_pool"),
        (23, "state_system_runtime_child"),
        (24, "postgres_only_authority"),
        (25, "decision_system"),
        (26, "decision_authority_hardening"),
    )


def test_migration_022_upgrades_an_existing_021_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:21]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (22, "state_system_dynamic_pool"),
        (23, "state_system_runtime_child"),
        (24, "postgres_only_authority"),
        (25, "decision_system"),
        (26, "decision_authority_hardening"),
    )


def test_migration_023_upgrades_an_existing_022_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:22]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (23, "state_system_runtime_child"),
        (24, "postgres_only_authority"),
        (25, "decision_system"),
        (26, "decision_authority_hardening"),
    )


def test_migrations_024_through_026_upgrade_existing_023_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:23]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (24, "postgres_only_authority"),
        (25, "decision_system"),
        (26, "decision_authority_hardening"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        latest = connection.execute("SELECT version, name FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
        decision_table = connection.execute("SELECT to_regclass('daily_decision_summary')").fetchone()
    assert latest == (26, "decision_authority_hardening")
    assert decision_table == ("daily_decision_summary",)


def test_migration_026_preserves_prerelease_v1_decision_rows_forward_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:25]).apply_all(postgres_factory)
    digest = "sha256:" + "a" * 64
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO manual_account_observation(
                observation_id, content_hash, account_id, trading_date,
                as_of_time, total_equity, available_cash, frozen_cash,
                source, actor, reason, notes, idempotency_key, command_hash,
                revision, previous_observation_id, payload_json, created_at
            ) VALUES (
                'prerelease-v1-observation', %s, 'account-a', DATE '2026-08-06',
                TIMESTAMPTZ '2026-08-06 06:45:00+00', 100, 100, 0,
                'MANUAL', 'tester', 'migration guard', '', 'v1-observation',
                %s, 1, NULL, '{}'::jsonb, TIMESTAMPTZ '2026-08-06 06:45:00+00'
            )
            """,
            (digest, digest),
        )

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        applied = connection.execute(
            "SELECT max(version) FROM schema_migrations"
        ).fetchone()
        preserved = connection.execute(
            """
            SELECT observation_id FROM manual_account_observation
            WHERE observation_id = 'prerelease-v1-observation'
            """
        ).fetchone()
    assert tuple((item.version, item.name) for item in upgraded) == (
        (26, "decision_authority_hardening"),
    )
    assert applied == (26,)
    assert preserved == ("prerelease-v1-observation",)
