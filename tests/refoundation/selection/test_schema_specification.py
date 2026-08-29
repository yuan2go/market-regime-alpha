from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_SELECTION_TABLES,
    SchemaManager,
)


def test_selection_schema_has_exactly_the_seven_core_authority_relations(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'mra'").fetchall()}
    assert EXPECTED_SELECTION_TABLES == {
        "universe",
        "universe_revision",
        "universe_member",
        "eligibility_policy",
        "eligibility_rule",
        "eligibility_assessment",
        "eligibility_reason",
    }
    assert EXPECTED_SELECTION_TABLES <= tables
    assert not {name for name in tables if name.startswith(("candidate", "decision", "research_definition"))}


def test_selection_counts_three_state_rule_shape_and_scope_identity_are_declarative(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    names = {
        "universe_revision_counts_ck",
        "universe_revision_artifact_fk",
        "universe_member_disposition_ck",
        "eligibility_rule_shape_ck",
        "eligibility_rule_missing_ck",
        "eligibility_assessment_counts_ck",
        "eligibility_assessment_aggregate_ck",
        "eligibility_reason_observed_ck",
        "eligibility_reason_reason_ck",
        "eligibility_reason_lineage_ck",
    }
    with psycopg.connect(target_database_url) as connection:
        constraints = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT constraint_item.conname,
                       pg_get_constraintdef(constraint_item.oid, true)
                FROM pg_constraint AS constraint_item
                JOIN pg_namespace AS namespace
                  ON namespace.oid = constraint_item.connamespace
                WHERE namespace.nspname = 'mra'
                  AND constraint_item.conname = ANY(%s)
                """,
                (list(names),),
            ).fetchall()
        }
    assert set(constraints) == names
    assert "total_count = (included_count + excluded_count + unknown_count)" in constraints["universe_revision_counts_ck"]
    assert "scope_artifact_id, scope_content_sha256, scope_size_bytes" in constraints["universe_revision_artifact_fk"]
    assert "missing_result = 'UNKNOWN'::text" in constraints["eligibility_rule_missing_ck"]
    assert "fail_count > 0" in constraints["eligibility_assessment_aggregate_ck"]
    assert "market_fact_revision_ids" in constraints["eligibility_reason_lineage_ck"]


def test_selection_uses_numeric_lineage_indexes_and_only_append_only_triggers(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        numeric_columns = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'mra'
                  AND table_name = ANY(%s)
                  AND data_type = 'numeric'
                """,
                (list(EXPECTED_SELECTION_TABLES),),
            ).fetchall()
        }
        trigger_functions = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """
                SELECT event_object_table, action_statement
                FROM information_schema.triggers
                WHERE trigger_schema = 'mra'
                  AND event_object_table = ANY(%s)
                """,
                (list(EXPECTED_SELECTION_TABLES),),
            ).fetchall()
        }
        indexes = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'mra'
                  AND tablename = ANY(%s)
                """,
                (list(EXPECTED_SELECTION_TABLES),),
            ).fetchall()
        }
    assert {
        ("eligibility_rule", "threshold_decimal"),
        ("eligibility_reason", "observed_decimal"),
        ("eligibility_reason", "threshold_decimal"),
    } <= numeric_columns
    assert trigger_functions
    assert all("reject_append_only_mutation" in statement for _, statement in trigger_functions)
    assert "USING gin (market_fact_revision_ids)" in indexes["eligibility_reason_fact_lineage_gin"]
    assert "USING gin (market_bar_revision_ids)" in indexes["eligibility_reason_bar_lineage_gin"]


def test_artifact_integrity_and_market_freshness_are_distinct_policy_seams(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        definitions = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT routine_name, routine_definition
                FROM information_schema.routines
                WHERE routine_schema = 'mra'
                  AND routine_name IN (
                      'artifact_has_verified_integrity',
                      'market_artifact_is_readable'
                  )
                """
            ).fetchall()
        }
    assert "24 hours" not in definitions["artifact_has_verified_integrity"]
    assert "artifact_has_verified_integrity" in definitions["market_artifact_is_readable"]
    assert "24 hours" in definitions["market_artifact_is_readable"]
