from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_DECISION_SUPPORT_TABLES,
    EXPECTED_OUTCOME_TABLES,
    EXPECTED_RESEARCH_QUALIFICATION_TABLES,
    EXPECTED_RESEARCH_VALIDITY_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


def test_decision_support_schema_adds_exactly_four_authority_relations(
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
        columns = {
            (str(row[0]), str(row[1]), str(row[2]))
            for row in connection.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'mra'
                  AND table_name = ANY(%s)
                """,
                (list(EXPECTED_DECISION_SUPPORT_TABLES),),
            ).fetchall()
        }
    assert EXPECTED_DECISION_SUPPORT_TABLES == {
        "decision_run",
        "decision_run_target",
        "decision_target_commitment",
        "decision_reference_observation",
    }
    assert tables == EXPECTED_TARGET_TABLES
    assert EXPECTED_DECISION_SUPPORT_TABLES <= tables
    assert {
        table for table in tables if table.startswith("market_target_outcome")
    } == EXPECTED_OUTCOME_TABLES
    assert EXPECTED_RESEARCH_VALIDITY_TABLES <= tables
    assert EXPECTED_RESEARCH_QUALIFICATION_TABLES <= tables
    assert not {data_type for _, _, data_type in columns if data_type == "jsonb"}
    assert not {
        table
        for table in tables
        if table.startswith(
            (
                "outcome",
                "context",
                "qualification",
                "model",
                "trade_outcome",
            )
        )
    }


def test_decision_run_closure_uses_composite_fks_and_one_reference_per_commitment(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    required_constraints = {
        "decision_run_candidate_set_uk",
        "decision_run_candidate_set_fk",
        "decision_run_runtime_run_fk",
        "decision_run_runtime_step_fk",
        "decision_run_runtime_attempt_fk",
        "decision_run_receipt_claim_fk",
        "decision_run_counts_ck",
        "decision_run_time_ck",
        "decision_run_target_ordinal_uk",
        "decision_run_target_definition_uk",
        "decision_run_target_definition_fk",
        "decision_run_target_checkpoint_fk",
        "decision_run_target_provider_product_fk",
        "decision_commitment_candidate_target_uk",
        "decision_commitment_candidate_fk",
        "decision_commitment_run_target_fk",
        "decision_commitment_run_scope_fk",
        "decision_reference_commitment_uk",
        "decision_reference_commitment_fk",
        "decision_commitment_reference_fk",
        "decision_reference_bar_fk",
        "decision_reference_gap_fk",
        "decision_reference_source_ck",
        "decision_reference_state_ck",
        "decision_reference_known_at_ck",
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
                (list(required_constraints),),
            ).fetchall()
        }
        triggers = {
            (str(row[0]), str(row[1]), str(row[2]))
            for row in connection.execute(
                """
                SELECT event_object_table, trigger_name, action_statement
                FROM information_schema.triggers
                WHERE trigger_schema = 'mra'
                  AND event_object_table = ANY(%s)
                """,
                (list(EXPECTED_DECISION_SUPPORT_TABLES),),
            ).fetchall()
        }
    assert set(constraints) == required_constraints
    assert "candidate_id, candidate_set_id, instrument_id" in constraints[
        "decision_commitment_candidate_fk"
    ]
    assert "decision_run_target_id, decision_run_id" in constraints[
        "decision_commitment_run_target_fk"
    ]
    assert "DEFERRABLE INITIALLY DEFERRED" in constraints[
        "decision_commitment_reference_fk"
    ]
    assert "bar_revision_id" in constraints["decision_reference_bar_fk"]
    assert "source_gap_id" in constraints["decision_reference_gap_fk"]
    trigger_names = {name for _, name, _ in triggers}
    assert {
        "decision_run_append_only",
        "decision_run_target_append_only",
        "decision_commitment_append_only",
        "decision_reference_append_only",
        "decision_run_target_open_guard",
        "decision_commitment_open_guard",
        "decision_reference_open_guard",
        "decision_run_closure_guard",
    } <= trigger_names


def test_decision_support_has_authority_and_replay_indexes(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        indexes = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'mra'
                  AND tablename = ANY(%s)
                """,
                (list(EXPECTED_DECISION_SUPPORT_TABLES),),
            ).fetchall()
        }
    assert {
        "decision_run_candidate_set_idx",
        "decision_run_request_idx",
        "decision_run_runtime_idx",
        "decision_run_target_replay_idx",
        "decision_run_target_definition_idx",
        "decision_commitment_cross_product_idx",
        "decision_commitment_candidate_idx",
        "decision_commitment_target_idx",
        "decision_reference_replay_idx",
        "decision_reference_bar_idx",
        "decision_reference_gap_idx",
        "decision_reference_known_at_idx",
    } <= set(indexes)
