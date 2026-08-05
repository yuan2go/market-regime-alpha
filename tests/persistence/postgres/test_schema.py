from __future__ import annotations

import psycopg
import pytest

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    EXPECTED_AUTHORITY_TABLES,
    PostgresSchemaError,
    verify_postgres_authority_schema,
)


def test_authority_schema_has_exact_expected_table_inventory(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        verify_postgres_authority_schema(connection)
        rows = connection.execute(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = current_schema()
            ORDER BY tablename
            """
        ).fetchall()

    assert {str(row[0]) for row in rows} == EXPECTED_AUTHORITY_TABLES


def test_missing_authority_table_is_rejected(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)
    with postgres_factory.connection() as connection:
        connection.execute("DROP TABLE lifecycle_events")
        connection.commit()

    with postgres_factory.connection(read_only=True) as connection:
        with pytest.raises(PostgresSchemaError, match="missing tables"):
            verify_postgres_authority_schema(connection)


@pytest.mark.parametrize(
    ("table", "seed_sql"),
    [
        (
            "manual_fills",
            """
            INSERT INTO manual_trade_records(
                manual_trade_id, risk_decision_id, account_id, symbol, side,
                state, filled_quantity, aggregate_json, version
            ) VALUES (
                'trade-1', 'risk-1', 'account-1', '600000.SH', 'BUY',
                'RECORDED', 0, '{}', 0
            );
            INSERT INTO manual_fills(
                fill_id, external_fill_id, manual_trade_id, account_id,
                symbol, fill_kind, correction_of_fill_id, fill_json,
                recorded_at, idempotency_key
            ) VALUES (
                'fill-1', 'external-1', 'trade-1', 'account-1',
                '600000.SH', 'EXECUTION', NULL, '{}',
                '2026-08-05T01:00:00+00:00', 'fill-key-1'
            )
            """,
        ),
        (
            "lifecycle_events",
            """
            INSERT INTO lifecycle_runs(
                run_id, idempotency_key, command_hash, command_json, run_type,
                decision_date, as_of_time, status, run_json, version,
                claim_token, created_at, updated_at
            ) VALUES (
                'run-1', 'key-1', 'sha256:' || repeat('a', 64), '{}',
                'CANONICAL_DECISION_LIFECYCLE',
                '2026-08-05', '2026-08-05T01:00:00+00:00', 'CREATED', '{}',
                1, 0, '2026-08-05T01:00:00+00:00',
                '2026-08-05T01:00:00+00:00'
            );
            INSERT INTO lifecycle_events(
                event_id, run_id, sequence_number, event_type, event_json,
                payload_json, payload_hash, created_at, claim_token
            ) VALUES (
                'event-1', 'run-1', 1, 'RUN_CREATED', '{}', '{}',
                'sha256:' || repeat('b', 64),
                '2026-08-05T01:00:00+00:00', 0
            )
            """,
        ),
    ],
)
def test_append_only_tables_reject_update_and_delete(
    postgres_factory: PostgresConnectionFactory,
    table: str,
    seed_sql: str,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)
    with postgres_factory.connection() as connection:
        connection.execute(seed_sql)
        connection.commit()

    with postgres_factory.connection() as connection:
        with pytest.raises(psycopg.errors.RaiseException):
            connection.execute(f"DELETE FROM {table}")
