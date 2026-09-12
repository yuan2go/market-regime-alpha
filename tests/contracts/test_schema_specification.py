from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_CANDIDATE_TABLES,
    EXPECTED_CONTEXT_TABLES,
    EXPECTED_DECISION_SUPPORT_TABLES,
    EXPECTED_EXPLORATORY_BACKTEST_TABLES,
    EXPECTED_EXPLORATORY_EVALUATION_SOURCE_TABLES,
    EXPECTED_FOUNDATION_TABLES,
    EXPECTED_MARKET_TABLES,
    EXPECTED_MODEL_TABLES,
    EXPECTED_OUTCOME_TABLES,
    EXPECTED_INFERENCE_TABLES,
    EXPECTED_OPPORTUNITY_TABLES,
    EXPECTED_PORTFOLIO_TABLES,
    EXPECTED_RESEARCH_DEFINITION_TABLES,
    EXPECTED_RESEARCH_QUALIFICATION_TABLES,
    EXPECTED_RESEARCH_VALIDITY_TABLES,
    EXPECTED_SELECTION_TABLES,
    EXPECTED_STRATEGY_TABLES,
    EXPECTED_TARGET_DEFINITION_TABLES,
    EXPECTED_TARGET_TABLES,
    EXPECTED_RISK_TABLES,
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
        | EXPECTED_DECISION_SUPPORT_TABLES
        | EXPECTED_CONTEXT_TABLES
        | EXPECTED_STRATEGY_TABLES
        | EXPECTED_INFERENCE_TABLES
        | EXPECTED_OPPORTUNITY_TABLES
        | EXPECTED_PORTFOLIO_TABLES
        | EXPECTED_RISK_TABLES
        | EXPECTED_OUTCOME_TABLES
        | EXPECTED_RESEARCH_VALIDITY_TABLES
        | EXPECTED_RESEARCH_QUALIFICATION_TABLES
        | EXPECTED_EXPLORATORY_EVALUATION_SOURCE_TABLES
        | EXPECTED_EXPLORATORY_BACKTEST_TABLES
        | EXPECTED_MODEL_TABLES
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
        migrations = connection.execute(
            "SELECT version, name, checksum FROM mra.schema_migrations ORDER BY version"
        ).fetchall()
    assert counts == (1, 8, 0, 0, 0, 0)
    assert migrations == [
        (1, "001_baseline", "f417b63cf3dc534b1a5d329c5a30462945bfeb6b8c4389bf8ab3a9e1f4efbd27"),
        (2, "002_prospective_revision_gap", "bd5978ae2ccfd56a9d117c41e13e0a8f7c76fbdd4d83d4aa1b32757dbe753063"),
        (3, "003_daily_model_research", "44d27a9f13d4045402b86a27f7c47150dfc67421a8fc071d8a691f0405480400"),
        (4, "004_daily_operational_closure", "903653a6bdc7abee9a37a43ff0442ef05aa5ea298a59bebeff5961699ac822aa"),
        (5, "005_static_research_universe", "5499f2137d268eb0eb4bd5ebe5301295240675319657e2e99f93f87f0ef8daf3"),
        (6, "006_historical_archive_inventory", "bd838d8ac883c4a2adb2883af14ae63ce67174beaee659dea21132dbbbaedeaa"),
        (7, "007_backtest_model_subsets", "af8de6bda7051916fa868d3a08139ccef7214d9dcf0540c29dc55f35d79a9334"),
        (8, "008_backtest_exploratory_holdout", "7b3fec55f3ad340dd65b462131d378693c9ab841fb09502e484ccce746958d87"),
    ]
