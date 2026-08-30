from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_CANDIDATE_TABLES,
    SchemaManager,
)


def test_candidate_schema_adds_exactly_five_selection_authority_tables(
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

    assert EXPECTED_CANDIDATE_TABLES == {
        "candidate_policy",
        "candidate_policy_component",
        "candidate_set",
        "candidate",
        "candidate_score_component",
    }
    assert EXPECTED_CANDIDATE_TABLES <= tables
    assert not {
        name
        for name in tables
        if name.startswith(
            (
                "model",
                "target",
                "evaluation",
                "evidence",
                "qualification",
                "decision",
                "outcome",
            )
        )
    }


def test_candidate_policy_has_only_declared_weight_and_real_feature_binding(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        columns = {
            (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in connection.execute(
                """
                SELECT table_name, column_name, data_type, udt_name
                FROM information_schema.columns
                WHERE table_schema = 'mra'
                  AND table_name = ANY(%s)
                """,
                (["candidate_policy", "candidate_policy_component"],),
            ).fetchall()
        }
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
                (
                    [
                        "candidate_policy_identity_uk",
                        "candidate_policy_content_uk",
                        "candidate_policy_shape_ck",
                        "candidate_policy_code_artifact_fk",
                        "candidate_policy_config_artifact_fk",
                        "candidate_policy_component_identity_uk",
                        "candidate_policy_component_ordinal_uk",
                        "candidate_policy_component_feature_uk",
                        "candidate_policy_component_feature_fk",
                        "candidate_policy_component_shape_ck",
                    ],
                ),
            ).fetchall()
        }

    component_names = {
        name
        for table, name, _, _ in columns
        if table == "candidate_policy_component"
    }
    assert (
        "candidate_policy_component",
        "declared_weight",
        "numeric",
        "numeric",
    ) in columns
    assert "normalized_weight" not in component_names
    assert not {
        "dataset_id",
        "dataset_source_id",
        "model_version_id",
        "target_id",
        "evidence_id",
        "qualification_id",
    } & component_names
    assert set(constraints) == {
        "candidate_policy_identity_uk",
        "candidate_policy_content_uk",
        "candidate_policy_shape_ck",
        "candidate_policy_code_artifact_fk",
        "candidate_policy_config_artifact_fk",
        "candidate_policy_component_identity_uk",
        "candidate_policy_component_ordinal_uk",
        "candidate_policy_component_feature_uk",
        "candidate_policy_component_feature_fk",
        "candidate_policy_component_shape_ck",
    }
    assert "declared_weight > 0::numeric" in constraints[
        "candidate_policy_component_shape_ck"
    ]
    assert "declared_weight < 'Infinity'::numeric" in constraints[
        "candidate_policy_component_shape_ck"
    ]
    assert "decimal_projection_version = 1" in constraints[
        "candidate_policy_shape_ck"
    ]
    assert "feature_value_type = ANY (ARRAY['DECIMAL'::text, 'INTEGER'::text])" in constraints[
        "candidate_policy_component_shape_ck"
    ]


def test_candidate_set_funnel_and_boundary_shape_are_declarative(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    expected = {
        "candidate_set_identity_uk",
        "candidate_set_policy_fk",
        "candidate_set_dataset_fk",
        "candidate_set_counts_ck",
        "candidate_set_component_counts_ck",
        "candidate_set_ranking_ck",
        "candidate_set_boundary_ck",
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
    assert "population_count = (rankable_count + unrankable_count)" in constraints[
        "candidate_set_counts_ck"
    ]
    assert "rankable_count = (selected_count + ranked_not_selected_count)" in constraints[
        "candidate_set_counts_ck"
    ]
    assert "score_component_count = (population_count::bigint * component_count::bigint)" in constraints[
        "candidate_set_counts_ck"
    ]
    assert "available_component_count + constant_component_count" in constraints[
        "candidate_set_component_counts_ck"
    ]
    assert "ranking_status = 'NOT_ESTIMABLE'::text" in constraints[
        "candidate_set_ranking_ck"
    ]
    assert "boundary_rank = (strictly_above_boundary_count + 1)" in constraints[
        "candidate_set_boundary_ck"
    ]
    assert "selected_overflow_count" in constraints["candidate_set_boundary_ck"]


def test_candidate_and_score_matrix_enforce_typed_complete_case_without_unique_rank(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    expected = {
        "candidate_identity_uk",
        "candidate_population_source_uk",
        "candidate_set_scope_fk",
        "candidate_population_source_fk",
        "candidate_disposition_ck",
        "candidate_reason_ck",
        "candidate_score_component_identity_uk",
        "candidate_score_component_candidate_fk",
        "candidate_score_component_policy_component_fk",
        "candidate_score_component_dataset_feature_fk",
        "candidate_score_component_raw_ck",
        "candidate_score_component_ranking_ck",
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
        indexes = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'mra'
                  AND tablename = ANY(%s)
                """,
                (list(EXPECTED_CANDIDATE_TABLES),),
            ).fetchall()
        }
        score_columns = {
            (str(row[0]), str(row[1]), str(row[2]))
            for row in connection.execute(
                """
                SELECT column_name, data_type, udt_name
                FROM information_schema.columns
                WHERE table_schema = 'mra'
                  AND table_name = 'candidate_score_component'
                """
            ).fetchall()
        }

    assert set(constraints) == expected
    assert "dataset_source_id, dataset_id, instrument_id, source_role" in constraints[
        "candidate_population_source_fk"
    ]
    assert "UNRANKABLE" in constraints["candidate_disposition_ck"]
    assert "raw_status = 'AVAILABLE'::text" in constraints[
        "candidate_score_component_raw_ck"
    ]
    assert "candidate_disposition = 'UNRANKABLE'::text" in constraints[
        "candidate_score_component_ranking_ck"
    ]
    assert {
        ("raw_decimal_value", "numeric", "numeric"),
        ("raw_integer_value", "numeric", "numeric"),
        ("normalized_weight", "numeric", "numeric"),
        ("percentile", "numeric", "numeric"),
        ("contribution", "numeric", "numeric"),
    } <= score_columns
    assert not any(
        data_type == "ARRAY" or udt_name.startswith("_")
        for _, data_type, udt_name in score_columns
    )
    raw_shape = constraints["candidate_score_component_raw_ck"]
    assert "raw_decimal_value > '-Infinity'::numeric" in raw_shape
    assert "raw_decimal_value < 'Infinity'::numeric" in raw_shape
    assert "scale(raw_decimal_value) <= 12" in raw_shape
    assert (
        "abs(raw_decimal_value) < '100000000000000000000000000'::numeric"
        in raw_shape
    )
    assert "raw_integer_value > '-Infinity'::numeric" in raw_shape
    assert "raw_integer_value < 'Infinity'::numeric" in raw_shape
    assert "candidate_set_rank_idx" in indexes
    assert "CREATE INDEX" in indexes["candidate_set_rank_idx"]
    assert "CREATE UNIQUE INDEX" not in indexes["candidate_set_rank_idx"]
    assert not any(
        "competition_rank" in definition and "CREATE UNIQUE INDEX" in definition
        for definition in indexes.values()
    )
    assert not any("USING gin" in definition for definition in indexes.values())
    assert "candidate_set_policy_dataset_idx" not in indexes
    assert "candidate_score_component_candidate_idx" not in indexes


def test_candidate_views_explain_funnel_component_status_and_complete_matrix(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        views = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT viewname, definition
                FROM pg_views
                WHERE schemaname = 'mra'
                  AND viewname = ANY(%s)
                """,
                (["candidate_funnel", "candidate_component_diagnostic"],),
            ).fetchall()
        }

    assert set(views) == {"candidate_funnel", "candidate_component_diagnostic"}
    diagnostic = views["candidate_component_diagnostic"]
    assert "raw_available_count" in diagnostic
    assert "observed_count" in diagnostic
    assert "distinct_count" in diagnostic
    assert "available_but_not_observed_count" in diagnostic
    assert "NOT_ESTIMABLE" in diagnostic
    assert "CONSTANT" in diagnostic
    funnel = views["candidate_funnel"]
    assert "actual_population_count" in funnel
    assert "actual_score_component_count" in funnel
    assert "population_reconciled" in funnel
    assert "rankable_reconciled" in funnel
    assert "score_matrix_reconciled" in funnel


def test_candidate_tables_reuse_only_generic_append_only_mutation_guard(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        triggers = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """
                SELECT event_object_table, action_statement
                FROM information_schema.triggers
                WHERE trigger_schema = 'mra'
                  AND event_object_table = ANY(%s)
                """,
                (list(EXPECTED_CANDIDATE_TABLES),),
            ).fetchall()
        }
        candidate_functions = connection.execute(
            """
            SELECT count(*)
            FROM information_schema.routines
            WHERE routine_schema = 'mra'
              AND routine_name LIKE 'candidate%'
            """
        ).fetchone()

    assert {table for table, _ in triggers} == EXPECTED_CANDIDATE_TABLES
    assert all(
        "reject_append_only_mutation" in statement for _, statement in triggers
    )
    assert candidate_functions == (0,)


def test_runtime_step_vocabulary_uses_closed_candidate_set_name(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        definition = connection.execute(
            """
            SELECT pg_get_constraintdef(constraint_item.oid, true)
            FROM pg_constraint AS constraint_item
            JOIN pg_namespace AS namespace
              ON namespace.oid = constraint_item.connamespace
            WHERE namespace.nspname = 'mra'
              AND constraint_item.conname = 'runtime_step_kind_ck'
            """
        ).fetchone()

    assert definition is not None
    assert "REGISTER_DATASET" in str(definition[0])
    assert "BUILD_CANDIDATE_SET" in str(definition[0])
    assert "BUILD_CANDIDATES" not in str(definition[0])
