"""Repository Protocol and immutable Runtime Journal records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Mapping, Protocol

from market_regime_alpha.application.daily_loop.commands import (
    DailyRunCommand,
    DailyRunId,
    DailyRunIdentity,
    RunRequestId,
)
from market_regime_alpha.application.daily_loop.state import DailyRunStatus
from market_regime_alpha.core.identity import ArtifactId


_POST_SOURCE_FREEZE_STATUSES = frozenset(
    {
        DailyRunStatus.SOURCE_FROZEN,
        DailyRunStatus.DATA_BLOCKED,
        DailyRunStatus.UNIVERSE_READY,
        DailyRunStatus.FEATURES_READY,
        DailyRunStatus.PREDICTIONS_PUBLISHED,
        DailyRunStatus.DECISION_PUBLISHED,
        DailyRunStatus.OUTCOME_PENDING,
        DailyRunStatus.REVIEW_PUBLISHED,
    }
)


def _require_aware(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class DailyRunRecord:
    command: DailyRunCommand
    status: DailyRunStatus
    daily_run_identity: DailyRunIdentity | None
    resume_status: DailyRunStatus | None
    failure_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.status, DailyRunStatus):
            raise TypeError("status must be a DailyRunStatus")
        if self.daily_run_identity is not None and (
            self.daily_run_identity.run_request_id != self.command.run_request_id
            or self.daily_run_identity.run_request_hash != self.command.content_hash
        ):
            raise ValueError("DailyRunIdentity does not bind this RunRequest")
        identity_required = self.status in _POST_SOURCE_FREEZE_STATUSES or (
            self.status is DailyRunStatus.FAILED
            and self.resume_status in _POST_SOURCE_FREEZE_STATUSES
        )
        if identity_required and self.daily_run_identity is None:
            raise ValueError("post-Source-Freeze record requires DailyRunIdentity")
        if self.resume_status is not None and self.status is not DailyRunStatus.FAILED:
            raise ValueError("resume_status is valid only for FAILED records")
        if self.status is DailyRunStatus.FAILED:
            if self.resume_status is None or not self.failure_reason:
                raise ValueError("FAILED record requires resume_status and failure_reason")
        elif self.failure_reason is not None:
            raise ValueError("failure_reason is valid only for FAILED records")
        if isinstance(self.version, bool) or self.version < 0:
            raise ValueError("version must be a non-negative integer")
        _require_aware("created_at", self.created_at)
        _require_aware("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")

    @property
    def run_request_id(self) -> RunRequestId:
        return self.command.run_request_id

    @property
    def daily_run_id(self) -> DailyRunId | None:
        return (
            self.daily_run_identity.daily_run_id
            if self.daily_run_identity is not None
            else None
        )


@dataclass(frozen=True, slots=True)
class StageReceipt:
    SCHEMA_VERSION = "daily-stage-receipt-v1"

    run_request_id: RunRequestId
    stage: DailyRunStatus
    input_artifact_ids: tuple[ArtifactId, ...]
    output_artifact_ids: tuple[ArtifactId, ...]
    completed_at: datetime
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.run_request_id, RunRequestId):
            raise TypeError("run_request_id must be a RunRequestId")
        if not isinstance(self.stage, DailyRunStatus):
            raise TypeError("stage must be a DailyRunStatus")
        for label, values in (
            ("input_artifact_ids", self.input_artifact_ids),
            ("output_artifact_ids", self.output_artifact_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
            if tuple(sorted(values, key=str)) != values:
                raise ValueError(f"{label} must be sorted")
        _require_aware("completed_at", self.completed_at)
        object.__setattr__(
            self,
            "content_hash",
            _canonical_hash(self.semantic_payload()),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "run_request_id": str(self.run_request_id),
            "stage": self.stage.value,
            "input_artifact_ids": [str(value) for value in self.input_artifact_ids],
            "output_artifact_ids": [
                str(value) for value in self.output_artifact_ids
            ],
            "completed_at": self.completed_at.isoformat(),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {**self.semantic_payload(), "content_hash": self.content_hash}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StageReceipt:
        expected = {
            "schema_version",
            "run_request_id",
            "stage",
            "input_artifact_ids",
            "output_artifact_ids",
            "completed_at",
            "content_hash",
        }
        if set(payload) != expected:
            raise ValueError("StageReceipt fields mismatch")
        if payload.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported StageReceipt schema")
        inputs = _artifact_ids(payload.get("input_artifact_ids"), "input_artifact_ids")
        outputs = _artifact_ids(
            payload.get("output_artifact_ids"),
            "output_artifact_ids",
        )
        completed_at = _datetime_value(
            payload.get("completed_at"),
            "completed_at",
        )
        result = cls(
            run_request_id=RunRequestId(
                _string(payload.get("run_request_id"), "run_request_id")
            ),
            stage=DailyRunStatus(_string(payload.get("stage"), "stage")),
            input_artifact_ids=inputs,
            output_artifact_ids=outputs,
            completed_at=completed_at,
        )
        if result.content_hash != _string(
            payload.get("content_hash"),
            "content_hash",
        ):
            raise ValueError("StageReceipt content hash mismatch")
        return result


class DailyRunRepository(Protocol):
    """Persistence boundary for a replaceable Runtime Journal."""

    def create_or_get(
        self,
        command: DailyRunCommand,
        *,
        created_at: datetime,
    ) -> DailyRunRecord: ...

    def get(self, run_request_id: RunRequestId) -> DailyRunRecord: ...

    def get_by_daily_run_id(self, daily_run_id: DailyRunId) -> DailyRunRecord: ...

    def begin_source_acquisition(
        self,
        run_request_id: RunRequestId,
        *,
        changed_at: datetime,
    ) -> bool: ...

    def bind_source_frozen(
        self,
        run_request_id: RunRequestId,
        *,
        identity: DailyRunIdentity,
        changed_at: datetime,
    ) -> DailyRunRecord: ...

    def transition(
        self,
        run_request_id: RunRequestId,
        *,
        expected_status: DailyRunStatus,
        target_status: DailyRunStatus,
        changed_at: datetime,
    ) -> DailyRunRecord: ...

    def mark_failed(
        self,
        run_request_id: RunRequestId,
        *,
        reason: str,
        changed_at: datetime,
    ) -> DailyRunRecord: ...

    def resume_failed(
        self,
        run_request_id: RunRequestId,
        *,
        changed_at: datetime,
    ) -> DailyRunRecord: ...

    def record_stage_receipt(self, receipt: StageReceipt) -> StageReceipt: ...

    def get_stage_receipt(
        self,
        run_request_id: RunRequestId,
        stage: DailyRunStatus,
    ) -> StageReceipt | None: ...


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _datetime_value(value: object, label: str) -> datetime:
    raw = _string(value, label)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    _require_aware(label, parsed)
    return parsed


def _artifact_ids(value: object, label: str) -> tuple[ArtifactId, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(ArtifactId(item) for item in value)
