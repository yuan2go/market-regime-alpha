from __future__ import annotations

import pytest

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


@pytest.mark.unmigrated_postgres
def test_phase_ii_migration_is_forward_only_idempotent_and_extends_existing_evidence(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrator = PostgresMigrator()

    first = migrator.apply_all(postgres_factory)
    second = migrator.apply_all(postgres_factory)

    assert first[-1].version == 106
    assert first[-1].name == "alpha_correctness_failure_revision"
    assert second == ()
    with postgres_factory.connection(read_only=True) as connection:
        latest = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()
        phase_ii_and_closure = connection.execute(
            "SELECT version, name FROM schema_migrations WHERE version >= 91 ORDER BY version"
        ).fetchall()
        constraint = connection.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'historical_research_evidence_evidence_kind_check'
              AND conrelid = 'historical_research_evidence'::regclass
            """
        ).fetchone()

        forecast_constraint = connection.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'strategy_contract_forecast_semantics_check'
              AND conrelid = 'strategy_contract'::regclass
            """
        ).fetchone()

    assert latest == (106, "alpha_correctness_failure_revision")
    assert phase_ii_and_closure == [
        (91, "alpha_research_phase_ii"),
        (92, "strategy_forecast_contract_semantics"),
        (93, "frozen_temporal_validation_window"),
        (94, "pre_strategy_risk_opportunity"),
        (95, "daily_alpha_continuous_projection"),
        (96, "daily_alpha_outcome_lineage"),
        (97, "daily_alpha_target_session"),
        (98, "wp_alpha_proof_locked_scope"),
        (99, "historical_fact_membership_index"),
        (100, "historical_fact_guard_fk_indexes"),
        (101, "locked_oos_typed_calendar_owner"),
        (102, "historical_component_physical_payload"),
        (103, "historical_outcome_forecast_index"),
        (104, "historical_outcome_forecast_fk_index"),
        (105, "alpha_correctness_target_semantics"),
        (106, "alpha_correctness_failure_revision"),
    ]
    assert constraint is not None
    definition = str(constraint[0])
    for value in (
        "ALPHA_CORRECTNESS",
        "EXTERNAL_VALIDATION",
        "CONTEXT_CONDITIONAL",
        "CANDIDATE_POLICY",
        "CONDITIONAL_PREDICTION",
    ):
        assert value in definition
    assert forecast_constraint is not None
    forecast_definition = str(forecast_constraint[0])
    assert "CONDITIONAL_PREDICTION" in forecast_definition
    assert "FORECAST_REQUIRED" in forecast_definition
