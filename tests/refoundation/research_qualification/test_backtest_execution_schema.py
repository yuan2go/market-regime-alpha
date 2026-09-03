from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_EXPLORATORY_BACKTEST_TABLES,
    SchemaManager,
)


_TABLES = {
    "backtest_runtime_binding",
    "backtest_evaluation_execution",
    "backtest_model_lineage",
    "backtest_report_artifact",
}


def test_execution_relations_are_lineage_not_a_second_state_machine(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()

    assert _TABLES <= EXPECTED_EXPLORATORY_BACKTEST_TABLES
    with psycopg.connect(target_database_url) as connection:
        columns = connection.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'mra' AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (sorted(_TABLES),),
        ).fetchall()
        constraints = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT conname
                FROM pg_constraint
                WHERE connamespace = 'mra'::regnamespace
                  AND conrelid IN (
                    SELECT oid FROM pg_class
                    WHERE relnamespace = 'mra'::regnamespace
                      AND relname = ANY(%s)
                  )
                """,
                (sorted(_TABLES),),
            ).fetchall()
        }
        triggers = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid IN (
                    SELECT oid FROM pg_class
                    WHERE relnamespace = 'mra'::regnamespace
                      AND relname = ANY(%s)
                ) AND NOT tgisinternal
                """,
                (sorted(_TABLES),),
            ).fetchall()
        }

    assert columns
    assert not [row for row in columns if row[2] in {"json", "jsonb"}]
    assert not [row for row in columns if row[1] in {"state", "current_step"}]
    assert {
        "backtest_runtime_binding_runtime_fk",
        "backtest_runtime_binding_specification_fk",
        "backtest_evaluation_execution_requirement_fk",
        "backtest_evaluation_execution_run_fk",
        "backtest_model_lineage_requirement_fk",
        "backtest_model_lineage_evaluation_fk",
        "backtest_model_lineage_training_fk",
        "backtest_model_lineage_version_fk",
        "backtest_report_artifact_json_fk",
        "backtest_report_artifact_markdown_fk",
    } <= constraints
    assert {
        "backtest_runtime_binding_append_only",
        "backtest_evaluation_execution_append_only",
        "backtest_evaluation_execution_guard",
        "backtest_model_lineage_append_only",
        "backtest_model_lineage_guard",
        "backtest_report_artifact_append_only",
        "backtest_report_artifact_guard",
    } <= triggers


def test_research_partition_can_bind_exact_generic_backtest_decision_scope(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()

    with psycopg.connect(target_database_url) as connection:
        columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'mra'
                  AND table_name = 'research_partition'
                """
            ).fetchall()
        }
        constraints = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT conname FROM pg_constraint
                WHERE connamespace = 'mra'::regnamespace
                  AND conrelid = 'mra.research_partition'::regclass
                """
            ).fetchall()
        }

    assert {
        "source_backtest_run_id",
        "source_backtest_arm_id",
        "source_backtest_fold_id",
        "source_backtest_sha256",
    } <= columns
    assert {
        "research_partition_backtest_run_fk",
        "research_partition_backtest_arm_fk",
        "research_partition_backtest_fold_fk",
    } <= constraints


def test_runtime_step_catalog_contains_generic_evaluation_and_model_owner_steps(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()

    with psycopg.connect(target_database_url) as connection:
        row = connection.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE connamespace = 'mra'::regnamespace
              AND conname = 'runtime_step_kind_ck'
            """
        ).fetchone()

    assert row is not None
    for step_kind in (
        "FREEZE_PARTITION",
        "REGISTER_EXPERIMENT",
        "OPEN_EXPERIMENT_RUN",
        "OPEN_EVALUATION",
        "OPEN_MODEL_TRAINING_RUN",
        "REGISTER_MODEL_VERSION",
    ):
        assert step_kind in str(row[0])
