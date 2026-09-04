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
from tests.refoundation.research_qualification.test_backtest_execution_planner import (
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
