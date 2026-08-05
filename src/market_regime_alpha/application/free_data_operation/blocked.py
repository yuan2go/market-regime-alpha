"""Immutable fail-closed evidence before a Controlled parent can be created."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, cast

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)


FREE_DATA_BLOCKED_SCHEMA = "free-data-operation-blocked-v1"


@dataclass(frozen=True, slots=True)
class FreeDataBlockedArtifact:
    artifact_id: ArtifactId
    content_hash: str
    command_hash: str
    source_archive_id: ArtifactId
    source_manifest_id: ArtifactId
    source_manifest_hash: str
    provider_result_hash: str
    reason_code: str
    error_type: str
    created_at: datetime
    code_revision: str
    limitations: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        command_hash: str,
        source_archive_id: ArtifactId,
        source_manifest_id: ArtifactId,
        source_manifest_hash: str,
        provider_result_hash: str,
        reason_code: str,
        error_type: str,
        created_at: datetime,
        code_revision: str,
    ) -> FreeDataBlockedArtifact:
        limitations = (
            "BROKER_NOT_INVOKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_FILL_CREATED",
            "NO_ORDER_CREATED",
            "NO_POSITION_MUTATION",
            "TRADING_AUTHORITY_NOT_GRANTED",
        )
        values = {
            "command_hash": command_hash,
            "source_archive_id": source_archive_id,
            "source_manifest_id": source_manifest_id,
            "source_manifest_hash": source_manifest_hash,
            "provider_result_hash": provider_result_hash,
            "reason_code": reason_code,
            "error_type": error_type,
            "created_at": created_at,
            "code_revision": code_revision,
            "limitations": limitations,
        }
        digest = canonical_hash(_payload(**values))
        return cls(
            artifact_id=ArtifactId(
                f"free-data-blocked-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            **cast(Any, values),
        )

    def __post_init__(self) -> None:
        require_sha256("content_hash", self.content_hash)
        require_sha256("command_hash", self.command_hash)
        require_sha256("source_manifest_hash", self.source_manifest_hash)
        require_sha256("provider_result_hash", self.provider_result_hash)
        require_text("reason_code", self.reason_code)
        require_text("error_type", self.error_type)
        require_text("code_revision", self.code_revision)
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("blocked artifact created_at must be timezone-aware")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("blocked limitations must be ordered and unique")
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("blocked artifact hash mismatch")
        expected = f"free-data-blocked-{self.content_hash.split(':', 1)[1][:24]}"
        if str(self.artifact_id) != expected:
            raise ValueError("blocked artifact identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(
            command_hash=self.command_hash,
            source_archive_id=self.source_archive_id,
            source_manifest_id=self.source_manifest_id,
            source_manifest_hash=self.source_manifest_hash,
            provider_result_hash=self.provider_result_hash,
            reason_code=self.reason_code,
            error_type=self.error_type,
            created_at=self.created_at,
            code_revision=self.code_revision,
            limitations=self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }


class FreeDataOperationBlocked(ValueError):
    def __init__(self, artifact: FreeDataBlockedArtifact, path: Path) -> None:
        self.artifact = artifact
        self.path = path
        super().__init__(artifact.reason_code)


def publish_free_data_blocked(
    *, root: Path, artifact: FreeDataBlockedArtifact
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    destination = root / str(artifact.artifact_id)
    if destination.exists():
        if load_free_data_blocked(destination) != artifact:
            raise ValueError("free-data blocked identity conflict")
        return destination
    staging = Path(tempfile.mkdtemp(prefix=f".{artifact.artifact_id}.", dir=root))
    installed = False
    try:
        raw = (canonical_json(artifact.to_canonical_dict()) + "\n").encode()
        (staging / "artifact.json").write_bytes(raw)
        checksums = {"artifact.json": f"sha256:{sha256(raw).hexdigest()}"}
        (staging / "SHA256SUMS.json").write_text(
            canonical_json(checksums) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, destination)
        installed = True
    finally:
        if not installed and staging.exists():
            shutil.rmtree(staging)
    load_free_data_blocked(destination)
    return destination


def load_free_data_blocked(path: Path) -> FreeDataBlockedArtifact:
    root = path.resolve()
    expected_files = {"artifact.json", "SHA256SUMS.json"}
    actual_files = {child.name for child in root.iterdir()}
    if actual_files != expected_files:
        raise ValueError("free-data blocked file set mismatch")
    raw = (root / "artifact.json").read_bytes()
    checksums = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    if checksums != {"artifact.json": f"sha256:{sha256(raw).hexdigest()}"}:
        raise ValueError("free-data blocked checksum mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, Mapping):
        raise ValueError("free-data blocked payload must be an object")
    if raw != (canonical_json(payload) + "\n").encode():
        raise ValueError("free-data blocked payload is not canonical")
    if payload.get("schema_version") != FREE_DATA_BLOCKED_SCHEMA:
        raise ValueError("unsupported free-data blocked schema")
    artifact = FreeDataBlockedArtifact(
        artifact_id=ArtifactId(str(payload["artifact_id"])),
        content_hash=str(payload["content_hash"]),
        command_hash=str(payload["command_hash"]),
        source_archive_id=ArtifactId(str(payload["source_archive_id"])),
        source_manifest_id=ArtifactId(str(payload["source_manifest_id"])),
        source_manifest_hash=str(payload["source_manifest_hash"]),
        provider_result_hash=str(payload["provider_result_hash"]),
        reason_code=str(payload["reason_code"]),
        error_type=str(payload["error_type"]),
        created_at=datetime.fromisoformat(str(payload["created_at"])),
        code_revision=str(payload["code_revision"]),
        limitations=tuple(str(item) for item in payload["limitations"]),
    )
    if root.name != str(artifact.artifact_id):
        raise ValueError("free-data blocked directory identity mismatch")
    if payload != artifact.to_canonical_dict():
        raise ValueError("free-data blocked payload contains unknown fields")
    return artifact


def _payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": FREE_DATA_BLOCKED_SCHEMA,
        "command_hash": values["command_hash"],
        "source_archive_id": str(values["source_archive_id"]),
        "source_manifest_id": str(values["source_manifest_id"]),
        "source_manifest_hash": values["source_manifest_hash"],
        "provider_result_hash": values["provider_result_hash"],
        "reason_code": values["reason_code"],
        "error_type": values["error_type"],
        "created_at": values["created_at"].isoformat(),
        "code_revision": values["code_revision"],
        "limitations": list(values["limitations"]),
    }


__all__ = [
    "FREE_DATA_BLOCKED_SCHEMA",
    "FreeDataBlockedArtifact",
    "FreeDataOperationBlocked",
    "load_free_data_blocked",
    "publish_free_data_blocked",
]
