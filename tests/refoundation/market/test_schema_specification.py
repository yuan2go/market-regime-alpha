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
    assert "known_at = GREATEST(capture_completed_at, recorded_at)" in constraints
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
        ("corporate_action_revision", "cash_amount_per_share"),
        ("corporate_action_revision", "ratio_factor"),
        ("corporate_action_revision", "subscription_price"),
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
    assert "price_basis" in definition[0]
    assert "revision" in definition[0]


def test_a_share_session_timezone_is_a_database_invariant(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        definition = connection.execute(
            """
            SELECT pg_get_constraintdef(oid, true)
            FROM pg_constraint
            WHERE conrelid = 'mra.trading_session'::regclass
              AND conname = 'trading_session_timezone_ck'
            """
        ).fetchone()
    assert definition is not None
    assert "timezone_name = 'Asia/Shanghai'" in definition[0]


def test_normalized_market_facts_own_visibility_and_capture_product_lineage(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    normalized_relations = {
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
    with psycopg.connect(target_database_url) as connection:
        temporal_columns = {
            str(row[0]): {str(item) for item in row[1]}
            for row in connection.execute(
                """
                SELECT table_name, array_agg(column_name::text ORDER BY column_name)
                FROM information_schema.columns
                WHERE table_schema = 'mra'
                  AND table_name = ANY(%s)
                  AND column_name IN ('recorded_at', 'known_at', 'decision_visible_at')
                GROUP BY table_name
                """,
                (list(normalized_relations),),
            ).fetchall()
        }
        temporal_triggers = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT event_object_table
                FROM information_schema.triggers
                WHERE trigger_schema = 'mra'
                  AND trigger_name LIKE '%%temporal_validate'
                """
            ).fetchall()
        }
        product_columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'mra' AND table_name = 'provider_product'
                """
            ).fetchall()
        }
        composite_foreign_keys = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT table_object.relname,
                       pg_get_constraintdef(constraint_item.oid, true)
                FROM pg_constraint AS constraint_item
                JOIN pg_class AS table_object
                  ON table_object.oid = constraint_item.conrelid
                JOIN pg_namespace AS namespace
                  ON namespace.oid = table_object.relnamespace
                WHERE namespace.nspname = 'mra'
                  AND constraint_item.conname LIKE '%%capture_product_fk'
                """
            ).fetchall()
        }
        gap_identity = connection.execute(
            """
            SELECT pg_get_constraintdef(oid, true)
            FROM pg_constraint
            WHERE conrelid = 'mra.source_gap'::regclass
              AND conname = 'source_gap_identity_uk'
            """
        ).fetchone()

    assert set(temporal_columns) == normalized_relations
    assert all(
        columns == {"recorded_at", "known_at", "decision_visible_at"}
        for columns in temporal_columns.values()
    )
    assert temporal_triggers == normalized_relations
    assert {
        "fact_kinds",
        "bar_timeframes",
        "price_bases",
    } <= product_columns
    assert set(composite_foreign_keys) == {
        "market_bar_revision",
        "instrument_fact_revision",
        "corporate_action_revision",
        "source_gap",
    }
    assert all(
        "FOREIGN KEY (capture_id, provider_product_id)" in definition
        for definition in composite_foreign_keys.values()
    )
    assert gap_identity is not None
    assert "NULLS NOT DISTINCT" in gap_identity[0]
