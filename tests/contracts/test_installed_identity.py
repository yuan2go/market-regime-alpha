"""Installed change detection uses real wheel bytes and disposable files only."""

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from zipfile import ZipFile

import pytest

import market_regime_alpha
from market_regime_alpha.bootstrap import TargetSettings
from market_regime_alpha.interfaces import deployment_profile as deployment
from market_regime_alpha.interfaces import installed_identity as identity
from market_regime_alpha.interfaces.prospective_operation_guard import ProspectiveOperationGuard
from market_regime_alpha.interfaces.prospective_operations import ProspectiveOperationConfig, implementation_source_sha256


@pytest.fixture
def installed_scope(tmp_path, monkeypatch):
    site = tmp_path / "site-packages"
    package = site / "market_regime_alpha"
    package.mkdir(parents=True)
    sources = {"__init__.py": b"x = 1\n", "schema.sql": b"SELECT 1;\n", "protocol.json": b'{"version":1}\n'}
    metadata = site / "market_regime_alpha-0.1.0.dist-info"
    metadata.mkdir()
    metadata_bytes = {"METADATA": b"Metadata-Version: 2.1\nName: market-regime-alpha\nVersion: 0.1.0\n",
                      "WHEEL": b"Wheel-Version: 1.0\n", "entry_points.txt": b"[console_scripts]\nmra = package:main\n"}
    wheel = tmp_path / "mra.whl"
    with ZipFile(wheel, "w") as archive:
        for name, content in sources.items():
            (package / name).write_bytes(content)
            archive.writestr(f"market_regime_alpha/{name}", content)
        for name, content in metadata_bytes.items():
            (metadata / name).write_bytes(content)
            archive.writestr(f"{metadata.name}/{name}", content)
    installed = SimpleNamespace(locate_file=lambda name: site / name,
                                read_text=lambda name: (metadata / name).read_text() if (metadata / name).is_file() else None,
                                metadata={"Name": "market-regime-alpha"}, version="0.1.0")
    monkeypatch.setattr(market_regime_alpha, "__file__", str(package / "__init__.py"))
    monkeypatch.setattr(deployment, "distribution", lambda _: installed)
    monkeypatch.setattr(deployment, "distributions", lambda: (installed,))
    monkeypatch.setattr(identity, "_metadata_roots", lambda: tuple(sorted(site.glob("*.dist-info"))))
    config = ProspectiveOperationConfig(
        version=1, database_name="disposable-scope", database_oid=1, cluster_identity="123",
        schema_epoch="MRA_REFOUNDATION_1", baseline_checksum="a" * 64, catalog_checksum="b" * 64,
        artifact_root_binding_sha256="c" * 64, source_sha256=implementation_source_sha256(),
        series_code="identity-test", target_definition_id=str(UUID(int=1)), target_sha256="d" * 64,
        backup_directory=str(tmp_path / "backup"), backup_sha256="e" * 64, backup_receipt_sha256="f" * 64,
        maximum_backup_age_hours=24, minimum_free_bytes=1, minimum_calendar_sessions=3,
        maximum_pool_connections=4, provider_kind="BAOSTOCK_EXPLORATORY", provider_timeout_seconds=1,
        provider_maximum_rows=1000, provider_maximum_response_bytes=1000, maximum_attempts_per_tick=1,
        maximum_tick_seconds=120, code_sha="1" * 40, actor_id="operator", worker_id="worker", lease_seconds=120,
        wakeup_seconds=30,
    )
    receipt = {"runtime_principal": {"name": "restricted-runtime", "oid": 42},
               "installation": {**deployment._installed(wheel), "source_sha": config.code_sha,
                                "wheel_path": str(wheel), "wheel_sha256": sha256(wheel.read_bytes()).hexdigest()},
               "scope": deployment._scope(config)}
    receipt_path = tmp_path / "deployment.receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    config = replace(config, version=2, deployment_receipt=str(receipt_path),
                     deployment_receipt_sha256=sha256(receipt_path.read_bytes()).hexdigest())
    calls = []
    def verify(current):
        calls.append(current.content_sha256)
        return deployment.require_installation(current)
    monkeypatch.setattr(identity, "require_installation", verify)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    return SimpleNamespace(config=config, package=package, metadata=metadata, wheel=wheel,
                           receipt=receipt_path, calls=calls, settings=TargetSettings("postgresql://unused", artifacts))


