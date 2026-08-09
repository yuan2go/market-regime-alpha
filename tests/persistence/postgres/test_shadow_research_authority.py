from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.shadow_research import (
    PostgresShadowResearchRepository,
    ShadowOutcomeStatus,
    ShadowResearchConflict,
    ShadowSessionCommand,
    ShadowSessionStatus,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from tests.persistence.postgres.test_free_data_continuous_runtime import (
    _calendar,
    _configuration,
    _continuous_command,
)


def test_shadow_session_is_postgres_cas_recoverable_and_append_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    calendar = _calendar()
    configuration = _configuration(calendar)
    run = _continuous_command(
        ("000001.SZ",),
        calendar,
        configuration,
        RuntimeAuthorityMode.SHADOW,
    )
    PostgresContinuousResearchJournal(
        postgres_factory, clock=lambda: now
    ).create_or_get(run)
    repository = PostgresShadowResearchRepository(
        postgres_factory, clock=lambda: now
    )
    command = ShadowSessionCommand.create(
        idempotency_key="shadow-cas-recovery",
        run_id=run.run_id,
        trading_date=run.trading_date,
        runtime_mode=RuntimeAuthorityMode.SHADOW,
        scheduled_at=now - timedelta(minutes=25),
        operator_observation="RECORDED_ENGINEERING_TEST",
    )

    scheduled = repository.schedule(command)
    assert repository.schedule(command) == scheduled
    assert scheduled.status is ShadowSessionStatus.SCHEDULED
    running = repository.mark_running(
        command.session_id, expected_version=scheduled.version
    )
    with pytest.raises(ShadowResearchConflict, match="not startable"):
        repository.mark_running(
            command.session_id, expected_version=scheduled.version
        )
    failed = repository.fail(
        command.session_id,
        expected_version=running.version,
        reason_codes=("RECORDED_PROVIDER_OUTAGE",),
    )
    recovered = repository.mark_running(
        command.session_id,
        expected_version=failed.version,
        recovered=True,
    )
    invalidated = repository.invalidate(
        command.session_id,
        expected_version=recovered.version,
        reason_codes=("ENGINEERING_SESSION_INVALIDATED",),
    )

    assert invalidated.status is ShadowSessionStatus.INVALIDATED
    assert invalidated.outcome_status is ShadowOutcomeStatus.INVALIDATED
    assert [item["event_type"] for item in repository.events(command.session_id)] == [
        "SESSION_SCHEDULED",
        "SESSION_RUNNING",
        "SESSION_FAILED",
        "SESSION_RECOVERED",
        "SESSION_INVALIDATED",
    ]
    with postgres_factory.connection() as connection:
        with pytest.raises(psycopg.errors.RaiseException, match="cannot be deleted"):
            connection.execute(
                "DELETE FROM shadow_research_session WHERE session_id = %s",
                (str(command.session_id),),
            )


def test_shadow_session_rejects_non_shadow_canonical_run(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    calendar = _calendar()
    configuration = _configuration(calendar)
    run = _continuous_command(
        ("000001.SZ",),
        calendar,
        configuration,
        RuntimeAuthorityMode.RESEARCH,
    )
    PostgresContinuousResearchJournal(postgres_factory).create_or_get(run)
    repository = PostgresShadowResearchRepository(postgres_factory)
    command = ShadowSessionCommand.create(
        idempotency_key="forged-research-as-shadow",
        run_id=run.run_id,
        trading_date=run.trading_date,
        runtime_mode=RuntimeAuthorityMode.SHADOW,
        scheduled_at=now,
        operator_observation=None,
    )

    with pytest.raises(ShadowResearchConflict, match="lineage mismatch"):
        repository.schedule(command)
