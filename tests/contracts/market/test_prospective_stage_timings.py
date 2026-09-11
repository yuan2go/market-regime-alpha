"""Stage diagnostics preserve exception identity, budgets and owner ordering."""

from contextlib import contextmanager
from importlib import import_module
from io import StringIO
import json
from types import SimpleNamespace

import psycopg
import pytest

from market_regime_alpha.interfaces.daily_research import encode_daily_plan
from tests.contracts.research_qualification.test_daily_prediction import plan


@pytest.fixture
def stage_cli(tmp_path, monkeypatch):
    module = import_module("market_regime_alpha.interfaces.cli.main")
    frozen = plan()
    path = tmp_path / "frozen-daily.json"
    path.write_bytes(encode_daily_plan(frozen))
    configuration = SimpleNamespace(series_code="stage-fixture", code_sha=frozen.code_sha, actor_id="operator",
        worker_id="worker", lease_seconds=120, wakeup_seconds=0.001, database_name="disposable",
        provider_timeout_seconds=1, maximum_attempts_per_tick=2, maximum_tick_seconds=120,
        provider_maximum_rows=100_000, provider_maximum_response_bytes=33_554_432,
        content_sha256="2"*64, backup_receipt_sha256="3"*64)
    control = {"fail": None, "bootstrap_count": 0}
    calls = []
    def action(name, result=None):
        calls.append(name)
        if control["fail"] == name:
            raise psycopg.errors.QueryCanceled("do not expose postgresql://principal:PRIVATE_PASSWORD@host/db")
        return result
    guard = SimpleNamespace(verify_startup=lambda _: action("guard_preflight", {"ready": True}),
                            snapshot=lambda: action("tick_scope"), validate_scope=lambda _: action("composition_scope"),
                            before_action=lambda: action("before_action"), backup_snapshot_at=None, backup_verified_at=None,
                            session=SimpleNamespace(allow_expired_daily_recovery=lambda *_: None))
    health = {"database": {"name": "disposable", "oid": 1}, "observed_at": "database-clock",
              "summary": {"alerts": (), "operational_state": "NOT_DUE"}, "scopes": {"ALL_HISTORY": {"state": "AVAILABLE"}}}
    application = SimpleNamespace(evidence=SimpleNamespace(inventory=lambda: {}),
        prospective_health=SimpleNamespace(inspect=lambda *_args, **_kwargs: action("prospective_health", health)),
        daily_prediction_reads=SimpleNamespace(validate_configuration=lambda _: action("daily_preparation")))
    @contextmanager
    def session(*_):
        action("supervisor_scope")
        yield guard
    @contextmanager
    def bootstrap(_):
        control["bootstrap_count"] += 1
        action("startup_bootstrap" if control["bootstrap_count"] == 1 else "tick_bootstrap")
        yield application
    def continuation(_application, **kwargs):
        kwargs["before_action"]()
        return action("prospective_continuation", {"state": "NO_DUE_WORK"})
    def daily(_application, _template, _provider, **kwargs):
        kwargs["before_action"]()
        return action("daily_research", {"state": "FROZEN_OWNER_WORK_UNCHANGED"})
    monkeypatch.setattr(module, "load_operation_config", lambda _: configuration)
    monkeypatch.setattr(module, "require_installation", lambda _: action("installed_profile"))
    monkeypatch.setattr(module, "operational_session", session)
    monkeypatch.setattr(module, "bootstrap_application", bootstrap)
    monkeypatch.setattr(module, "verify_provider_access", lambda *_args, **_kwargs: action("provider_login", {"access": "fixture"}))
    monkeypatch.setattr(module, "continue_prospective_series", continuation)
    monkeypatch.setattr("market_regime_alpha.interfaces.daily_service.prepare_pending_daily_recovery", lambda *_: None)
    monkeypatch.setattr("market_regime_alpha.interfaces.daily_service.daily_tick", daily)
    monkeypatch.setattr("market_regime_alpha.notifications.build_notifiers", lambda **_: ([], []))
    monkeypatch.setattr("market_regime_alpha.interfaces.daily_health.daily_health", lambda *_args, **_kwargs: action("daily_health", {"ledger": []}))
    def invoke(*, preflight=False):
        common = ["--operation-config", "isolated-profile.json", "--daily-plan-template", str(path),
                  "--expected-database-name", configuration.database_name]
        if preflight:
            arguments = ["archive", "prospective", "preflight", *common]
        else:
            arguments = ["archive", "prospective", "serve", *common, "--series-code", configuration.series_code,
                         "--code-sha", configuration.code_sha, "--actor-id", "operator", "--worker-id", "worker",
                         "--wakeup-seconds", "0.001", "--maximum-wakeups", "1"]
        output, error = StringIO(), StringIO()
        result = module.main(arguments, environ={"MRA_DATABASE_URL": "postgresql://localhost/disposable", "MRA_ARTIFACT_ROOT": str(tmp_path)},
                             stdout=output, stderr=error)
        return result, [json.loads(line) for line in output.getvalue().splitlines()], error.getvalue()
    return control, calls, invoke, configuration


