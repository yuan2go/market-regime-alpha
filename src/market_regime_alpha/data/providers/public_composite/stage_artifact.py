"""Immutable acquisition-substage Artifact for recoverable LIVE source fetches."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite.contracts import (
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeBatch,
    PublicQuote,
)


class PublicSourceAcquisitionStage(str, Enum):
    HISTORY_SOURCE_FROZEN = "HISTORY_SOURCE_FROZEN"
    DECISION_QUOTE_SOURCE_FROZEN = "DECISION_QUOTE_SOURCE_FROZEN"


SOURCE_STAGE_ARTIFACT_SCHEMA = "public-source-acquisition-stage-v1"
SOURCE_STAGE_ARTIFACT_FILES = (
    "SHA256SUMS.json",
    "batch.json",
    "manifest.json",
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


def _batch_payload(batch: PublicCompositeBatch) -> dict[str, Any]:
    return {
        "raw_payloads": [
            item.to_canonical_dict(include_payload=True)
            for item in batch.raw_payloads
        ],
        "bars": [item.to_canonical_dict() for item in batch.bars],
        "quotes": [item.to_canonical_dict() for item in batch.quotes],
        "source_conflicts": list(batch.source_conflicts),
        "limitations": list(batch.limitations),
    }


def _batch_from_payload(payload: Mapping[str, Any]) -> PublicCompositeBatch:
    expected = {
        "raw_payloads",
        "bars",
        "quotes",
        "source_conflicts",
        "limitations",
    }
    if set(payload) != expected:
        raise ValueError("source stage batch fields mismatch")
    batch = PublicCompositeBatch(
        raw_payloads=tuple(
            AcquiredSourcePayload.from_canonical_dict(item)
            for item in payload["raw_payloads"]
        ),
        bars=tuple(PublicBar.from_canonical_dict(item) for item in payload["bars"]),
        quotes=tuple(
            PublicQuote.from_canonical_dict(item) for item in payload["quotes"]
        ),
        source_conflicts=tuple(str(item) for item in payload["source_conflicts"]),
        limitations=tuple(str(item) for item in payload["limitations"]),
    )
    known = {item.source_artifact_id for item in batch.raw_payloads}
    if any(item.source_artifact_id not in known for item in batch.bars):
        raise ValueError("source stage bar references unarchived bytes")
    if any(item.source_artifact_id not in known for item in batch.quotes):
        raise ValueError("source stage quote references unarchived bytes")
    return batch


def source_stage_artifact_id(
    *,
    stage: PublicSourceAcquisitionStage,
    batch: PublicCompositeBatch,
) -> tuple[ArtifactId, str]:
    content_hash = _canonical_hash(
        {
            "schema_version": SOURCE_STAGE_ARTIFACT_SCHEMA,
            "stage": stage.value,
            "batch": _batch_payload(batch),
        }
    )
    return (
        ArtifactId(
            f"source-stage-{stage.value.lower().replace('_', '-')}-"
            f"{content_hash.split(':', 1)[1][:24]}"
        ),
        content_hash,
    )


@dataclass(frozen=True, slots=True)
class VerifiedPublicSourceStageArtifact:
    root: Path
    artifact_id: ArtifactId
    stage: PublicSourceAcquisitionStage
    batch: PublicCompositeBatch
    content_hash: str
    checksums_hash: str


def publish_public_source_stage_artifact(
    *,
    root: Path,
    stage: PublicSourceAcquisitionStage,
    batch: PublicCompositeBatch,
) -> Path:
    artifact_id, content_hash = source_stage_artifact_id(
        stage=stage,
        batch=batch,
    )
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact_id)
    if final.exists():
        raise FileExistsError(f"source stage Artifact exists: {final}")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{artifact_id}.", dir=root)
    )
    try:
        _write_json(staging / "batch.json", _batch_payload(batch))
        _write_json(
            staging / "manifest.json",
            {
                "schema_version": SOURCE_STAGE_ARTIFACT_SCHEMA,
                "artifact_id": str(artifact_id),
                "stage": stage.value,
                "content_hash": content_hash,
                "required_artifacts": sorted(SOURCE_STAGE_ARTIFACT_FILES),
            },
        )
        _write_json(
            staging / "SHA256SUMS.json",
            {
                name: _file_hash(staging / name)
                for name in ("batch.json", "manifest.json")
            },
        )
        if {item.name for item in staging.iterdir()} != set(
            SOURCE_STAGE_ARTIFACT_FILES
        ):
            raise RuntimeError("source stage exact file set mismatch")
        staging.rename(final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final


def load_verified_public_source_stage_artifact(
    path: Path,
) -> VerifiedPublicSourceStageArtifact:
    if not path.is_dir():
        raise ValueError("source stage Artifact path is not a directory")
    if {item.name for item in path.iterdir()} != set(
        SOURCE_STAGE_ARTIFACT_FILES
    ):
        raise ValueError("source stage exact file set mismatch")
    checksums = _read_json(path / "SHA256SUMS.json")
    if set(checksums) != {"batch.json", "manifest.json"}:
        raise ValueError("source stage checksum index mismatch")
    for name, expected in checksums.items():
        if _file_hash(path / name) != expected:
            raise ValueError(f"source stage checksum mismatch: {name}")
    manifest = _read_json(path / "manifest.json")
    if (
        manifest.get("schema_version") != SOURCE_STAGE_ARTIFACT_SCHEMA
        or manifest.get("required_artifacts")
        != sorted(SOURCE_STAGE_ARTIFACT_FILES)
    ):
        raise ValueError("source stage manifest mismatch")
    stage = PublicSourceAcquisitionStage(str(manifest["stage"]))
    batch = _batch_from_payload(_read_json(path / "batch.json"))
    artifact_id, content_hash = source_stage_artifact_id(
        stage=stage,
        batch=batch,
    )
    if (
        manifest.get("artifact_id") != str(artifact_id)
        or manifest.get("content_hash") != content_hash
        or path.name != str(artifact_id)
    ):
        raise ValueError("source stage semantic identity mismatch")
    return VerifiedPublicSourceStageArtifact(
        root=path,
        artifact_id=artifact_id,
        stage=stage,
        batch=batch,
        content_hash=content_hash,
        checksums_hash=_canonical_hash(
            {str(key): value for key, value in sorted(checksums.items())}
        ),
    )


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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid source stage JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"source stage JSON must be object: {path.name}")
    return payload


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
