from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

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
from market_regime_alpha.application.continuous_research.scheduler import (
    ContinuousResearchScheduleRunner,
    ContinuousScheduleStatus,
    TradingDayAssessment,
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
)
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


def _trading_day(is_trading_day: bool = True) -> TradingDayAssessment:
    command = _command()
    return TradingDayAssessment(
        trading_calendar_id=command.trading_calendar_id,
        trading_calendar_hash=command.trading_calendar_hash,
        trading_date=command.trading_date,
        is_trading_day=is_trading_day,
        reason_codes=("TRADING_DAY" if is_trading_day else "NON_TRADING_DAY",),
    )


def _scheduler(
    postgres_factory: PostgresConnectionFactory,
    provider: ScriptedProvider,
) -> tuple[PostgresContinuousResearchJournal, ContinuousResearchScheduleRunner]:
    policy = default_continuous_decision_window_policy()
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    tick_runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=provider,
        children=CountingChildren(),
        policy=policy,
        clock=lambda: NOW,
    )
    return journal, ContinuousResearchScheduleRunner(
        journal=journal,
        tick_runner=tick_runner,
        policy=policy,
        provider_request_builder=lambda _run, _tick: _request(),
    )


def test_trading_day_assessment_reader_rejects_string_boolean() -> None:
    payload = _trading_day().to_canonical_dict()
    payload["is_trading_day"] = "false"

    with pytest.raises(ValueError, match="is_trading_day must be bool"):
        TradingDayAssessment.from_canonical_dict(payload)


def test_schedule_reserves_one_due_tick_and_persists_next_tick(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command()
    journal, scheduler = _scheduler(
        postgres_factory,
        ScriptedProvider([_provider_result(HASHES[8])]),
    )

    first = scheduler.run_due_once(
        run_command=command,
        trading_day=_trading_day(),
        now=NOW,
    )
    not_due = scheduler.run_due_once(
        run_command=command,
        trading_day=_trading_day(),
        now=NOW,
    )

    assert first.tick_result is not None
    assert first.tick_result.tick.command.observed_at == NOW
    assert first.schedule.next_tick_at == NOW + timedelta(seconds=60)
    assert not_due.status == "NOT_DUE"
    assert journal.get_run(command.run_id).current_tick_sequence == 1


def test_non_trading_day_stops_without_creating_a_tick(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command()
    journal, scheduler = _scheduler(postgres_factory, ScriptedProvider([]))

    result = scheduler.run_due_once(
        run_command=command,
        trading_day=_trading_day(False),
        now=NOW,
    )

    assert result.status == "NON_TRADING_DAY"
    assert result.schedule.status is ContinuousScheduleStatus.NON_TRADING_DAY
    assert journal.get_run(command.run_id).ticks == ()


def test_scheduler_recovers_a_reserved_tick_after_process_restart(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command()
    policy = default_continuous_decision_window_policy()
    journal, scheduler = _scheduler(
        postgres_factory,
        ScriptedProvider([_provider_result(HASHES[8])]),
    )
    journal.create_or_get(command)
    journal.initialize_schedule(
        run_command=command,
        policy=policy,
        trading_day=_trading_day(),
        initial_tick_at=NOW,
    )
    reserved = journal.reserve_due_tick(
        run_command=command,
        policy=policy,
        now=NOW,
    )
    assert reserved is not None

    recovered = scheduler.run_due_once(
        run_command=command,
        trading_day=_trading_day(),
        now=NOW,
    )

    assert recovered.tick_result is not None
    assert recovered.tick_result.tick.command.tick_id == reserved.command.tick_id
    assert recovered.tick_result.tick.status.value == "COMPLETED"


def test_concurrent_schedulers_reserve_only_one_tick(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command()
    policy = default_continuous_decision_window_policy()
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    journal.create_or_get(command)
    journal.initialize_schedule(
        run_command=command,
        policy=policy,
        trading_day=_trading_day(),
        initial_tick_at=NOW,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        reservations = tuple(
            executor.map(
                lambda _: journal.reserve_due_tick(
                    run_command=command,
                    policy=policy,
                    now=NOW,
                ),
                range(2),
            )
        )

    assert sum(item is not None for item in reservations) == 1
    assert journal.get_run(command.run_id).current_tick_sequence == 1
