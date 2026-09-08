from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_EXPLORATORY_EVALUATION_SOURCE_TABLES,
    SchemaManager,
)


def test_exploratory_evaluation_sources_are_typed_relational_children(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'mra'
                  AND table_name = ANY(%s)
                """,
                (sorted(EXPECTED_EXPLORATORY_EVALUATION_SOURCE_TABLES),),
            ).fetchall()
        }
        assert tables == EXPECTED_EXPLORATORY_EVALUATION_SOURCE_TABLES
        generic_columns = connection.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'mra'
              AND table_name = ANY(%s)
              AND (data_type IN ('json', 'jsonb')
                   OR column_name IN ('subject', 'subject_id', 'subject_kind'))
            """,
            (sorted(EXPECTED_EXPLORATORY_EVALUATION_SOURCE_TABLES),),
        ).fetchall()
        assert generic_columns == []


def test_every_canonical_source_has_concrete_foreign_keys_and_append_only_guard(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        foreign_keys = {
            row[0]
            for row in connection.execute(
                """
                SELECT conname
                FROM pg_constraint
                WHERE connamespace = 'mra'::regnamespace
                  AND contype = 'f'
                  AND conrelid IN (
                      SELECT oid FROM pg_class
                      WHERE relnamespace = 'mra'::regnamespace
                        AND relname = ANY(%s)
                  )
                """,
                (sorted(EXPECTED_EXPLORATORY_EVALUATION_SOURCE_TABLES),),
            ).fetchall()
        }
        assert {
            "evaluation_backtest_input_fk",
            "evaluation_backtest_decision_fk",
            "evaluation_candidate_input_fk",
            "evaluation_candidate_outcome_input_fk",
            "evaluation_signal_input_fk",
            "evaluation_forecast_input_fk",
            "evaluation_portfolio_input_fk",
            "evaluation_portfolio_cost_fact_fk",
            "evaluation_risk_input_fk",
        } <= foreign_keys
        triggers = {
            row[0]
            for row in connection.execute(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid IN (
                    SELECT oid FROM pg_class
                    WHERE relnamespace = 'mra'::regnamespace
                      AND relname = ANY(%s)
                ) AND NOT tgisinternal
                """,
                (sorted(EXPECTED_EXPLORATORY_EVALUATION_SOURCE_TABLES),),
            ).fetchall()
        }
        for table in EXPECTED_EXPLORATORY_EVALUATION_SOURCE_TABLES:
            assert f"{table}_append_only" in triggers


def test_protocol_freezes_reducer_source_and_arm_compatibility_in_postgres(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        columns = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'mra'
                  AND table_name = 'evaluation_protocol_metric'
                  AND column_name IN (
                      'source_kind', 'source_measure', 'backtest_arm_kind'
                  )
                """
            ).fetchall()
        }
        assert columns == {
            "source_kind": "NO",
            "source_measure": "NO",
            "backtest_arm_kind": "YES",
        }
        definition = connection.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE connamespace = 'mra'::regnamespace
              AND conname = 'evaluation_protocol_metric_shape_ck'
            """
        ).fetchone()
        assert definition is not None
        contract = str(definition[0])
        assert "SPEARMAN_RANK_CORRELATION" in contract
        assert "MAX_DRAWDOWN" in contract
        assert "TOP_BOTTOM_SPREAD" in contract
        assert "CANDIDATE_OUTCOME_PAIR" in contract
        assert "EXPLORATORY_BACKTEST_ARM" in contract
        assert "NET_PORTFOLIO_RETURN_ASSUMED_COST" in contract
        source_type_guard = connection.execute(
            """
            SELECT pg_get_functiondef(
                'mra.validate_evaluation_protocol_metric_source_type()'::regprocedure
            )
            """
        ).fetchone()
        assert source_type_guard is not None
        assert "Outcome Evaluation source type" in str(source_type_guard[0])


def test_completed_run_guard_requires_complete_typed_source_rosters(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        definition = connection.execute(
            """
            SELECT pg_get_functiondef('mra.guard_evaluation_run_transition()'::regprocedure)
            """
        ).fetchone()
        assert definition is not None
        guard = str(definition[0])
        for table in EXPECTED_EXPLORATORY_EVALUATION_SOURCE_TABLES - {
            "evaluation_portfolio_cost_source"
        }:
            assert table in guard
        assert "Evaluation canonical source roster does not reconcile" in guard
        assert "Evaluation assumed-cost source roster does not reconcile" in guard
