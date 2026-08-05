"""Immutable evidence boundary for one Controlled Decision-Time operation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.application.controlled_operation.journal import (
    ControlledOperationCommand,
    DecisionTimeOperationReceipt,
)
from market_regime_alpha.application.controlled_operation.policy import (
    DecisionTimeOperationPolicy,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second


CONTROLLED_OPERATION_PACKAGE_SCHEMA = "controlled-operational-evidence-package-v1"
CONTROLLED_OPERATION_PACKAGE_MANIFEST_SCHEMA = (
    "controlled-operational-evidence-package-manifest-v1"
)
CONTROLLED_OPERATION_PACKAGE_FILES = (
    "SHA256SUMS.json",
    "artifact.json",
    "manifest.json",
)


class ControlledOperationalEvidenceStatus(str, Enum):
    OPERATIONAL_EXPLORATORY_ARCHIVE = "OPERATIONAL_EXPLORATORY_ARCHIVE"
    DATA_BLOCKED = "DATA_BLOCKED"
    DEADLINE_MISSED = "DEADLINE_MISSED"
    OUTCOME_PENDING = "OUTCOME_PENDING"
    SETTLED = "SETTLED"


@dataclass(frozen=True, slots=True)
class ControlledEvidenceReference:
    reference_type: str
    object_id: ArtifactId
    content_hash: str
    locator: str

    def __post_init__(self) -> None:
        require_text("reference_type", self.reference_type)
        require_sha256("content_hash", self.content_hash)
        _require_relative_locator(self.locator)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "reference_type": self.reference_type,
            "object_id": str(self.object_id),
            "content_hash": self.content_hash,
            "locator": self.locator,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ControlledEvidenceReference:
        if set(payload) != {"reference_type", "object_id", "content_hash", "locator"}:
            raise ValueError("Controlled evidence reference fields mismatch")
        return cls(
            reference_type=str(payload["reference_type"]),
            object_id=ArtifactId(str(payload["object_id"])),
            content_hash=str(payload["content_hash"]),
            locator=str(payload["locator"]),
        )


@dataclass(frozen=True, slots=True)
class StageRuntimeLatency:
    stage_name: str
    elapsed_ms: int

    def __post_init__(self) -> None:
        require_text("stage_name", self.stage_name)
        if self.elapsed_ms < 0:
            raise ValueError("stage latency cannot be negative")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"stage_name": self.stage_name, "elapsed_ms": self.elapsed_ms}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StageRuntimeLatency:
        if set(payload) != {"stage_name", "elapsed_ms"}:
            raise ValueError("stage latency fields mismatch")
        return cls(stage_name=str(payload["stage_name"]), elapsed_ms=int(payload["elapsed_ms"]))


@dataclass(frozen=True, slots=True)
class ControlledOperationalEvidencePackage:
    schema_version: str
    package_id: ArtifactId
    content_hash: str
    command: ControlledOperationCommand
    policy: DecisionTimeOperationPolicy
    status: ControlledOperationalEvidenceStatus
    evidence_references: tuple[ControlledEvidenceReference, ...]
    stage_receipts: tuple[DecisionTimeOperationReceipt, ...]
    code_revision: str
    configuration_manifest_id: ArtifactId
    configuration_manifest_hash: str
    model_manifest_id: ArtifactId
    model_manifest_hash: str
    feature_set_id: ArtifactId
    signal_model_id: str
    signal_model_version: str
    configuration_hashes: tuple[str, ...]
    universe_count: int
    candidate_count: int
    minute_success_count: int
    minute_failure_count: int
    signal_state_counts: tuple[tuple[str, int], ...]
    stage_latencies: tuple[StageRuntimeLatency, ...]
    deadline_status: str
    created_at: datetime
    authority_ceiling: tuple[str, ...]
    limitations: tuple[str, ...]
    supersedes_package_id: ArtifactId | None = None
    supersedes_package_hash: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != CONTROLLED_OPERATION_PACKAGE_SCHEMA:
            raise ValueError("unsupported Controlled operation package schema")
        require_sha256("content_hash", self.content_hash)
        require_sha256("configuration_manifest_hash", self.configuration_manifest_hash)
        require_sha256("model_manifest_hash", self.model_manifest_hash)
        require_utc_second("created_at", self.created_at)
        require_text("code_revision", self.code_revision)
        require_text("deadline_status", self.deadline_status)
        require_text("signal_model_id", self.signal_model_id)
        require_text("signal_model_version", self.signal_model_version)
        if not self.configuration_hashes or self.configuration_hashes != tuple(
            sorted(set(self.configuration_hashes))
        ):
            raise ValueError("Controlled package configuration hashes are invalid")
        for digest in self.configuration_hashes:
            require_sha256("configuration hash", digest)
        if (self.supersedes_package_id is None) != (self.supersedes_package_hash is None):
            raise ValueError("superseded package reference is incomplete")
        if self.supersedes_package_hash is not None:
            require_sha256("supersedes_package_hash", self.supersedes_package_hash)
        if self.command.code_revision != self.code_revision:
            raise ValueError("Controlled package code revision mismatch")
        if (
            self.command.policy_id != self.policy.policy_id
            or self.command.policy_hash != self.policy.content_hash
        ):
            raise ValueError("Controlled package policy binding mismatch")
        if (
            self.command.configuration_manifest_id != self.configuration_manifest_id
            or self.command.configuration_manifest_hash != self.configuration_manifest_hash
            or self.command.model_manifest_id != self.model_manifest_id
            or self.command.model_manifest_hash != self.model_manifest_hash
        ):
            raise ValueError("Controlled package manifest binding mismatch")
        for name, value in (
            ("universe_count", self.universe_count),
            ("candidate_count", self.candidate_count),
            ("minute_success_count", self.minute_success_count),
            ("minute_failure_count", self.minute_failure_count),
        ):
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.minute_success_count + self.minute_failure_count != self.candidate_count:
            raise ValueError("Controlled package minute coverage counts mismatch")
        reference_keys = tuple(
            (item.reference_type, str(item.object_id)) for item in self.evidence_references
        )
        if reference_keys != tuple(sorted(set(reference_keys))):
            raise ValueError("Controlled package evidence references must be unique and sorted")
        receipt_keys = tuple(item.stage_name.value for item in self.stage_receipts)
        if receipt_keys != tuple(sorted(set(receipt_keys))):
            raise ValueError("Controlled package stage Receipts must be unique and sorted")
        signal_keys = tuple(item[0] for item in self.signal_state_counts)
        if signal_keys != tuple(sorted(set(signal_keys))) or any(
            count < 0 for _, count in self.signal_state_counts
        ):
            raise ValueError("Controlled package Signal counts are invalid")
        latency_keys = tuple(item.stage_name for item in self.stage_latencies)
        if latency_keys != tuple(sorted(set(latency_keys))):
            raise ValueError("Controlled package stage latencies must be unique and sorted")
        for label, values in (
            ("authority_ceiling", self.authority_ceiling),
            ("limitations", self.limitations),
        ):
            if not values or values != tuple(sorted(set(values))):
                raise ValueError(f"Controlled package {label} must be non-empty and sorted")
        for required in (
            "BROKER_NOT_INVOKED",
            "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_FILL_CREATED",
            "NO_ORDER_CREATED",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ):
            if required not in self.authority_ceiling:
                raise ValueError("Controlled package authority ceiling is incomplete")
        if self.status is ControlledOperationalEvidenceStatus.SETTLED:
            if self.supersedes_package_id is None or "OUTCOME_OBSERVATION" not in {
                item.reference_type for item in self.evidence_references
            }:
                raise ValueError("settled package requires prior package and Outcome evidence")
        self._validate_required_references()
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        command: ControlledOperationCommand,
        policy: DecisionTimeOperationPolicy,
        status: ControlledOperationalEvidenceStatus,
        evidence_references: tuple[ControlledEvidenceReference, ...],
        stage_receipts: tuple[DecisionTimeOperationReceipt, ...],
        code_revision: str,
        feature_set_id: ArtifactId,
        signal_model_id: str,
        signal_model_version: str,
        configuration_hashes: tuple[str, ...],
        universe_count: int,
        candidate_count: int,
        minute_success_count: int,
        minute_failure_count: int,
        signal_state_counts: tuple[tuple[str, int], ...],
        stage_latencies: tuple[StageRuntimeLatency, ...],
        deadline_status: str,
        created_at: datetime,
        authority_ceiling: tuple[str, ...],
        limitations: tuple[str, ...],
        supersedes_package_id: ArtifactId | None = None,
        supersedes_package_hash: str | None = None,
    ) -> ControlledOperationalEvidencePackage:
        values: dict[str, Any] = {
            "command": command,
            "policy": policy,
            "status": status,
            "evidence_references": tuple(
                sorted(evidence_references, key=lambda item: (item.reference_type, str(item.object_id)))
            ),
            "stage_receipts": tuple(sorted(stage_receipts, key=lambda item: item.stage_name.value)),
            "code_revision": code_revision,
            "configuration_manifest_id": command.configuration_manifest_id,
            "configuration_manifest_hash": command.configuration_manifest_hash,
            "model_manifest_id": command.model_manifest_id,
            "model_manifest_hash": command.model_manifest_hash,
            "feature_set_id": feature_set_id,
            "signal_model_id": signal_model_id,
            "signal_model_version": signal_model_version,
            "configuration_hashes": tuple(sorted(set(configuration_hashes))),
            "universe_count": universe_count,
            "candidate_count": candidate_count,
            "minute_success_count": minute_success_count,
            "minute_failure_count": minute_failure_count,
            "signal_state_counts": tuple(sorted(signal_state_counts)),
            "stage_latencies": tuple(sorted(stage_latencies, key=lambda item: item.stage_name)),
            "deadline_status": deadline_status,
            "created_at": created_at,
            "authority_ceiling": tuple(sorted(set(authority_ceiling))),
            "limitations": tuple(sorted(set(limitations))),
            "supersedes_package_id": supersedes_package_id,
            "supersedes_package_hash": supersedes_package_hash,
        }
        digest = canonical_hash(_payload(**values))
        return cls(
            schema_version=CONTROLLED_OPERATION_PACKAGE_SCHEMA,
            package_id=ArtifactId(f"controlled-package-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            **values,
        )

    def _validate_required_references(self) -> None:
        present = {item.reference_type for item in self.evidence_references}
        required = {
            "TRADING_CALENDAR",
            "OPERATIONAL_UNIVERSE",
            "DAILY_SOURCE_ARCHIVE",
            "DAILY_SOURCE_MANIFEST",
            "DAILY_DATASET",
            "STATIC_FEATURE_BUNDLE",
            "CONTROLLED_RESEARCH",
            "CANDIDATE_SET",
            "MINUTE_ACQUISITION_COVERAGE",
            "MINUTE_DATASET",
            "INTRADAY_FEATURE_OVERLAY",
            "CANDIDATE_FEATURE_VIEW_V2",
            "SIGNAL_V3",
            "PATH_FORECAST",
            "ENTRY_BLOCKER",
            "CANONICAL_LIFECYCLE_RUN",
        }
        if self.status in {
            ControlledOperationalEvidenceStatus.OPERATIONAL_EXPLORATORY_ARCHIVE,
            ControlledOperationalEvidenceStatus.OUTCOME_PENDING,
            ControlledOperationalEvidenceStatus.SETTLED,
        } and not required.issubset(present):
            missing = ",".join(sorted(required - present))
            raise ValueError(f"Controlled package required evidence is missing: {missing}")
        if self.status is ControlledOperationalEvidenceStatus.SETTLED:
            settlement_required = {
                "OUTCOME_SOURCE_ARCHIVE",
                "OUTCOME_SOURCE_MANIFEST",
                "OUTCOME_DATASET",
                "OUTCOME_OBSERVATION",
            }
            if not settlement_required.issubset(present):
                missing = ",".join(sorted(settlement_required - present))
                raise ValueError(
                    f"settled Controlled package evidence is missing: {missing}"
                )

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(**_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Controlled operation package hash mismatch")
        expected = f"controlled-package-{digest.split(':', 1)[1][:24]}"
        if str(self.package_id) != expected:
            raise ValueError("Controlled operation package identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "package_id": str(self.package_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ControlledOperationalEvidencePackage:
        expected = {"package_id", "content_hash", *_payload_keys()}
        if set(payload) != expected:
            raise ValueError("Controlled operation package fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            package_id=ArtifactId(str(payload["package_id"])),
            content_hash=str(payload["content_hash"]),
            command=ControlledOperationCommand.from_canonical_dict(
                _object(payload["command"], "command")
            ),
            policy=DecisionTimeOperationPolicy.from_canonical_dict(
                _object(payload["policy"], "policy")
            ),
            status=ControlledOperationalEvidenceStatus(str(payload["status"])),
            evidence_references=tuple(
                ControlledEvidenceReference.from_canonical_dict(item)
                for item in _objects(payload["evidence_references"], "evidence references")
            ),
            stage_receipts=tuple(
                DecisionTimeOperationReceipt.from_canonical_dict(item)
                for item in _objects(payload["stage_receipts"], "stage receipts")
            ),
            code_revision=str(payload["code_revision"]),
            configuration_manifest_id=ArtifactId(str(payload["configuration_manifest_id"])),
            configuration_manifest_hash=str(payload["configuration_manifest_hash"]),
            model_manifest_id=ArtifactId(str(payload["model_manifest_id"])),
            model_manifest_hash=str(payload["model_manifest_hash"]),
            feature_set_id=ArtifactId(str(payload["feature_set_id"])),
            signal_model_id=str(payload["signal_model_id"]),
            signal_model_version=str(payload["signal_model_version"]),
            configuration_hashes=_strings(
                payload["configuration_hashes"], "configuration hashes"
            ),
            universe_count=int(payload["universe_count"]),
            candidate_count=int(payload["candidate_count"]),
            minute_success_count=int(payload["minute_success_count"]),
            minute_failure_count=int(payload["minute_failure_count"]),
            signal_state_counts=_signal_state_counts(payload["signal_state_counts"]),
            stage_latencies=tuple(
                StageRuntimeLatency.from_canonical_dict(item)
                for item in _objects(payload["stage_latencies"], "stage latencies")
            ),
            deadline_status=str(payload["deadline_status"]),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            authority_ceiling=_strings(payload["authority_ceiling"], "authority ceiling"),
            limitations=_strings(payload["limitations"], "limitations"),
            supersedes_package_id=(
                ArtifactId(str(payload["supersedes_package_id"]))
                if payload["supersedes_package_id"] is not None
                else None
            ),
            supersedes_package_hash=(
                str(payload["supersedes_package_hash"])
                if payload["supersedes_package_hash"] is not None
                else None
            ),
        )


def publish_controlled_operation_package(
    *, root: Path, artifact: ControlledOperationalEvidencePackage
) -> Path:
    artifact.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / str(artifact.package_id)
    if destination.exists():
        if load_controlled_operation_package(destination) != artifact:
            raise ValueError("Controlled operation package identity conflict")
        return destination
    staging = Path(tempfile.mkdtemp(prefix=f".{artifact.package_id}.", dir=root))
    try:
        _write_json(staging / "artifact.json", artifact.to_canonical_dict())
        checksums = {"artifact.json": _file_sha256(staging / "artifact.json")}
        _write_json(staging / "SHA256SUMS.json", checksums)
        _write_json(
            staging / "manifest.json",
            {
                "schema_version": CONTROLLED_OPERATION_PACKAGE_MANIFEST_SCHEMA,
                "package_id": str(artifact.package_id),
                "content_hash": artifact.content_hash,
                "exact_file_set": list(CONTROLLED_OPERATION_PACKAGE_FILES),
                "checksums_sha256": _file_sha256(staging / "SHA256SUMS.json"),
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
    if load_controlled_operation_package(destination) != artifact:
        raise ValueError("published Controlled operation package semantic mismatch")
    return destination


def load_controlled_operation_package(path: Path) -> ControlledOperationalEvidencePackage:
    expected = set(CONTROLLED_OPERATION_PACKAGE_FILES)
    actual = {item.name for item in path.iterdir() if item.is_file()}
    if actual != expected:
        raise ValueError("Controlled operation package exact file set mismatch")
    manifest = _read_json(path / "manifest.json")
    if manifest.get("schema_version") != CONTROLLED_OPERATION_PACKAGE_MANIFEST_SCHEMA:
        raise ValueError("Controlled operation package manifest schema mismatch")
    if manifest.get("exact_file_set") != list(CONTROLLED_OPERATION_PACKAGE_FILES):
        raise ValueError("Controlled operation package manifest file set mismatch")
    if manifest.get("checksums_sha256") != _file_sha256(path / "SHA256SUMS.json"):
        raise ValueError("Controlled operation package checksums hash mismatch")
    checksums = _read_json(path / "SHA256SUMS.json")
    if checksums != {"artifact.json": _file_sha256(path / "artifact.json")}:
        raise ValueError("Controlled operation package checksum mismatch")
    artifact = ControlledOperationalEvidencePackage.from_canonical_dict(
        _read_json(path / "artifact.json")
    )
    if (
        manifest.get("package_id") != str(artifact.package_id)
        or manifest.get("content_hash") != artifact.content_hash
    ):
        raise ValueError("Controlled operation package manifest identity mismatch")
    return artifact


def replay_controlled_operation_package(path: Path) -> ControlledOperationalEvidencePackage:
    artifact = load_controlled_operation_package(path)
    replayed = ControlledOperationalEvidencePackage.create(
        **_values(artifact),
    )
    if replayed != artifact:
        raise ValueError("Controlled operation package replay divergence")
    return replayed


def _values(item: ControlledOperationalEvidencePackage) -> dict[str, Any]:
    return {
        name: getattr(item, name)
        for name in _value_names()
    }


def _value_names() -> tuple[str, ...]:
    return (
        "command", "policy", "status", "evidence_references", "stage_receipts",
        "code_revision", "feature_set_id", "signal_model_id", "signal_model_version",
        "configuration_hashes", "universe_count", "candidate_count", "minute_success_count",
        "minute_failure_count", "signal_state_counts", "stage_latencies",
        "deadline_status", "created_at", "authority_ceiling", "limitations",
        "supersedes_package_id", "supersedes_package_hash",
    )


def _payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTROLLED_OPERATION_PACKAGE_SCHEMA,
        "command": values["command"].to_canonical_dict(),
        "policy": values["policy"].to_canonical_dict(),
        "status": values["status"].value,
        "evidence_references": [item.to_canonical_dict() for item in values["evidence_references"]],
        "stage_receipts": [item.to_canonical_dict() for item in values["stage_receipts"]],
        "code_revision": values["code_revision"],
        "configuration_manifest_id": str(values.get("configuration_manifest_id", values["command"].configuration_manifest_id)),
        "configuration_manifest_hash": values.get("configuration_manifest_hash", values["command"].configuration_manifest_hash),
        "model_manifest_id": str(values.get("model_manifest_id", values["command"].model_manifest_id)),
        "model_manifest_hash": values.get("model_manifest_hash", values["command"].model_manifest_hash),
        "feature_set_id": str(values["feature_set_id"]),
        "signal_model_id": values["signal_model_id"],
        "signal_model_version": values["signal_model_version"],
        "configuration_hashes": list(values["configuration_hashes"]),
        "universe_count": values["universe_count"],
        "candidate_count": values["candidate_count"],
        "minute_success_count": values["minute_success_count"],
        "minute_failure_count": values["minute_failure_count"],
        "signal_state_counts": [
            {"state": state, "count": count} for state, count in values["signal_state_counts"]
        ],
        "stage_latencies": [item.to_canonical_dict() for item in values["stage_latencies"]],
        "deadline_status": values["deadline_status"],
        "created_at": canonical_datetime(values["created_at"]),
        "authority_ceiling": list(values["authority_ceiling"]),
        "limitations": list(values["limitations"]),
        "supersedes_package_id": (
            str(values["supersedes_package_id"])
            if values["supersedes_package_id"] is not None else None
        ),
        "supersedes_package_hash": values["supersedes_package_hash"],
    }


def _payload_keys() -> set[str]:
    return set(_payload(**_dummy_values()))


def _dummy_values() -> dict[str, Any]:
    # Only keys are needed by the strict parser; avoid constructing domain objects.
    return {
        "command": _KeyOnly(), "policy": _KeyOnly(),
        "status": ControlledOperationalEvidenceStatus.OUTCOME_PENDING,
        "evidence_references": (), "stage_receipts": (), "code_revision": "x",
        "feature_set_id": ArtifactId("x"), "signal_model_id": "x",
        "signal_model_version": "x", "configuration_hashes": ("sha256:" + "0" * 64,),
        "universe_count": 0, "candidate_count": 0, "minute_success_count": 0,
        "minute_failure_count": 0, "signal_state_counts": (), "stage_latencies": (),
        "deadline_status": "x", "created_at": datetime(2000, 1, 1).astimezone(),
        "authority_ceiling": (), "limitations": (), "supersedes_package_id": None,
        "supersedes_package_hash": None,
    }


class _KeyOnly:
    configuration_manifest_id = ArtifactId("x")
    configuration_manifest_hash = "sha256:" + "0" * 64
    model_manifest_id = ArtifactId("x")
    model_manifest_hash = "sha256:" + "0" * 64

    def to_canonical_dict(self) -> dict[str, Any]:
        return {}


def _require_relative_locator(value: str) -> None:
    require_text("locator", value)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ValueError("evidence locator must be a normalized relative path")


def _file_sha256(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("Controlled operation package JSON must be an object")
    return payload


def _objects(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must be an object array")
    return tuple(value)


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _signal_state_counts(value: object) -> tuple[tuple[str, int], ...]:
    items = _objects(value, "signal state counts")
    if any(set(item) != {"state", "count"} for item in items):
        raise ValueError("signal state count fields mismatch")
    return tuple((str(item["state"]), int(item["count"])) for item in items)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _fsync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "CONTROLLED_OPERATION_PACKAGE_FILES",
    "ControlledEvidenceReference",
    "ControlledOperationalEvidencePackage",
    "ControlledOperationalEvidenceStatus",
    "StageRuntimeLatency",
    "load_controlled_operation_package",
    "publish_controlled_operation_package",
    "replay_controlled_operation_package",
]
