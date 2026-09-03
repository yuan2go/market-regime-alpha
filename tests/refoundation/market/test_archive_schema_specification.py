from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_MARKET_ARCHIVE_TABLES,
    SchemaManager,
)


def test_archive_schema_has_concrete_two_lane_authority(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'mra'"
            ).fetchall()
        }
        root_columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'mra' AND table_name = 'market_archive'
                """
            ).fetchall()
        }

    assert EXPECTED_MARKET_ARCHIVE_TABLES == {
        "market_archive",
        "market_archive_slice",
        "market_archive_capture_observation",
        "market_archive_slice_gap",
        "market_archive_resource_stop",
        "market_archive_seal",
    }
    assert EXPECTED_MARKET_ARCHIVE_TABLES <= tables
    assert {
        "lane",
        "archive_start_at",
        "event_window_start",
        "event_window_end",
        "slice_count",
        "slice_roster_sha256",
        "content_sha256",
    } <= root_columns


def test_archive_children_are_append_only_and_fk_indexed(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    relations = tuple(EXPECTED_MARKET_ARCHIVE_TABLES)
    with psycopg.connect(target_database_url) as connection:
        append_only = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT event_object_table
                FROM information_schema.triggers
                WHERE trigger_schema = 'mra'
                  AND event_object_table = ANY(%s)
                  AND event_manipulation IN ('UPDATE', 'DELETE')
                """,
                (list(relations),),
            ).fetchall()
        }
        fk_indexes = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname = 'mra'
                  AND indexname LIKE 'market_archive%%_idx'
                """
            ).fetchall()
        }

    assert append_only == set(relations)
    assert {
        "market_archive_slice_archive_idx",
        "market_archive_observation_slice_idx",
        "market_archive_observation_capture_idx",
        "market_archive_slice_gap_slice_idx",
        "market_archive_slice_gap_gap_idx",
        "market_archive_resource_stop_slice_idx",
        "market_archive_seal_archive_idx",
    } <= fk_indexes


def test_prospective_and_seal_guards_live_in_postgres(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        functions = "\n".join(
            str(row[0])
            for row in connection.execute(
                """
                SELECT pg_get_functiondef(item.oid)
                FROM pg_proc AS item
                JOIN pg_namespace AS namespace ON namespace.oid = item.pronamespace
                WHERE namespace.nspname = 'mra'
                  AND item.proname IN (
                    'validate_market_archive',
                    'market_capture_normalized_roster',
                    'validate_market_archive_observation',
                    'validate_market_archive_seal'
                  )
                ORDER BY item.proname
                """
            ).fetchall()
        )

    assert "PROSPECTIVE_CONTEMPORANEOUS" in functions
    assert "archive_start_at" in functions
    assert "observation_ordinal" in functions
    assert "NEW.known_at < NEW.event_window_start" in functions
    assert "normalized_revision_roster_sha256" in functions
    assert "SOURCE_GAP" in functions
    assert "RETROSPECTIVE_BACKFILL" in functions
    assert "PARTIAL_WITH_RESOURCE_LIMIT" in functions
