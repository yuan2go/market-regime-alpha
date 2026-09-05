from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_MODEL_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


def test_model_authority_is_concrete_relational_and_append_only(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    assert EXPECTED_MODEL_TABLES == {
        "model",
        "model_feature_definition",
        "model_training_run",
        "model_training_sample",
        "model_training_dependency",
        "model_training_hyperparameter",
        "model_training_reproducibility",
        "model_version",
    }
    assert EXPECTED_MODEL_TABLES <= EXPECTED_TARGET_TABLES
    with psycopg.connect(target_database_url) as connection:
        columns = connection.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'mra' AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (sorted(EXPECTED_MODEL_TABLES),),
        ).fetchall()
        constraints = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT conname FROM pg_constraint AS item
                JOIN pg_namespace AS namespace
                  ON namespace.oid = item.connamespace
                WHERE namespace.nspname = 'mra'
                  AND item.conname = ANY(%s)
                """,
                (
                    [
                        "model_target_fk",
                        "model_feature_definition_fk",
                        "model_training_evaluation_fk",
                        "model_training_protocol_metric_fk",
                        "model_training_backtest_arm_fk",
                        "model_training_backtest_fold_fk",
                        "model_training_sample_observation_fk",
                        "model_training_sample_metric_observation_fk",
                        "model_training_sample_dataset_fk",
                        "model_version_training_fk",
                        "model_version_fitted_artifact_fk",
                        "model_training_reproducibility_run_fk",
                        "model_training_dependency_owner_fk",
                        "model_training_hyperparameter_owner_fk",
                    ],
                ),
            ).fetchall()
        }
        triggers = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT trigger_name FROM information_schema.triggers
                WHERE trigger_schema = 'mra'
                  AND event_object_table = ANY(%s)
                """,
                (sorted(EXPECTED_MODEL_TABLES),),
            ).fetchall()
        }

    assert columns
    assert not [row for row in columns if row[2] in {"json", "jsonb"}]
    assert constraints == {
        "model_target_fk",
        "model_feature_definition_fk",
        "model_training_evaluation_fk",
        "model_training_protocol_metric_fk",
        "model_training_backtest_arm_fk",
        "model_training_backtest_fold_fk",
        "model_training_sample_observation_fk",
        "model_training_sample_metric_observation_fk",
        "model_training_sample_dataset_fk",
        "model_version_training_fk",
        "model_version_fitted_artifact_fk",
        "model_training_reproducibility_run_fk",
        "model_training_dependency_owner_fk",
        "model_training_hyperparameter_owner_fk",
    }
    assert {
        "model_reconcile_guard",
        "model_training_run_reconcile_guard",
        "model_version_guard",
        "model_append_only",
        "model_feature_definition_append_only",
        "model_training_run_append_only",
        "model_training_sample_append_only",
        "model_version_append_only",
        "model_training_reproducibility_reconcile_guard",
        "model_training_reproducibility_append_only",
        "model_training_dependency_append_only",
        "model_training_hyperparameter_append_only",
    } <= triggers


def test_model_training_samples_expose_no_performance_or_generic_subject_fields(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        names = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'mra'
                  AND table_name = 'model_training_sample'
                """
            ).fetchall()
        }
    assert {
        "evaluation_observation_id",
        "evaluation_metric_observation_id",
        "research_partition_member_id",
        "commitment_id",
        "dataset_id",
        "market_target_outcome_revision_id",
        "source_outcome_metric_id",
        "sample_state",
    } <= names
    assert not ({"performance", "subject", "subject_id", "subject_kind"} & names)
