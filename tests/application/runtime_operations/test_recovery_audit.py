from __future__ import annotations

from datetime import UTC, datetime

from market_regime_alpha.application.runtime_operations.recovery_audit import (
    PostgresRecoveryAudit,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


def test_recovery_audit_is_read_only_and_clean_for_empty_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    report = PostgresRecoveryAudit(postgres_factory).inspect(
        checked_at=datetime(2026, 8, 11, 8, tzinfo=UTC)
    )

    assert report.issues == ()
    assert report.portfolio_replay_verified_count == 0
    assert report.production_mutation_performed is False
    assert report.to_canonical_dict()["status"] == "CLEAN"
