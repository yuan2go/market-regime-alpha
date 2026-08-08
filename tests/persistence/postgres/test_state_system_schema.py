from __future__ import annotations

from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import verify_postgres_authority_schema


STATE_TABLES = {
    "market_regime_state_observation",
    "market_regime_state",
    "market_regime_state_transition",
    "etf_rotation_state_observation",
    "etf_rotation_state",
    "etf_rotation_state_transition",
    "theme_rotation_state_observation",
    "theme_rotation_state",
    "theme_rotation_state_transition",
    "capital_state_observation",
    "capital_state",
    "capital_state_transition",
    "state_current_pointer",
    "dynamic_stock_pool",
    "dynamic_stock_pool_member",
    "dynamic_stock_pool_change",
    "state_runtime_receipt",
}


def test_migration_022_adds_explicit_state_and_pool_authorities(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        verify_postgres_authority_schema(connection)
        actual = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = current_schema()
                  AND (
                    tablename LIKE '%state%'
                    OR tablename LIKE 'dynamic_stock_pool%'
                  )
                """
            ).fetchall()
        }

    assert STATE_TABLES <= actual


def test_state_business_values_are_rows_not_trigger_generated(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        trigger_functions = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT action_statement
                FROM information_schema.triggers
                WHERE trigger_schema = current_schema()
                  AND event_object_table IN (
                    'market_regime_state', 'etf_rotation_state',
                    'theme_rotation_state', 'capital_state',
                    'dynamic_stock_pool'
                  )
                """
            ).fetchall()
        }

    assert trigger_functions == {"EXECUTE FUNCTION reject_append_only_mutation()"}
