from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.postgres.backtest_uow import (
    PostgresBacktestUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.uow import (
    PostgresUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.backtests import (
    PostgresBacktestQueryPort,
)
from market_regime_alpha.research_qualification.application.backtest_execution import (
    BacktestExecutionPlanner,
)
from market_regime_alpha.research_qualification.application.backtest_runtime import (
    BacktestRuntimeActionExecutor,
)
from market_regime_alpha.research_qualification.application.backtests import (
    BacktestApplication,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestNextOperation,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    FrozenBacktestSource,
)
from market_regime_alpha.research_qualification.ports.backtest_runtime import (
    BacktestRuntimeStep,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.application import RuntimeApplication
from market_regime_alpha.shared.hashing import canonical_json_sha256

from tests.refoundation.research_qualification import (
    test_backtest_postgres as _backtests,
)


@pytest.fixture
def backtest_stack(target_database_url, tmp_path, request):
    return _backtests.backtest_stack.__wrapped__(
        target_database_url, tmp_path, request
    )


class _CompletingHandler:
    def __init__(self, runtime) -> None:
        self.runtime = runtime
        self.executed: list[str] = []

    def requested_at(self, specification, action):
        del specification, action
        return datetime(2026, 9, 4, 0, 0, tzinfo=UTC)

    def decision_time(self, specification, action):
        del specification, action
        return None

    def steps(self, specification, action):
        del specification
        return (
            BacktestRuntimeStep(
                "record-first",
                "RECORD_EVIDENCE",
                canonical_json_sha256(
                    {"action": action.action_id, "step": "first"}
                ),
            ),
            BacktestRuntimeStep(
                "record-second",
                "RECORD_EVIDENCE",
                canonical_json_sha256(
                    {"action": action.action_id, "step": "second"}
                ),
            ),
        )

    def execute_step(self, specification, action, claim):
        del specification, action
        self.executed.append(claim.step_key)
        self.runtime.succeed_attempt(
            claim,
            result_hash=canonical_json_sha256(
                {"attempt_id": claim.attempt_id, "step_key": claim.step_key}
            ),
            context=_context(f"succeed-{claim.attempt_id}"),
        )


class _RetryOnceHandler(_CompletingHandler):
    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self.failed = False

    def steps(self, specification, action):
        del specification
        return (
            BacktestRuntimeStep(
                "record-retry",
                "RECORD_EVIDENCE",
                canonical_json_sha256(
                    {"action": action.action_id, "step": "retry"}
                ),
            ),
        )

    def execute_step(self, specification, action, claim):
        del specification, action
        self.executed.append(claim.step_key)
        if not self.failed:
            self.failed = True
            self.runtime.fail_attempt(
                claim,
                error_class="BACKTEST",
                error_code="BACKTEST_ACTION_RETRYABLE",
                context=_context(f"fail-{claim.attempt_id}"),
            )
            return
        self.runtime.succeed_attempt(
            claim,
            result_hash=canonical_json_sha256({"attempt_id": claim.attempt_id}),
            context=_context(f"succeed-{claim.attempt_id}"),
        )


def _context(suffix: str) -> CommandContext:
    return CommandContext(
        idempotency_key=f"backtest-runtime-test:{suffix}",
        actor_type=ActorType.OPERATOR,
        actor_id="backtest-runtime-test",
        reason_code="BACKTEST_EXECUTION",
    )


def _executor(backtest_stack, handler):
    return BacktestRuntimeActionExecutor(
        runtime=handler.runtime,
        backtests=BacktestApplication(
            PostgresBacktestUnitOfWorkProvider(backtest_stack.pool),
            id_factory=uuid4,
        ),
        specifications=PostgresBacktestQueryPort(backtest_stack.pool),
        handler=handler,
        worker_id="backtest-runtime-test",
    )


def test_action_executor_binds_and_drives_one_runtime_dag(backtest_stack) -> None:
    specification = _backtests._current_specification(backtest_stack)
    backtests = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool), id_factory=uuid4
    )
    backtests.predeclare(specification, _context("predeclare"))
    frozen = backtests.plan(specification)
    action = BacktestExecutionPlanner().compile(frozen).expected_actions[0]
    runtime = RuntimeApplication(PostgresUnitOfWorkProvider(backtest_stack.pool))
    handler = _CompletingHandler(runtime)

    _executor(backtest_stack, handler).execute(
        frozen, action, BacktestNextOperation.EXECUTE
    )

    assert handler.executed == ["record-first", "record-second"]
    with backtest_stack.pool.connection(read_only=True) as connection:
        binding = connection.execute(
            """
            SELECT runtime_run_id FROM mra.backtest_runtime_binding
            WHERE action_id = %s
            """,
            (action.action_id,),
        ).fetchone()
    assert binding is not None
    trace = runtime.inspect_run(binding[0])
    assert trace.run_state == "SUCCEEDED"
    assert tuple(step.state for step in trace.steps) == ("SUCCEEDED", "SUCCEEDED")


def test_action_retry_reuses_runtime_and_creates_a_new_attempt(backtest_stack) -> None:
    specification = _backtests._current_specification(backtest_stack)
    backtests = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool), id_factory=uuid4
    )
    backtests.predeclare(specification, _context("retry-predeclare"))
    frozen = backtests.plan(specification)
    action = BacktestExecutionPlanner().compile(frozen).expected_actions[0]
    runtime = RuntimeApplication(PostgresUnitOfWorkProvider(backtest_stack.pool))
    handler = _RetryOnceHandler(runtime)
    executor = _executor(backtest_stack, handler)

    executor.execute(frozen, action, BacktestNextOperation.EXECUTE)
    executor.execute(frozen, action, BacktestNextOperation.RETRY)

    with backtest_stack.pool.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT runtime.run_id, count(attempt.attempt_id)
            FROM mra.backtest_runtime_binding AS binding
            JOIN mra.runtime_run AS runtime
              ON runtime.run_id = binding.runtime_run_id
            JOIN mra.runtime_step AS step ON step.run_id = runtime.run_id
            JOIN mra.runtime_attempt AS attempt ON attempt.step_id = step.step_id
            WHERE binding.action_id = %s
            GROUP BY runtime.run_id
            """,
            (action.action_id,),
        ).fetchone()
    assert row is not None and row[1] == 2
    assert runtime.inspect_run(row[0]).run_state == "SUCCEEDED"
    assert handler.executed == ["record-retry", "record-retry"]


def test_action_executor_rejects_non_current_projection(backtest_stack) -> None:
    specification = _backtests._current_specification(backtest_stack)
    frozen = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool), id_factory=uuid4
    ).plan(specification)
    action = BacktestExecutionPlanner().compile(frozen).expected_actions[0]
    runtime = RuntimeApplication(PostgresUnitOfWorkProvider(backtest_stack.pool))

    with pytest.raises(ValueError, match="current relational"):
        _executor(
            backtest_stack, _CompletingHandler(runtime)
        ).execute(
            replace(frozen, source=FrozenBacktestSource.HISTORICAL_EXACT),
            action,
            BacktestNextOperation.EXECUTE,
        )
