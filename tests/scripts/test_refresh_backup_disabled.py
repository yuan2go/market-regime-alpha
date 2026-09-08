"""The installed project lifecycle must honor either launchctl disabled format."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
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
