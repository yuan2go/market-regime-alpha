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

from tests.contracts.test_installed_identity import installed_scope  # noqa: F401


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


@pytest.mark.parametrize("case", ["current", "old-profile", "stopped", "over-budget", "wrong-tick-profile", "wrong-backup", "old-tick", "stopped-after-tick"])
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
        {"event": "PROSPECTIVE_TICK", "observed_at": (started_at if case == "old-tick" else datetime.now(timezone.utc)).isoformat(),
         "configuration_sha256": "old" if case == "wrong-tick-profile" else "current",
         "backup_observation": {"receipt_sha256": "old" if case == "wrong-backup" else "backup"},
         "tick_elapsed_seconds": 121 if case == "over-budget" else 50},
    ]
    if case == "stopped-after-tick":
        rows.append({"stop_reason": "TICK_BUDGET_EXCEEDED"})
    (tmp_path / "logs/service-observed.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    config = SimpleNamespace(content_sha256="current", backup_receipt_sha256="backup", maximum_tick_seconds=120, wakeup_seconds=30)
    identity = {"pid": 123, "uid": os.getuid(), "started": "Fri Sep 11 08:30:00 2026",
                "command_sha256": "c" * 64, "command_kind": "CANONICAL_SERVICE"}
    monkeypatch.setattr(module, "owned_job", lambda **_: None if case == "stopped" else identity)
    ticks = iter((0, 0, 181))
    monkeypatch.setattr(module, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(module, "sleep", lambda _: None)
    if case == "current":
        module.observe_restarted_tick(config, started_at=started_at)
        assert json.loads((module.RECORDS / "subsequent-tick.json").read_text()) == rows[1]
        assert module.events[-1]["phase"] == "subsequent-tick"
        assert module.events[-1]["configuration_sha256"] == "current"
        assert module.events[-1]["backup_receipt_sha256"] == "backup"
        assert module.events[-1]["owned_service_identity"] == identity
    else:
        expected = {"old-profile": "NOT_OBSERVED", "stopped": "NOT_OBSERVED", "over-budget": "EXCEEDED_BUDGET",
                    "wrong-tick-profile": "NOT_OBSERVED", "wrong-backup": "NOT_OBSERVED", "old-tick": "NOT_OBSERVED",
                    "stopped-after-tick": "SERVICE_STOPPED"}[case]
        with pytest.raises(ValueError, match=expected):
            module.observe_restarted_tick(config, started_at=started_at)
        assert not (module.RECORDS / "subsequent-tick.json").exists()


@pytest.fixture
def refresh_module(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[2] / "docs/operations/templates"
    for name in ("refresh_backup.py", "verify_prospective_artifacts.py"):
        shutil.copy2(source / name, tmp_path / name)
    (tmp_path / "receipts").mkdir()
    (tmp_path / "deployment.json").write_text(json.dumps({
        "uid": os.getuid(), "label": "local.mra.prospective.r2-xshg32",
        "uv": "/uv", "runtime_python": "/runtime/python", "mra_executable": "/runtime/mra",
    }))
    monkeypatch.syspath_prepend(str(tmp_path))
    spec = importlib.util.spec_from_file_location("owned_refresh_test", tmp_path / "refresh_backup.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backup_renewal_reverifies_real_installed_guard_without_weakening_profile_pin(refresh_module, request, monkeypatch):
    from dataclasses import replace
    from hashlib import sha256
    from market_regime_alpha.interfaces import deployment_profile
    from market_regime_alpha.interfaces.prospective_operation_guard import ProspectiveOperationGuard
    from market_regime_alpha.shared.hashing import canonical_json_sha256

    scope = request.getfixturevalue("installed_scope")
    now = datetime.now(timezone.utc)
    session = SimpleNamespace(connection=object(), require_supervisor_lock=lambda _: None, clock=lambda: now)
    monkeypatch.setattr(deployment_profile, "inspect_runtime_principal", lambda _: {"name": "restricted-runtime", "oid": 42})
    def inspect_synthetic_dump(command, **kwargs):
        # Only the external archive listing is a fixture; every guard/profile,
        # wheel/receipt hash, Artifact check and backup byte check runs unchanged.
        assert command[:2] == ["pg_restore", "--list"] and kwargs["check"]
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("market_regime_alpha.interfaces.prospective_operation_guard.subprocess.run", inspect_synthetic_dump)
    original = ProspectiveOperationGuard(scope.settings, scope.config, session)
    original.verify_runtime_principal()
    assert len(scope.calls) == 1
    destination = scope.settings.artifact_root.parent / "renewed-backup"
    destination.mkdir()
    (destination / "artifacts").mkdir()
    dump = b"SYNTHETIC_ONLY_BACKUP_BYTES"
    (destination / "database.dump").write_bytes(dump)
    database = {"name": scope.config.database_name, "oid": scope.config.database_oid, "cluster_identity": scope.config.cluster_identity}
    schema = {"epoch": scope.config.schema_epoch, "baseline_checksum": scope.config.baseline_checksum, "catalog_checksum": scope.config.catalog_checksum}
    inventory = {"database": database, "schema": schema, "observed_at": now.isoformat(), "artifacts": []}
    inventory_bytes = json.dumps(inventory).encode()
    (destination / "inventory.json").write_bytes(inventory_bytes)
    receipt = {"database": database, "source_artifact_root": str(scope.settings.artifact_root),
        "snapshot_contract": "POSTGRES_EXPORTED_SNAPSHOT_AND_EXACT_ARTIFACT_ROSTER", "backup_sha256": sha256(dump).hexdigest(),
        "backup_size_bytes": len(dump), "inventory_sha256": sha256(inventory_bytes).hexdigest(),
        "artifact_roster_sha256": canonical_json_sha256([]), "artifact_count": 0, "verified_at": now.isoformat()}
    receipt_bytes = json.dumps(receipt).encode()
    (destination / "receipt.json").write_bytes(receipt_bytes)
    updated = replace(scope.config, backup_directory=str(destination), backup_sha256=receipt["backup_sha256"], backup_receipt_sha256=sha256(receipt_bytes).hexdigest())
    # This is the original failure: a same-process cached identity must reject it.
    original.config = updated
    with pytest.raises(ValueError, match="INSTALLATION_PROFILE_CHANGED"):
        original.verify_backup(inventory)
    original.config = scope.config
    renewed = refresh_module.renewed_backup_guard(original, updated, inventory)
    assert renewed is not original and renewed.session is original.session
    assert renewed.config == updated and original.config == scope.config
    assert len(scope.calls) == 2  # actual wheel, receipt, installed-file hashing
    renewed.check_resources()
    assert len(scope.calls) == 2
    with pytest.raises(ValueError, match="BACKUP_RENEWAL_SCOPE_CHANGED"):
        refresh_module.renewed_backup_guard(original, replace(updated, maximum_tick_seconds=121), inventory)
    renewed.config = replace(updated, backup_sha256="0" * 64)
    with pytest.raises(ValueError, match="INSTALLATION_PROFILE_CHANGED"):
        renewed.check_resources()


@pytest.mark.parametrize("change", ["pid", "started", "command", "uid"])
def test_owned_job_rejects_stale_or_foreign_process(refresh_module, monkeypatch, change):
    module = refresh_module
    args = module.MRA + ["archive", "prospective", "serve", "--operation-config", str(module.PROFILE)]
    values = {"pid": 123, "started": "Fri Sep 11 08:30:00 2026", "command": " ".join(args), "uid": os.getuid()}
    monkeypatch.setattr(module, "job", lambda: values["pid"])
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=f'{values["uid"]} {values["started"]} {values["command"]}'))
    identity = module.owned_job()
    assert identity["pid"] == 123
    values[change] = {"pid": 124, "started": "Fri Sep 11 09:30:00 2026", "command": "/bin/sleep 100", "uid": os.getuid() + 1}[change]
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH|STALE_OR_REPLACED"):
        module.owned_job(expected=identity)


def test_graceful_exit_during_process_inspection_is_not_an_identity_failure(refresh_module, monkeypatch):
    observed = iter((123, 0))
    monkeypatch.setattr(refresh_module, "job", lambda: next(observed))
    monkeypatch.setattr(refresh_module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=""))
    assert refresh_module.owned_job() is None


@pytest.mark.parametrize("source", ["verified", "foreign", "absent"])
def test_scheduled_fire_requires_actual_backup_launchagent_process(refresh_module, monkeypatch, source):
    module = refresh_module
    class ScheduledClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 11, 11, tzinfo=timezone.utc)
    monkeypatch.setattr(module, "datetime", ScheduledClock)
    monkeypatch.setattr(sys, "argv", ["refresh_backup.py", "--scheduled"])
    def inspect_only(args, **_):
        if args[1] == "print":
            return SimpleNamespace(returncode=1 if source == "absent" else 0,
                stdout=f'pid = {os.getppid() if source == "verified" else 99999999}\n')
        assert args[1] == "print-disabled"
        return SimpleNamespace(stdout='"local.mra.prospective.r2-xshg32" => true')
    monkeypatch.setattr(module.subprocess, "run", inspect_only)
    with pytest.raises(ValueError, match="INTENTIONALLY_DISABLED" if source == "verified" else "FIRE_SOURCE_UNVERIFIED"):
        module.main()
    invocations = [event for event in module.events if event["phase"] == "invocation"]
    assert len(invocations) == (1 if source == "verified" else 0)
    if invocations:
        assert invocations[0]["invocation_kind"] == "SCHEDULED"
        assert invocations[0]["maximum_restart_requests"] == 1


