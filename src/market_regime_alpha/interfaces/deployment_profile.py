"""Verify a frozen wheel handoff; local profiles remain non-authoritative intent."""

from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
from importlib.metadata import distribution, distributions
import json
import os
from pathlib import Path
import subprocess
import tomllib
from typing import Any
from zipfile import BadZipFile, ZipFile

import market_regime_alpha
from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application
from market_regime_alpha.interfaces.prospective_operations import (
    ProspectiveOperationConfig, implementation_source_sha256,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _package_files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): _hash(p) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def verify_package_roster(wheel: Path, root: Path) -> str:
    try:
        with ZipFile(wheel) as archive:
            names = [name for name in archive.namelist() if name.startswith("market_regime_alpha/") and not name.endswith("/")]
            if not names or len(set(names)) != len(names) or any(".." in Path(name).parts for name in names):
                raise ValueError("DEPLOYMENT_WHEEL_ROSTER_INVALID")
            expected = {name.removeprefix("market_regime_alpha/"): sha256(archive.read(name)).hexdigest() for name in names}
    except BadZipFile as exc:
        raise ValueError("DEPLOYMENT_WHEEL_UNREADABLE") from exc
    if expected != _package_files(root):
        raise ValueError("DEPLOYMENT_INSTALLED_PACKAGE_MISMATCH")
    return str(canonical_json_sha256(expected))


def _installed(wheel: Path) -> dict[str, Any]:
    package_root = Path(market_regime_alpha.__file__).resolve().parent
    installed = distribution("market-regime-alpha")
    if Path(str(installed.locate_file("market_regime_alpha"))).resolve() != package_root:
        raise ValueError("DEPLOYMENT_EDITABLE_INSTALL_NOT_ADMITTED")
    direct = json.loads(installed.read_text("direct_url.json") or "{}")
    if direct.get("dir_info", {}).get("editable"):
        raise ValueError("DEPLOYMENT_EDITABLE_INSTALL_NOT_ADMITTED")
    roster = verify_package_roster(wheel, package_root)
    with ZipFile(wheel) as archive:
        metadata = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise ValueError("DEPLOYMENT_WHEEL_METADATA_INVALID")
        prefix = metadata[0].removesuffix("METADATA")
        identity = {}
        for name in ("METADATA", "WHEEL", "entry_points.txt"):
            content = archive.read(prefix + name)
            if content != (installed.read_text(name) or "").encode():
                raise ValueError("DEPLOYMENT_INSTALLED_METADATA_MISMATCH")
            identity[name] = sha256(content).hexdigest()
    return {"package_roster_sha256": roster,
            "metadata_sha256": str(canonical_json_sha256(identity)),
            "source_sha256": implementation_source_sha256(),
            "dependencies": {item.metadata["Name"].lower().replace("_", "-"): item.version
                             for item in distributions() if item.metadata["Name"].lower().replace("_", "-") != "market-regime-alpha"}}


def _git(checkout: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(checkout), *args], check=True,
                              capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("DEPLOYMENT_SOURCE_UNVERIFIABLE") from exc


def inspect_installation(*, wheel: Path, source_checkout: Path, expected_source_sha: str) -> dict[str, Any]:
    installed = _installed(wheel)
    if _git(source_checkout, "rev-parse", "HEAD") != expected_source_sha:
        raise ValueError("DEPLOYMENT_SOURCE_REVISION_MISMATCH")
    if _git(source_checkout, "status", "--porcelain", "--untracked-files=all", "--", "src", "tests", "pyproject.toml", "uv.lock", "docs/operations/templates"):
        raise ValueError("DEPLOYMENT_SOURCE_NOT_FROZEN")
    # Compare the whole installed package, not a caller-supplied digest. Git's
    # clean index and the wheel roster jointly exclude untracked writer files.
    verify_package_roster(wheel, source_checkout / "src/market_regime_alpha")
    locked = tomllib.loads((source_checkout / "uv.lock").read_text())
    versions = {(item["name"], item["version"]) for item in locked["package"]}
    if any((name, version) not in versions for name, version in installed["dependencies"].items()):
        raise ValueError("DEPLOYMENT_DEPENDENCIES_DIFFER_FROM_LOCK")
    return {**installed, "source_sha": expected_source_sha,
            "source_tree": _git(source_checkout, "rev-parse", "HEAD:src"),
            "tests_tree": _git(source_checkout, "rev-parse", "HEAD:tests"),
            "lock_sha256": _hash(source_checkout / "uv.lock"),
            "wheel_sha256": _hash(wheel), "wheel_path": str(wheel.resolve())}


