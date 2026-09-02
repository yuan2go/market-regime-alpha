from __future__ import annotations

from pathlib import Path

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_OPPORTUNITY_TABLES,
    EXPECTED_PORTFOLIO_TABLES,
    EXPECTED_RISK_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql"


def test_remaining_decision_support_is_twelve_relational_tables() -> None:
    assert EXPECTED_OPPORTUNITY_TABLES == {
        "opportunity_set", "opportunity", "opportunity_context",
        "thesis", "thesis_condition",
    }
    assert EXPECTED_PORTFOLIO_TABLES == {
        "portfolio_policy", "portfolio_proposal", "portfolio_line",
    }
    assert EXPECTED_RISK_TABLES == {
        "risk_policy", "risk_rule", "risk_decision", "risk_reason",
    }
    tables = EXPECTED_OPPORTUNITY_TABLES | EXPECTED_PORTFOLIO_TABLES | EXPECTED_RISK_TABLES
    assert tables <= EXPECTED_TARGET_TABLES
    sql = BASELINE.read_text()
    for table in tables:
        assert f"CREATE TABLE mra.{table}" in sql
    assert "execution_authorized" not in sql
    assert "broker" not in "\n".join(
        line for line in sql.splitlines() if "CREATE TABLE mra.risk" in line
    )


def test_remaining_decision_support_has_concrete_fk_and_no_json_authority(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    tables = sorted(EXPECTED_OPPORTUNITY_TABLES | EXPECTED_PORTFOLIO_TABLES | EXPECTED_RISK_TABLES)
    expected_constraints = {
        "opportunity_set_forecast_fk", "opportunity_forecast_fk",
        "opportunity_commitment_fk", "opportunity_context_binding_fk",
        "thesis_opportunity_fk", "thesis_condition_thesis_fk",
        "portfolio_proposal_opportunity_set_fk", "portfolio_line_opportunity_fk",
        "risk_rule_policy_fk", "risk_decision_proposal_fk",
        "risk_reason_rule_fk", "risk_reason_line_fk",
    }
    with psycopg.connect(target_database_url) as connection:
        columns = connection.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'mra' AND table_name = ANY(%s)
            """,
            (tables,),
        ).fetchall()
        constraints = {
            str(row[0]) for row in connection.execute(
                "SELECT conname FROM pg_constraint "
                "WHERE connamespace = 'mra'::regnamespace AND conname = ANY(%s)",
                (list(expected_constraints),),
            ).fetchall()
        }
    assert not [row for row in columns if row[2] in {"json", "jsonb"}]
    assert constraints == expected_constraints
    SchemaManager(target_database_url).verify()
