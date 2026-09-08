from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_TARGET_DEFINITION_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


def test_target_definition_schema_adds_exactly_four_normalized_relations(
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
                (list(EXPECTED_TARGET_DEFINITION_TABLES),),
            ).fetchall()
        }
    assert EXPECTED_TARGET_DEFINITION_TABLES == {
        "target_definition",
        "target_checkpoint",
        "target_metric_definition",
        "target_metric_dependency",
    }
    assert tables == EXPECTED_TARGET_TABLES
    assert EXPECTED_TARGET_DEFINITION_TABLES <= tables
    assert not {
        name
        for table, name, _ in columns
        if table in EXPECTED_TARGET_DEFINITION_TABLES
        and name in {"provider_id", "provider_product_id", "receipt_id"}
    }
    assert not {data_type for _, _, data_type in columns if data_type == "jsonb"}


def test_target_definition_relational_closure_and_supersession_are_database_enforced(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    required_constraints = {
        "target_definition_identity_uk",
        "target_definition_content_uk",
        "target_definition_supersedes_uk",
        "target_definition_version_chain_ck",
        "target_definition_counts_ck",
        "target_checkpoint_definition_fk",
        "target_checkpoint_ordinal_uk",
        "target_checkpoint_code_uk",
        "target_checkpoint_role_horizon_ck",
        "target_metric_definition_fk",
        "target_metric_ordinal_uk",
        "target_metric_code_uk",
        "target_metric_barrier_shape_ck",
        "target_metric_dependency_definition_fk",
        "target_metric_dependency_metric_fk",
        "target_metric_dependency_checkpoint_fk",
        "target_metric_dependency_ordinal_uk",
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
                (list(EXPECTED_TARGET_DEFINITION_TABLES),),
            ).fetchall()
        }
    assert set(constraints) == required_constraints
    assert "DEFERRABLE INITIALLY DEFERRED" in constraints[
        "target_checkpoint_definition_fk"
    ]
    assert "target_metric_definition_id, target_definition_id" in constraints[
        "target_metric_dependency_metric_fk"
    ]
    assert "target_checkpoint_id, target_definition_id" in constraints[
        "target_metric_dependency_checkpoint_fk"
    ]
    trigger_names = {name for _, name, _ in triggers}
    assert {
        "target_definition_append_only",
        "target_checkpoint_append_only",
        "target_metric_definition_append_only",
        "target_metric_dependency_append_only",
        "target_checkpoint_open_guard",
        "target_metric_open_guard",
        "target_metric_dependency_open_guard",
        "target_definition_closure_guard",
    } <= trigger_names
    assert any(
        "validate_target_definition_closure" in statement
        for _, name, statement in triggers
        if name == "target_definition_closure_guard"
    )


def test_target_closure_enforces_outcome_metric_parity_and_a_required_metric(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        definition = connection.execute(
            """
            SELECT pg_get_functiondef(
                'mra.validate_target_definition_closure()'::regprocedure
            )
            """
        ).fetchone()
    assert definition is not None
    function_sql = str(definition[0])
    assert "required_metric_count" in function_sql
    assert "completion_rule = 'REQUIRED'" in function_sql
    for metric_kind in (
        "SIMPLE_RETURN",
        "OBSERVATION_VALUE",
        "MAX_FAVORABLE_EXCURSION",
        "MAX_ADVERSE_EXCURSION",
        "BARRIER_HIT",
    ):
        assert metric_kind in function_sql
    assert "dependency.dependency_role = 'PATH_MEMBER'" in function_sql
    assert "checkpoint.checkpoint_role <> 'DECISION_REFERENCE'" in function_sql
    assert "checkpoint.checkpoint_role <> 'OUTCOME_OBSERVATION'" in function_sql


def test_target_definition_has_fk_and_replay_indexes(
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
                (list(EXPECTED_TARGET_DEFINITION_TABLES),),
            ).fetchall()
        }
    assert {
        "target_definition_code_version_idx",
        "target_definition_supersedes_idx",
        "target_definition_code_artifact_idx",
        "target_definition_config_artifact_idx",
        "target_checkpoint_definition_idx",
        "target_metric_definition_target_idx",
        "target_metric_code_artifact_idx",
        "target_metric_config_artifact_idx",
        "target_metric_dependency_target_idx",
        "target_metric_dependency_metric_idx",
        "target_metric_dependency_checkpoint_idx",
    } <= set(indexes)
