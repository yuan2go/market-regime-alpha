from __future__ import annotations

from pathlib import Path

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_INFERENCE_TABLES,
    EXPECTED_STRATEGY_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql"


def test_strategy_and_inference_are_nine_relational_authority_tables() -> None:
    assert EXPECTED_STRATEGY_TABLES == {
        "strategy",
        "strategy_version",
        "strategy_context_requirement",
        "strategy_signal_rule",
        "strategy_forecast_rule",
    }
    assert EXPECTED_INFERENCE_TABLES == {
        "signal",
        "signal_context_binding",
        "forecast",
        "forecast_estimate",
    }
    assert EXPECTED_STRATEGY_TABLES | EXPECTED_INFERENCE_TABLES <= (
        EXPECTED_TARGET_TABLES
    )
    sql = BASELINE.read_text()
    for table in EXPECTED_STRATEGY_TABLES | EXPECTED_INFERENCE_TABLES:
        assert f"CREATE TABLE mra.{table}" in sql
    assert "forecast_model_binding" not in sql
    assert "calibrated_probability" not in sql


def test_strategy_inference_catalog_has_concrete_fk_closure(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    names = sorted(EXPECTED_STRATEGY_TABLES | EXPECTED_INFERENCE_TABLES)
    with psycopg.connect(target_database_url) as connection:
        columns = connection.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'mra' AND table_name = ANY(%s)
            """,
            (names,),
        ).fetchall()
        constraints = {
            row[0]
            for row in connection.execute(
                """
                SELECT conname FROM pg_constraint
                WHERE connamespace = 'mra'::regnamespace
                  AND conname = ANY(%s)
                """,
                (
                    [
                        "strategy_version_strategy_fk",
                        "strategy_context_requirement_version_fk",
                        "strategy_signal_rule_version_fk",
                        "strategy_forecast_rule_target_fk",
                        "strategy_forecast_rule_checkpoint_fk",
                        "strategy_forecast_rule_metric_fk",
                        "signal_run_candidate_fk",
                        "signal_strategy_version_fk",
                        "signal_context_binding_signal_fk",
                        "signal_context_binding_assessment_fk",
                        "forecast_signal_fk",
                        "forecast_commitment_fk",
                        "forecast_estimate_forecast_fk",
                        "forecast_estimate_rule_fk",
                    ],
                ),
            ).fetchall()
        }
    assert not [row for row in columns if row[2] in {"json", "jsonb"}]
    assert len(constraints) == 14
    SchemaManager(target_database_url).verify()
