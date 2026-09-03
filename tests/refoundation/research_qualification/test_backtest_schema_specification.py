from __future__ import annotations

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_EXPLORATORY_BACKTEST_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


CURRENT_SPECIFICATION_TABLES = {
    "backtest_specification",
    "backtest_sample_member",
    "backtest_arm_specification",
    "backtest_fold_dependency",
    "backtest_arm_fold",
    "backtest_model_training_requirement",
    "backtest_evaluation_requirement",
}


def test_current_backtest_specification_is_one_relational_root_owned_closure(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()

    assert CURRENT_SPECIFICATION_TABLES <= EXPECTED_EXPLORATORY_BACKTEST_TABLES
    assert CURRENT_SPECIFICATION_TABLES <= EXPECTED_TARGET_TABLES
    with psycopg.connect(target_database_url) as connection:
        columns = connection.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'mra' AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (sorted(CURRENT_SPECIFICATION_TABLES),),
        ).fetchall()
        constraints = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT conname
                FROM pg_constraint AS item
                JOIN pg_namespace AS namespace ON namespace.oid = item.connamespace
                WHERE namespace.nspname = 'mra'
                  AND item.conname = ANY(%s)
                """,
                (
                    [
                        "backtest_specification_run_fk",
                        "backtest_run_current_specification_fk",
                        "backtest_specification_universe_fk",
                        "backtest_sample_member_universe_fk",
                        "backtest_arm_specification_arm_fk",
                        "backtest_arm_specification_owner_fk",
                        "backtest_fold_dependency_fit_fk",
                        "backtest_fold_dependency_validation_fk",
                        "backtest_model_requirement_model_fk",
                    ],
                ),
            ).fetchall()
        }

    assert columns
    assert not [row for row in columns if row[2] in {"json", "jsonb"}]
    assert constraints == {
        "backtest_specification_run_fk",
        "backtest_run_current_specification_fk",
        "backtest_specification_universe_fk",
        "backtest_sample_member_universe_fk",
        "backtest_arm_specification_arm_fk",
        "backtest_arm_specification_owner_fk",
        "backtest_fold_dependency_fit_fk",
        "backtest_fold_dependency_validation_fk",
        "backtest_model_requirement_model_fk",
    }
