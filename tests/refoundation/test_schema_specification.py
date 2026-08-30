from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_CANDIDATE_TABLES,
    EXPECTED_FOUNDATION_TABLES,
    EXPECTED_MARKET_TABLES,
    EXPECTED_RESEARCH_DEFINITION_TABLES,
    EXPECTED_SELECTION_TABLES,
    EXPECTED_TARGET_DEFINITION_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


def test_target_draft_schema_has_exact_relations_views_and_no_jsonb_or_partitions(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        tables = frozenset(
            row[0]
            for row in connection.execute(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'mra' ORDER BY tablename
                """
            ).fetchall()
        )
        views = frozenset(
            row[0]
            for row in connection.execute(
                "SELECT viewname FROM pg_views WHERE schemaname = 'mra'"
            ).fetchall()
        )
        jsonb_columns = connection.execute(
            """
            SELECT count(*) FROM information_schema.columns
            WHERE table_schema = 'mra' AND data_type = 'jsonb'
            """
        ).fetchone()
        partitions = connection.execute(
            """
            SELECT count(*)
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'mra' AND relation.relispartition
            """
        ).fetchone()

    assert tables == EXPECTED_TARGET_TABLES
    assert EXPECTED_TARGET_TABLES == (
        EXPECTED_FOUNDATION_TABLES
        | EXPECTED_MARKET_TABLES
        | EXPECTED_SELECTION_TABLES
        | EXPECTED_RESEARCH_DEFINITION_TABLES
        | EXPECTED_TARGET_DEFINITION_TABLES
    )
    assert views == {
        "artifact_integrity_status",
        "candidate_component_diagnostic",
        "candidate_funnel",
        "run_trace",
    }
    assert EXPECTED_CANDIDATE_TABLES <= EXPECTED_SELECTION_TABLES
    assert jsonb_columns == (0,)
    assert partitions == (0,)


def test_target_foreign_keys_restrict_and_critical_partial_indexes_exist(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        delete_actions = connection.execute(
            """
            SELECT DISTINCT constraint_item.confdeltype
            FROM pg_constraint AS constraint_item
            JOIN pg_namespace AS namespace
              ON namespace.oid = constraint_item.connamespace
            WHERE namespace.nspname = 'mra' AND constraint_item.contype = 'f'
            """
        ).fetchall()
        index_definitions = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT indexname, indexdef FROM pg_indexes
                WHERE schemaname = 'mra'
                """
            ).fetchall()
        }

    assert delete_actions == [("r",)]
    assert "WHERE (state = ANY (ARRAY['CLAIMED'::text, 'RUNNING'::text]))" in index_definitions[
        "runtime_attempt_one_live_idx"
    ]
    assert "WHERE enabled" in index_definitions["runtime_schedule_one_enabled_idx"]
    assert "command_kind, scope_id, idempotency_key" in index_definitions[
        "command_receipt_idempotency_uk"
    ]


def test_runtime_claim_links_and_receipt_results_are_database_enforced(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        constraints = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT constraint_item.conname,
                       pg_get_constraintdef(constraint_item.oid, true)
                FROM pg_constraint AS constraint_item
                JOIN pg_namespace AS namespace
                  ON namespace.oid = constraint_item.connamespace
                WHERE namespace.nspname = 'mra'
                  AND constraint_item.conname IN (
                      'runtime_step_current_attempt_fk',
                      'command_receipt_runtime_claim_fk',
                      'command_receipt_result_ck'
                  )
                """
            ).fetchall()
        }

    assert set(constraints) == {
        "runtime_step_current_attempt_fk",
        "command_receipt_runtime_claim_fk",
        "command_receipt_result_ck",
    }
    assert "current_attempt_id, step_id, current_fence" in constraints[
        "runtime_step_current_attempt_fk"
    ]
    assert "runtime_attempt_id, runtime_step_id, fence_token" in constraints[
        "command_receipt_runtime_claim_fk"
    ]
    assert "status = 'SUCCEEDED'::text" in constraints["command_receipt_result_ck"]


def test_seed_initializes_only_epoch_and_migration_reference_state(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.schema_epoch),
                (SELECT count(*) FROM mra.schema_migrations),
                (SELECT count(*) FROM mra.runtime_schedule),
                (SELECT count(*) FROM mra.runtime_run),
                (SELECT count(*) FROM mra.artifact),
                (SELECT count(*) FROM mra.command_receipt)
            """
        ).fetchone()
    assert counts == (1, 1, 0, 0, 0, 0)
