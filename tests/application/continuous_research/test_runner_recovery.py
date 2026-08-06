from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from market_regime_alpha.application.continuous_research.policy import (
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.continuous_research.runner import (
    ContinuousResearchTickRunner,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.application.continuous_research.test_runner import (
    HASHES,
    NOW,
    CountingChildren,
    ScriptedProvider,
    _command,
    _provider_result,
    _request,
    _tick,
)
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


def _runtime(postgres_factory: PostgresConnectionFactory):
    current = NOW

    def clock() -> datetime:
        return current

    command = _command()
    journal = PostgresContinuousResearchJournal(
        postgres_factory, clock=clock, lease_duration=timedelta(seconds=10)
    )
    provider = ScriptedProvider([_provider_result(HASHES[8])])
    children = CountingChildren()
    runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=provider,
        children=children,
        policy=default_continuous_decision_window_policy(),
        clock=clock,
    )

    def expire() -> None:
        nonlocal current
        current += timedelta(seconds=11)

    return command, journal, provider, children, runner, expire


def test_recovery_after_evidence_cas_skips_provider_republication(
    postgres_factory: PostgresConnectionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command, journal, provider, children, runner, expire = _runtime(
        postgres_factory
    )
    original = journal.record_change_decision

    def crash_after_evidence(**kwargs):
        raise RuntimeError("crash-after-evidence")

    monkeypatch.setattr(journal, "record_change_decision", crash_after_evidence)
    with pytest.raises(RuntimeError, match="crash-after-evidence"):
        runner.execute(
            run_command=command,
            tick_command=_tick(command, 0),
            provider_request=_request(),
        )
    tick = journal.get_tick(command.run_id, _tick(command, 0).tick_id)
    assert tick.evidence_commit_id is not None
    assert tick.change_decision_id is None

    expire()
    monkeypatch.setattr(journal, "record_change_decision", original)
    recovered = runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )

    assert recovered.decision is not None
    assert provider.call_count == 1
    assert sum(children.calls.values()) == 4


def test_recovery_after_child_receipts_uses_durable_child_lookup(
    postgres_factory: PostgresConnectionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command, journal, provider, children, runner, expire = _runtime(
        postgres_factory
    )
    original = journal.record_child_reference

    def crash_before_reference(**kwargs):
        raise RuntimeError("crash-after-child-receipts")

    monkeypatch.setattr(journal, "record_child_reference", crash_before_reference)
    with pytest.raises(RuntimeError, match="crash-after-child-receipts"):
        runner.execute(
            run_command=command,
            tick_command=_tick(command, 0),
            provider_request=_request(),
        )
    assert sum(children.calls.values()) == 4

    expire()
    monkeypatch.setattr(journal, "record_child_reference", original)
    recovered = runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )

    assert provider.call_count == 1
    assert sum(children.calls.values()) == 4
    assert len(recovered.child_references) == 4


def test_recovery_after_partial_crr_child_lineage_only_fills_missing_rows(
    postgres_factory: PostgresConnectionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command, journal, provider, children, runner, expire = _runtime(
        postgres_factory
    )
    original = journal.record_child_reference
    recorded = 0

    def crash_after_one_reference(**kwargs):
        nonlocal recorded
        if recorded == 1:
            raise RuntimeError("crash-after-one-reference")
        recorded += 1
        return original(**kwargs)

    monkeypatch.setattr(
        journal, "record_child_reference", crash_after_one_reference
    )
    with pytest.raises(RuntimeError, match="crash-after-one-reference"):
        runner.execute(
            run_command=command,
            tick_command=_tick(command, 0),
            provider_request=_request(),
        )
    assert len(
        journal.get_child_references(command.run_id, _tick(command, 0).tick_id)
    ) == 1

    expire()
    monkeypatch.setattr(journal, "record_child_reference", original)
    recovered = runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )

    assert len(recovered.child_references) == 4
    assert provider.call_count == 1
    assert sum(children.calls.values()) == 4


def test_completed_tick_replay_is_read_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command, _journal, provider, children, runner, _expire = _runtime(
        postgres_factory
    )
    first = runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )
    calls = (provider.call_count, children.calls.copy())

    replayed = runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )

    assert replayed.tick == first.tick
    assert (provider.call_count, children.calls) == calls
