from __future__ import annotations

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


def test_phase_ii_migration_is_forward_only_idempotent_and_extends_existing_evidence(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrator = PostgresMigrator()

    first = migrator.apply_all(postgres_factory)
    second = migrator.apply_all(postgres_factory)

    assert first[-1].version == 91
    assert first[-1].name == "alpha_research_phase_ii"
    assert second == ()
    with postgres_factory.connection(read_only=True) as connection:
        latest = connection.execute(
            "SELECT max(version), max(name) FILTER (WHERE version = 91) FROM schema_migrations"
        ).fetchone()
        constraint = connection.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'historical_research_evidence_evidence_kind_check'
            """
        ).fetchone()

    assert latest == (91, "alpha_research_phase_ii")
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
