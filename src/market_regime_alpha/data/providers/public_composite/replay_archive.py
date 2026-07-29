"""Immutable content-addressed source archive for network-free replay."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.data.providers.public_composite.contracts import (
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    PublicCompositeProviderResult,
)
from market_regime_alpha.data.source_manifest import SourceManifest


SOURCE_REPLAY_ARCHIVE_SCHEMA = "public-composite-source-replay-archive-v1"
SOURCE_REPLAY_ARCHIVE_FILES = (
    "SHA256SUMS.json",
    "manifest.json",
    "provider_result.json",
    "source_manifest.json",
)


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


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


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


@dataclass(frozen=True, slots=True)
class AcquiredReplaySource:
    source_manifest: SourceManifest
    provider_result: PublicCompositeProviderResult
    archive_id: str


def source_archive_id(
    *,
    provider_result: PublicCompositeProviderResult,
    source_manifest: SourceManifest,
) -> str:
    """Derive the immutable archive identity from its semantic records."""

    identity_hash = _canonical_hash(
        {
            "schema_version": SOURCE_REPLAY_ARCHIVE_SCHEMA,
            "provider_result_hash": provider_result.content_hash,
            "source_manifest_hash": source_manifest.content_hash,
        }
    )
    return f"source-replay-{identity_hash.split(':', 1)[1][:24]}"


def publish_source_archive(
    *,
    root: Path,
    provider_result: PublicCompositeProviderResult,
    source_manifest: SourceManifest,
) -> Path:
    if provider_result.profile_id != source_manifest.provider_profile_id:
        raise ValueError("source archive profile mismatch")
    if (
        provider_result.decision_time != source_manifest.decision_time
        or provider_result.source_artifact_references
        != source_manifest.source_artifacts
    ):
        raise ValueError("ProviderResult and SourceManifest source scope mismatch")
    archive_id = source_archive_id(
        provider_result=provider_result,
        source_manifest=source_manifest,
    )
    root.mkdir(parents=True, exist_ok=True)
    final = root / archive_id
    if final.exists():
        raise FileExistsError(f"source replay archive already exists: {final}")
    stage = Path(tempfile.mkdtemp(prefix=f".{archive_id}.", dir=root))
    try:
        _write_json(stage / "source_manifest.json", source_manifest.to_canonical_dict())
        _write_json(
            stage / "provider_result.json",
            provider_result.to_canonical_dict(include_raw_payloads=True),
        )
        _write_json(
            stage / "manifest.json",
            {
                "schema_version": SOURCE_REPLAY_ARCHIVE_SCHEMA,
                "archive_id": archive_id,
                "provider_result_hash": provider_result.content_hash,
                "source_manifest_hash": source_manifest.content_hash,
                "required_artifacts": sorted(SOURCE_REPLAY_ARCHIVE_FILES),
            },
        )
        checksums = {
            name: _file_hash(stage / name)
            for name in (
                "manifest.json",
                "provider_result.json",
                "source_manifest.json",
            )
        }
        _write_json(stage / "SHA256SUMS.json", checksums)
        if {item.name for item in stage.iterdir()} != set(
            SOURCE_REPLAY_ARCHIVE_FILES
        ):
            raise RuntimeError("source replay staging exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def publish_source_replay_archive(
    *,
    root: Path,
    provider_result: PublicCompositeProviderResult,
    source_manifest: SourceManifest,
) -> Path:
    """Preserve the original replay-profile-only publisher contract."""

    if provider_result.profile_id != PUBLIC_COMPOSITE_REPLAY_PROFILE_ID:
        raise ValueError("source replay archive requires replay ProviderResult")
    if source_manifest.provider_profile_id != PUBLIC_COMPOSITE_REPLAY_PROFILE_ID:
        raise ValueError("source replay archive requires replay SourceManifest")
    return publish_source_archive(
        root=root,
        provider_result=provider_result,
        source_manifest=source_manifest,
    )


class SourceReplayArchiveReader:
    """Checksum and semantic verifier for one source replay archive."""

    def read(self, path: Path) -> AcquiredReplaySource:
        if not path.is_dir():
            raise ValueError("source replay archive path is not a directory")
        if {item.name for item in path.iterdir()} != set(SOURCE_REPLAY_ARCHIVE_FILES):
            raise ValueError("source replay archive exact file set mismatch")
        checksums = _read_json(path / "SHA256SUMS.json")
        if set(checksums) != {
            "manifest.json",
            "provider_result.json",
            "source_manifest.json",
        }:
            raise ValueError("source replay checksum index mismatch")
        for name, expected in checksums.items():
            if _file_hash(path / name) != expected:
                raise ValueError(f"source replay checksum mismatch: {name}")
        manifest = _read_json(path / "manifest.json")
        if manifest.get("schema_version") != SOURCE_REPLAY_ARCHIVE_SCHEMA:
            raise ValueError("unsupported source replay archive schema")
        if manifest.get("required_artifacts") != sorted(SOURCE_REPLAY_ARCHIVE_FILES):
            raise ValueError("source replay required artifacts mismatch")
        source_manifest = SourceManifest.from_canonical_dict(
            _read_json(path / "source_manifest.json")
        )
        provider_result = PublicCompositeProviderResult.from_canonical_dict(
            _read_json(path / "provider_result.json")
        )
        if (
            manifest.get("source_manifest_hash") != source_manifest.content_hash
            or manifest.get("provider_result_hash") != provider_result.content_hash
            or manifest.get("archive_id") != path.name
        ):
            raise ValueError("source replay archive semantic identity mismatch")
        return AcquiredReplaySource(
            source_manifest=source_manifest,
            provider_result=provider_result,
            archive_id=str(manifest["archive_id"]),
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON artifact: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path.name}")
    return payload