def test_successful_daily_tick_reports_disjoint_parent_stages_and_inclusive_guard(stage_cli):
    _control, calls, invoke, configuration = stage_cli
    status, rows, error = invoke()
    assert status == 0, error
    assert configuration.maximum_tick_seconds == 120
    tick = rows[1]
    assert tick["event"] == "PROSPECTIVE_TICK"
    assert set(tick["stage_timings"]) == {"installation_scope_checks", "bootstrap_scope", "before_action_guard",
                                          "prospective_continuation", "daily_research", "prospective_health", "daily_health"}
    stages = tick["stage_timings"]
    assert stages["before_action_guard"]["count"] == 2
    assert stages["before_action_guard"]["inclusive_child"] is True
    assert stages["before_action_guard"]["add_to_other_stage_totals"] is False
    assert stages["daily_research"]["add_to_other_stage_totals"] is True
    assert stages["before_action_guard"]["elapsed_seconds"] <= stages["prospective_continuation"]["elapsed_seconds"] + stages["daily_research"]["elapsed_seconds"]
    assert calls.index("prospective_continuation") < calls.index("daily_research") < calls.index("prospective_health") < calls.index("daily_health")
    assert all(stage["failed_count"] == 0 and stage["elapsed_seconds"] >= 0 for stage in stages.values())


@pytest.mark.parametrize("failure,phase,stage", (
    ("installed_profile", "STARTUP", "installed_profile"),
    ("supervisor_scope", "STARTUP", "supervisor_scope"),
    ("startup_bootstrap", "STARTUP", "bootstrap_scope"),
    ("daily_preparation", "STARTUP", "daily_preparation"),
    ("guard_preflight", "STARTUP", "guard_preflight_principal_artifact_backup"),
    ("provider_login", "STARTUP", "provider_login"),
    ("tick_scope", "TICK", "installation_scope_checks"),
    ("tick_bootstrap", "TICK", "bootstrap_scope"),
    ("prospective_continuation", "TICK", "prospective_continuation"),
    ("daily_research", "TICK", "daily_research"),
    ("prospective_health", "TICK", "prospective_health"),
    ("daily_health", "TICK", "daily_health"),
))
def test_query_cancellation_emits_exact_failure_stage_without_retry_or_secret(stage_cli, failure, phase, stage):
    control, calls, invoke, configuration = stage_cli
    control["fail"] = failure
    status, rows, error = invoke()
    assert status == 2
    assert configuration.maximum_tick_seconds == 120
    failures = [row for row in rows if row.get("event") == "PROSPECTIVE_STAGE_FAILURE"]
    assert len(failures) == 1
    assert failures[0]["stage"] == stage and failures[0]["phase"] == phase
    assert failures[0]["error_type"] == "QueryCanceled"
    assert failures[0]["stage_elapsed_seconds"] >= 0
    assert failures[0]["stage_timings"][stage]["failed_count"] == 1
    assert failures[0]["tick_sequence"] == (1 if phase == "TICK" else None)
    assert all(row.get("event") != "PROSPECTIVE_TICK" for row in rows)
    assert calls.count(failure) == 1
    assert "PRIVATE_PASSWORD" not in json.dumps(rows) + error
    assert json.loads(error)["message"] == "OPERATION_FAILED_CLOSED_RECONCILE_BEFORE_RESTART"


def test_nested_guard_failure_is_marked_child_and_keeps_parent_elapsed(stage_cli):
    control, calls, invoke, _configuration = stage_cli
    control["fail"] = "before_action"
    status, rows, _error = invoke()
    assert status == 2
    failures = [row for row in rows if row.get("event") == "PROSPECTIVE_STAGE_FAILURE"]
    assert [row["stage"] for row in failures] == ["before_action_guard", "prospective_continuation"]
    assert failures[0]["inclusive_child"] is True
    assert failures[1]["inclusive_child"] is False
    assert failures[0]["stage_elapsed_seconds"] <= failures[1]["stage_elapsed_seconds"]
    assert calls.count("before_action") == 1
    assert "daily_research" not in calls


def test_preflight_output_times_its_actual_health_without_starting_tick(stage_cli):
    _control, calls, invoke, _configuration = stage_cli
    status, rows, error = invoke(preflight=True)
    assert status == 0, error
    assert len(rows) == 1
    assert rows[0]["ready"] is True
    assert rows[0]["stage_timings"]["prospective_health"]["count"] == 1
    assert "prospective_continuation" not in calls
    assert "daily_research" not in calls