def test_owned_backup_job_kick_outside_window_cannot_claim_scheduled(refresh_module, monkeypatch):
    class OutsideScheduleClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 11, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(refresh_module, "datetime", OutsideScheduleClock)
    monkeypatch.setattr(sys, "argv", ["refresh_backup.py", "--scheduled"])
    monkeypatch.setattr(refresh_module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=f"pid = {os.getppid()}\n"))
    with pytest.raises(ValueError, match="FIRE_WINDOW_UNVERIFIED"):
        refresh_module.main()
    assert not any(row.get("invocation_kind") == "SCHEDULED" for row in refresh_module.events)


def test_template_restart_proof_is_verifiable_by_actual_read_only_summary(refresh_module, monkeypatch):
    from market_regime_alpha.interfaces.operational_reliability import scheduled_backup_reliability

    module = refresh_module
    (module.HERE / "logs").mkdir()
    profile, backup = "a" * 64, "b" * 64
    config = SimpleNamespace(content_sha256=profile, backup_receipt_sha256=backup, maximum_tick_seconds=120, wakeup_seconds=30)
    identity = {"pid": 123, "uid": os.getuid(), "started": "Fri Sep 11 08:30:00 2026",
                "command_sha256": "c" * 64, "command_kind": "CANONICAL_SERVICE"}
    module.event("invocation", invocation_kind="MANUAL_CONTROLLED_RECOVERY")
    module.event("profile-advanced", configuration_sha256=profile, backup_receipt_sha256=backup)
    started_at = datetime.now(timezone.utc)
    rows = [{"event": "PROSPECTIVE_PREFLIGHT", "configuration_sha256": profile, "observed_at": datetime.now(timezone.utc).isoformat()},
            {"event": "PROSPECTIVE_TICK", "configuration_sha256": profile, "observed_at": datetime.now(timezone.utc).isoformat(),
             "backup_observation": {"receipt_sha256": backup}, "tick_elapsed_seconds": 50}]
    (module.HERE / "logs/service-observed.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    monkeypatch.setattr(module, "owned_job", lambda **_: identity)
    module.observe_restarted_tick(config, started_at=started_at)
    module.event("complete", status="PASS")
    observed = scheduled_backup_reliability(module.RECORDS.parent)
    assert observed["receipts"][0]["restart_verified"]
    assert observed["manual_receipt_count"] == 1 and observed["SCHEDULED_BACKUP_RELIABILITY"]["completed"] == 0
    assert observed["business_writes"] == 0
    (module.RECORDS / "subsequent-tick.json").unlink()
    refused = scheduled_backup_reliability(module.RECORDS.parent)
    assert not refused["receipts"][0]["restart_verified"]
    assert refused["receipts"][0]["reason_code"] == "BACKUP_RESTART_PROOF_ARTIFACT_MISSING"
