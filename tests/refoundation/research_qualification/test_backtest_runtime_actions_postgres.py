from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
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


def test_runtime_observation_reads_latest_attempt_roster_once(backtest_stack) -> None:
    specification = _backtests._current_specification(backtest_stack)
    backtests = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool), id_factory=uuid4
    )
    backtests.predeclare(specification, _context("observation-roster"))
    frozen = backtests.plan(specification)
    runtime = RuntimeApplication(PostgresUnitOfWorkProvider(backtest_stack.pool))
    handler = _CompletingHandler(runtime)
    actions = BacktestExecutionPlanner().compile(frozen).expected_actions[:5]
    for action in actions[:-1]:
        _executor(backtest_stack, handler).execute(
            frozen, action, BacktestNextOperation.EXECUTE
        )
    retrying = _RetryOnceHandler(runtime)
    _executor(backtest_stack, retrying).execute(
        frozen, actions[-1], BacktestNextOperation.EXECUTE
    )
    path = Path(__file__).parents[3] / "src/market_regime_alpha/infrastructure/postgres/queries/backtest_execution.py"
    statements = [
        node.value for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and "SELECT binding.backtest_runtime_binding_id," in node.value
    ]
    assert len(statements) == 1
    # Qualify plans against this fixture's actual cardinalities, rather than
    # PostgreSQL's initial estimates for freshly bootstrapped empty tables.
    with backtest_stack.pool.connection() as connection:
        connection.execute("ANALYZE mra.backtest_runtime_binding")
        connection.execute("ANALYZE mra.runtime_run")
        connection.execute("ANALYZE mra.runtime_step")
        connection.execute("ANALYZE mra.runtime_attempt")
        connection.commit()
    with backtest_stack.pool.connection(read_only=True) as connection:
        binding_ids = [row[0] for row in connection.execute(
            "SELECT backtest_runtime_binding_id FROM mra.backtest_runtime_binding WHERE exploratory_backtest_run_id=%s ORDER BY backtest_runtime_binding_id",
            (specification.exploratory_backtest_run_id,),
        ).fetchall()]
        parameters = (specification.exploratory_backtest_run_id, binding_ids)
        rows = connection.execute(
            statements[0], parameters
        ).fetchall()
        assert len(rows) == len(actions) == 5
        assert {row[-1] for row in rows} == {"SUCCEEDED", "FAILED_RETRYABLE"}
        plan = connection.execute(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statements[0],
            parameters,
        ).fetchone()[0][0]["Plan"]
    pending = [plan]
    attempts = []
    while pending:
        node = pending.pop()
        pending.extend(node.get("Plans", ()))
        if node.get("Relation Name") == "runtime_attempt":
            attempts.append(node)
    assert attempts
    # A campaign grows in Runs and Steps. Latest-state observation must not
    # issue one Attempt probe per Step while reading the complete roster.
    assert sum(node["Actual Loops"] for node in attempts) == 1
    _executor(backtest_stack, retrying).execute(
        frozen, actions[-1], BacktestNextOperation.RETRY
    )
    with backtest_stack.pool.connection(read_only=True) as connection:
        resumed_rows = connection.execute(
            statements[0], parameters
        ).fetchall()
    assert len(resumed_rows) == len(rows)
    assert {row[-1] for row in resumed_rows} == {"SUCCEEDED"}


def test_observer_bounds_runtime_queries_without_losing_bindings(backtest_stack) -> None:
    from market_regime_alpha.infrastructure.postgres.queries.backtest_execution import PostgresBacktestExecutionObservationPort

    specification = _backtests._current_specification(backtest_stack)
    backtests = BacktestApplication(PostgresBacktestUnitOfWorkProvider(backtest_stack.pool), id_factory=uuid4)
    backtests.predeclare(specification, _context("bounded-runtime-roster"))
    frozen = backtests.plan(specification)
    actions = BacktestExecutionPlanner().compile(frozen).expected_actions[:9]
    assert len(actions) == 9
    handler = _CompletingHandler(RuntimeApplication(PostgresUnitOfWorkProvider(backtest_stack.pool)))
    for action in actions:
        _executor(backtest_stack, handler).execute(frozen, action, BacktestNextOperation.EXECUTE)
    batches = []

    class SavedRows:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class TracedCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def __enter__(self):
            self.cursor.__enter__()
            return self

        def __exit__(self, *args):
            return self.cursor.__exit__(*args)

        def execute(self, statement, parameters):
            result = self.cursor.execute(statement, parameters)
            if "SELECT binding.backtest_runtime_binding_id," in statement:
                rows = result.fetchall()
                batches.append(rows)
                return SavedRows(rows)
            return result

    class TracedConnection:
        def __init__(self, connection):
            self.connection = connection

        def cursor(self, **kwargs):
            return TracedCursor(self.connection.cursor(**kwargs))

    class TracedPool:
        @contextmanager
        def connection(self, *, read_only=False):
            with backtest_stack.pool.connection(read_only=read_only) as connection:
                yield TracedConnection(connection)

    # Exercise the observer's real PostgreSQL metadata path, without inventing
    # completed Dataset/Decision owners for the Runtime-only fixture handler.
    assert PostgresBacktestExecutionObservationPort(TracedPool()).observe(frozen, ()) == ()
    assert batches
    assert max(map(len, batches)) <= 8
    rows = [row for batch in batches for row in batch]
    assert len(rows) == 9
    assert {row["action_id"] for row in rows} == {action.action_id for action in actions}
    assert {row["latest_attempt_state"] for row in rows} == {"SUCCEEDED"}
