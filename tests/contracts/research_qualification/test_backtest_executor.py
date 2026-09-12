from __future__ import annotations

from dataclasses import dataclass

import pytest

from market_regime_alpha.research_qualification.application.backtest_execution import (
    BacktestExecutor,
    BacktestExecutionPlanner,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestActionObservation,
    BacktestExecutionState,
    BacktestNextOperation,
    BacktestObservedState,
    BacktestResearchState,
)
from market_regime_alpha.research_qualification.errors import (
    BacktestExecutionIntegrityError,
)
from tests.contracts.research_qualification.test_backtest_execution_planner import (
    _run,
)


@dataclass
class _CanonicalState:
    observations: dict[object, BacktestActionObservation]

    def observe(self, run, expected_actions):
        del run
        return tuple(self.observations[action.action_id] for action in expected_actions if action.action_id in self.observations)

    def execute(self, run, action, operation):
        del run
        assert operation in {
            BacktestNextOperation.EXECUTE,
            BacktestNextOperation.RECOVER,
            BacktestNextOperation.RETRY,
        }
        research_state = (
            BacktestResearchState.NOT_ESTIMABLE if action.kind.value.startswith("COMPLETE_") else BacktestResearchState.NOT_APPLICABLE
        )
        self.observations[action.action_id] = BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MATCHED_COMPLETE,
            research_state,
        )


def test_executor_reconciles_after_every_action_and_completes_not_estimable_run() -> None:
    run = _run()
    state = _CanonicalState({})
    executor = BacktestExecutor(state, state)

    completed = executor.run(run)
    replay = executor.resume(run)

    assert completed.execution_state is BacktestExecutionState.COMPLETED
    assert completed.research_state is BacktestResearchState.NOT_ESTIMABLE
    assert replay == completed
    assert len(state.observations) == len(BacktestExecutionPlanner().compile(run).expected_actions)


def test_reserved_holdout_stays_visible_without_terminal_failure_or_owner_writes():
    frozen = _run()
    state = _CanonicalState({})
    blockers = ["EXPLORATORY_HOLDOUT_RESERVED:fixture"]
    executor = BacktestExecutor(state, state, execution_blockers=lambda identity: tuple(blockers))
    result = executor.run(frozen)
    assert result.execution_state is BacktestExecutionState.PLANNED
    assert result.execution_blockers == tuple(blockers)
    assert result.ready_actions == () and result.expected_actions
    assert not state.observations
    assert executor.last_invocation.stop_reason == "BLOCKED"
    assert executor.inspect(frozen) == result
    blockers.clear()
    assert executor.resume(frozen).execution_state is BacktestExecutionState.COMPLETED


def test_run_requires_zero_existing_execution_but_resume_reuses_completed_actions() -> None:
    frozen = _run()
    first = BacktestExecutionPlanner().compile(frozen).expected_actions[0]
    state = _CanonicalState(
        {
            first.action_id: BacktestActionObservation(
                first.action_id,
                BacktestObservedState.MATCHED_COMPLETE,
            )
        }
    )
    executor = BacktestExecutor(state, state)

    with pytest.raises(BacktestExecutionIntegrityError, match="no execution evidence"):
        executor.run(frozen)

    assert executor.resume(frozen).execution_state is BacktestExecutionState.COMPLETED


def test_integrity_mismatch_stops_before_any_action_execution() -> None:
    frozen = _run()
    first = BacktestExecutionPlanner().compile(frozen).expected_actions[0]
    state = _CanonicalState(
        {
            first.action_id: BacktestActionObservation(
                first.action_id,
                BacktestObservedState.MISMATCH,
            )
        }
    )

    with pytest.raises(BacktestExecutionIntegrityError, match="INTEGRITY_ERROR"):
        BacktestExecutor(state, state).resume(frozen)

    assert state.observations == {
        first.action_id: BacktestActionObservation(
            first.action_id,
            BacktestObservedState.MISMATCH,
        )
    }


