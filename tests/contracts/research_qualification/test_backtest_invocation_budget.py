import pytest

from market_regime_alpha.research_qualification.application.backtest_execution import BacktestExecutor, BacktestExecutionPlanner
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestExecutionBudget, BacktestExecutionState, BacktestActionObservation, BacktestObservedState,
)
from tests.contracts.research_qualification.test_backtest_execution_planner import _run


class OwnerContract:
    def __init__(self):
        self.executed = []
        self.read_sizes = []
        self.on_execute = lambda: None

    def observe(self, run, actions):
        self.read_sizes.append(len(actions))
        return tuple(BacktestActionObservation(a.action_id,
            BacktestObservedState.MATCHED_COMPLETE if a.action_id in self.executed else BacktestObservedState.ABSENT) for a in actions)

    def execute(self, run, action, operation):
        assert action.action_id not in self.executed
        self.executed.append(action.action_id)
        self.on_execute()


def test_bounded_stop_keeps_full_roster_and_resume_never_reexecutes_committed_actions():
    owner = OwnerContract()
    executor = BacktestExecutor(owner, owner)
    run = _run()
    expected = BacktestExecutionPlanner().compile(run).expected_actions
    first = executor.run(run, budget=BacktestExecutionBudget(maximum_actions=2))
    assert len(owner.executed) == 2
    assert first.expected_actions == expected and first.ready_actions
    assert executor.last_invocation.stop_reason == "BUDGET_REACHED"
    assert owner.read_sizes[0] == owner.read_sizes[-1] == len(expected)
    for _ in range(len(expected)):
        result = executor.resume(run, budget=BacktestExecutionBudget(maximum_actions=3))
        if result.execution_state is BacktestExecutionState.COMPLETED:
            break
    assert result.execution_state is BacktestExecutionState.COMPLETED
    assert set(owner.executed) == {a.action_id for a in expected}
    assert len(owner.executed) == len(expected)
    executor.resume(run, budget=BacktestExecutionBudget(maximum_actions=1))
    assert executor.last_invocation.attempted_actions == 0


def test_elapsed_budget_drains_after_owner_commit_and_preserves_unknown_effect_exception(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("market_regime_alpha.research_qualification.application.backtest_execution.perf_counter", lambda: clock[0])
    owner = OwnerContract()
    owner.on_execute = lambda: clock.__setitem__(0, clock[0] + 2)
    executor = BacktestExecutor(owner, owner)
    executor.run(_run(), budget=BacktestExecutionBudget(maximum_seconds=1))
    assert len(owner.executed) == 1
    assert executor.last_invocation.action_seconds == 2
    original = RuntimeError("unknown result after owner accepted")
    def interrupt():
        raise original
    owner.on_execute = interrupt
    with pytest.raises(RuntimeError) as failure:
        executor.resume(_run(), budget=BacktestExecutionBudget(maximum_actions=1))
    assert failure.value is original
    assert executor.last_invocation.stop_reason == "EXCEPTION_REQUIRES_RECONCILIATION"
    owner.on_execute = lambda: None
    executor.resume(_run(), budget=BacktestExecutionBudget(maximum_actions=1))
    assert len(owner.executed) == 3


@pytest.mark.parametrize("kwargs", [{"maximum_actions": 0}, {"maximum_actions": True}, {"maximum_seconds": float("nan")}, {"maximum_seconds": 0}, {"maximum_seconds": 7201}])
def test_invalid_budget_fails_before_execution(kwargs):
    with pytest.raises(ValueError):
        BacktestExecutionBudget(**kwargs)
