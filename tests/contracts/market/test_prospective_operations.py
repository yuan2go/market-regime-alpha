from io import StringIO
from importlib import import_module
import json
import pytest

from market_regime_alpha.interfaces.cli import main


def test_serve_without_pinned_operation_configuration_cannot_start(monkeypatch):
    module = import_module(main.__module__)
    calls = []
    monkeypatch.setattr(module, "_dispatch", lambda *_: calls.append("business tick"))
    output, errors = StringIO(), StringIO()
    result = main([
        "archive", "prospective", "serve", "--series-code", "series",
        "--code-sha", "1" * 40, "--expected-database-name", "mra_operational",
        "--actor-id", "operator", "--worker-id", "worker",
        "--wakeup-seconds", "1", "--maximum-wakeups", "1",
    ], environ={"MRA_DATABASE_URL": "postgresql://localhost/mra_operational",
                "MRA_ARTIFACT_ROOT": "/unused-by-rejected-request"},
       stdout=output, stderr=errors)
    assert result == 2
    assert calls == []
    assert "operation-config" in errors.getvalue()


def test_operation_configuration_is_closed_and_cannot_hide_bad_limits(tmp_path):
    from market_regime_alpha.interfaces.prospective_operations import load_operation_config

    path = tmp_path / "operation.json"
    path.write_text(json.dumps({"version": 1, "database_url": "secret", "maximum_attempts_per_tick": 0}))
    with pytest.raises(ValueError, match="configuration"):
        load_operation_config(path)


def test_nonexistent_configuration_cannot_dispatch_even_when_name_matches(monkeypatch, tmp_path):
    module = import_module(main.__module__)
    calls = []
    monkeypatch.setattr(module, "_dispatch", lambda *_: calls.append("business tick"))
    errors = StringIO()
    result = main([
        "archive", "prospective", "serve", "--series-code", "series",
        "--code-sha", "1" * 40, "--expected-database-name", "mra_operational",
        "--actor-id", "operator", "--worker-id", "worker", "--wakeup-seconds", "1",
        "--maximum-wakeups", "1", "--operation-config", str(tmp_path / "absent.json"),
    ], environ={"MRA_DATABASE_URL": "postgresql://localhost/mra_operational",
                "MRA_ARTIFACT_ROOT": "/unused-by-rejected-request"},
       stdout=StringIO(), stderr=errors)
    assert result == 2
    assert calls == []
    assert "configuration" in errors.getvalue()


def test_provider_probe_has_no_capture_and_keeps_sdk_output_out_of_logs(capsys):
    from market_regime_alpha.interfaces.prospective_operation_guard import verify_provider_access
    from tests.contracts.market.test_baostock_archive_provider import _Sdk, _SdkResult

    class NoisySdk(_Sdk):
        def login(self):
            print("machine-local credential must never enter structured output")
            return super().login()
    sdk = NoisySdk(_SdkResult([], []))
    assert verify_provider_access(sdk, timeout_seconds=1) == {
        "provider": "BAOSTOCK_EXPLORATORY", "access": "LOGIN_LOGOUT_SUCCEEDED",
        "capture_proven": False, "maximum_attempts": 1,
    }
    assert [call[0] for call in sdk.calls] == ["login", "logout"]
    assert capsys.readouterr().out == ""


def test_provider_probe_fails_closed_without_retry_or_raw_provider_message():
    from market_regime_alpha.interfaces.prospective_operation_guard import verify_provider_access
    from tests.contracts.market.test_baostock_archive_provider import _Sdk, _SdkResult
    sdk = _Sdk(_SdkResult([], []), login_code="429")
    with pytest.raises(ValueError, match="OPERATION_PROVIDER_ACCESS_UNAVAILABLE"):
        verify_provider_access(sdk, timeout_seconds=1)
    assert [call[0] for call in sdk.calls] == ["login", "logout"]


def test_alert_changes_are_deduplicated_and_resolution_remains_visible():
    from market_regime_alpha.interfaces.prospective_service import OperationAlertChanges
    changes = OperationAlertChanges()
    assert changes.observe(()) == ()
    alert = {"reason_code": "MISSED_WINDOWS", "count": 2, "severity": "WARNING"}
    assert changes.observe((alert,)) == ({**alert, "change": "OPENED"},)
    assert changes.observe((alert,)) == ()
    updated = {**alert, "count": 3}
    assert changes.observe((updated,)) == ({**updated, "change": "UPDATED"},)
    assert changes.observe(()) == ({"reason_code": "MISSED_WINDOWS", "change": "RESOLVED"},)
    assert changes.observe(()) == ()
