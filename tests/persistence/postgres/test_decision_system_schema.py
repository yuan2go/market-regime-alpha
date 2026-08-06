from __future__ import annotations

import psycopg
import pytest

from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


DECISION_TABLES = {
    "manual_account_observation",
    "manual_position_observation",
    "account_reconciliation",
    "reconciliation_difference",
    "daily_decision_summary",
    "daily_summary_candidate",
    "research_portfolio_proposal",
    "research_portfolio_line",
    "independent_risk_decision",
    "decision_runtime_receipt",
}


def test_migration_025_installs_exact_decision_authority_and_append_guards(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT tablename FROM pg_catalog.pg_tables
                WHERE schemaname = current_schema()
                  AND tablename = ANY(%s)
                """,
                (sorted(DECISION_TABLES),),
            ).fetchall()
        }
        triggers = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """
                SELECT event_object_table, trigger_name
                FROM information_schema.triggers
                WHERE trigger_schema = current_schema()
                  AND event_object_table = ANY(%s)
                """,
                (sorted(DECISION_TABLES),),
            ).fetchall()
        }
        final_index = connection.execute(
            """
            SELECT indexdef FROM pg_catalog.pg_indexes
            WHERE schemaname = current_schema()
              AND indexname = 'daily_decision_one_original_terminal_idx'
            """
        ).fetchone()
        child_kind_constraint = connection.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_catalog.pg_constraint
            WHERE connamespace = current_schema()::regnamespace
              AND conname = 'continuous_child_run_child_kind_check'
            """
        ).fetchone()

    assert tables == DECISION_TABLES
    assert triggers == {(table, f"{table}_no_{operation}") for table in DECISION_TABLES for operation in ("update", "delete")}
    assert final_index is not None
    assert "UNIQUE INDEX" in str(final_index[0])
    assert "FINALIZED" in str(final_index[0])
    assert "BLOCKED" in str(final_index[0])
    assert child_kind_constraint is not None
    assert "DECISION_SYSTEM" in str(child_kind_constraint[0])


def test_migration_024_rejects_non_postgres_runtime_binding(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection() as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO runtime_database_bindings(
                    scope_type, scope_id, backend, locator, created_at
                ) VALUES (
                    'CONTINUOUS_RESEARCH', 'non-postgres-binding',
                    'sqlite', 'file.db', now()
                )
                """
            )
