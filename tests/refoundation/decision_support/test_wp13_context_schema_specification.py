from __future__ import annotations

from pathlib import Path

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_CONTEXT_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql"


def test_context_adds_exactly_five_relational_authority_tables() -> None:
    assert EXPECTED_CONTEXT_TABLES == {
        "context_policy",
        "context_policy_metric",
        "context_assessment",
        "context_metric",
        "context_metric_source",
    }
    assert EXPECTED_CONTEXT_TABLES <= EXPECTED_TARGET_TABLES
    sql = BASELINE.read_text()
    for table in EXPECTED_CONTEXT_TABLES:
        assert f"CREATE TABLE mra.{table}" in sql
    assert "context_payload" not in sql
    assert "context_subject_kind" not in sql


def test_context_catalog_has_exact_lineage_closure_and_leading_indexes(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        columns = connection.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'mra' AND table_name = ANY(%s)
            """,
            (sorted(EXPECTED_CONTEXT_TABLES),),
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
                        "context_policy_metric_policy_fk",
                        "context_policy_supersedes_fk",
                        "context_assessment_run_fk",
                        "context_assessment_policy_fk",
                        "context_metric_assessment_fk",
                        "context_metric_definition_fk",
                        "context_metric_source_metric_fk",
                        "context_metric_source_reference_fk",
                        "context_metric_source_bar_fk",
                        "context_metric_source_gap_fk",
                    ],
                ),
            ).fetchall()
        }
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
                (sorted(EXPECTED_CONTEXT_TABLES),),
            ).fetchall()
        }
    assert not [row for row in columns if row[2] in {"json", "jsonb"}]
    assert len(constraints) == 10
    assert {
        "context_policy_closure_guard",
        "context_assessment_closure_guard",
        "context_policy_append_only",
        "context_policy_metric_append_only",
        "context_assessment_append_only",
        "context_metric_append_only",
        "context_metric_source_append_only",
    } <= triggers
    SchemaManager(target_database_url).verify()
