from __future__ import annotations

import psycopg
import pytest

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    verify_postgres_authority_schema,
)


CONTINUOUS_TABLES = {
    "continuous_research_run",
    "continuous_runtime_tick",
    "continuous_provider_attempt",
    "continuous_evidence_commit",
    "continuous_current_evidence",
    "continuous_change_decision",
    "continuous_child_run",
    "continuous_runtime_event",
    "continuous_runtime_schedule",
    "continuous_runtime_authority_evidence",
}


def test_migration_020_adds_exact_continuous_runtime_authorities(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        verify_postgres_authority_schema(connection)
        tables = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = current_schema()
                  AND tablename LIKE 'continuous_%'
                """
            ).fetchall()
        }
        migration = connection.execute("SELECT version, name FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()

    assert tables == CONTINUOUS_TABLES
    assert migration == (97, "daily_alpha_target_session")


def test_migration_020_extends_runtime_binding_scope_without_weakening_it(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO runtime_database_bindings(
                scope_type, scope_id, backend, locator, created_at
            ) VALUES (
                'CONTINUOUS_RESEARCH', 'run-1', 'postgres',
                'postgresql://***@127.0.0.1/test?schema=isolated',
                '2026-08-06T00:00:00+00:00'
            )
            """
        )
        connection.commit()
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO runtime_database_bindings(
                    scope_type, scope_id, backend, locator, created_at
                ) VALUES (
                    'UNKNOWN_RUNTIME', 'run-2', 'postgres', 'invalid',
                    '2026-08-06T00:00:00+00:00'
                )
                """
            )


def test_continuous_history_tables_have_mutation_guards(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        triggers = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """
                SELECT event_object_table, trigger_name
                FROM information_schema.triggers
                WHERE trigger_schema = current_schema()
                  AND event_object_table LIKE 'continuous_%'
                """
            ).fetchall()
        }

    assert triggers == {
        ("continuous_research_run", "continuous_research_run_identity_immutable"),
        ("continuous_research_run", "continuous_research_run_no_delete"),
        ("continuous_runtime_tick", "continuous_runtime_tick_no_delete"),
        ("continuous_runtime_tick", "continuous_runtime_tick_terminal_immutable"),
        ("continuous_provider_attempt", "continuous_provider_attempt_no_delete"),
        ("continuous_provider_attempt", "continuous_provider_attempt_transition_guard"),
        ("continuous_evidence_commit", "continuous_evidence_commit_no_update"),
        ("continuous_evidence_commit", "continuous_evidence_commit_no_delete"),
        ("continuous_current_evidence", "continuous_current_evidence_no_delete"),
        ("continuous_current_evidence", "continuous_current_evidence_transition_guard"),
        ("continuous_change_decision", "continuous_change_decision_no_update"),
        ("continuous_change_decision", "continuous_change_decision_no_delete"),
        ("continuous_child_run", "continuous_child_run_no_update"),
        ("continuous_child_run", "continuous_child_run_no_delete"),
        ("continuous_runtime_event", "continuous_runtime_event_no_update"),
        ("continuous_runtime_event", "continuous_runtime_event_no_delete"),
        ("continuous_runtime_schedule", "continuous_runtime_schedule_identity_immutable"),
        ("continuous_runtime_schedule", "continuous_runtime_schedule_no_delete"),
        (
            "continuous_runtime_authority_evidence",
            "continuous_runtime_authority_evidence_no_update",
        ),
        (
            "continuous_runtime_authority_evidence",
            "continuous_runtime_authority_evidence_no_delete",
        ),
    }
