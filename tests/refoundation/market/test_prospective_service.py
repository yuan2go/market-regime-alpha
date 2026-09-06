from __future__ import annotations

from io import StringIO
import json
import os
import signal
from threading import Event

import pytest

from market_regime_alpha.interfaces.cli import main as cli_main


def test_service_uses_the_existing_continuation_for_each_wakeup(monkeypatch):
    from market_regime_alpha.interfaces.cli import main
    from importlib import import_module

    module = import_module(main.__module__)
    calls = []

    def dispatch(arguments, settings):
        calls.append((arguments.prospective_command, settings.database_url))
        return {"due_attempt_count": 0, "observed_at": "database-clock"}

    monkeypatch.setattr(module, "_dispatch", dispatch)
    output, errors = StringIO(), StringIO()
    result = cli_main([
        "archive", "prospective", "serve", "--series-code", "series",
        "--code-sha", "1" * 40, "--expected-database-name", "mra_operational",
        "--actor-id", "operator", "--worker-id", "worker",
        "--wakeup-seconds", "0.001", "--maximum-wakeups", "2",
    ], environ={"MRA_DATABASE_URL": "postgresql://localhost/mra_operational",
                "MRA_ARTIFACT_ROOT": "/evidence/artifacts"}, stdout=output, stderr=errors)
    assert result == 0, errors.getvalue()
    assert calls == [("continue", "postgresql://localhost/mra_operational")] * 2
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[:2] == [{"due_attempt_count": 0, "observed_at": "database-clock"}] * 2
    assert rows[2] == {"stop_reason": "WAKEUP_LIMIT", "completed_wakeups": 2}


def test_service_does_not_retry_an_unknown_tick_effect():
    from market_regime_alpha.interfaces.prospective_service import serve_prospective

    calls = []

    def unknown():
        calls.append("effect")
        raise OSError("commit acknowledgement lost")

    with pytest.raises(OSError, match="acknowledgement"):
        serve_prospective(unknown, emit=lambda value: None, wakeup_seconds=1,
                          maximum_wakeups=2)
    assert calls == ["effect"]


def test_shutdown_finishes_current_tick_without_starting_another():
    from market_regime_alpha.interfaces.prospective_service import serve_prospective

    stop = Event()
    emitted = []

    def tick():
        stop.set()
        return {"terminal_fact": "committed"}

    result = serve_prospective(tick, emit=emitted.append, wakeup_seconds=60,
                               maximum_wakeups=5, stop=stop)
    assert emitted == [{"terminal_fact": "committed"}]
    assert result == {"stop_reason": "STOP_REQUESTED", "completed_wakeups": 1}


def test_sigterm_drains_tick_restores_handlers_and_restart_reenters_owner():
    from market_regime_alpha.interfaces.prospective_service import serve_prospective

    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    calls = []
    emitted = []

    def tick():
        calls.append("owner-reconciliation")
        os.kill(os.getpid(), signal.SIGTERM)
        calls.append("commit")
        return "completed"

    for _ in range(2):
        assert serve_prospective(tick, emit=emitted.append, wakeup_seconds=60) == {
            "stop_reason": "STOP_REQUESTED", "completed_wakeups": 1,
        }
        assert {number: signal.getsignal(number) for number in previous} == previous
    assert calls == ["owner-reconciliation", "commit"] * 2
    assert emitted == ["completed", "completed"]


@pytest.mark.parametrize("seconds,limit", [(0, 1), (-1, 1), (float("nan"), 1),
                                         (float("inf"), 1), (1, 0), (1, -1)])
def test_invalid_lifecycle_limits_fail_before_tick(seconds, limit):
    from market_regime_alpha.interfaces.prospective_service import serve_prospective

    def forbidden():
        pytest.fail("invalid configuration started a business tick")

    with pytest.raises(ValueError):
        serve_prospective(forbidden, emit=lambda value: None, wakeup_seconds=seconds,
                          maximum_wakeups=limit)
