from __future__ import annotations

from io import StringIO
import json
import os
import signal
import subprocess
from threading import Event

import pytest

from market_regime_alpha.interfaces.cli import main as cli_main


def test_service_uses_the_existing_continuation_for_each_wakeup(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from market_regime_alpha.interfaces.cli import main
    from importlib import import_module

    module = import_module(main.__module__)
    monkeypatch.setattr(module, "require_installation", lambda _: None)
    calls = []

    def continuation(application, **kwargs):
        kwargs["before_action"]()
        calls.append((kwargs["series_code"], kwargs["maximum_attempts"], kwargs["provider_timeout_seconds"]))
        return {"due_attempt_count": 0, "observed_at": "database-clock"}

    configuration = SimpleNamespace(series_code="series", code_sha="1"*40, actor_id="operator",
        worker_id="worker", lease_seconds=120, wakeup_seconds=0.001, database_name="mra_operational",
        provider_timeout_seconds=1, maximum_attempts_per_tick=2, maximum_tick_seconds=60,
        provider_maximum_rows=100_000, provider_maximum_response_bytes=33_554_432,
        content_sha256="2"*64, backup_receipt_sha256="3"*64)
    guard_calls = []
    guard = SimpleNamespace(
        verify_startup=lambda app: {"ready": True},
        snapshot=lambda: guard_calls.append("supervisor"),
        validate_scope=lambda scope: guard_calls.append("composition"),
        before_action=lambda: guard_calls.append("claim"),
        backup_snapshot_at=None, backup_verified_at=None,
    )
    health = {"database": {"name": "mra_operational", "oid": 1}, "observed_at": "database-clock",
              "summary": {"alerts": (), "operational_state": "NOT_DUE"},
              "scopes": {"ALL_HISTORY": {"state": "AVAILABLE"}}}
    def inspect_after_owner_recovery(_, *, cutover_at):
        assert cutover_at is None
        # A prior process may stop after Archive predeclaration but before
        # every capture Runtime registration. Strict health cannot yet pass;
        # the existing continuation must repair that roster first.
        if not calls:
            raise ValueError("incomplete Runtime roster before canonical recovery")
        return health
    application = SimpleNamespace(
        evidence=SimpleNamespace(inventory=lambda: {"scope": "canonical"}),
        prospective_health=SimpleNamespace(inspect=inspect_after_owner_recovery),
    )
    @contextmanager
    def session(*_):
        yield guard
    @contextmanager
    def bootstrap(settings):
        assert settings.database_url == "postgresql://localhost/mra_operational"
        yield application
    monkeypatch.setattr(module, "operational_session", session)
    monkeypatch.setattr(module, "bootstrap_application", bootstrap)
    monkeypatch.setattr(module, "load_operation_config", lambda _: configuration)
    monkeypatch.setattr(module, "verify_provider_access", lambda *_, **__: {"access": "fixture"})
    monkeypatch.setattr(module, "continue_prospective_series", continuation)
    output, errors = StringIO(), StringIO()
    result = cli_main([
        "archive", "prospective", "serve", "--series-code", "series",
        "--code-sha", "1" * 40, "--expected-database-name", "mra_operational",
        "--actor-id", "operator", "--worker-id", "worker",
        "--wakeup-seconds", "0.001", "--maximum-wakeups", "2",
        "--operation-config", "machine-local-operation.json",
    ], environ={"MRA_DATABASE_URL": "postgresql://localhost/mra_operational",
                "MRA_ARTIFACT_ROOT": "/evidence/artifacts"}, stdout=output, stderr=errors)
    assert result == 0, errors.getvalue()
    assert calls == [("series", 2, 1)] * 2
    assert guard_calls == ["supervisor", "composition", "claim"] * 2
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[0]["event"] == "PROSPECTIVE_PREFLIGHT"
    assert [row["continuation"] for row in rows[1:3]] == [{"due_attempt_count": 0, "observed_at": "database-clock"}] * 2
    assert rows[1]["configuration_sha256"] == "2"*64
    assert rows[1]["alert_changes"] == rows[2]["alert_changes"] == []
    assert rows[3] == {"stop_reason": "WAKEUP_LIMIT", "completed_wakeups": 2}


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


def test_exceeded_tick_budget_drains_committed_result_and_stops_before_next(monkeypatch):
    from importlib import import_module
    module = import_module("market_regime_alpha.interfaces.prospective_service")
    clock = iter((100.0, 106.0))
    monkeypatch.setattr(module, "monotonic", lambda: next(clock))
    emitted, calls = [], []
    def tick():
        calls.append("committed")
        return {"committed": True}
    result = module.serve_prospective(tick, emit=emitted.append, wakeup_seconds=1,
        maximum_wakeups=2, maximum_tick_seconds=5)
    assert result == {"stop_reason": "TICK_BUDGET_EXCEEDED", "completed_wakeups": 1,
                      "tick_elapsed_seconds": 6.0}
    assert calls == ["committed"]
    assert emitted == [{"committed": True}]


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


def test_signal_stop_is_visible_to_the_current_owner_action_boundary():
    from market_regime_alpha.interfaces.prospective_service import OperationStopRequest, serve_prospective
    request = OperationStopRequest()
    def tick():
        assert request.requested is False
        os.kill(os.getpid(), signal.SIGTERM)
        assert request.requested is True
        return "last-started-action-drained"
    assert serve_prospective(tick, emit=lambda _: None, wakeup_seconds=1, stop_request=request) == {
        "stop_reason": "STOP_REQUESTED", "completed_wakeups": 1,
    }


@pytest.mark.parametrize("signal_name", ["SIGINT", "SIGTERM"])
def test_signal_during_event_wait_cannot_reenter_its_lock(signal_name):
    # Deterministically deliver the signal in Event.wait's non-reentrant lock
    # window, in a disposable child so the regression cannot hang pytest.
    code = f'''
import os, signal
from threading import Event
from market_regime_alpha.interfaces.prospective_service import serve_prospective
class SignalDuringWait(Event):
    def wait(self, timeout=None):
        with self._cond:
            os.kill(os.getpid(), signal.{signal_name})
        return False
result = serve_prospective(lambda: "complete", emit=lambda value: None,
    wakeup_seconds=60, stop=SignalDuringWait())
assert result == {{"stop_reason": "STOP_REQUESTED", "completed_wakeups": 1}}
'''
    result = subprocess.run(["uv", "run", "--no-sync", "python", "-c", code],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("seconds,limit", [(0, 1), (-1, 1), (float("nan"), 1),
                                         (float("inf"), 1), (1, 0), (1, -1)])
def test_invalid_lifecycle_limits_fail_before_tick(seconds, limit):
    from market_regime_alpha.interfaces.prospective_service import serve_prospective

    def forbidden():
        pytest.fail("invalid configuration started a business tick")

    with pytest.raises(ValueError):
        serve_prospective(forbidden, emit=lambda value: None, wakeup_seconds=seconds,
                          maximum_wakeups=limit)
