"""The installed project lifecycle must honor either launchctl disabled format."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("disabled_value", ["true", "disabled"])
def test_refresh_never_restarts_an_explicitly_disabled_project(tmp_path, monkeypatch, disabled_value):
    source = Path(__file__).resolve().parents[2] / "docs/operations/templates"
    for name in ("refresh_backup.py", "verify_prospective_artifacts.py"):
        shutil.copy2(source / name, tmp_path / name)
    (tmp_path / "receipts").mkdir()
    (tmp_path / "deployment.json").write_text(json.dumps({
        "uid": os.getuid(), "label": "local.mra.prospective.r2-xshg32",
        "uv": "uv", "runtime_python": "unused", "mra_executable": "unused",
    }))
    monkeypatch.syspath_prepend(str(tmp_path))
    spec = importlib.util.spec_from_file_location("project_refresh_test", tmp_path / "refresh_backup.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["refresh_backup.py", "--recover-stopped"])

    def inspect_only(command, **_):
        assert command == ["launchctl", "print-disabled", f"gui/{os.getuid()}"]
        return SimpleNamespace(stdout='"local.mra.prospective.r2-xshg32" => ' + disabled_value)

    monkeypatch.setattr(module.subprocess, "run", inspect_only)
    with pytest.raises(ValueError, match="SERVICE_INTENTIONALLY_DISABLED"):
        module.main()


@pytest.mark.parametrize("case", ["current", "old-profile", "stopped", "over-budget"])
def test_refresh_requires_a_current_bounded_tick_before_restart_proof(tmp_path, monkeypatch, case):
    source = Path(__file__).resolve().parents[2] / "docs/operations/templates"
    for name in ("refresh_backup.py", "verify_prospective_artifacts.py"):
        shutil.copy2(source / name, tmp_path / name)
    (tmp_path / "receipts").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "deployment.json").write_text(json.dumps({
        "uid": os.getuid(), "label": "local.mra.prospective.r2-xshg32",
        "uv": "uv", "runtime_python": "unused", "mra_executable": "unused",
    }))
    monkeypatch.syspath_prepend(str(tmp_path))
    spec = importlib.util.spec_from_file_location("restart_proof_test", tmp_path / "refresh_backup.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    started_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    rows = [
        {"event": "PROSPECTIVE_PREFLIGHT", "configuration_sha256": "old" if case == "old-profile" else "current",
         "observed_at": datetime.now(timezone.utc).isoformat()},
        {"event": "PROSPECTIVE_TICK", "observed_at": datetime.now(timezone.utc).isoformat(),
         "tick_elapsed_seconds": 121 if case == "over-budget" else 50},
    ]
    (tmp_path / "logs/service-observed.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    config = SimpleNamespace(content_sha256="current", maximum_tick_seconds=120, wakeup_seconds=30)
    monkeypatch.setattr(module, "job", lambda: None if case == "stopped" else 123)
    ticks = iter((0, 0, 181))
    monkeypatch.setattr(module, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(module, "sleep", lambda _: None)
    if case == "current":
        module.observe_restarted_tick(config, started_at=started_at)
        assert json.loads((module.RECORDS / "subsequent-tick.json").read_text()) == rows[1]
        assert module.events[-1]["phase"] == "subsequent-tick"
    else:
        expected = {"old-profile": "NOT_OBSERVED", "stopped": "SERVICE_STOPPED", "over-budget": "EXCEEDED_BUDGET"}[case]
        with pytest.raises(ValueError, match=expected):
            module.observe_restarted_tick(config, started_at=started_at)
        assert not (module.RECORDS / "subsequent-tick.json").exists()
