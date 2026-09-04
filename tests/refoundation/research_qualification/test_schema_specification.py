from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_CANDIDATE_TABLES,
    EXPECTED_EXPLORATORY_BACKTEST_TABLES,
    EXPECTED_MODEL_TABLES,
    EXPECTED_RESEARCH_DEFINITION_TABLES,
    EXPECTED_RESEARCH_QUALIFICATION_TABLES,
    EXPECTED_RESEARCH_VALIDITY_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


def test_research_and_qualification_schema_has_exact_owned_relations(
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
    assert EXPECTED_RESEARCH_DEFINITION_TABLES == {
        "dataset",
        "dataset_source",
        "feature_definition",
        "formal_research_dataset",
        "exploratory_retrospective_dataset",
    }
    assert EXPECTED_RESEARCH_DEFINITION_TABLES <= tables
    assert EXPECTED_RESEARCH_VALIDITY_TABLES <= tables
    assert EXPECTED_RESEARCH_QUALIFICATION_TABLES <= tables
    assert EXPECTED_EXPLORATORY_BACKTEST_TABLES == {
        "backtest_arm_fold",
        "backtest_arm_specification",
        "backtest_evaluation_requirement",
        "backtest_fold_dependency",
        "backtest_model_training_requirement",
        "backtest_sample_member",
        "backtest_specification",
        "exploratory_backtest_run",
        "exploratory_backtest_feature",
        "exploratory_backtest_arm",
        "exploratory_backtest_arm_strategy",
        "exploratory_backtest_fold",
        "exploratory_backtest_fold_session",
        "exploratory_backtest_cost_assumption",
        "exploratory_backtest_dataset",
    }
    assert EXPECTED_EXPLORATORY_BACKTEST_TABLES <= tables
    assert tables == EXPECTED_TARGET_TABLES
    assert {
        name for name in tables if name.startswith("candidate")
    } == EXPECTED_CANDIDATE_TABLES
    assert {name for name in tables if name.startswith("model")} == EXPECTED_MODEL_TABLES


def test_research_definition_identity_population_and_role_shape_are_declarative(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    expected = {
        "feature_definition_identity_uk",
        "feature_definition_content_uk",
        "feature_definition_code_artifact_fk",
        "feature_definition_config_artifact_fk",
        "feature_definition_sources_ck",
        "dataset_identity_uk",
        "dataset_content_uk",
        "dataset_kind_ck",
        "dataset_counts_ck",
        "dataset_universe_decision_fk",
        "dataset_manifest_artifact_fk",
        "dataset_code_artifact_fk",
        "dataset_config_artifact_fk",
        "dataset_source_role_ck",
        "dataset_source_shape_ck",
        "dataset_source_dataset_scope_fk",
        "dataset_source_population_member_fk",
        "dataset_source_population_assessment_fk",
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
                (list(expected),),
            ).fetchall()
        }
    assert set(constraints) == expected
    assert "dataset_kind = 'DECISION_INPUT'::text" in constraints["dataset_kind_ck"]
    assert "cell_count = (row_count * feature_count)" in constraints["dataset_counts_ck"]
    assert "membership_status = 'INCLUDED'::text" in constraints["dataset_source_shape_ck"]
    assert "eligibility_result = 'ELIGIBLE'::text" in constraints["dataset_source_shape_ck"]
    assert "universe_member_id, universe_revision_id, instrument_id, membership_status" in constraints[
        "dataset_source_population_member_fk"
    ]
    assert "eligibility_assessment_id, universe_member_id, universe_revision_id" in constraints[
        "dataset_source_population_assessment_fk"
    ]


def test_dataset_source_has_only_closed_real_fk_roles_and_required_indexes(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        columns = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'mra'
                  AND table_name = 'dataset_source'
                """
            ).fetchall()
        }
        indexes = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'mra'
                  AND tablename IN ('dataset', 'dataset_source', 'feature_definition')
                """
            ).fetchall()
        }
        triggers = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """
                SELECT event_object_table, action_statement
                FROM information_schema.triggers
                WHERE trigger_schema = 'mra'
                  AND event_object_table = ANY(%s)
                """,
                (list(EXPECTED_RESEARCH_DEFINITION_TABLES),),
            ).fetchall()
        }
    assert not {"source_type", "source_id", "business_lineage", "lineage"} & set(columns)
    assert "jsonb" not in columns.values()
    assert {
        "dataset_decision_scope_idx",
        "dataset_source_dataset_role_idx",
        "dataset_source_population_uk",
        "dataset_source_feature_uk",
        "dataset_source_market_bar_idx",
        "dataset_source_market_bar_uk",
        "dataset_source_instrument_fact_idx",
        "dataset_source_instrument_fact_uk",
        "dataset_source_session_idx",
        "dataset_source_session_uk",
        "dataset_source_gap_idx",
        "dataset_source_gap_uk",
        "dataset_source_capture_idx",
        "dataset_source_capture_uk",
        "feature_definition_code_artifact_idx",
        "feature_definition_config_artifact_idx",
    } <= set(indexes)
    assert {table for table, _ in triggers} == EXPECTED_RESEARCH_DEFINITION_TABLES
    assert all(
        any(
            trigger_table == table
            and "reject_append_only_mutation" in statement
            for trigger_table, statement in triggers
        )
        for table in EXPECTED_RESEARCH_DEFINITION_TABLES
    )
