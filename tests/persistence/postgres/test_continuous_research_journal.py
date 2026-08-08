from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousTickStatus,
    RuntimeTickReceipt,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousRunState,
    ContinuousSessionPhase,
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    ContinuousResearchClaimRejected,
    ContinuousResearchConflict,
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


NOW = datetime(2026, 8, 6, 6, 42, tzinfo=timezone.utc)
HASH_1 = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64
HASH_3 = "sha256:" + "3" * 64
LIMITATIONS = (
    "ENTRY_BLOCKED",
    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
    "FORMAL_PIT_NOT_ESTABLISHED",
    "NO_BROKER_AUTHORITY",
)


@dataclass
class MutableClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


def _command(
    *,
    code_revision: str = "baseline-head",
    idempotency_key: str = "continuous-2026-08-06",
) -> ContinuousResearchCommand:
    policy = default_continuous_decision_window_policy()
    return ContinuousResearchCommand.create(
        idempotency_key=idempotency_key,
        trading_date=date(2026, 8, 6),
        requested_symbols=("000001.SZ", "600000.SH"),
        trading_calendar_id=ArtifactId("calendar-fixture"),
        trading_calendar_hash=HASH_1,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        provider_configuration_id=ArtifactId("provider-config-fixture"),
        provider_configuration_hash=HASH_2,
        research_configuration_id=ArtifactId("research-config-fixture"),
        research_configuration_hash=HASH_3,
        code_revision=code_revision,
        limitations=LIMITATIONS,
    )


def _tick(
    command: ContinuousResearchCommand,
    *,
    minute: int = 42,
) -> RuntimeTickCommand:
    return RuntimeTickCommand.create(
        idempotency_key=f"continuous-tick-{minute}",
        run_id=command.run_id,
        trading_date=command.trading_date,
        observed_at=NOW.replace(minute=minute),
        request_scope_hash=command.request_scope_hash,
        provider_configuration_id=command.provider_configuration_id,
        provider_configuration_hash=command.provider_configuration_hash,
        research_configuration_id=command.research_configuration_id,
        research_configuration_hash=command.research_configuration_hash,
    )


def _receipt(claim) -> RuntimeTickReceipt:
    return RuntimeTickReceipt.create(
        claim=claim,
        input_references=(),
        output_references=(),
        reason_codes=("NO_MATERIAL_CHANGE",),
        created_at=NOW,
    )


def test_run_and_tick_creation_are_idempotent_and_conflicts_fail_closed(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    command = _command()

    first = journal.create_or_get(command)
    second = journal.create_or_get(command)
    tick = _tick(command)
    admitted = journal.admit_tick(
        tick,
        session_phase=ContinuousSessionPhase.DECISION_WINDOW,
    )
    duplicate = journal.admit_tick(
        tick,
        session_phase=ContinuousSessionPhase.DECISION_WINDOW,
    )

    assert first.command == second.command == command
    assert first.status is ContinuousRunState.CREATED
    assert admitted == duplicate
    assert admitted.status is ContinuousTickStatus.PENDING
    assert admitted.tick_sequence == 1
    assert journal.get_run(command.run_id).status is ContinuousRunState.DECISION_WINDOW_OPEN
    with pytest.raises(ContinuousResearchConflict, match="idempotency conflict"):
        journal.create_or_get(_command(code_revision="different-head"))
    with pytest.raises(ContinuousResearchConflict, match="one Continuous parent"):
        journal.create_or_get(_command(idempotency_key="second-parent"))


def test_claim_heartbeat_complete_and_restart_are_durable(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    journal = PostgresContinuousResearchJournal(
        postgres_factory,
        clock=clock,
        lease_duration=timedelta(seconds=30),
    )
    command = _command()
    journal.create_or_get(command)
    tick = journal.admit_tick(
        _tick(command),
        session_phase=ContinuousSessionPhase.DECISION_WINDOW,
    )

    claim = journal.claim_tick(run_id=command.run_id, tick_id=tick.command.tick_id)
    with pytest.raises(ContinuousResearchClaimRejected, match="active lease"):
        journal.claim_tick(run_id=command.run_id, tick_id=tick.command.tick_id)
    clock.advance(timedelta(seconds=5))
    heartbeat = journal.heartbeat(claim)
    completed = journal.complete_tick(
        claim=heartbeat,
        receipt=_receipt(heartbeat),
        run_state=ContinuousRunState.WAITING_FOR_NEW_DATA,
    )
    restarted = PostgresContinuousResearchJournal(
        postgres_factory,
        clock=clock,
        lease_duration=timedelta(seconds=30),
    )

    assert completed.status is ContinuousTickStatus.COMPLETED
    assert completed.receipt is not None
    assert restarted.get_tick(command.run_id, tick.command.tick_id) == completed
    assert restarted.get_run(command.run_id).status is ContinuousRunState.WAITING_FOR_NEW_DATA


def test_expired_lease_is_recovered_and_stale_worker_is_fenced(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    journal = PostgresContinuousResearchJournal(
        postgres_factory,
        clock=clock,
        lease_duration=timedelta(seconds=10),
    )
    command = _command()
    journal.create_or_get(command)
    tick = journal.admit_tick(
        _tick(command),
        session_phase=ContinuousSessionPhase.AFTERNOON_SESSION,
    )
    stale = journal.claim_tick(run_id=command.run_id, tick_id=tick.command.tick_id)

    clock.advance(timedelta(seconds=11))
    recovered = journal.resume(command.run_id)
    fresh = journal.claim_tick(run_id=command.run_id, tick_id=tick.command.tick_id)

    assert recovered.ticks[0].status is ContinuousTickStatus.PENDING
    assert recovered.ticks[0].last_error == "LEASE_EXPIRED"
    assert fresh.fencing_token == stale.fencing_token + 1
    with pytest.raises(ContinuousResearchClaimRejected, match="child final write"):
        journal.assert_claim_active(stale)
    journal.assert_claim_active(fresh)
    with pytest.raises(ContinuousResearchClaimRejected, match="fencing"):
        journal.complete_tick(
            claim=stale,
            receipt=_receipt(stale),
            run_state=ContinuousRunState.MONITORING,
        )


def test_retryable_failure_returns_tick_to_pending_without_losing_fence(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    command = _command()
    journal.create_or_get(command)
    tick = journal.admit_tick(
        _tick(command),
        session_phase=ContinuousSessionPhase.AFTERNOON_SESSION,
    )
    claim = journal.claim_tick(run_id=command.run_id, tick_id=tick.command.tick_id)

    failed = journal.fail_tick(
        claim=claim,
        error="PROVIDER_TIMED_OUT",
        retryable=True,
        retry_at=NOW + timedelta(seconds=30),
    )

    assert failed.status is ContinuousTickStatus.PENDING
    assert failed.fencing_token == claim.fencing_token
    assert failed.last_error == "PROVIDER_TIMED_OUT"
    assert journal.get_run(command.run_id).status is ContinuousRunState.RETRYING
