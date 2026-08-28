from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_MARKET_TABLES,
    SchemaManager,
)


def test_market_schema_has_the_twelve_approved_authority_relations(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        tables = frozenset(
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'mra'"
            ).fetchall()
        )
    assert EXPECTED_MARKET_TABLES == {
        "provider",
        "provider_product",
        "data_capture",
        "instrument",
        "instrument_identifier",
        "trading_session",
        "classification",
        "classification_membership_revision",
        "market_bar_revision",
        "instrument_fact_revision",
        "corporate_action_revision",
        "source_gap",
    }
    assert EXPECTED_MARKET_TABLES <= tables


def test_capture_owns_independent_pit_axes_without_latest_or_backfill_flags(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        columns = {
            row[0]
            for row in connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'mra' AND table_name = 'data_capture'
                """
            ).fetchall()
        }
        constraints = "\n".join(
            row[0]
            for row in connection.execute(
                """
                SELECT pg_get_constraintdef(item.oid, true)
                FROM pg_constraint AS item
                WHERE item.conrelid = 'mra.data_capture'::regclass
                ORDER BY item.conname
                """
            ).fetchall()
        )
    assert {
        "provider_time",
        "source_availability_status",
        "source_available_at",
        "capture_started_at",
        "capture_completed_at",
        "recorded_at",
        "known_at",
        "decision_visible_at",
    } <= columns
    assert not {name for name in columns if "latest" in name or "backfill" in name}
    assert "decision_visible_at = known_at" in constraints
    assert "source_availability_status = 'UNKNOWN'" in constraints


def test_market_financial_values_use_numeric_and_revision_rows_are_append_only(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        numeric_columns = {
            (row[0], row[1])
            for row in connection.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'mra' AND data_type = 'numeric'
                """
            ).fetchall()
        }
        trigger_actions = {
            row[0]: frozenset(str(row[1]).split(","))
            for row in connection.execute(
                """
                SELECT event_object_table,
                       string_agg(event_manipulation, ',' ORDER BY event_manipulation)
                FROM information_schema.triggers
                WHERE trigger_schema = 'mra'
                  AND event_object_table IN (
                      'market_bar_revision', 'instrument_fact_revision',
                      'corporate_action_revision',
                      'classification_membership_revision', 'source_gap'
                  )
                GROUP BY event_object_table
                """
            ).fetchall()
        }
    assert {
        ("market_bar_revision", "open_value"),
        ("market_bar_revision", "high_value"),
        ("market_bar_revision", "low_value"),
        ("market_bar_revision", "close_value"),
        ("market_bar_revision", "volume_value"),
        ("corporate_action_revision", "cash_amount"),
        ("corporate_action_revision", "ratio_factor"),
    } <= numeric_columns
    assert set(trigger_actions) == {
        "classification_membership_revision",
        "corporate_action_revision",
        "instrument_fact_revision",
        "market_bar_revision",
        "source_gap",
    }
    assert all({"DELETE", "UPDATE"} <= actions for actions in trigger_actions.values())


def test_market_bar_identity_keeps_basis_timeframe_and_revision_separate(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        definition = connection.execute(
            """
            SELECT pg_get_constraintdef(oid, true)
            FROM pg_constraint
            WHERE conrelid = 'mra.market_bar_revision'::regclass
              AND conname = 'market_bar_revision_identity_uk'
            """
        ).fetchone()
    assert definition is not None
    assert "timeframe" in definition[0]
    assert "adjustment_basis" in definition[0]
    assert "revision" in definition[0]
