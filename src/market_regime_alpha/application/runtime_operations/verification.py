"""Commit-bound local engineering verification evidence, never capability evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any, Mapping

from market_regime_alpha.application.canonical_lifecycle._immutable_io import (
    publish_immutable_text,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)


VERIFICATION_RECORD_SCHEMA = "engineering-verification-record/v1"
REQUIRED_LOCAL_GATES = (
    "UV_SYNC",
    "DOCS_LINKS",
    "PYTEST",
    "RUFF",
    "MYPY",
    "BUILD",
    "GIT_DIFF_CHECK",
)


class VerificationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"
    BLOCKED = "BLOCKED"


class CIStatus(str, Enum):
    PASS = "CI_PASS"
    FAIL = "CI_FAIL"
    NOT_RUN = "CI_NOT_RUN"
    EXTERNAL_BLOCKED = "CI_EXTERNAL_BLOCKED"


class EngineeringReadiness(str, Enum):
    ENGINEERING_READY = "ENGINEERING_READY"
    ENGINEERING_NOT_READY = "ENGINEERING_NOT_READY"


@dataclass(frozen=True, slots=True)
class VerificationGateResult:
    gate: str
    command: tuple[str, ...]
    status: VerificationStatus
    exit_code: int | None
    duration_seconds: float
    output_sha256: str | None
    summary: str

    def __post_init__(self) -> None:
        require_text("gate", self.gate)
        if not self.command or any(not item for item in self.command):
            raise ValueError("Verification command must be non-empty")
        if self.duration_seconds < 0:
            raise ValueError("Verification duration cannot be negative")
        if self.status in {VerificationStatus.PASS, VerificationStatus.FAIL}:
            if self.exit_code is None or self.output_sha256 is None:
                raise ValueError("executed Verification gate requires result evidence")
        elif self.exit_code is not None or self.output_sha256 is not None:
            raise ValueError("unexecuted Verification gate cannot claim process evidence")
        if self.output_sha256 is not None and not re.fullmatch(
            r"[0-9a-f]{64}", self.output_sha256
        ):
            raise ValueError("Verification output hash must be raw SHA-256 hex")
        require_text("summary", self.summary)

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "gate": self.gate,
            "command": list(self.command),
            "status": self.status.value,
            "exit_code": self.exit_code,
            "duration_seconds": format(self.duration_seconds, ".3f"),
            "output_sha256": self.output_sha256,
            "summary": self.summary,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> VerificationGateResult:
        exit_code = payload["exit_code"]
        output_hash = payload["output_sha256"]
        return cls(
            gate=_text(payload["gate"]),
            command=_strings(payload["command"]),
            status=VerificationStatus(_text(payload["status"])),
            exit_code=None if exit_code is None else int(exit_code),
            duration_seconds=float(_text(payload["duration_seconds"])),
            output_sha256=(None if output_hash is None else _text(output_hash)),
            summary=_text(payload["summary"]),
        )


@dataclass(frozen=True, slots=True)
class EngineeringVerificationRecord:
    record_id: ArtifactId
    record_hash: str
    commit_sha: str
    python_version: str
    uv_version: str
    postgres_version: str
    migration_head: int
    application_schema: str
    environment: str
    dirty_worktree: bool
    gates: tuple[VerificationGateResult, ...]
    ci_status: CIStatus
    readiness: EngineeringReadiness
    verified_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = VERIFICATION_RECORD_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != VERIFICATION_RECORD_SCHEMA:
            raise ValueError("unsupported Engineering Verification schema")
        require_sha256("record_hash", self.record_hash)
        if not re.fullmatch(r"[0-9a-f]{40}", self.commit_sha):
            raise ValueError("Verification commit SHA must be a full Git SHA")
        for label, value in (
            ("python_version", self.python_version),
            ("uv_version", self.uv_version),
            ("postgres_version", self.postgres_version),
            ("application_schema", self.application_schema),
            ("environment", self.environment),
        ):
            require_text(label, value)
        if self.migration_head <= 0 or isinstance(self.migration_head, bool):
            raise ValueError("Verification migration head must be positive")
        gate_names = tuple(item.gate for item in self.gates)
        if gate_names != REQUIRED_LOCAL_GATES:
            raise ValueError("Verification Record requires every ordered local gate")
        expected_readiness = (
            EngineeringReadiness.ENGINEERING_READY
            if not self.dirty_worktree
            and all(item.status is VerificationStatus.PASS for item in self.gates)
            else EngineeringReadiness.ENGINEERING_NOT_READY
        )
        if self.readiness is not expected_readiness:
            raise ValueError("Engineering readiness does not match observed gates")
        _aware("verified_at", self.verified_at)
        required = {
            "ENGINEERING_EVIDENCE_ONLY",
            "NOT_ALPHA_EVIDENCE",
            "NOT_LIVE_EVIDENCE",
            "NOT_PRODUCTION_AUTHORIZATION",
            "NOT_PROSPECTIVE_EVIDENCE",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Verification authority ceiling is incomplete")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Verification limitations must be unique and sorted")
        if canonical_hash(self.semantic_payload()) != self.record_hash:
            raise ValueError("Engineering Verification hash mismatch")
        if self.record_id != _content_id("engineering-verification", self.record_hash):
            raise ValueError("Engineering Verification identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> EngineeringVerificationRecord:
        normalized = dict(values)
        normalized["limitations"] = tuple(sorted(set(values["limitations"])))
        digest = canonical_hash(_record_payload(**normalized))
        return cls(
            record_id=_content_id("engineering-verification", digest),
            record_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, object]:
        return _record_payload(
            commit_sha=self.commit_sha,
            python_version=self.python_version,
            uv_version=self.uv_version,
            postgres_version=self.postgres_version,
            migration_head=self.migration_head,
            application_schema=self.application_schema,
            environment=self.environment,
            dirty_worktree=self.dirty_worktree,
            gates=self.gates,
            ci_status=self.ci_status,
            readiness=self.readiness,
            verified_at=self.verified_at,
            limitations=self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "record_id": str(self.record_id),
            "record_hash": self.record_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> EngineeringVerificationRecord:
        return cls(
            record_id=ArtifactId(_text(payload["record_id"])),
            record_hash=_text(payload["record_hash"]),
            commit_sha=_text(payload["commit_sha"]),
            python_version=_text(payload["python_version"]),
            uv_version=_text(payload["uv_version"]),
            postgres_version=_text(payload["postgres_version"]),
            migration_head=int(payload["migration_head"]),
            application_schema=_text(payload["application_schema"]),
            environment=_text(payload["environment"]),
            dirty_worktree=bool(payload["dirty_worktree"]),
            gates=tuple(
                VerificationGateResult.from_canonical_dict(_mapping(item))
                for item in _array(payload["gates"])
            ),
            ci_status=CIStatus(_text(payload["ci_status"])),
            readiness=EngineeringReadiness(_text(payload["readiness"])),
            verified_at=_instant(payload["verified_at"]),
            limitations=_strings(payload["limitations"]),
            schema_version=_text(payload["schema_version"]),
        )


def publish_engineering_verification(
    *, root: Path, record: EngineeringVerificationRecord
) -> Path:
    path = root / f"{record.record_id}.json"
    publish_immutable_text(
        path=path,
        payload=canonical_json(record.to_canonical_dict()) + "\n",
        collision_message="Engineering Verification identity conflict",
    )
    if load_engineering_verification(path) != record:
        raise ValueError("published Engineering Verification semantic mismatch")
    return path


def load_engineering_verification(path: Path) -> EngineeringVerificationRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Engineering Verification payload must be an object")
    return EngineeringVerificationRecord.from_canonical_dict(payload)


def _record_payload(**values: Any) -> dict[str, object]:
    return {
        "schema_version": VERIFICATION_RECORD_SCHEMA,
        "commit_sha": values["commit_sha"],
        "python_version": values["python_version"],
        "uv_version": values["uv_version"],
        "postgres_version": values["postgres_version"],
        "migration_head": values["migration_head"],
        "application_schema": values["application_schema"],
        "environment": values["environment"],
        "dirty_worktree": values["dirty_worktree"],
        "gates": [item.to_canonical_dict() for item in values["gates"]],
        "ci_status": values["ci_status"].value,
        "readiness": values["readiness"].value,
        "verified_at": canonical_datetime(values["verified_at"]),
        "limitations": list(values["limitations"]),
    }


def _content_id(prefix: str, digest: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{digest.split(':', 1)[1][:24]}")


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _instant(value: object) -> datetime:
    parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    _aware("instant", parsed)
    return parsed


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Verification value must be non-empty text")
    return value


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Verification value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Verification value must be an array")
    return value


def _strings(value: object) -> tuple[str, ...]:
    values = _array(value)
    if any(not isinstance(item, str) for item in values):
        raise ValueError("Verification value must be a string array")
    return tuple(str(item) for item in values)


__all__ = [
    "CIStatus",
    "EngineeringReadiness",
    "EngineeringVerificationRecord",
    "REQUIRED_LOCAL_GATES",
    "VerificationGateResult",
    "VerificationStatus",
    "load_engineering_verification",
    "publish_engineering_verification",
]
