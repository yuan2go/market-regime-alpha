from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousSessionPhase,
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


NOW = datetime(2026, 8, 6, 6, 40, tzinfo=timezone.utc)
HASH = "sha256:" + "1" * 64


def _command() -> ContinuousResearchCommand:
    policy = default_continuous_decision_window_policy()
    return ContinuousResearchCommand.create(
        idempotency_key="continuous-concurrency",
        trading_date=date(2026, 8, 6),
        requested_symbols=("600000.SH",),
        trading_calendar_id=ArtifactId("calendar-fixture"),
        trading_calendar_hash=HASH,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        provider_configuration_id=ArtifactId("provider-config"),
        provider_configuration_hash=HASH,
        research_configuration_id=ArtifactId("research-config"),
        research_configuration_hash=HASH,
        code_revision="baseline-head",
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )


def test_workers_claim_disjoint_ticks_with_skip_locked(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    command = _command()
    journal.create_or_get(command)
    for index in range(2):
        journal.admit_tick(
            RuntimeTickCommand.create(
                idempotency_key=f"tick-{index}",
                run_id=command.run_id,
                trading_date=command.trading_date,
                observed_at=NOW.replace(minute=40 + index),
                request_scope_hash=command.request_scope_hash,
                provider_configuration_id=command.provider_configuration_id,
                provider_configuration_hash=command.provider_configuration_hash,
                research_configuration_id=command.research_configuration_id,
                research_configuration_hash=command.research_configuration_hash,
            ),
            session_phase=ContinuousSessionPhase.AFTERNOON_SESSION,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = tuple(
            executor.map(lambda _: journal.claim_next(command.run_id), range(2))
        )

    assert len({claim.tick_id for claim in claims}) == 2
    assert {claim.tick_sequence for claim in claims} == {1, 2}