def test_resume_uses_one_fresh_observation_per_transition_and_final_verification() -> None:
    class CountingState(_CanonicalState):
        reads = 0
        executions = 0

        def observe(self, run, expected_actions):
            self.reads += 1
            return super().observe(run, expected_actions)

        def execute(self, run, action, operation):
            assert self.reads == self.executions + 1
            self.executions += 1
            super().execute(run, action, operation)

    state = CountingState({})
    executor = BacktestExecutor(state, state)
    assert executor.resume(_run()).execution_state is BacktestExecutionState.COMPLETED
    assert state.reads == state.executions + 1
    completed_executions = state.executions
    assert executor.resume(_run()).execution_state is BacktestExecutionState.COMPLETED
    assert state.executions == completed_executions
    assert state.reads == completed_executions + 2


def test_inspect_reports_running_when_completed_actions_precede_remaining_work() -> None:
    frozen = _run()
    first = BacktestExecutionPlanner().compile(frozen).expected_actions[0]
    state = _CanonicalState({first.action_id: BacktestActionObservation(
        first.action_id, BacktestObservedState.MATCHED_COMPLETE,
    )})
    assert BacktestExecutor(state, state).inspect(frozen).execution_state is BacktestExecutionState.RUNNING


def test_resume_leaves_an_unexpired_incomplete_owner_running_without_integrity_failure() -> None:
    frozen = _run()
    first = BacktestExecutionPlanner().compile(frozen).expected_actions[0]

    class LeasedState(_CanonicalState):
        recoveries = 0

        def execute(self, run, action, operation):
            assert operation is BacktestNextOperation.RECOVER
            self.recoveries += 1

    state = LeasedState({first.action_id: BacktestActionObservation(
        first.action_id, BacktestObservedState.MATCHED_INCOMPLETE,
    )})
    result = BacktestExecutor(state, state).resume(frozen)
    assert result.execution_state is BacktestExecutionState.RUNNING
    assert state.recoveries == 1
    assert not result.integrity_mismatch_action_ids
    assert len(state.observations) == 1


def test_ready_actions_do_not_repeat_full_owner_reads_quadratically() -> None:
    frozen = _run()
    expected = BacktestExecutionPlanner().compile(frozen).expected_actions
    all_ids = tuple(action.action_id for action in expected)
    levels = {}
    for action in expected:
        levels[action.action_id] = 1 + max((levels[identity] for identity in action.dependency_action_ids), default=0)

    class MeasuredState(_CanonicalState):
        owner_reads = 0
        scopes = []
        fully_reconciled = set()

        def observe(self, run, expected_actions):
            result = super().observe(run, expected_actions)
            scope = tuple(action.action_id for action in expected_actions)
            self.scopes.append(scope)
            self.owner_reads += len(expected_actions)
            if scope == all_ids:
                self.fully_reconciled = {
                    item.action_id for item in result
                    if item.state is BacktestObservedState.MATCHED_COMPLETE
                }
            return result

        def execute(self, run, action, operation):
            # A newly completed local action cannot unlock a dependent action
            # until another complete canonical graph reconciliation occurs.
            assert set(action.dependency_action_ids) <= self.fully_reconciled
            super().execute(run, action, operation)

    state = MeasuredState({})
    assert BacktestExecutor(state, state).resume(frozen).execution_state is BacktestExecutionState.COMPLETED
    assert state.scopes[0] == state.scopes[-1] == all_ids
    assert state.owner_reads <= len(expected) * (max(levels.values()) + 2)
    assert len(state.observations) == len(expected)


def test_mismatch_after_an_action_prevents_independent_later_writes() -> None:
    class BrokenState(_CanonicalState):
        executed = []

        def execute(self, run, action, operation):
            del run, operation
            self.executed.append(action.action_id)
            self.observations[action.action_id] = BacktestActionObservation(
                action.action_id, BacktestObservedState.MISMATCH,
            )

    state = BrokenState({})
    with pytest.raises(BacktestExecutionIntegrityError, match="INTEGRITY_ERROR"):
        BacktestExecutor(state, state).resume(_run())
    assert len(state.executed) == 1


def test_terminal_failure_does_not_continue_the_previous_ready_set() -> None:
    class TerminalState(_CanonicalState):
        executed = []

        def execute(self, run, action, operation):
            del run, operation
            self.executed.append(action.action_id)
            self.observations[action.action_id] = BacktestActionObservation(
                action.action_id, BacktestObservedState.FAILED_TERMINAL,
            )

    state = TerminalState({})
    result = BacktestExecutor(state, state).resume(_run())
    assert result.execution_state is BacktestExecutionState.FAILED
    assert not result.ready_actions
    assert len(state.executed) == 1
