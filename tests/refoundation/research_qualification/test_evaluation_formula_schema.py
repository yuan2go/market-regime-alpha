from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import SchemaManager


_TABLES = {"evaluation_metric_formula", "evaluation_formula_parameter"}


def test_formula_closure_is_typed_relational_and_append_only(
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
                WHERE table_schema = 'mra' AND table_name = ANY(%s)
                """,
                (sorted(_TABLES),),
            ).fetchall()
        }
        assert tables == _TABLES
        generic_columns = connection.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'mra' AND table_name = ANY(%s)
              AND data_type IN ('json', 'jsonb')
            """,
            (sorted(_TABLES),),
        ).fetchall()
        assert generic_columns == []
        constraints = {
            row[0]
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
        assert {
            "evaluation_metric_formula_metric_fk",
            "evaluation_formula_parameter_owner_fk",
            "evaluation_formula_parameter_shape_ck",
        } <= constraints
        triggers = {
            row[0]
            for row in connection.execute(
                """
                SELECT tgname
                FROM pg_trigger
                WHERE tgrelid IN (
                    SELECT oid FROM pg_class
                    WHERE relnamespace = 'mra'::regnamespace
                      AND relname = ANY(%s)
                ) AND NOT tgisinternal
                """,
                (sorted(_TABLES),),
            ).fetchall()
        }
        assert {
            "evaluation_metric_formula_append_only",
            "evaluation_metric_formula_closure_guard",
            "evaluation_formula_parameter_append_only",
        } <= triggers


def test_current_backtest_validator_requires_formula_companions(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        row = connection.execute(
            """
            SELECT pg_get_functiondef(
                'mra.validate_current_backtest_specification()'::regprocedure
            )
            """
        ).fetchone()
    assert row is not None
    assert "Current Backtest Evaluation formula closure is incomplete" in str(row[0])
