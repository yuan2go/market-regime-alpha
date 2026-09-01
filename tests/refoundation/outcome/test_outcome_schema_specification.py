from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_OUTCOME_TABLES,
    EXPECTED_RESEARCH_QUALIFICATION_TABLES,
    EXPECTED_RESEARCH_VALIDITY_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


def test_wp10_adds_exactly_eight_outcome_authority_relations(
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
        json_columns = connection.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'mra'
              AND table_name = ANY(%s)
              AND data_type IN ('json', 'jsonb')
            """,
            (list(EXPECTED_OUTCOME_TABLES),),
        ).fetchall()
    assert EXPECTED_OUTCOME_TABLES == {
        "market_target_outcome",
        "market_target_outcome_revision",
        "market_target_outcome_source",
        "market_target_outcome_observation",
        "market_target_outcome_metric",
        "market_target_outcome_metric_reference",
        "market_target_outcome_metric_observation",
        "market_target_outcome_reason",
    }
    assert tables == EXPECTED_TARGET_TABLES
    assert EXPECTED_OUTCOME_TABLES <= tables
    assert EXPECTED_RESEARCH_VALIDITY_TABLES <= tables
    assert EXPECTED_RESEARCH_QUALIFICATION_TABLES <= tables
    assert json_columns == []
    assert not {
        table
        for table in tables
        if table.startswith(
            (
                "model",
                "qualification",
                "context",
                "trade_outcome",
            )
        )
    }


def test_outcome_authority_has_concrete_fk_and_revision_closure_constraints(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    required = {
        "market_target_outcome_commitment_uk",
        "market_target_outcome_commitment_fk",
        "market_target_outcome_reference_fk",
        "outcome_revision_ordinal_uk",
        "outcome_revision_request_hash_uk",
        "outcome_revision_supersedes_uk",
        "outcome_revision_chain_ck",
        "outcome_revision_cutoffs_ck",
        "outcome_revision_counts_ck",
        "outcome_revision_receipt_claim_fk",
        "outcome_source_revision_fk",
        "outcome_source_session_fk",
        "outcome_source_bar_fk",
        "outcome_source_gap_fk",
        "outcome_source_shape_ck",
        "outcome_source_cutoffs_ck",
        "outcome_observation_checkpoint_fk",
        "outcome_observation_source_fk",
        "outcome_observation_state_ck",
        "outcome_metric_definition_fk",
        "outcome_metric_state_ck",
        "outcome_metric_reference_dependency_fk",
        "outcome_metric_reference_observation_fk",
        "outcome_metric_reference_role_ck",
        "outcome_metric_observation_dependency_fk",
        "outcome_metric_observation_fact_fk",
        "outcome_metric_observation_role_ck",
        "outcome_reason_shape_ck",
    }
    with psycopg.connect(target_database_url) as connection:
        constraints = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT item.conname, pg_get_constraintdef(item.oid, true)
                FROM pg_constraint AS item
                JOIN pg_namespace AS namespace ON namespace.oid = item.connamespace
                WHERE namespace.nspname = 'mra'
                  AND item.conname = ANY(%s)
                """,
                (list(required),),
            ).fetchall()
        }
    assert set(constraints) == required
    assert "decision_reference_observation" in constraints[
        "market_target_outcome_reference_fk"
    ]
    assert "dependency_role = 'REFERENCE'" in constraints[
        "outcome_metric_reference_role_ck"
    ]
    assert "dependency_role = ANY (ARRAY['OBSERVATION'" in constraints[
        "outcome_metric_observation_role_ck"
    ]
    assert "bar_revision_id" in constraints["outcome_source_bar_fk"]
    assert "source_gap_id" in constraints["outcome_source_gap_fk"]
    assert "trading_session_id" in constraints["outcome_source_session_fk"]


def test_outcome_relations_are_append_only_and_revision_root_closes_children(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        triggers = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """
                SELECT event_object_table, trigger_name
                FROM information_schema.triggers
                WHERE trigger_schema = 'mra'
                  AND event_object_table = ANY(%s)
                """,
                (list(EXPECTED_OUTCOME_TABLES),),
            ).fetchall()
        }
    for table in EXPECTED_OUTCOME_TABLES:
        assert (table, f"{table}_append_only") in triggers
    assert {
        ("market_target_outcome_revision", "outcome_revision_predecessor_guard"),
        ("market_target_outcome_revision", "outcome_revision_closure_guard"),
        ("market_target_outcome_source", "outcome_source_open_guard"),
        ("market_target_outcome_observation", "outcome_observation_open_guard"),
        ("market_target_outcome_metric", "outcome_metric_open_guard"),
        (
            "market_target_outcome_metric_reference",
            "outcome_metric_reference_open_guard",
        ),
        (
            "market_target_outcome_metric_observation",
            "outcome_metric_observation_open_guard",
        ),
        ("market_target_outcome_reason", "outcome_reason_open_guard"),
    } <= triggers


def test_outcome_fk_and_replay_paths_have_leading_indexes(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    required = {
        "market_target_outcome_commitment_idx",
        "outcome_revision_leaf_idx",
        "outcome_revision_request_idx",
        "outcome_revision_runtime_idx",
        "outcome_source_revision_idx",
        "outcome_source_bar_idx",
        "outcome_source_gap_idx",
        "outcome_source_session_idx",
        "outcome_observation_revision_idx",
        "outcome_observation_source_idx",
        "outcome_metric_revision_idx",
        "outcome_metric_definition_idx",
        "outcome_metric_reference_revision_idx",
        "outcome_metric_reference_observation_idx",
        "outcome_metric_observation_revision_idx",
        "outcome_metric_observation_fact_idx",
        "outcome_reason_revision_idx",
    }
    with psycopg.connect(target_database_url) as connection:
        indexes = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'mra'
                  AND tablename = ANY(%s)
                """,
                (list(EXPECTED_OUTCOME_TABLES),),
            ).fetchall()
        }
    assert required <= indexes
