"""Immutable contracts for the canonical Lifecycle Runtime Journal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Mapping, TypeVar

from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    WAITING_LIFECYCLE_RUN_STATUSES,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId, StableId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)


class LifecycleRunId(StableId):
    """Stable identity of one canonical lifecycle run."""


class LifecycleAttemptId(StableId):
    """Stable identity of one append-only stage invocation."""


class LifecycleEventId(StableId):
    """Stable identity of one append-only journal event."""


class LifecycleObjectId(StableId):
    """Lossless reference identity for an Artifact or domain object."""


class LifecycleObjectType(str, Enum):
    COMPOSITE_OPERATIONAL_MANIFEST = "COMPOSITE_OPERATIONAL_MANIFEST"
    SOURCE_MANIFEST = "SOURCE_MANIFEST"
    DAILY_DECISION_ARTIFACT = "DAILY_DECISION_ARTIFACT"
    SUPPLEMENTAL_RESEARCH_EVIDENCE = "SUPPLEMENTAL_RESEARCH_EVIDENCE"
    PLATFORM_RESEARCH_ARTIFACT = "PLATFORM_RESEARCH_ARTIFACT"
    SIGNAL_ARTIFACT = "SIGNAL_ARTIFACT"
    PATH_FORECAST_ARTIFACT = "PATH_FORECAST_ARTIFACT"
    ENTRY_ASSESSMENT = "ENTRY_ASSESSMENT"
    OPPORTUNITY = "OPPORTUNITY"
    THESIS = "THESIS"
    PORTFOLIO_DECISION = "PORTFOLIO_DECISION"
    RISK_DECISION = "RISK_DECISION"
    RISK_REDUCING_DECISION = "RISK_REDUCING_DECISION"
    OPERATIONAL_EXIT_DIRECTIVE = "OPERATIONAL_EXIT_DIRECTIVE"
    REDUCING_EXECUTION_OBSERVATION = "REDUCING_EXECUTION_OBSERVATION"
    SYMBOL_TRADING_SESSION_STATUS_SET = "SYMBOL_TRADING_SESSION_STATUS_SET"
    RISK_REDUCTION_CONFIRMATION_POLICY = "RISK_REDUCTION_CONFIRMATION_POLICY"
    RISK_REDUCTION_CONFIRMATION = "RISK_REDUCTION_CONFIRMATION"
    MANUAL_TRADE = "MANUAL_TRADE"
    FILL = "FILL"
    POSITION_SNAPSHOT = "POSITION_SNAPSHOT"
    POSITION_BOOK = "POSITION_BOOK"
    TRADING_CALENDAR_ARTIFACT = "TRADING_CALENDAR_ARTIFACT"
    THESIS_HEALTH_OBSERVATION = "THESIS_HEALTH_OBSERVATION"
    HOLDING_ASSESSMENT = "HOLDING_ASSESSMENT"
    EXIT_ASSESSMENT = "EXIT_ASSESSMENT"
    OUTCOME_REVIEW = "OUTCOME_REVIEW"
    FEATURE_ARTIFACT = "FEATURE_ARTIFACT"
    MODEL_COMPARISON_REPORT = "MODEL_COMPARISON_REPORT"


class LifecycleReaderKind(str, Enum):
    COMPOSITE_OPERATIONAL_ARTIFACT_READER = (
        "COMPOSITE_OPERATIONAL_ARTIFACT_READER"
    )
    SOURCE_MANIFEST_READER = "SOURCE_MANIFEST_READER"
    DAILY_DECISION_ARTIFACT_READER = "DAILY_DECISION_ARTIFACT_READER"
    SUPPLEMENTAL_RESEARCH_EVIDENCE_READER = (
        "SUPPLEMENTAL_RESEARCH_EVIDENCE_READER"
    )
    PLATFORM_RESEARCH_ARTIFACT_READER = "PLATFORM_RESEARCH_ARTIFACT_READER"
    SIGNAL_ARTIFACT_READER = "SIGNAL_ARTIFACT_READER"
    PATH_FORECAST_ARTIFACT_READER = "PATH_FORECAST_ARTIFACT_READER"
    DECISION_LIFECYCLE_REPOSITORY = "DECISION_LIFECYCLE_REPOSITORY"
    PORTFOLIO_RISK_REPOSITORY = "PORTFOLIO_RISK_REPOSITORY"
    RISK_REDUCTION_REPOSITORY = "RISK_REDUCTION_REPOSITORY"
    OPERATIONAL_EXIT_DIRECTIVE_REPOSITORY = (
        "OPERATIONAL_EXIT_DIRECTIVE_REPOSITORY"
    )
    REDUCING_EXECUTION_OBSERVATION_READER = (
        "REDUCING_EXECUTION_OBSERVATION_READER"
    )
    SYMBOL_TRADING_SESSION_STATUS_READER = (
        "SYMBOL_TRADING_SESSION_STATUS_READER"
    )
    RISK_REDUCTION_CONFIRMATION_POLICY_READER = (
        "RISK_REDUCTION_CONFIRMATION_POLICY_READER"
    )
    MANUAL_TRADE_REPOSITORY = "MANUAL_TRADE_REPOSITORY"
    MANUAL_FILL_LEDGER = "MANUAL_FILL_LEDGER"
    POSITION_SNAPSHOT_REPOSITORY = "POSITION_SNAPSHOT_REPOSITORY"
    POSITION_BOOK_REPOSITORY = "POSITION_BOOK_REPOSITORY"
    TRADING_CALENDAR_ARTIFACT_READER = "TRADING_CALENDAR_ARTIFACT_READER"
    THESIS_HEALTH_REPOSITORY = "THESIS_HEALTH_REPOSITORY"
    HOLDING_ASSESSMENT_REPOSITORY = "HOLDING_ASSESSMENT_REPOSITORY"
    EXIT_ASSESSMENT_REPOSITORY = "EXIT_ASSESSMENT_REPOSITORY"
    OUTCOME_REVIEW_REPOSITORY = "OUTCOME_REVIEW_REPOSITORY"
    FEATURE_ARTIFACT_READER = "FEATURE_ARTIFACT_READER"
    MODEL_COMPARISON_REPORT_READER = "MODEL_COMPARISON_REPORT_READER"


class LifecycleConfigurationKind(str, Enum):
    """Typed restart boundary for executable lifecycle configuration files."""

    RESEARCH_PIPELINE = "RESEARCH_PIPELINE"
    SIGNAL_MODEL = "SIGNAL_MODEL"
    PATH_FORECAST = "PATH_FORECAST"
    COMPLETE_ACCOUNT_RISK = "COMPLETE_ACCOUNT_RISK"
    RISK_REDUCING_GATE = "RISK_REDUCING_GATE"
    RISK_REDUCTION_CONFIRMATION_POLICY = "RISK_REDUCTION_CONFIRMATION_POLICY"
    GENERIC = "GENERIC"


class LifecycleRetryState(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    AVAILABLE = "AVAILABLE"
    IN_PROGRESS = "IN_PROGRESS"


class LifecycleAttemptResult(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"


class LifecycleEventType(str, Enum):
    RUN_CREATED = "RUN_CREATED"
    RUN_CLAIMED = "RUN_CLAIMED"
    RUN_STATUS_CHANGED = "RUN_STATUS_CHANGED"
    STAGE_STATUS_CHANGED = "STAGE_STATUS_CHANGED"
    ATTEMPT_STARTED = "ATTEMPT_STARTED"
    ATTEMPT_FINISHED = "ATTEMPT_FINISHED"
    RECEIPT_RECORDED = "RECEIPT_RECORDED"


_RECEIPT_RESULTS = frozenset(
    {
        LifecycleStageStatus.COMPLETED,
        LifecycleStageStatus.WAITING,
        LifecycleStageStatus.BLOCKED,
        LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
    }
)


def require_utc_second(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    if value.microsecond != 0:
        raise ValueError(f"{label} must have whole-second precision")


def parse_utc_second(label: str, value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be canonical UTC RFC3339 with a Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be a canonical datetime") from exc
    require_utc_second(label, parsed)
    if canonical_datetime(parsed) != value:
        raise ValueError(f"{label} is not canonical")
    return parsed


def _require_positive(label: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


def _require_non_negative(label: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _require_optional_text(label: str, value: str | None) -> None:
    if value is not None:
        require_text(label, value)


def _require_sorted_text(label: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{label} must be a tuple")
    require_unique_text(label, values)
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} must be sorted")


def _expect_fields(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_text_value(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload[key]
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload[key]
    _require_positive(key, value)
    return value


def _non_negative_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload[key]
    _require_non_negative(key, value)
    return value


def _string_tuple(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be an array of strings")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class LifecycleObjectReference:
    object_type: LifecycleObjectType
    object_id: LifecycleObjectId
    content_hash: str
    reader_kind: LifecycleReaderKind
    locator: str | None
    available_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.object_type, LifecycleObjectType):
            raise TypeError("object_type must be a LifecycleObjectType")
        if not isinstance(self.object_id, LifecycleObjectId):
            raise TypeError("object_id must be a LifecycleObjectId")
        require_sha256("content_hash", self.content_hash)
        if not isinstance(self.reader_kind, LifecycleReaderKind):
            raise TypeError("reader_kind must be a LifecycleReaderKind")
        _require_optional_text("locator", self.locator)
        if self.locator is not None:
            if "://" in self.locator or "\x00" in self.locator:
                raise ValueError("locator must be a controlled local locator")
        require_utc_second("available_at", self.available_at)

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return self.object_type.value, str(self.object_id), self.reader_kind.value

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type.value,
            "object_id": str(self.object_id),
            "content_hash": self.content_hash,
            "reader_kind": self.reader_kind.value,
            "locator": self.locator,
            "available_at": canonical_datetime(self.available_at),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> LifecycleObjectReference:
        _expect_fields(
            payload,
            {
                "object_type",
                "object_id",
                "content_hash",
                "reader_kind",
                "locator",
                "available_at",
            },
            "LifecycleObjectReference",
        )
        return cls(
            object_type=LifecycleObjectType(_text(payload, "object_type")),
            object_id=LifecycleObjectId(_text(payload, "object_id")),
            content_hash=_text(payload, "content_hash"),
            reader_kind=LifecycleReaderKind(_text(payload, "reader_kind")),
            locator=_optional_text_value(payload, "locator"),
            available_at=parse_utc_second("available_at", payload["available_at"]),
        )


@dataclass(frozen=True, slots=True)
class LifecycleConfigurationReference:
    configuration_kind: LifecycleConfigurationKind
    configuration_id: ArtifactId
    configuration_version: str
    content_hash: str
    locator: str

    def __post_init__(self) -> None:
        if not isinstance(self.configuration_kind, LifecycleConfigurationKind):
            raise TypeError("configuration_kind must be a LifecycleConfigurationKind")
        if not isinstance(self.configuration_id, ArtifactId):
            raise TypeError("configuration_id must be an ArtifactId")
        require_text("configuration_version", self.configuration_version)
        require_sha256("configuration content_hash", self.content_hash)
        require_text("configuration locator", self.locator)
        if "://" in self.locator or "\x00" in self.locator:
            raise ValueError("configuration locator must be a controlled local locator")

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (
            self.configuration_kind.value,
            str(self.configuration_id),
            self.configuration_version,
        )

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "configuration_kind": self.configuration_kind.value,
            "configuration_id": str(self.configuration_id),
            "configuration_version": self.configuration_version,
            "content_hash": self.content_hash,
            "locator": self.locator,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> LifecycleConfigurationReference:
        _expect_fields(
            payload,
            {
                "configuration_kind",
                "configuration_id",
                "configuration_version",
                "content_hash",
                "locator",
            },
            "LifecycleConfigurationReference",
        )
        return cls(
            configuration_kind=LifecycleConfigurationKind(
                _text(payload, "configuration_kind")
            ),
            configuration_id=ArtifactId(_text(payload, "configuration_id")),
            configuration_version=_text(payload, "configuration_version"),
            content_hash=_text(payload, "content_hash"),
            locator=_text(payload, "locator"),
        )


@dataclass(frozen=True, slots=True)
class LifecycleModelVersionReference:
    model_id: ModelId
    model_version: str
    content_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, ModelId):
            raise TypeError("model_id must be a ModelId")
        require_text("model_version", self.model_version)
        require_sha256("model content_hash", self.content_hash)

    @property
    def sort_key(self) -> tuple[str, str]:
        return str(self.model_id), self.model_version

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "model_id": str(self.model_id),
            "model_version": self.model_version,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> LifecycleModelVersionReference:
        _expect_fields(
            payload,
            {"model_id", "model_version", "content_hash"},
            "LifecycleModelVersionReference",
        )
        return cls(
            model_id=ModelId(_text(payload, "model_id")),
            model_version=_text(payload, "model_version"),
            content_hash=_text(payload, "content_hash"),
        )


def validate_lifecycle_object_references(
    label: str, values: tuple[LifecycleObjectReference, ...]
) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(item, LifecycleObjectReference) for item in values
    ):
        raise TypeError(f"{label} must contain LifecycleObjectReference values")
    if values != tuple(sorted(values, key=lambda item: item.sort_key)):
        raise ValueError(f"{label} must be sorted")
    if len({item.sort_key for item in values}) != len(values):
        raise ValueError(f"{label} must be unique")
    ids: dict[LifecycleObjectId, str] = {}
    hashes: dict[str, LifecycleObjectId] = {}
    for item in values:
        prior_hash = ids.setdefault(item.object_id, item.content_hash)
        if prior_hash != item.content_hash:
            raise ValueError(f"{label} maps one object ID to conflicting hashes")
        prior_id = hashes.setdefault(item.content_hash, item.object_id)
        if prior_id != item.object_id:
            raise ValueError(f"{label} maps one hash to different object IDs")


_ReferenceT = TypeVar(
    "_ReferenceT", LifecycleConfigurationReference, LifecycleModelVersionReference
)


def _validate_version_references(label: str, values: tuple[_ReferenceT, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{label} must be a tuple")
    if values != tuple(sorted(values, key=lambda item: item.sort_key)):
        raise ValueError(f"{label} must be sorted")
    if len({item.sort_key for item in values}) != len(values):
        raise ValueError(f"{label} must be unique")


def configuration_manifest_hash(
    references: tuple[LifecycleConfigurationReference, ...],
) -> str:
    _validate_version_references("configuration references", references)
    return canonical_hash(
        {
            "schema_version": "lifecycle-configuration-manifest-v1",
            "references": [item.to_canonical_dict() for item in references],
        }
    )


def model_version_manifest_hash(
    references: tuple[LifecycleModelVersionReference, ...],
) -> str:
    _validate_version_references("model references", references)
    return canonical_hash(
        {
            "schema_version": "lifecycle-model-version-manifest-v1",
            "references": [item.to_canonical_dict() for item in references],
        }
    )


@dataclass(frozen=True, slots=True)
class LifecycleRun:
    SCHEMA_VERSION = "canonical-lifecycle-run-v1"

    run_id: LifecycleRunId
    idempotency_key: str
    command_hash: str
    run_type: LifecycleRunType
    decision_date: date
    as_of_time: datetime
    status: LifecycleRunStatus
    current_stage: LifecycleStageName | None
    input_manifest_id: ArtifactId | None
    input_content_hash: str | None
    completed_stages: tuple[LifecycleStageName, ...]
    configuration_references: tuple[LifecycleConfigurationReference, ...]
    configuration_manifest_hash: str
    model_references: tuple[LifecycleModelVersionReference, ...]
    model_version_manifest_hash: str
    retry_state: LifecycleRetryState
    failure_reason: str | None
    blocker_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    version: int
    claim_token: int

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, LifecycleRunId):
            raise TypeError("run_id must be a LifecycleRunId")
        require_text("idempotency_key", self.idempotency_key)
        require_sha256("command_hash", self.command_hash)
        if not isinstance(self.run_type, LifecycleRunType):
            raise TypeError("run_type must be a LifecycleRunType")
        if type(self.decision_date) is not date:
            raise TypeError("decision_date must be a date")
        require_utc_second("as_of_time", self.as_of_time)
        if not isinstance(self.status, LifecycleRunStatus):
            raise TypeError("status must be a LifecycleRunStatus")
        if self.current_stage is not None and not isinstance(
            self.current_stage, LifecycleStageName
        ):
            raise TypeError("current_stage must be a LifecycleStageName or None")
        if (self.input_manifest_id is None) != (self.input_content_hash is None):
            raise ValueError("input manifest identity and hash must be paired")
        if self.input_content_hash is not None:
            require_sha256("input_content_hash", self.input_content_hash)
        if not isinstance(self.completed_stages, tuple) or any(
            not isinstance(item, LifecycleStageName) for item in self.completed_stages
        ):
            raise TypeError("completed_stages must contain LifecycleStageName values")
        if len(set(self.completed_stages)) != len(self.completed_stages):
            raise ValueError("completed_stages must be unique")
        order = {stage: index for index, stage in enumerate(LIFECYCLE_STAGE_ORDER)}
        if self.completed_stages != tuple(
            sorted(self.completed_stages, key=order.__getitem__)
        ):
            raise ValueError("completed_stages must follow lifecycle order")
        _validate_version_references(
            "configuration references", self.configuration_references
        )
        require_sha256("configuration_manifest_hash", self.configuration_manifest_hash)
        if self.configuration_manifest_hash != configuration_manifest_hash(
            self.configuration_references
        ):
            raise ValueError("configuration manifest hash mismatch")
        _validate_version_references("model references", self.model_references)
        require_sha256("model_version_manifest_hash", self.model_version_manifest_hash)
        if self.model_version_manifest_hash != model_version_manifest_hash(
            self.model_references
        ):
            raise ValueError("model version manifest hash mismatch")
        if not isinstance(self.retry_state, LifecycleRetryState):
            raise TypeError("retry_state must be a LifecycleRetryState")
        expected_retry_state = {
            LifecycleRunStatus.FAILED: LifecycleRetryState.AVAILABLE,
            LifecycleRunStatus.RETRYING: LifecycleRetryState.IN_PROGRESS,
        }.get(self.status, LifecycleRetryState.NOT_REQUIRED)
        if self.retry_state is not expected_retry_state:
            raise ValueError("retry_state does not match run status")
        _require_optional_text("failure_reason", self.failure_reason)
        _require_optional_text("blocker_reason", self.blocker_reason)
        if (self.status is LifecycleRunStatus.FAILED) != (
            self.failure_reason is not None
        ):
            raise ValueError("failure_reason is required only for FAILED runs")
        if (self.status in WAITING_LIFECYCLE_RUN_STATUSES) != (
            self.blocker_reason is not None
        ):
            raise ValueError("blocker_reason must match a waiting or blocked run")
        require_utc_second("created_at", self.created_at)
        require_utc_second("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if self.completed_at is not None:
            require_utc_second("completed_at", self.completed_at)
            if self.completed_at < self.updated_at:
                raise ValueError("completed_at cannot precede updated_at")
        terminal = self.status in {
            LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
            LifecycleRunStatus.COMPLETED,
        }
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal evidence states must carry completed_at")
        _require_positive("version", self.version)
        _require_non_negative("claim_token", self.claim_token)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "run_id": str(self.run_id),
            "idempotency_key": self.idempotency_key,
            "command_hash": self.command_hash,
            "run_type": self.run_type.value,
            "decision_date": self.decision_date.isoformat(),
            "as_of_time": canonical_datetime(self.as_of_time),
            "status": self.status.value,
            "current_stage": self.current_stage.value if self.current_stage else None,
            "input_manifest_id": (
                str(self.input_manifest_id) if self.input_manifest_id else None
            ),
            "input_content_hash": self.input_content_hash,
            "completed_stages": [item.value for item in self.completed_stages],
            "configuration_references": [
                item.to_canonical_dict() for item in self.configuration_references
            ],
            "configuration_manifest_hash": self.configuration_manifest_hash,
            "model_references": [
                item.to_canonical_dict() for item in self.model_references
            ],
            "model_version_manifest_hash": self.model_version_manifest_hash,
            "retry_state": self.retry_state.value,
            "failure_reason": self.failure_reason,
            "blocker_reason": self.blocker_reason,
            "created_at": canonical_datetime(self.created_at),
            "updated_at": canonical_datetime(self.updated_at),
            "completed_at": (
                canonical_datetime(self.completed_at) if self.completed_at else None
            ),
            "version": self.version,
            "claim_token": self.claim_token,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> LifecycleRun:
        expected = {
            "schema_version", "run_id", "idempotency_key", "command_hash",
            "run_type", "decision_date", "as_of_time", "status", "current_stage",
            "input_manifest_id", "input_content_hash", "completed_stages",
            "configuration_references", "configuration_manifest_hash",
            "model_references", "model_version_manifest_hash", "retry_state",
            "failure_reason", "blocker_reason", "created_at", "updated_at",
            "completed_at", "version", "claim_token",
        }
        _expect_fields(payload, expected, "LifecycleRun")
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported LifecycleRun schema")
        manifest_id = _optional_text_value(payload, "input_manifest_id")
        current_stage = _optional_text_value(payload, "current_stage")
        completed_at = payload["completed_at"]
        return cls(
            run_id=LifecycleRunId(_text(payload, "run_id")),
            idempotency_key=_text(payload, "idempotency_key"),
            command_hash=_text(payload, "command_hash"),
            run_type=LifecycleRunType(_text(payload, "run_type")),
            decision_date=_parse_date(payload["decision_date"], "decision_date"),
            as_of_time=parse_utc_second("as_of_time", payload["as_of_time"]),
            status=LifecycleRunStatus(_text(payload, "status")),
            current_stage=(LifecycleStageName(current_stage) if current_stage else None),
            input_manifest_id=ArtifactId(manifest_id) if manifest_id else None,
            input_content_hash=_optional_text_value(payload, "input_content_hash"),
            completed_stages=tuple(
                LifecycleStageName(item)
                for item in _string_tuple(payload, "completed_stages")
            ),
            configuration_references=tuple(
                LifecycleConfigurationReference.from_canonical_dict(item)
                for item in _mapping_array(payload, "configuration_references")
            ),
            configuration_manifest_hash=_text(payload, "configuration_manifest_hash"),
            model_references=tuple(
                LifecycleModelVersionReference.from_canonical_dict(item)
                for item in _mapping_array(payload, "model_references")
            ),
            model_version_manifest_hash=_text(payload, "model_version_manifest_hash"),
            retry_state=LifecycleRetryState(_text(payload, "retry_state")),
            failure_reason=_optional_text_value(payload, "failure_reason"),
            blocker_reason=_optional_text_value(payload, "blocker_reason"),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            updated_at=parse_utc_second("updated_at", payload["updated_at"]),
            completed_at=(
                parse_utc_second("completed_at", completed_at)
                if completed_at is not None
                else None
            ),
            version=_positive_int(payload, "version"),
            claim_token=_non_negative_int(payload, "claim_token"),
        )


@dataclass(frozen=True, slots=True)
class LifecycleStage:
    SCHEMA_VERSION = "canonical-lifecycle-stage-v1"

    run_id: LifecycleRunId
    stage_name: LifecycleStageName
    stage_status: LifecycleStageStatus
    attempt_count: int
    input_references: tuple[LifecycleObjectReference, ...]
    output_references: tuple[LifecycleObjectReference, ...]
    started_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None
    blocker_reason: str | None
    version: int

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, LifecycleRunId):
            raise TypeError("run_id must be a LifecycleRunId")
        if not isinstance(self.stage_name, LifecycleStageName):
            raise TypeError("stage_name must be a LifecycleStageName")
        if not isinstance(self.stage_status, LifecycleStageStatus):
            raise TypeError("stage_status must be a LifecycleStageStatus")
        _require_non_negative("attempt_count", self.attempt_count)
        validate_lifecycle_object_references("input_references", self.input_references)
        validate_lifecycle_object_references("output_references", self.output_references)
        _require_optional_text("failure_reason", self.failure_reason)
        _require_optional_text("blocker_reason", self.blocker_reason)
        if self.started_at is not None:
            require_utc_second("started_at", self.started_at)
        if self.completed_at is not None:
            require_utc_second("completed_at", self.completed_at)
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        if self.stage_status is LifecycleStageStatus.PENDING:
            if self.attempt_count != 0 or any(
                value is not None
                for value in (
                    self.started_at,
                    self.completed_at,
                    self.failure_reason,
                    self.blocker_reason,
                )
            ):
                raise ValueError("PENDING stage cannot carry attempt outcome state")
        else:
            if self.attempt_count == 0 or self.started_at is None:
                raise ValueError("non-PENDING stage requires an attempt and started_at")
        if self.stage_status is LifecycleStageStatus.RUNNING:
            if self.completed_at is not None or self.failure_reason or self.blocker_reason:
                raise ValueError("RUNNING stage cannot carry outcome state")
        elif self.stage_status is not LifecycleStageStatus.PENDING:
            if self.completed_at is None:
                raise ValueError("settled stage projection requires completed_at")
        if (self.stage_status is LifecycleStageStatus.FAILED) != (
            self.failure_reason is not None
        ):
            raise ValueError("failure_reason is required only for FAILED stages")
        reasoned = self.stage_status in {
            LifecycleStageStatus.WAITING,
            LifecycleStageStatus.BLOCKED,
            LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
        }
        if reasoned != (self.blocker_reason is not None):
            raise ValueError("waiting, blocked, and skipped stages require a reason")
        if self.stage_status in {LifecycleStageStatus.PENDING, LifecycleStageStatus.RUNNING}:
            if self.output_references:
                raise ValueError("unsettled stage cannot publish output references")
        _require_positive("version", self.version)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "run_id": str(self.run_id),
            "stage_name": self.stage_name.value,
            "stage_status": self.stage_status.value,
            "attempt_count": self.attempt_count,
            "input_references": [item.to_canonical_dict() for item in self.input_references],
            "output_references": [item.to_canonical_dict() for item in self.output_references],
            "started_at": canonical_datetime(self.started_at) if self.started_at else None,
            "completed_at": canonical_datetime(self.completed_at) if self.completed_at else None,
            "failure_reason": self.failure_reason,
            "blocker_reason": self.blocker_reason,
            "version": self.version,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> LifecycleStage:
        _expect_fields(
            payload,
            {"schema_version", "run_id", "stage_name", "stage_status", "attempt_count",
             "input_references", "output_references", "started_at", "completed_at",
             "failure_reason", "blocker_reason", "version"},
            "LifecycleStage",
        )
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported LifecycleStage schema")
        started_at = payload["started_at"]
        completed_at = payload["completed_at"]
        return cls(
            run_id=LifecycleRunId(_text(payload, "run_id")),
            stage_name=LifecycleStageName(_text(payload, "stage_name")),
            stage_status=LifecycleStageStatus(_text(payload, "stage_status")),
            attempt_count=_non_negative_int(payload, "attempt_count"),
            input_references=tuple(
                LifecycleObjectReference.from_canonical_dict(item)
                for item in _mapping_array(payload, "input_references")
            ),
            output_references=tuple(
                LifecycleObjectReference.from_canonical_dict(item)
                for item in _mapping_array(payload, "output_references")
            ),
            started_at=parse_utc_second("started_at", started_at) if started_at else None,
            completed_at=(parse_utc_second("completed_at", completed_at) if completed_at else None),
            failure_reason=_optional_text_value(payload, "failure_reason"),
            blocker_reason=_optional_text_value(payload, "blocker_reason"),
            version=_positive_int(payload, "version"),
        )


@dataclass(frozen=True, slots=True)
class LifecycleAttempt:
    SCHEMA_VERSION = "canonical-lifecycle-attempt-v1"

    attempt_id: LifecycleAttemptId
    run_id: LifecycleRunId
    stage_name: LifecycleStageName
    attempt_number: int
    started_at: datetime
    completed_at: datetime | None
    result: LifecycleAttemptResult
    exception_type: str | None
    exception_message: str | None
    claim_token: int

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, LifecycleAttemptId):
            raise TypeError("attempt_id must be a LifecycleAttemptId")
        if not isinstance(self.run_id, LifecycleRunId):
            raise TypeError("run_id must be a LifecycleRunId")
        if not isinstance(self.stage_name, LifecycleStageName):
            raise TypeError("stage_name must be a LifecycleStageName")
        _require_positive("attempt_number", self.attempt_number)
        require_utc_second("started_at", self.started_at)
        if not isinstance(self.result, LifecycleAttemptResult):
            raise TypeError("result must be a LifecycleAttemptResult")
        if self.completed_at is not None:
            require_utc_second("completed_at", self.completed_at)
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot precede started_at")
        _require_optional_text("exception_type", self.exception_type)
        _require_optional_text("exception_message", self.exception_message)
        if (self.exception_type is None) != (self.exception_message is None):
            raise ValueError("exception type and message must be paired")
        if self.result is LifecycleAttemptResult.RUNNING:
            if self.completed_at is not None or self.exception_type is not None:
                raise ValueError("RUNNING attempt cannot carry completion state")
        else:
            if self.completed_at is None:
                raise ValueError("settled attempt requires completed_at")
        if (self.result is LifecycleAttemptResult.FAILED) != (
            self.exception_type is not None
        ):
            raise ValueError("only FAILED attempts carry an exception")
        _require_positive("claim_token", self.claim_token)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "attempt_id": str(self.attempt_id),
            "run_id": str(self.run_id),
            "stage_name": self.stage_name.value,
            "attempt_number": self.attempt_number,
            "started_at": canonical_datetime(self.started_at),
            "completed_at": canonical_datetime(self.completed_at) if self.completed_at else None,
            "result": self.result.value,
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "claim_token": self.claim_token,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> LifecycleAttempt:
        _expect_fields(
            payload,
            {"schema_version", "attempt_id", "run_id", "stage_name", "attempt_number",
             "started_at", "completed_at", "result", "exception_type",
             "exception_message", "claim_token"},
            "LifecycleAttempt",
        )
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported LifecycleAttempt schema")
        completed_at = payload["completed_at"]
        return cls(
            attempt_id=LifecycleAttemptId(_text(payload, "attempt_id")),
            run_id=LifecycleRunId(_text(payload, "run_id")),
            stage_name=LifecycleStageName(_text(payload, "stage_name")),
            attempt_number=_positive_int(payload, "attempt_number"),
            started_at=parse_utc_second("started_at", payload["started_at"]),
            completed_at=(parse_utc_second("completed_at", completed_at) if completed_at else None),
            result=LifecycleAttemptResult(_text(payload, "result")),
            exception_type=_optional_text_value(payload, "exception_type"),
            exception_message=_optional_text_value(payload, "exception_message"),
            claim_token=_positive_int(payload, "claim_token"),
        )


@dataclass(frozen=True, slots=True)
class StageReceipt:
    SCHEMA_VERSION = "canonical-lifecycle-stage-receipt-v1"

    receipt_id: ArtifactId
    run_id: LifecycleRunId
    stage_name: LifecycleStageName
    attempt_number: int
    input_hashes: tuple[str, ...]
    output_hashes: tuple[str, ...]
    model_versions: tuple[str, ...]
    configuration_hashes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    stage_result: LifecycleStageStatus
    created_at: datetime
    receipt_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_id, ArtifactId):
            raise TypeError("receipt_id must be an ArtifactId")
        if not isinstance(self.run_id, LifecycleRunId):
            raise TypeError("run_id must be a LifecycleRunId")
        if not isinstance(self.stage_name, LifecycleStageName):
            raise TypeError("stage_name must be a LifecycleStageName")
        _require_positive("attempt_number", self.attempt_number)
        for label, values in (
            ("input_hashes", self.input_hashes),
            ("output_hashes", self.output_hashes),
            ("configuration_hashes", self.configuration_hashes),
        ):
            _require_sorted_text(label, values)
            for value in values:
                require_sha256(label, value)
        _require_sorted_text("model_versions", self.model_versions)
        _require_sorted_text("reason_codes", self.reason_codes)
        if not isinstance(self.stage_result, LifecycleStageStatus):
            raise TypeError("stage_result must be a LifecycleStageStatus")
        if self.stage_result not in _RECEIPT_RESULTS:
            raise ValueError("stage_result is not receipt-bearing")
        require_utc_second("created_at", self.created_at)
        require_sha256("receipt_hash", self.receipt_hash)
        expected_hash = canonical_hash(self.semantic_payload())
        expected_id = ArtifactId(
            f"lifecycle-receipt-{expected_hash.split(':', 1)[1][:24]}"
        )
        if self.receipt_hash != expected_hash or self.receipt_id != expected_id:
            raise ValueError("StageReceipt semantic identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        run_id: LifecycleRunId,
        stage_name: LifecycleStageName,
        attempt_number: int,
        input_hashes: tuple[str, ...],
        output_hashes: tuple[str, ...],
        model_versions: tuple[str, ...],
        configuration_hashes: tuple[str, ...],
        reason_codes: tuple[str, ...],
        stage_result: LifecycleStageStatus,
        created_at: datetime,
    ) -> StageReceipt:
        semantic = cls.semantic_payload_for(
            run_id=run_id,
            stage_name=stage_name,
            input_hashes=input_hashes,
            output_hashes=output_hashes,
            model_versions=model_versions,
            configuration_hashes=configuration_hashes,
            reason_codes=reason_codes,
            stage_result=stage_result,
        )
        digest = canonical_hash(semantic)
        return cls(
            receipt_id=ArtifactId(
                f"lifecycle-receipt-{digest.split(':', 1)[1][:24]}"
            ),
            run_id=run_id,
            stage_name=stage_name,
            attempt_number=attempt_number,
            input_hashes=input_hashes,
            output_hashes=output_hashes,
            model_versions=model_versions,
            configuration_hashes=configuration_hashes,
            reason_codes=reason_codes,
            stage_result=stage_result,
            created_at=created_at,
            receipt_hash=digest,
        )

    @staticmethod
    def semantic_payload_for(**values: Any) -> dict[str, Any]:
        return {
            "schema_version": StageReceipt.SCHEMA_VERSION,
            "run_id": str(values["run_id"]),
            "stage_name": values["stage_name"].value,
            "input_hashes": list(values["input_hashes"]),
            "output_hashes": list(values["output_hashes"]),
            "model_versions": list(values["model_versions"]),
            "configuration_hashes": list(values["configuration_hashes"]),
            "reason_codes": list(values["reason_codes"]),
            "stage_result": values["stage_result"].value,
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            run_id=self.run_id,
            stage_name=self.stage_name,
            input_hashes=self.input_hashes,
            output_hashes=self.output_hashes,
            model_versions=self.model_versions,
            configuration_hashes=self.configuration_hashes,
            reason_codes=self.reason_codes,
            stage_result=self.stage_result,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "attempt_number": self.attempt_number,
            "created_at": canonical_datetime(self.created_at),
            "receipt_hash": self.receipt_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StageReceipt:
        _expect_fields(
            payload,
            {"schema_version", "receipt_id", "run_id", "stage_name", "attempt_number",
             "input_hashes", "output_hashes", "model_versions", "configuration_hashes",
             "reason_codes", "stage_result", "created_at", "receipt_hash"},
            "StageReceipt",
        )
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported StageReceipt schema")
        return cls(
            receipt_id=ArtifactId(_text(payload, "receipt_id")),
            run_id=LifecycleRunId(_text(payload, "run_id")),
            stage_name=LifecycleStageName(_text(payload, "stage_name")),
            attempt_number=_positive_int(payload, "attempt_number"),
            input_hashes=_string_tuple(payload, "input_hashes"),
            output_hashes=_string_tuple(payload, "output_hashes"),
            model_versions=_string_tuple(payload, "model_versions"),
            configuration_hashes=_string_tuple(payload, "configuration_hashes"),
            reason_codes=_string_tuple(payload, "reason_codes"),
            stage_result=LifecycleStageStatus(_text(payload, "stage_result")),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            receipt_hash=_text(payload, "receipt_hash"),
        )


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    SCHEMA_VERSION = "canonical-lifecycle-event-v1"

    event_id: LifecycleEventId
    run_id: LifecycleRunId
    sequence_number: int
    event_type: LifecycleEventType
    from_status: LifecycleRunStatus | None
    to_status: LifecycleRunStatus | None
    stage_name: LifecycleStageName | None
    attempt_id: LifecycleAttemptId | None
    receipt_id: ArtifactId | None
    reason_codes: tuple[str, ...]
    payload_hash: str
    created_at: datetime
    claim_token: int

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, LifecycleEventId):
            raise TypeError("event_id must be a LifecycleEventId")
        if not isinstance(self.run_id, LifecycleRunId):
            raise TypeError("run_id must be a LifecycleRunId")
        _require_positive("sequence_number", self.sequence_number)
        if not isinstance(self.event_type, LifecycleEventType):
            raise TypeError("event_type must be a LifecycleEventType")
        if self.from_status is not None and not isinstance(
            self.from_status, LifecycleRunStatus
        ):
            raise TypeError("from_status must be a LifecycleRunStatus or None")
        if self.to_status is not None and not isinstance(
            self.to_status, LifecycleRunStatus
        ):
            raise TypeError("to_status must be a LifecycleRunStatus or None")
        if self.stage_name is not None and not isinstance(
            self.stage_name, LifecycleStageName
        ):
            raise TypeError("stage_name must be a LifecycleStageName or None")
        if self.attempt_id is not None and not isinstance(
            self.attempt_id, LifecycleAttemptId
        ):
            raise TypeError("attempt_id must be a LifecycleAttemptId or None")
        if self.receipt_id is not None and not isinstance(self.receipt_id, ArtifactId):
            raise TypeError("receipt_id must be an ArtifactId or None")
        _require_sorted_text("reason_codes", self.reason_codes)
        require_sha256("payload_hash", self.payload_hash)
        require_utc_second("created_at", self.created_at)
        _require_non_negative("claim_token", self.claim_token)
        if self.event_type is LifecycleEventType.RUN_CREATED:
            if self.from_status is not None or self.to_status is not LifecycleRunStatus.CREATED:
                raise ValueError("RUN_CREATED must transition from null to CREATED")
        elif self.event_type is LifecycleEventType.RUN_STATUS_CHANGED:
            if self.from_status is None or self.to_status is None:
                raise ValueError("RUN_STATUS_CHANGED requires both run statuses")
        elif self.event_type in {
            LifecycleEventType.STAGE_STATUS_CHANGED,
            LifecycleEventType.ATTEMPT_STARTED,
            LifecycleEventType.ATTEMPT_FINISHED,
            LifecycleEventType.RECEIPT_RECORDED,
        } and self.stage_name is None:
            raise ValueError("stage journal event requires stage_name")
        if self.event_type in {
            LifecycleEventType.ATTEMPT_STARTED,
            LifecycleEventType.ATTEMPT_FINISHED,
        } and self.attempt_id is None:
            raise ValueError("attempt event requires attempt_id")
        if self.event_type is LifecycleEventType.RECEIPT_RECORDED and self.receipt_id is None:
            raise ValueError("receipt event requires receipt_id")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "event_id": str(self.event_id),
            "run_id": str(self.run_id),
            "sequence_number": self.sequence_number,
            "event_type": self.event_type.value,
            "from_status": self.from_status.value if self.from_status else None,
            "to_status": self.to_status.value if self.to_status else None,
            "stage_name": self.stage_name.value if self.stage_name else None,
            "attempt_id": str(self.attempt_id) if self.attempt_id else None,
            "receipt_id": str(self.receipt_id) if self.receipt_id else None,
            "reason_codes": list(self.reason_codes),
            "payload_hash": self.payload_hash,
            "created_at": canonical_datetime(self.created_at),
            "claim_token": self.claim_token,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> LifecycleEvent:
        _expect_fields(
            payload,
            {"schema_version", "event_id", "run_id", "sequence_number", "event_type",
             "from_status", "to_status", "stage_name", "attempt_id", "receipt_id",
             "reason_codes", "payload_hash", "created_at", "claim_token"},
            "LifecycleEvent",
        )
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported LifecycleEvent schema")
        from_status = _optional_text_value(payload, "from_status")
        to_status = _optional_text_value(payload, "to_status")
        stage_name = _optional_text_value(payload, "stage_name")
        attempt_id = _optional_text_value(payload, "attempt_id")
        receipt_id = _optional_text_value(payload, "receipt_id")
        return cls(
            event_id=LifecycleEventId(_text(payload, "event_id")),
            run_id=LifecycleRunId(_text(payload, "run_id")),
            sequence_number=_positive_int(payload, "sequence_number"),
            event_type=LifecycleEventType(_text(payload, "event_type")),
            from_status=LifecycleRunStatus(from_status) if from_status else None,
            to_status=LifecycleRunStatus(to_status) if to_status else None,
            stage_name=LifecycleStageName(stage_name) if stage_name else None,
            attempt_id=LifecycleAttemptId(attempt_id) if attempt_id else None,
            receipt_id=ArtifactId(receipt_id) if receipt_id else None,
            reason_codes=_string_tuple(payload, "reason_codes"),
            payload_hash=_text(payload, "payload_hash"),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            claim_token=_non_negative_int(payload, "claim_token"),
        )


def _parse_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{label} is not canonical")
    return parsed


def _mapping_array(
    payload: Mapping[str, Any], key: str
) -> tuple[Mapping[str, Any], ...]:
    value = payload[key]
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{key} must be an array of objects")
    return tuple(value)
