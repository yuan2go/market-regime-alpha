"""Exact immutable packages for Calendar, SourceManifest, and runtime configuration."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Mapping, TypeVar

from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_json


CONTROLLED_INPUT_PACKAGE_FILES = ("SHA256SUMS.json", "artifact.json", "manifest.json")
T = TypeVar("T")


def publish_controlled_trading_calendar(*, root: Path, artifact: TradingCalendarArtifact) -> Path:
    return _publish(
        root=root,
        artifact_id=str(artifact.artifact_id),
        content_hash=artifact.content_hash,
        artifact_payload=artifact.to_canonical_dict(),
        package_schema="controlled-trading-calendar-package-v1",
        loader=load_controlled_trading_calendar,
        expected=artifact,
    )


def load_controlled_trading_calendar(path: Path) -> TradingCalendarArtifact:
    payload = _load(
        path=path,
        package_schema="controlled-trading-calendar-package-v1",
    )
    artifact = TradingCalendarArtifact.from_canonical_dict(payload)
    _validate_manifest_identity(path, str(artifact.artifact_id), artifact.content_hash)
    return artifact


def publish_controlled_source_manifest(*, root: Path, artifact: SourceManifest) -> Path:
    return _publish(
        root=root,
        artifact_id=str(artifact.source_manifest_id),
        content_hash=artifact.content_hash,
        artifact_payload=artifact.to_canonical_dict(),
        package_schema="controlled-source-manifest-package-v1",
        loader=load_controlled_source_manifest,
        expected=artifact,
    )


def load_controlled_source_manifest(path: Path) -> SourceManifest:
    payload = _load(path=path, package_schema="controlled-source-manifest-package-v1")
    artifact = SourceManifest.from_canonical_dict(payload)
    _validate_manifest_identity(path, str(artifact.source_manifest_id), artifact.content_hash)
    return artifact


def publish_controlled_runtime_configuration(
    *, root: Path, artifact: ControlledOperationRuntimeConfiguration
) -> Path:
    return _publish(
        root=root,
        artifact_id=str(artifact.configuration_id),
        content_hash=artifact.configuration_hash,
        artifact_payload=artifact.to_canonical_dict(),
        package_schema="controlled-runtime-configuration-package-v1",
        loader=load_controlled_runtime_configuration,
        expected=artifact,
    )


def load_controlled_runtime_configuration(path: Path) -> ControlledOperationRuntimeConfiguration:
    payload = _load(path=path, package_schema="controlled-runtime-configuration-package-v1")
    artifact = ControlledOperationRuntimeConfiguration.from_canonical_dict(payload)
    _validate_manifest_identity(path, str(artifact.configuration_id), artifact.configuration_hash)
    return artifact


def _publish(
    *,
    root: Path,
    artifact_id: str,
    content_hash: str,
    artifact_payload: Mapping[str, Any],
    package_schema: str,
    loader: Callable[[Path], T],
    expected: T,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    destination = root / artifact_id
    if destination.exists():
        if loader(destination) != expected:
            raise ValueError("Controlled input Artifact identity conflict")
        return destination
    staging = Path(tempfile.mkdtemp(prefix=f".{artifact_id}.", dir=root))
    try:
        _write_json(staging / "artifact.json", artifact_payload)
        _write_json(staging / "SHA256SUMS.json", {"artifact.json": _file_hash(staging / "artifact.json")})
        _write_json(staging / "manifest.json", {
            "schema_version": package_schema,
            "artifact_id": artifact_id,
            "content_hash": content_hash,
            "exact_file_set": list(CONTROLLED_INPUT_PACKAGE_FILES),
            "checksums_sha256": _file_hash(staging / "SHA256SUMS.json"),
        })
        _fsync_directory(staging)
        staging.rename(destination)
        _fsync_directory(root)
    except FileExistsError:
        shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if loader(destination) != expected:
        raise ValueError("published Controlled input semantic mismatch")
    return destination


def _load(*, path: Path, package_schema: str) -> dict[str, Any]:
    actual = {item.name for item in path.iterdir() if item.is_file()}
    if actual != set(CONTROLLED_INPUT_PACKAGE_FILES):
        raise ValueError("Controlled input exact file set mismatch")
    manifest = _read_json(path / "manifest.json")
    if (
        manifest.get("schema_version") != package_schema
        or manifest.get("exact_file_set") != list(CONTROLLED_INPUT_PACKAGE_FILES)
        or manifest.get("checksums_sha256") != _file_hash(path / "SHA256SUMS.json")
    ):
        raise ValueError("Controlled input manifest mismatch")
    if _read_json(path / "SHA256SUMS.json") != {
        "artifact.json": _file_hash(path / "artifact.json")
    }:
        raise ValueError("Controlled input checksum mismatch")
    return _read_json(path / "artifact.json")


def _validate_manifest_identity(path: Path, artifact_id: str, content_hash: str) -> None:
    manifest = _read_json(path / "manifest.json")
    if (
        path.name != artifact_id
        or manifest.get("artifact_id") != artifact_id
        or manifest.get("content_hash") != content_hash
    ):
        raise ValueError("Controlled input manifest identity mismatch")


def _file_hash(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("Controlled input JSON must be an object")
    return payload


def _fsync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "CONTROLLED_INPUT_PACKAGE_FILES",
    "load_controlled_runtime_configuration",
    "load_controlled_source_manifest",
    "load_controlled_trading_calendar",
    "publish_controlled_runtime_configuration",
    "publish_controlled_source_manifest",
    "publish_controlled_trading_calendar",
]
