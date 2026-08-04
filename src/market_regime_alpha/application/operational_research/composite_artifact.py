"""Immutable exact-file package for one terminal H6 composite manifest."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from market_regime_alpha.application.operational_research.composite_manifest import (
    COMPOSITE_OPERATIONAL_INPUT_MANIFEST_SCHEMA,
    CompositeOperationalCompositionPolicy,
    CompositeOperationalInputManifest,
)


COMPOSITE_OPERATIONAL_ARTIFACT_SCHEMA = (
    "composite-operational-manifest-artifact-v1"
)
COMPOSITE_OPERATIONAL_ARTIFACT_FILES = (
    "SHA256SUMS.json",
    "artifact.json",
    "manifest.json",
)
_H6_STAGING_DIRECTORY = re.compile(
    r"^\.composite-operational-[0-9a-f]{24}\.staging-[A-Za-z0-9._-]+$"
)


@dataclass(frozen=True, slots=True)
class VerifiedCompositeOperationalManifest:
    root: Path
    manifest: CompositeOperationalInputManifest
    composition_policy: CompositeOperationalCompositionPolicy
    checksums_hash: str


def publish_composite_operational_manifest(
    *,
    root: Path,
    manifest: CompositeOperationalInputManifest,
    composition_policy: CompositeOperationalCompositionPolicy,
    before_rename: Callable[[Path], None] | None = None,
) -> Path:
    """Publish file-first; identical content reuses an existing valid package."""

    policy = CompositeOperationalCompositionPolicy.from_canonical_dict(
        composition_policy.to_canonical_dict()
    )
    restored = CompositeOperationalInputManifest.from_canonical_dict(
        manifest.to_canonical_dict(), composition_policy=policy
    )
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(restored.manifest_id)
    if final.exists():
        existing = load_verified_composite_operational_manifest(final)
        if existing.manifest != restored or existing.composition_policy != policy:
            raise FileExistsError(
                f"conflicting Composite Operational Manifest exists: {final}"
            )
        return final
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{restored.manifest_id}.staging-",
            dir=root,
        )
    )
    try:
        _write_json(stage / "artifact.json", restored.to_canonical_dict())
        _write_json(stage / "manifest.json", _package_manifest(restored, policy))
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in COMPOSITE_OPERATIONAL_ARTIFACT_FILES
                if name != "SHA256SUMS.json"
            },
        )
        _load_verified(stage, enforce_root_name=False)
        if before_rename is not None:
            before_rename(stage)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def load_verified_composite_operational_manifest(
    path: Path,
) -> VerifiedCompositeOperationalManifest:
    return _load_verified(path.resolve(), enforce_root_name=True)


def cleanup_orphan_composite_staging(root: Path) -> tuple[Path, ...]:
    """Remove only H6-owned staging directories under an explicit package root."""

    if not root.exists():
        return ()
    removed: list[Path] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        if entry.is_dir() and _H6_STAGING_DIRECTORY.fullmatch(entry.name):
            shutil.rmtree(entry)
            removed.append(entry)
    return tuple(removed)


def _load_verified(
    root: Path,
    *,
    enforce_root_name: bool,
) -> VerifiedCompositeOperationalManifest:
    _verify_files(root)
    package_manifest = _read_object(root / "manifest.json")
    expected = {
        "schema_version",
        "artifact_schema_version",
        "manifest_id",
        "content_hash",
        "status",
        "composition_policy",
        "daily_artifact_id",
        "daily_artifact_hash",
        "daily_source_manifest_id",
        "daily_source_manifest_hash",
        "supplemental_bundle_id",
        "supplemental_bundle_hash",
        "supplemental_source_manifest_id",
        "supplemental_source_manifest_hash",
        "component_references",
        "field_authority_references",
        "required_artifacts",
        "data_eligibility",
        "formal_pit",
        "formal_oos_alpha",
        "trading_authority",
    }
    if set(package_manifest) != expected:
        raise ValueError("composite package manifest fields mismatch")
    if (
        package_manifest["schema_version"]
        != COMPOSITE_OPERATIONAL_ARTIFACT_SCHEMA
        or package_manifest["artifact_schema_version"]
        != COMPOSITE_OPERATIONAL_INPUT_MANIFEST_SCHEMA
        or package_manifest["required_artifacts"]
        != sorted(COMPOSITE_OPERATIONAL_ARTIFACT_FILES)
    ):
        raise ValueError("composite package manifest schema mismatch")
    policy = CompositeOperationalCompositionPolicy.from_canonical_dict(
        _object(package_manifest["composition_policy"])
    )
    manifest = CompositeOperationalInputManifest.from_canonical_dict(
        _read_object(root / "artifact.json"),
        composition_policy=policy,
    )
    if package_manifest != _package_manifest(manifest, policy):
        raise ValueError("composite package manifest is not reconstructible")
    if enforce_root_name and root.name != str(manifest.manifest_id):
        raise ValueError("composite package directory identity mismatch")
    return VerifiedCompositeOperationalManifest(
        root=root,
        manifest=manifest,
        composition_policy=policy,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def _package_manifest(
    manifest: CompositeOperationalInputManifest,
    policy: CompositeOperationalCompositionPolicy,
) -> dict[str, Any]:
    return {
        "schema_version": COMPOSITE_OPERATIONAL_ARTIFACT_SCHEMA,
        "artifact_schema_version": COMPOSITE_OPERATIONAL_INPUT_MANIFEST_SCHEMA,
        "manifest_id": str(manifest.manifest_id),
        "content_hash": manifest.content_hash,
        "status": manifest.status.value,
        "composition_policy": policy.to_canonical_dict(),
        "daily_artifact_id": str(manifest.daily_artifact_id),
        "daily_artifact_hash": manifest.daily_artifact_hash,
        "daily_source_manifest_id": str(manifest.daily_source_manifest_id),
        "daily_source_manifest_hash": manifest.daily_source_manifest_hash,
        "supplemental_bundle_id": str(manifest.supplemental_bundle_id),
        "supplemental_bundle_hash": manifest.supplemental_bundle_hash,
        "supplemental_source_manifest_id": str(
            manifest.supplemental_source_manifest_id
        ),
        "supplemental_source_manifest_hash": (
            manifest.supplemental_source_manifest_hash
        ),
        "component_references": [
            item.to_canonical_dict() for item in manifest.component_references
        ],
        "field_authority_references": [
            item.to_canonical_dict()
            for item in manifest.field_authority_references
        ],
        "required_artifacts": sorted(COMPOSITE_OPERATIONAL_ARTIFACT_FILES),
        "data_eligibility": manifest.data_eligibility.value,
        "formal_pit": manifest.formal_pit,
        "formal_oos_alpha": manifest.formal_oos_alpha,
        "trading_authority": manifest.trading_authority,
    }


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("Composite Operational Manifest package is missing")
    entries = tuple(root.iterdir())
    if {item.name for item in entries} != set(
        COMPOSITE_OPERATIONAL_ARTIFACT_FILES
    ):
        raise ValueError("composite package exact file set mismatch")
    if any(not item.is_file() for item in entries):
        raise ValueError("composite package exact file set contains a non-file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(COMPOSITE_OPERATIONAL_ARTIFACT_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected:
        raise ValueError("composite package checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(
            root / name
        ) != expected_hash:
            raise ValueError(f"composite package checksum mismatch: {name}")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid composite package JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("composite package value must be an object")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