def test_hot_checks_reenumerate_identity_without_reading_hashed_content_and_restart_rehashes(installed_scope, monkeypatch):
    scope = installed_scope
    verified = identity.VerifiedInstallation.verify(scope.config)
    assert len(scope.calls) == 1
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", lambda _: pytest.fail("content read on unchanged hot path"))
        patch.setattr(Path, "read_text", lambda *_args, **_kwargs: pytest.fail("metadata content read on hot path"))
        for _ in range(3):
            verified.require_unchanged(scope.config)
    assert len(scope.calls) == 1
    restarted = identity.VerifiedInstallation.verify(scope.config)
    assert len(scope.calls) == 2
    restarted.require_unchanged(scope.config)


@pytest.mark.parametrize("filename", ("__init__.py", "schema.sql", "protocol.json"))
def test_same_size_tampering_with_restored_mtime_is_detected_by_ctime(installed_scope, filename):
    scope = installed_scope
    verified = identity.VerifiedInstallation.verify(scope.config)
    path = scope.package / filename
    previous = path.stat()
    content = path.read_bytes()
    path.write_bytes(bytes([content[0] ^ 1]) + content[1:])
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    assert path.stat().st_size == previous.st_size
    assert path.stat().st_mtime_ns == previous.st_mtime_ns
    with pytest.raises(ValueError, match="IMPLEMENTATION_CHANGED"):
        verified.require_unchanged(scope.config)
    with pytest.raises(ValueError, match="INSTALLED_PACKAGE_MISMATCH"):
        identity.VerifiedInstallation.verify(scope.config)


@pytest.mark.parametrize("change", ("add_python", "add_json", "delete", "replace", "symlink", "permissions", "hidden_source"))
def test_complete_package_roster_file_identity_and_permissions_cannot_drift(installed_scope, change):
    scope = installed_scope
    verified = identity.VerifiedInstallation.verify(scope.config)
    path = scope.package / "protocol.json"
    if change in {"add_python", "add_json"}:
        (scope.package / ("new_writer.py" if change == "add_python" else "new_protocol.json")).write_bytes(b"{}")
    elif change == "delete":
        path.unlink()
    elif change == "replace":
        replacement = scope.package / "replacement"
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
    elif change == "symlink":
        target = scope.package.parent / "external.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    elif change == "permissions":
        path.chmod(path.stat().st_mode ^ 0o100)
    else:
        cache = scope.package / "__pycache__"
        cache.mkdir()
        (cache / "hidden.py").write_bytes(b"pass\n")
    with pytest.raises(ValueError, match="IMPLEMENTATION_CHANGED|INSTALLATION_NON_REGULAR_PATH|UNEXPECTED_CACHE_CONTENT"):
        verified.require_unchanged(scope.config)


def test_normal_generated_bytecode_does_not_change_verified_source_identity(installed_scope):
    scope = installed_scope
    verified = identity.VerifiedInstallation.verify(scope.config)
    cache = scope.package / "__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-312.pyc").write_bytes(b"disposable bytecode")
    verified.require_unchanged(scope.config)
    (cache / "__init__.cpython-312.pyc").write_bytes(b"changed bytecode")
    verified.require_unchanged(scope.config)


@pytest.mark.parametrize("changed", ("receipt", "wheel", "metadata", "new_metadata"))
def test_receipt_wheel_and_distribution_metadata_remain_pinned(installed_scope, changed):
    scope = installed_scope
    verified = identity.VerifiedInstallation.verify(scope.config)
    if changed == "new_metadata":
        new = scope.metadata.parent / "unexpected-1.0.dist-info"
        new.mkdir()
        (new / "METADATA").write_text("Name: unexpected\nVersion: 1.0\n")
    else:
        path = {"receipt": scope.receipt, "wheel": scope.wheel, "metadata": scope.metadata / "METADATA"}[changed]
        previous = path.stat()
        content = path.read_bytes()
        path.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    with pytest.raises(ValueError, match="IMPLEMENTATION_CHANGED"):
        verified.require_unchanged(scope.config)


@pytest.mark.parametrize("field,value", (("source_sha256", "0" * 64), ("code_sha", "0" * 40), ("version", 1),
                                        ("database_oid", 2), ("maximum_tick_seconds", 121), ("backup_sha256", "0" * 64)))
