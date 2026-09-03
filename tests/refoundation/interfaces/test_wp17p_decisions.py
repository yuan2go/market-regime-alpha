from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_regime_alpha.interfaces.wp17p_decisions import (
    Wp17pDecisionOperations,
    _schedule_runtime,
)


class _Runtime:
    def __init__(self) -> None:
        self.schedules = []
        self.runs = []
        self.started = []

    def create_schedule(self, schedule, context) -> None:
        self.schedules.append((schedule, context))

    def schedule_run(self, run, steps, dependencies, context) -> None:
        self.runs.append((run, steps, dependencies, context))

    def start_run(self, run_id, context) -> None:
        self.started.append((run_id, context))


def test_decision_runtime_freezes_archive_knowledge_time_as_requested_at() -> None:
    runtime = _Runtime()
    application = SimpleNamespace(runtime=runtime)
    backtest_id = uuid4()
    catalog = SimpleNamespace(
        backtest=SimpleNamespace(
            exploratory_backtest_run_id=backtest_id,
            content_sha256="a" * 64,
            config_artifact=SimpleNamespace(
                artifact_id=uuid4(),
                content_sha256="b" * 64,
            ),
        )
    )
    requested_at = datetime(2026, 8, 10, 8, tzinfo=UTC)
    simulated_decision_time = datetime(2026, 1, 5, 7, 1, tzinfo=UTC)
    runtime_run_id = uuid4()

    _schedule_runtime(
        application,
        catalog=catalog,
        runtime_run_id=runtime_run_id,
        decision_time=simulated_decision_time,
        requested_at=requested_at,
        complete_decision_support=False,
        code_sha="c" * 40,
    )

    assert len(runtime.runs) == 1
    run, steps, dependencies, _ = runtime.runs[0]
    assert run.requested_at == requested_at
    assert run.decision_time == simulated_decision_time
    assert run.runtime_mode.value == "HISTORICAL"
    assert tuple(item.step_kind for item in steps) == (
        "BUILD_CANDIDATE_SET",
        "OPEN_DECISION_RUN",
        "ASSESS_CONTEXT",
    )
    assert len(dependencies) == 2
    assert runtime.started[0][0] == runtime_run_id


def test_decision_operations_rejects_noncanonical_code_sha() -> None:
    with pytest.raises(ValueError, match="exact Git SHA"):
        Wp17pDecisionOperations(SimpleNamespace(), code_sha="F" * 40)
