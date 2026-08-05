"""Contracts for the parent Controlled Decision-Time Operation journal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Protocol, cast

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second


CONTROLLED_OPERATION_COMMAND_SCHEMA = "controlled-decision-time-operation-command-v1"
CONTROLLED_OPERATION_RECEIPT_SCHEMA = "decision-time-operation-receipt-v1"


class DecisionTimeOperationRunStatus(str, Enum):
    CREATED = "CREATED"
    WAITING_FOR_STATIC_INPUTS = "WAITING_FOR_STATIC_INPUTS"
    STATIC_READY = "STATIC_READY"
    WAITING_FOR_DECISION_WINDOW = "WAITING_FOR_DECISION_WINDOW"
    DECISION_WINDOW_RUNNING = "DECISION_WINDOW_RUNNING"
    DATA_BLOCKED = "DATA_BLOCKED"
    DEADLINE_MISSED = "DEADLINE_MISSED"
    OUTCOME_PENDING = "OUTCOME_PENDING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"


class DecisionTimeOperationStageName(str, Enum):
    CALENDAR_UNIVERSE_FREEZE = "CALENDAR_UNIVERSE_FREEZE"
    DAILY_SOURCE_FREEZE = "DAILY_SOURCE_FREEZE"
    DAILY_DATASET = "DAILY_DATASET"
    STATIC_FEATURES = "STATIC_FEATURES"
    OPERATIONAL_RESEARCH = "OPERATIONAL_RESEARCH"
    CANDIDATE_SET = "CANDIDATE_SET"
    CANDIDATE_MINUTE_ACQUISITION = "CANDIDATE_MINUTE_ACQUISITION"
    INTRADAY_DATASET = "INTRADAY_DATASET"
    INTRADAY_FEATURE_OVERLAY = "INTRADAY_FEATURE_OVERLAY"
    SIGNAL = "SIGNAL"
    PATH_FORECAST = "PATH_FORECAST"
    ENTRY_ASSESSMENT = "ENTRY_ASSESSMENT"
    OPERATION_PACKAGE = "OPERATION_PACKAGE"
    OUTCOME_SETTLEMENT = "OUTCOME_SETTLEMENT"


CONTROLLED_OPERATION_STAGE_ORDER = tuple(DecisionTimeOperationStageName)


class DecisionTimeOperationStageStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class DecisionTimeOperationJournal(Protocol):
    """Persistence boundary consumed by the Controlled operation runner."""

    def create_or_get(
        self, command: ControlledOperationCommand
    ) -> DecisionTimeOperationRunSnapshot: ...

    def resume(self, run_id: ArtifactId) -> DecisionTimeOperationRunSnapshot: ...

    def claim_stage(
        self,
        *,
        run_id: ArtifactId,
        stage_name: DecisionTimeOperationStageName,
    ) -> ClaimedDecisionTimeOperationStage: ...

    def complete_stage(
        self,
        *,
        claim: ClaimedDecisionTimeOperationStage,
        receipt: DecisionTimeOperationReceipt,
        run_status: DecisionTimeOperationRunStatus,
    ) -> DecisionTimeOperationRunSnapshot: ...

    def fail_stage(
        self,
        *,
        claim: ClaimedDecisionTimeOperationStage,
        error: str,
        run_status: DecisionTimeOperationRunStatus = (
            DecisionTimeOperationRunStatus.FAILED
        ),
    ) -> DecisionTimeOperationRunSnapshot: ...

    def set_run_status(
        self,
        *,
        run_id: ArtifactId,
        expected_version: int,
        status: DecisionTimeOperationRunStatus,
        reason: str,
    ) -> DecisionTimeOperationRunSnapshot: ...

    def get(self, run_id: ArtifactId) -> DecisionTimeOperationRunSnapshot: ...


class DecisionTimeOperationAttemptStatus(str, Enum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    LEASE_EXPIRED = "LEASE_EXPIRED"


class ChildRunReferenceKind(str, Enum):
    DAILY_ACQUISITION_RUN = "DAILY_ACQUISITION_RUN"
    STATIC_FEATURE_RUN = "STATIC_FEATURE_RUN"
    MINUTE_ACQUISITION_BATCH = "MINUTE_ACQUISITION_BATCH"
    INTRADAY_FEATURE_RUN = "INTRADAY_FEATURE_RUN"
    CANONICAL_LIFECYCLE_RUN = "CANONICAL_LIFECYCLE_RUN"
    OUTCOME_RUN = "OUTCOME_RUN"


@dataclass(frozen=True, slots=True)
class ControlledOperationCommand:
    schema_version: str
    run_id: ArtifactId
    command_hash: str
    idempotency_key: str
    decision_date: date
    decision_time: datetime
    policy_id: ArtifactId
    policy_hash: str
    trading_calendar_id: ArtifactId
    trading_calendar_hash: str
    configuration_manifest_id: ArtifactId
    configuration_manifest_hash: str
    model_manifest_id: ArtifactId
    model_manifest_hash: str
    code_revision: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTROLLED_OPERATION_COMMAND_SCHEMA:
            raise ValueError("unsupported Controlled operation command schema")
        require_text("idempotency_key", self.idempotency_key)
        require_text("code_revision", self.code_revision)
        require_utc_second("decision_time", self.decision_time)
        for label, value in (
            ("command_hash", self.command_hash),
            ("policy_hash", self.policy_hash),
            ("trading_calendar_hash", self.trading_calendar_hash),
            ("configuration_manifest_hash", self.configuration_manifest_hash),
            ("model_manifest_hash", self.model_manifest_hash),
        ):
            require_sha256(label, value)
        if not self.limitations or self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Controlled operation limitations must be non-empty and sorted")
        for required in (
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ):
            if required not in self.limitations:
                raise ValueError("Controlled operation command authority ceiling is incomplete")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        idempotency_key: str,
        decision_date: date,
        decision_time: datetime,
        policy_id: ArtifactId,
        policy_hash: str,
        trading_calendar_id: ArtifactId,
        trading_calendar_hash: str,
        configuration_manifest_id: ArtifactId,
        configuration_manifest_hash: str,
        model_manifest_id: ArtifactId,
        model_manifest_hash: str,
        code_revision: str,
        limitations: tuple[str, ...],
    ) -> ControlledOperationCommand:
        limitations = tuple(sorted(set(limitations)))
        values = {
            "idempotency_key": idempotency_key,
            "decision_date": decision_date,
            "decision_time": decision_time,
            "policy_id": policy_id,
            "policy_hash": policy_hash,
            "trading_calendar_id": trading_calendar_id,
            "trading_calendar_hash": trading_calendar_hash,
            "configuration_manifest_id": configuration_manifest_id,
            "configuration_manifest_hash": configuration_manifest_hash,
            "model_manifest_id": model_manifest_id,
            "model_manifest_hash": model_manifest_hash,
            "code_revision": code_revision,
            "limitations": limitations,
        }
        digest = canonical_hash(_command_payload(**values))
        return cls(
            schema_version=CONTROLLED_OPERATION_COMMAND_SCHEMA,
            run_id=ArtifactId(f"controlled-operation-{digest.split(':', 1)[1][:24]}"),
            command_hash=digest,
            **cast(Any, values),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _command_payload(**_command_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.command_hash:
            raise ValueError("Controlled operation command hash mismatch")
        expected = f"controlled-operation-{digest.split(':', 1)[1][:24]}"
        if str(self.run_id) != expected:
            raise ValueError("Controlled operation command identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "command_hash": self.command_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ControlledOperationCommand:
        if set(payload) != {"run_id", "command_hash", *_command_payload_keys()}:
            raise ValueError("Controlled operation command fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            run_id=ArtifactId(str(payload["run_id"])),
            command_hash=str(payload["command_hash"]),
            idempotency_key=str(payload["idempotency_key"]),
            decision_date=date.fromisoformat(str(payload["decision_date"])),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            trading_calendar_id=ArtifactId(str(payload["trading_calendar_id"])),
            trading_calendar_hash=str(payload["trading_calendar_hash"]),
            configuration_manifest_id=ArtifactId(str(payload["configuration_manifest_id"])),
            configuration_manifest_hash=str(payload["configuration_manifest_hash"]),
            model_manifest_id=ArtifactId(str(payload["model_manifest_id"])),
            model_manifest_hash=str(payload["model_manifest_hash"]),
            code_revision=str(payload["code_revision"]),
            limitations=_strings(payload["limitations"], "limitations"),
        )


@dataclass(frozen=True, slots=True)
class OperationArtifactReference:
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
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> OperationArtifactReference:
        if set(payload) != {"reference_type", "object_id", "content_hash"}:
            raise ValueError("Operation Artifact reference fields mismatch")
        return cls(
            reference_type=str(payload["reference_type"]),
            object_id=ArtifactId(str(payload["object_id"])),
            content_hash=str(payload["content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class OperationChildRunReference:
    reference_kind: ChildRunReferenceKind
    child_run_id: str
    child_receipt_hash: str

    def __post_init__(self) -> None:
        require_text("child_run_id", self.child_run_id)
        require_sha256("child_receipt_hash", self.child_receipt_hash)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "reference_kind": self.reference_kind.value,
            "child_run_id": self.child_run_id,
            "child_receipt_hash": self.child_receipt_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> OperationChildRunReference:
        if set(payload) != {"reference_kind", "child_run_id", "child_receipt_hash"}:
            raise ValueError("Operation child run reference fields mismatch")
        return cls(
            reference_kind=ChildRunReferenceKind(str(payload["reference_kind"])),
            child_run_id=str(payload["child_run_id"]),
            child_receipt_hash=str(payload["child_receipt_hash"]),
        )


@dataclass(frozen=True, slots=True)
class DecisionTimeOperationReceipt:
    schema_version: str
    receipt_id: ArtifactId
    content_hash: str
    run_id: ArtifactId
    stage_name: DecisionTimeOperationStageName
    attempt_number: int
    input_references: tuple[OperationArtifactReference, ...]
    output_references: tuple[OperationArtifactReference, ...]
    child_run_references: tuple[OperationChildRunReference, ...]
    reason_codes: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version != CONTROLLED_OPERATION_RECEIPT_SCHEMA:
            raise ValueError("unsupported Controlled operation Receipt schema")
        require_sha256("content_hash", self.content_hash)
        require_utc_second("created_at", self.created_at)
        if self.attempt_number <= 0:
            raise ValueError("Receipt attempt_number must be positive")
        for label, refs in (
            ("input", self.input_references),
            ("output", self.output_references),
        ):
            keys = tuple((item.reference_type, str(item.object_id)) for item in refs)
            if keys != tuple(sorted(set(keys))):
                raise ValueError(f"Receipt {label} references must be unique and sorted")
        child_keys = tuple(
            (item.reference_kind.value, item.child_run_id)
            for item in self.child_run_references
        )
        if child_keys != tuple(sorted(set(child_keys))):
            raise ValueError("Receipt child run references must be unique and sorted")
        if not self.reason_codes or self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Receipt reason codes must be non-empty and sorted")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        run_id: ArtifactId,
        stage_name: DecisionTimeOperationStageName,
        attempt_number: int,
        input_references: tuple[OperationArtifactReference, ...],
        output_references: tuple[OperationArtifactReference, ...],
        child_run_references: tuple[OperationChildRunReference, ...],
        reason_codes: tuple[str, ...],
        created_at: datetime,
    ) -> DecisionTimeOperationReceipt:
        inputs = tuple(sorted(input_references, key=lambda item: (item.reference_type, str(item.object_id))))
        outputs = tuple(sorted(output_references, key=lambda item: (item.reference_type, str(item.object_id))))
        children = tuple(sorted(child_run_references, key=lambda item: (item.reference_kind.value, item.child_run_id)))
        reasons = tuple(sorted(set(reason_codes)))
        values = {
            "run_id": run_id,
            "stage_name": stage_name,
            "attempt_number": attempt_number,
            "input_references": inputs,
            "output_references": outputs,
            "child_run_references": children,
            "reason_codes": reasons,
            "created_at": created_at,
        }
        digest = canonical_hash(_receipt_payload(**values))
        return cls(
            schema_version=CONTROLLED_OPERATION_RECEIPT_SCHEMA,
            receipt_id=ArtifactId(f"operation-receipt-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            **cast(Any, values),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _receipt_payload(**_receipt_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Controlled operation Receipt hash mismatch")
        expected = f"operation-receipt-{digest.split(':', 1)[1][:24]}"
        if str(self.receipt_id) != expected:
            raise ValueError("Controlled operation Receipt identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DecisionTimeOperationReceipt:
        if set(payload) != {"receipt_id", "content_hash", *_receipt_payload_keys()}:
            raise ValueError("Controlled operation Receipt fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            receipt_id=ArtifactId(str(payload["receipt_id"])),
            content_hash=str(payload["content_hash"]),
            run_id=ArtifactId(str(payload["run_id"])),
            stage_name=DecisionTimeOperationStageName(str(payload["stage_name"])),
            attempt_number=int(payload["attempt_number"]),
            input_references=tuple(
                OperationArtifactReference.from_canonical_dict(item)
                for item in _objects(payload["input_references"], "input references")
            ),
            output_references=tuple(
                OperationArtifactReference.from_canonical_dict(item)
                for item in _objects(payload["output_references"], "output references")
            ),
            child_run_references=tuple(
                OperationChildRunReference.from_canonical_dict(item)
                for item in _objects(payload["child_run_references"], "child references")
            ),
            reason_codes=_strings(payload["reason_codes"], "reason codes"),
            created_at=parse_utc_second("created_at", payload["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class ClaimedDecisionTimeOperationStage:
    run_id: ArtifactId
    stage_name: DecisionTimeOperationStageName
    claim_id: str
    claim_epoch: int
    stage_version: int
    attempt_number: int
    lease_acquired_at: datetime
    lease_expires_at: datetime
    heartbeat_at: datetime


@dataclass(frozen=True, slots=True)
class DecisionTimeOperationStageSnapshot:
    stage_name: DecisionTimeOperationStageName
    status: DecisionTimeOperationStageStatus
    version: int
    claim_epoch: int
    receipt: DecisionTimeOperationReceipt | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class DecisionTimeOperationRunSnapshot:
    command: ControlledOperationCommand
    status: DecisionTimeOperationRunStatus
    current_stage: DecisionTimeOperationStageName | None
    version: int
    stages: tuple[DecisionTimeOperationStageSnapshot, ...]
    child_run_references: tuple[OperationChildRunReference, ...]
    events: tuple[tuple[int, str, str | None, str], ...]


def _command_values(item: ControlledOperationCommand) -> dict[str, Any]:
    return {name: getattr(item, name) for name in _command_value_names()}


def _command_value_names() -> tuple[str, ...]:
    return (
        "idempotency_key", "decision_date", "decision_time", "policy_id",
        "policy_hash", "trading_calendar_id", "trading_calendar_hash",
        "configuration_manifest_id", "configuration_manifest_hash",
        "model_manifest_id", "model_manifest_hash", "code_revision", "limitations",
    )


def _command_payload_keys() -> set[str]:
    return {"schema_version", *_command_value_names()}


def _command_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTROLLED_OPERATION_COMMAND_SCHEMA,
        "idempotency_key": values["idempotency_key"],
        "decision_date": values["decision_date"].isoformat(),
        "decision_time": canonical_datetime(values["decision_time"]),
        "policy_id": str(values["policy_id"]),
        "policy_hash": values["policy_hash"],
        "trading_calendar_id": str(values["trading_calendar_id"]),
        "trading_calendar_hash": values["trading_calendar_hash"],
        "configuration_manifest_id": str(values["configuration_manifest_id"]),
        "configuration_manifest_hash": values["configuration_manifest_hash"],
        "model_manifest_id": str(values["model_manifest_id"]),
        "model_manifest_hash": values["model_manifest_hash"],
        "code_revision": values["code_revision"],
        "limitations": list(values["limitations"]),
    }


def _receipt_values(item: DecisionTimeOperationReceipt) -> dict[str, Any]:
    return {name: getattr(item, name) for name in _receipt_value_names()}


def _receipt_value_names() -> tuple[str, ...]:
    return (
        "run_id", "stage_name", "attempt_number", "input_references",
        "output_references", "child_run_references", "reason_codes", "created_at",
    )


def _receipt_payload_keys() -> set[str]:
    return {"schema_version", *_receipt_value_names()}


def _receipt_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTROLLED_OPERATION_RECEIPT_SCHEMA,
        "run_id": str(values["run_id"]),
        "stage_name": values["stage_name"].value,
        "attempt_number": values["attempt_number"],
        "input_references": [item.to_canonical_dict() for item in values["input_references"]],
        "output_references": [item.to_canonical_dict() for item in values["output_references"]],
        "child_run_references": [item.to_canonical_dict() for item in values["child_run_references"]],
        "reason_codes": list(values["reason_codes"]),
        "created_at": canonical_datetime(values["created_at"]),
    }


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _objects(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an object array")
    return tuple(value)


__all__ = [
    "CONTROLLED_OPERATION_STAGE_ORDER",
    "ChildRunReferenceKind",
    "ClaimedDecisionTimeOperationStage",
    "ControlledOperationCommand",
    "DecisionTimeOperationAttemptStatus",
    "DecisionTimeOperationReceipt",
    "DecisionTimeOperationRunSnapshot",
    "DecisionTimeOperationRunStatus",
    "DecisionTimeOperationStageName",
    "DecisionTimeOperationStageSnapshot",
    "DecisionTimeOperationStageStatus",
    "OperationArtifactReference",
    "OperationChildRunReference",
]
