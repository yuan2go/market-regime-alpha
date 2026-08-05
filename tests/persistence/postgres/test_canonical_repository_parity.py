from __future__ import annotations

from datetime import timedelta

import pytest

from market_regime_alpha.application.canonical_lifecycle.postgres_repository import (
    PostgresLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.postgres_composition import (
    postgres_lifecycle_stage_handlers,
)
from market_regime_alpha.application.canonical_lifecycle.stages.decision_risk import (
    OpportunityStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.execution_position import (
    ManualTradeStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.unavailable import (
    UnavailableLifecycleStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleConcurrentModification,
    LifecycleJournalIntegrityError,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    LifecycleStageStatus,
    LifecycleStageName,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.application.canonical_lifecycle.test_sqlite_repository import (
    T0,
    _claimed_started,
    _command,
    _transition,
)


def test_postgres_lifecycle_journal_settles_and_restarts_read_only(
    tmp_path,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresLifecycleRunRepository(postgres_factory)
    command = _command(tmp_path)
    created = repository.create_or_get(command, created_at=T0)
    assert repository.create_or_get(command, created_at=T0) == created
    assert tuple(item.stage_name for item in repository.history(created.run_id).stages) == (
        LIFECYCLE_STAGE_ORDER
    )

    run, stage, attempt = _claimed_started(repository, command)
    settled = repository.finish_stage(_transition(run, stage, attempt))
    history = repository.history(run.run_id)
    assert history.stages[0].stage_status is LifecycleStageStatus.COMPLETED
    assert len(history.receipts) == 1
    assert len(history.attempts) == 1

    read_only = PostgresLifecycleRunRepository(postgres_factory, read_only=True)
    assert read_only.history(run.run_id) == history
    with pytest.raises(LifecycleJournalIntegrityError, match="read-only"):
        read_only.claim(
            run.run_id,
            expected_version=settled.version,
            claimed_at=T0 + timedelta(seconds=4),
        )


def test_postgres_lifecycle_claim_uses_version_fencing(
    tmp_path,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresLifecycleRunRepository(postgres_factory)
    created = repository.create_or_get(_command(tmp_path), created_at=T0)
    repository.claim(
        created.run_id,
        expected_version=created.version,
        claimed_at=T0 + timedelta(seconds=1),
    )
    with pytest.raises(LifecycleConcurrentModification):
        repository.claim(
            created.run_id,
            expected_version=created.version,
            claimed_at=T0 + timedelta(seconds=2),
        )


def test_postgres_lifecycle_composition_binds_domain_authorities(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    base = tuple(
        UnavailableLifecycleStageHandler(
            stage_name=stage,
            reason_code="TEST_UNAVAILABLE",
            detail="PostgreSQL composition fixture",
        )
        for stage in LIFECYCLE_STAGE_ORDER
    )
    handlers = postgres_lifecycle_stage_handlers(
        factory=postgres_factory,
        base_handlers=base,
    )
    by_stage = dict(zip(LIFECYCLE_STAGE_ORDER, handlers, strict=True))
    assert isinstance(
        by_stage[LifecycleStageName.OPPORTUNITY], OpportunityStageHandler
    )
    assert isinstance(
        by_stage[LifecycleStageName.MANUAL_TRADE], ManualTradeStageHandler
    )
