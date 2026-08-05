"""Immutable receipt for the Canonical Signal/Path/Entry child run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import (
    parse_utc_second,
    require_utc_second,
)


CONTROLLED_CANONICAL_RUN_SCHEMA = "controlled-canonical-lifecycle-run-v1"
CONTROLLED_CANONICAL_RUN_PACKAGE_SCHEMA = (
    "controlled-canonical-lifecycle-run-package-v1"
)
CONTROLLED_CANONICAL_RUN_PACKAGE_FILES = (
    "SHA256SUMS.json",
    "artifact.json",
    "manifest.json",
)


@dataclass(frozen=True, slots=True)
class CanonicalLifecycleRunObjectReference:
    reference_type: str
    object_id: ArtifactId
    content_hash: str

    def __post_init__(self) -> None:
        require_text("reference_type", self.reference_type)
        require_sha256("content_hash", self.content_hash)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "reference_type": self.reference_type,
            "object_id": str(self.object_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CanonicalLifecycleRunObjectReference:
        if set(payload) != {"reference_type", "object_id", "content_hash"}:
            raise ValueError("Canonical child-run reference fields mismatch")
        return cls(
            reference_type=str(payload["reference_type"]),
            object_id=ArtifactId(str(payload["object_id"])),
            content_hash=str(payload["content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class ControlledCanonicalLifecycleRunReceipt:
    schema_version: str
    run_id: ArtifactId
    command_hash: str
    content_hash: str
    parent_operation_run_id: ArtifactId
    parent_operation_command_hash: str
    decision_time: datetime
    code_revision: str
    configuration_manifest_hash: str
    model_manifest_hash: str
    input_references: tuple[CanonicalLifecycleRunObjectReference, ...]
    output_references: tuple[CanonicalLifecycleRunObjectReference, ...]
    completed_stages: tuple[str, ...]
    created_at: datetime
    authority_ceiling: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTROLLED_CANONICAL_RUN_SCHEMA:
            raise ValueError("unsupported Controlled Canonical Lifecycle run schema")
        for label, value in (
            ("command_hash", self.command_hash),
            ("content_hash", self.content_hash),
            ("parent_operation_command_hash", self.parent_operation_command_hash),
            ("configuration_manifest_hash", self.configuration_manifest_hash),
            ("model_manifest_hash", self.model_manifest_hash),
        ):
            require_sha256(label, value)
        require_utc_second("decision_time", self.decision_time)
        require_utc_second("created_at", self.created_at)
        require_text("code_revision", self.code_revision)
        if self.created_at != self.decision_time:
            raise ValueError("Canonical child run created_at must use semantic DecisionTime")
        for label, references in (
            ("input", self.input_references),
            ("output", self.output_references),
        ):
            keys = tuple(
                (item.reference_type, str(item.object_id)) for item in references
            )
            if keys != tuple(sorted(set(keys))):
                raise ValueError(f"Canonical child-run {label} references are invalid")
        if self.completed_stages != (
            "ENTRY_ASSESSMENT",
            "PATH_FORECAST",
            "SIGNAL",
        ):
            raise ValueError("Canonical child run must settle the exact controlled segment")
        for required in (
            "BROKER_NOT_INVOKED",
            "ENTRY_BLOCKED",
            "NO_FILL_CREATED",
            "NO_MANUAL_TRADE_CREATED",
            "NO_ORDER_CREATED",
        ):
            if required not in self.authority_ceiling:
                raise ValueError("Canonical child-run authority ceiling is incomplete")
        if self.authority_ceiling != tuple(sorted(set(self.authority_ceiling))):
            raise ValueError("Canonical child-run authority ceiling is invalid")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        parent_operation_run_id: ArtifactId,
        parent_operation_command_hash: str,
        decision_time: datetime,
        code_revision: str,
        configuration_manifest_hash: str,
        model_manifest_hash: str,
        input_references: tuple[CanonicalLifecycleRunObjectReference, ...],
        output_references: tuple[CanonicalLifecycleRunObjectReference, ...],
        created_at: datetime,
    ) -> ControlledCanonicalLifecycleRunReceipt:
        inputs = tuple(
            sorted(
                input_references,
                key=lambda item: (item.reference_type, str(item.object_id)),
            )
        )
        outputs = tuple(
            sorted(
                output_references,
                key=lambda item: (item.reference_type, str(item.object_id)),
            )
        )
        command_payload = {
            "schema_version": CONTROLLED_CANONICAL_RUN_SCHEMA,
            "parent_operation_run_id": str(parent_operation_run_id),
            "parent_operation_command_hash": parent_operation_command_hash,
            "decision_time": canonical_datetime(decision_time),
            "code_revision": code_revision,
            "configuration_manifest_hash": configuration_manifest_hash,
            "model_manifest_hash": model_manifest_hash,
            "input_references": [item.to_canonical_dict() for item in inputs],
        }
        command_hash = canonical_hash(command_payload)
        run_id = ArtifactId(
            f"controlled-canonical-run-{command_hash.split(':', 1)[1][:24]}"
        )
        values = {
            **command_payload,
            "run_id": str(run_id),
            "command_hash": command_hash,
            "output_references": [item.to_canonical_dict() for item in outputs],
            "completed_stages": [
                "ENTRY_ASSESSMENT",
                "PATH_FORECAST",
                "SIGNAL",
            ],
            "created_at": canonical_datetime(created_at),
            "authority_ceiling": [
                "BROKER_NOT_INVOKED",
                "ENTRY_BLOCKED",
                "NO_FILL_CREATED",
                "NO_MANUAL_TRADE_CREATED",
                "NO_ORDER_CREATED",
            ],
        }
        digest = canonical_hash(values)
        return cls(
            schema_version=CONTROLLED_CANONICAL_RUN_SCHEMA,
            run_id=run_id,
            command_hash=command_hash,
            content_hash=digest,
            parent_operation_run_id=parent_operation_run_id,
            parent_operation_command_hash=parent_operation_command_hash,
            decision_time=decision_time,
            code_revision=code_revision,
            configuration_manifest_hash=configuration_manifest_hash,
            model_manifest_hash=model_manifest_hash,
            input_references=inputs,
            output_references=outputs,
            completed_stages=("ENTRY_ASSESSMENT", "PATH_FORECAST", "SIGNAL"),
            created_at=created_at,
            authority_ceiling=(
                "BROKER_NOT_INVOKED",
                "ENTRY_BLOCKED",
                "NO_FILL_CREATED",
                "NO_MANUAL_TRADE_CREATED",
                "NO_ORDER_CREATED",
            ),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": str(self.run_id),
            "command_hash": self.command_hash,
            "parent_operation_run_id": str(self.parent_operation_run_id),
            "parent_operation_command_hash": self.parent_operation_command_hash,
            "decision_time": canonical_datetime(self.decision_time),
            "code_revision": self.code_revision,
            "configuration_manifest_hash": self.configuration_manifest_hash,
            "model_manifest_hash": self.model_manifest_hash,
            "input_references": [
                item.to_canonical_dict() for item in self.input_references
            ],
            "output_references": [
                item.to_canonical_dict() for item in self.output_references
            ],
            "completed_stages": list(self.completed_stages),
            "created_at": canonical_datetime(self.created_at),
            "authority_ceiling": list(self.authority_ceiling),
        }

    def verify_identity(self) -> None:
        command_hash = canonical_hash(
            {
                key: value
                for key, value in self.semantic_payload().items()
                if key
                in {
                    "schema_version",
                    "parent_operation_run_id",
                    "parent_operation_command_hash",
                    "decision_time",
                    "code_revision",
                    "configuration_manifest_hash",
                    "model_manifest_hash",
                    "input_references",
                }
            }
        )
        if command_hash != self.command_hash:
            raise ValueError("Canonical child-run command hash mismatch")
        expected_run_id = (
            f"controlled-canonical-run-{command_hash.split(':', 1)[1][:24]}"
        )
        if str(self.run_id) != expected_run_id:
            raise ValueError("Canonical child-run identity mismatch")
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Canonical child-run Receipt hash mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"content_hash": self.content_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ControlledCanonicalLifecycleRunReceipt:
        expected = {
            "schema_version",
            "run_id",
            "command_hash",
            "content_hash",
            "parent_operation_run_id",
            "parent_operation_command_hash",
            "decision_time",
            "code_revision",
            "configuration_manifest_hash",
            "model_manifest_hash",
            "input_references",
            "output_references",
            "completed_stages",
            "created_at",
            "authority_ceiling",
        }
        if set(payload) != expected:
            raise ValueError("Canonical child-run Receipt fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            run_id=ArtifactId(str(payload["run_id"])),
            command_hash=str(payload["command_hash"]),
            content_hash=str(payload["content_hash"]),
            parent_operation_run_id=ArtifactId(
                str(payload["parent_operation_run_id"])
            ),
            parent_operation_command_hash=str(
                payload["parent_operation_command_hash"]
            ),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            code_revision=str(payload["code_revision"]),
            configuration_manifest_hash=str(
                payload["configuration_manifest_hash"]
            ),
            model_manifest_hash=str(payload["model_manifest_hash"]),
            input_references=_references(payload["input_references"], "input"),
            output_references=_references(payload["output_references"], "output"),
            completed_stages=_strings(payload["completed_stages"], "completed stages"),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            authority_ceiling=_strings(payload["authority_ceiling"], "authority ceiling"),
        )


def publish_controlled_canonical_lifecycle_run(
    *, root: Path, artifact: ControlledCanonicalLifecycleRunReceipt
) -> Path:
    artifact.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / str(artifact.run_id)
    if destination.exists():
        if load_controlled_canonical_lifecycle_run(destination) != artifact:
            raise ValueError("Canonical child-run identity conflict")
        return destination
    staging = Path(tempfile.mkdtemp(prefix=f".{artifact.run_id}.", dir=root))
    try:
        _write_json(staging / "artifact.json", artifact.to_canonical_dict())
        _write_json(
            staging / "SHA256SUMS.json",
            {"artifact.json": _file_hash(staging / "artifact.json")},
        )
        _write_json(
            staging / "manifest.json",
            {
                "schema_version": CONTROLLED_CANONICAL_RUN_PACKAGE_SCHEMA,
                "run_id": str(artifact.run_id),
                "content_hash": artifact.content_hash,
                "exact_file_set": list(CONTROLLED_CANONICAL_RUN_PACKAGE_FILES),
                "checksums_sha256": _file_hash(staging / "SHA256SUMS.json"),
            },
        )
        _fsync_directory(staging)
        staging.rename(destination)
        _fsync_directory(root)
    except FileExistsError:
        shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if load_controlled_canonical_lifecycle_run(destination) != artifact:
        raise ValueError("published Canonical child-run Receipt mismatch")
    return destination


def load_controlled_canonical_lifecycle_run(
    path: Path,
) -> ControlledCanonicalLifecycleRunReceipt:
    root = path.resolve()
    actual = tuple(sorted(item.name for item in root.iterdir() if item.is_file()))
    if actual != CONTROLLED_CANONICAL_RUN_PACKAGE_FILES:
        raise ValueError("Canonical child-run exact file set mismatch")
    manifest = _read_json(root / "manifest.json")
    if set(manifest) != {
        "schema_version",
        "run_id",
        "content_hash",
        "exact_file_set",
        "checksums_sha256",
    }:
        raise ValueError("Canonical child-run package manifest fields mismatch")
    if manifest["schema_version"] != CONTROLLED_CANONICAL_RUN_PACKAGE_SCHEMA:
        raise ValueError("unsupported Canonical child-run package schema")
    if tuple(manifest["exact_file_set"]) != CONTROLLED_CANONICAL_RUN_PACKAGE_FILES:
        raise ValueError("Canonical child-run manifest exact file set mismatch")
    if manifest["checksums_sha256"] != _file_hash(root / "SHA256SUMS.json"):
        raise ValueError("Canonical child-run checksum index mismatch")
    checksums = _read_json(root / "SHA256SUMS.json")
    if checksums != {"artifact.json": _file_hash(root / "artifact.json")}:
        raise ValueError("Canonical child-run checksums mismatch")
    result = ControlledCanonicalLifecycleRunReceipt.from_canonical_dict(
        _read_json(root / "artifact.json")
    )
    if (
        manifest["run_id"] != str(result.run_id)
        or manifest["content_hash"] != result.content_hash
    ):
        raise ValueError("Canonical child-run manifest identity mismatch")
    return result


def _references(
    value: object, label: str
) -> tuple[CanonicalLifecycleRunObjectReference, ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"Canonical child-run {label} references must be objects")
    return tuple(
        CanonicalLifecycleRunObjectReference.from_canonical_dict(item)
        for item in value
    )


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Canonical child-run {label} must be strings")
    return tuple(value)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("Canonical child-run JSON must be an object")
    return payload


def _file_hash(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _fsync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "CanonicalLifecycleRunObjectReference",
    "ControlledCanonicalLifecycleRunReceipt",
    "load_controlled_canonical_lifecycle_run",
    "publish_controlled_canonical_lifecycle_run",
]
