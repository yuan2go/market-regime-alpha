from __future__ import annotations

from market_regime_alpha.application.continuous_research.policy import (
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.continuous_research.replay import (
    replay_continuous_research,
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


def test_replay_is_deterministic_and_read_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command()
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=ScriptedProvider([_provider_result(HASHES[8])]),
        children=CountingChildren(),
        policy=default_continuous_decision_window_policy(),
        clock=lambda: NOW,
    )
    runner.execute(
        run_command=command,
        tick_command=_tick(command, 0),
        provider_request=_request(),
    )
    before = journal.get_run(command.run_id)

    first = replay_continuous_research(journal, command.run_id)
    second = replay_continuous_research(journal, command.run_id)

    assert first == second
    assert first.integrity_status == "VERIFIED"
    assert first.evidence_count == 1
    assert first.decision_count == 1
    assert first.child_reference_count == 4
    assert first.entry_authority_granted is False
    assert journal.get_run(command.run_id) == before
