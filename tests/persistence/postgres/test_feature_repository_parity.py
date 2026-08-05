from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from market_regime_alpha.features.materialization_run import (
    FeatureMaterializationExecutionMode,
)
from market_regime_alpha.features.postgres_materialization_run import (
    PostgresFeatureMaterializationRunRepository,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.features.test_materialization_run_hardening import (
    ARTIFACT_HASH,
    COMMAND_HASH,
    MutableClock,
    _task,
)


def test_postgres_feature_run_fences_expired_claims_and_restores_snapshot(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(datetime(2026, 8, 5, 6, 40, tzinfo=timezone.utc))
    repository = PostgresFeatureMaterializationRunRepository(
        postgres_factory,
        clock=clock,
        lease_duration=timedelta(seconds=30),
    )
    run = repository.prepare(
        idempotency_key="pg-feature-run",
        command_hash=COMMAND_HASH,
        tasks=(_task(),),
        mode=FeatureMaterializationExecutionMode.START_NEW,
    )
    assert run.run_id == 1
    original = repository.claim_next(run_id=run.run_id)
    assert original is not None
    assert original.claim_epoch == 1

    clock.advance(timedelta(seconds=31))
    repository.prepare(
        idempotency_key="pg-feature-run",
        command_hash=COMMAND_HASH,
        tasks=(_task(),),
        mode=FeatureMaterializationExecutionMode.RESUME_EXISTING,
    )
    replacement = repository.claim_next(run_id=run.run_id)
    assert replacement is not None
    assert replacement.claim_epoch == 2
    with pytest.raises(ValueError, match="stale.*writer"):
        repository.complete_task(
            original,
            artifact_id="artifact-stale",
            artifact_hash=ARTIFACT_HASH,
        )
    repository.complete_task(
        replacement,
        artifact_id="artifact-current",
        artifact_hash=ARTIFACT_HASH,
    )

    restarted = PostgresFeatureMaterializationRunRepository(
        postgres_factory,
        clock=clock,
        lease_duration=timedelta(seconds=30),
    )
    snapshot = restarted.snapshot(run.run_id)
    assert snapshot.tasks[0][2:] == ("artifact-current", ARTIFACT_HASH)
    assert "LEASE_EXPIRED" in tuple(item[1] for item in snapshot.events)