def test_live_profile_fingerprint_cannot_be_changed_or_downgraded(installed_scope, field, value):
    verified = identity.VerifiedInstallation.verify(installed_scope.config)
    with pytest.raises(ValueError, match="INSTALLATION_PROFILE_CHANGED"):
        verified.require_unchanged(replace(installed_scope.config, **{field: value}))


def test_tamper_during_initial_hashing_cannot_be_captured_as_a_trusted_baseline(installed_scope, monkeypatch):
    scope = installed_scope
    def mutate_after_full_hash(config):
        receipt = deployment.require_installation(config)
        (scope.package / "protocol.json").write_bytes(b'{"version":2}\n')
        return receipt
    monkeypatch.setattr(identity, "require_installation", mutate_after_full_hash)
    with pytest.raises(ValueError, match="CHANGED_DURING_VERIFICATION"):
        identity.VerifiedInstallation.verify(scope.config)


def _session():
    calls = []
    return SimpleNamespace(connection=object(), require_supervisor_lock=lambda code: calls.append(("supervisor", code)),
                           has_conflicting_attempts=lambda code: calls.append(("attempts", code)) or False, calls=calls)


def test_every_guard_action_still_checks_runtime_principal_supervision_and_attempts(installed_scope, monkeypatch):
    scope = installed_scope
    session = _session()
    principals = []
    current = {"name": "restricted-runtime", "oid": 42}
    def inspect(connection):
        assert connection is session.connection
        principals.append(dict(current))
        return dict(current)
    monkeypatch.setattr(deployment, "inspect_runtime_principal", inspect)
    guard = ProspectiveOperationGuard(scope.settings, scope.config, session)
    guard.before_action()
    guard.before_action()
    assert len(scope.calls) == 1
    assert len(principals) == 2
    assert session.calls == [("supervisor", scope.config.series_code), ("attempts", scope.config.series_code)] * 2
    current["oid"] = 43
    with pytest.raises(ValueError, match="RUNTIME_PRINCIPAL_CHANGED"):
        guard.before_action()
    assert len(principals) == 3
    current["oid"] = 42
    def reject_drift(_connection):
        raise ValueError("RUNTIME_PRIVILEGE_ENVELOPE_DRIFT")
    monkeypatch.setattr(deployment, "inspect_runtime_principal", reject_drift)
    with pytest.raises(ValueError, match="PRIVILEGE_ENVELOPE_DRIFT"):
        guard.before_action()


def test_guard_restart_performs_full_verification_and_source_changes_block_before_next_action(installed_scope, monkeypatch):
    scope = installed_scope
    monkeypatch.setattr(deployment, "inspect_runtime_principal", lambda _: {"name": "restricted-runtime", "oid": 42})
    first = ProspectiveOperationGuard(scope.settings, scope.config, _session())
    first.before_action()
    restarted = ProspectiveOperationGuard(scope.settings, scope.config, _session())
    restarted.before_action()
    assert len(scope.calls) == 2
    (scope.package / "new_resource.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="IMPLEMENTATION_CHANGED"):
        restarted.before_action()
    with pytest.raises(ValueError, match="INSTALLED_PACKAGE_MISMATCH"):
        ProspectiveOperationGuard(scope.settings, scope.config, _session()).before_action()


def test_each_explicit_startup_reverifies_all_installation_bytes(installed_scope, monkeypatch):
    scope = installed_scope
    monkeypatch.setattr(deployment, "inspect_runtime_principal", lambda _: {"name": "restricted-runtime", "oid": 42})
    session = _session()
    session.allow_prospective_recovery = lambda _: None
    guard = ProspectiveOperationGuard(scope.settings, scope.config, session)
    def stop_after_identity():
        raise ValueError("STOP_BEFORE_DISPOSABLE_SCOPE_INSPECTION")
    monkeypatch.setattr(guard, "snapshot", stop_after_identity)
    app = SimpleNamespace(prospective_archives=SimpleNamespace(recovery_admissions=lambda _: ()))
    for _ in range(2):
        with pytest.raises(ValueError, match="STOP_BEFORE_DISPOSABLE_SCOPE_INSPECTION"):
            guard.verify_startup(app)
    assert len(scope.calls) == 2