def require_installation(config: ProspectiveOperationConfig) -> dict[str, Any]:
    if config.version != 2 or not config.deployment_receipt or not config.deployment_receipt_sha256:
        raise ValueError("DEPLOYMENT_HANDOFF_REQUIRED")
    try:
        path = Path(config.deployment_receipt)
        if _hash(path) != config.deployment_receipt_sha256:
            raise ValueError("DEPLOYMENT_RECEIPT_MISMATCH")
        receipt = json.loads(path.read_bytes())
        installation = receipt["installation"]
        wheel = Path(installation["wheel_path"])
        if _hash(wheel) != installation["wheel_sha256"]:
            raise ValueError("DEPLOYMENT_WHEEL_CHANGED")
        actual = _installed(wheel)
        if any(actual[key] != installation[key] for key in actual):
            raise ValueError("DEPLOYMENT_INSTALLATION_CHANGED")
        if config.code_sha != installation["source_sha"] or config.source_sha256 != actual["source_sha256"]:
            raise ValueError("DEPLOYMENT_PROFILE_IMPLEMENTATION_MISMATCH")
        # Backup renewal may replace only backup fields. Exact DB, Artifact,
        # schema and business identities cannot be edited into another scope.
        if receipt["scope"] != _scope(config):
            raise ValueError("DEPLOYMENT_PROFILE_SCOPE_MISMATCH")
        return receipt
    except (OSError, KeyError, TypeError, json.JSONDecodeError, BadZipFile) as exc:
        raise ValueError("DEPLOYMENT_RECEIPT_UNREADABLE") from exc


def _scope(config: ProspectiveOperationConfig) -> dict[str, Any]:
    excluded = {"version", "deployment_receipt", "deployment_receipt_sha256",
                "backup_directory", "backup_sha256", "backup_receipt_sha256"}
    return {name: value for name, value in asdict(config).items() if name not in excluded}


def _write_new(path: Path, value: object) -> None:
    # Exclusive files preserve the former installation/profile/receipt for audit.
    content = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def prepare_deployment_profile(settings: TargetSettings, previous: ProspectiveOperationConfig, *,
                               wheel: Path, source_checkout: Path, expected_source_sha: str,
                               backup_directory: Path, output: Path) -> dict[str, Any]:
    from market_regime_alpha.interfaces.prospective_operation_guard import operational_session

    installation = inspect_installation(wheel=wheel, source_checkout=source_checkout, expected_source_sha=expected_source_sha)
    # Identity is inherited from explicit intent, never selected from an
    # available database. A restored copy necessarily fails this exact check.
    with operational_session(settings, previous) as guard, bootstrap_application(settings) as app:
        snapshot = guard.session.snapshot()
        receipt_bytes = (backup_directory / "receipt.json").read_bytes()
        backup = json.loads(receipt_bytes)
        candidate = replace(previous, version=1, source_sha256=installation["source_sha256"],
                            code_sha=installation["source_sha"], backup_directory=str(backup_directory.resolve()),
                            backup_sha256=backup["backup_sha256"], backup_receipt_sha256=sha256(receipt_bytes).hexdigest(),
                            deployment_receipt="", deployment_receipt_sha256="")
        guard.config = candidate
        verified = guard.verify_startup(app)
        guard.before_action()
        if snapshot["active_attempts"]:
            raise ValueError("DEPLOYMENT_ACTIVE_ATTEMPT_REQUIRES_DRAIN")
        receipt = {"kind": "VERIFIED_INSTALLED_RESEARCH_HANDOFF", "authority": False,
                   "previous_profile_sha256": previous.content_sha256, "installation": installation,
                   "scope": _scope(candidate), "verified_at": snapshot["observed_at"],
                   "backup_receipt_sha256": candidate.backup_receipt_sha256,
                   "generation_ids": verified["generation_ids"], "operational_activation": "NOT_PERFORMED"}
        receipt_path = output.with_name(output.name + ".receipt.json")
        if output.exists() or receipt_path.exists():
            raise ValueError("DEPLOYMENT_OUTPUT_ALREADY_EXISTS")
        _write_new(receipt_path, receipt)
        candidate = replace(candidate, version=2, deployment_receipt=str(receipt_path.resolve()),
                            deployment_receipt_sha256=_hash(receipt_path))
        _write_new(output, asdict(candidate))
        return {"status": "PREPARED", "authority": False, "configuration_sha256": candidate.content_sha256,
                "deployment_receipt_sha256": candidate.deployment_receipt_sha256,
                "installation": {k: v for k, v in installation.items() if k != "wheel_path"},
                "scope": _scope(candidate), "activation": "NOT_PERFORMED"}
