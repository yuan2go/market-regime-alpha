from __future__ import annotations

from pathlib import Path

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_RESEARCH_QUALIFICATION_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql"


def test_wp12_authority_remains_exactly_ten_relational_tables() -> None:
    assert EXPECTED_RESEARCH_QUALIFICATION_TABLES == {
        "evidence_item",
        "evidence_dependency",
        "research_assessment",
        "research_assessment_evaluation",
        "research_assessment_evidence",
        "research_qualification_policy",
        "research_qualification_policy_floor",
        "research_qualification_decision",
        "research_qualification_floor_result",
        "research_qualification_floor_evidence",
    }
    assert EXPECTED_RESEARCH_QUALIFICATION_TABLES <= EXPECTED_TARGET_TABLES


def test_wp12_uses_only_unreleased_baseline_and_no_generic_subject() -> None:
    migrations = sorted(item.name for item in BASELINE.parent.glob("*.sql"))
    assert migrations == ["001_baseline.sql"]
    sql = BASELINE.read_text()
    for table in EXPECTED_RESEARCH_QUALIFICATION_TABLES:
        assert f"CREATE TABLE mra.{table}" in sql
    assert "subject_kind" not in sql
    assert "subject_id" not in sql
    assert "business_payload json" not in sql
    for table in ("model", "model_version"):
        assert f"CREATE TABLE mra.{table}" not in sql


def test_wp12_rosters_and_supersession_are_database_closed() -> None:
    sql = BASELINE.read_text()
    required = {
        "validate_evidence_item_closure",
        "validate_research_assessment_closure",
        "validate_research_qualification_policy_closure",
        "validate_research_qualification_decision_closure",
        "guard_evidence_dependency_insert",
        "guard_research_assessment_insert",
        "guard_research_qualification_decision_insert",
        "evidence_dependency_child_fk",
        "research_assessment_evaluation_assessment_fk",
        "research_qualification_floor_result_decision_fk",
        "DEFERRABLE INITIALLY DEFERRED",
    }
    assert all(item in sql for item in required)


def test_wp12_concrete_fk_and_trigger_catalog(target_database_url: str) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        columns = connection.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'mra' AND table_name = ANY(%s)
            """,
            (sorted(EXPECTED_RESEARCH_QUALIFICATION_TABLES),),
        ).fetchall()
        assert not [row for row in columns if row[2] in {"json", "jsonb"}]
        assert not [row for row in columns if row[1] in {"subject_kind", "subject_id"}]
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
                        "evidence_item_evaluation_fk",
                        "evidence_item_metric_fk",
                        "evidence_dependency_parent_fk",
                        "research_assessment_experiment_fk",
                        "research_assessment_evaluation_run_fk",
                        "research_assessment_evidence_item_fk",
                        "research_qualification_policy_target_fk",
                        "research_qualification_policy_floor_metric_fk",
                        "research_qualification_decision_assessment_fk",
                        "research_qualification_decision_policy_fk",
                        "research_qualification_floor_result_floor_fk",
                        "research_qualification_floor_evidence_assessment_fk",
                    ],
                ),
            ).fetchall()
        }
        assert len(constraints) == 12
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
                (sorted(EXPECTED_RESEARCH_QUALIFICATION_TABLES),),
            ).fetchall()
        }
        assert {
            "evidence_item_closure_guard",
            "evidence_dependency_insert_guard",
            "research_assessment_closure_guard",
            "research_qualification_policy_closure_guard",
            "research_qualification_decision_closure_guard",
        } <= triggers


def test_wp12_all_foreign_keys_have_leading_indexes(target_database_url: str) -> None:
    SchemaManager(target_database_url).bootstrap()
    SchemaManager(target_database_url).verify()
