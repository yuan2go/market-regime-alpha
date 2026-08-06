"""Strict canonical JSON codecs and relational projection verification."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
import json
from typing import Any, TypeVar

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleAttemptId,
    LifecycleEvent,
    LifecycleRun,
    LifecycleRunId,
    LifecycleStage,
    LifecycleStageName,
    StageReceipt,
    require_utc_second,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleIdempotencyConflict,
    LifecycleJournalIntegrityError,
)
from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json


_RecordT = TypeVar(
    "_RecordT",
    CanonicalLifecycleCommand,
    LifecycleRun,
    LifecycleStage,
    LifecycleAttempt,
    StageReceipt,
    LifecycleEvent,
)


def attempt_id(
    run_id: LifecycleRunId,
    stage: LifecycleStageName,
    attempt_number: int,
) -> LifecycleAttemptId:
    digest = canonical_hash(
        {
            "schema_version": "canonical-lifecycle-attempt-identity-v1",
            "run_id": str(run_id),
            "stage_name": stage.value,
            "attempt_number": attempt_number,
        }
    )
    return LifecycleAttemptId(
        f"lifecycle-attempt-{digest.split(':', 1)[1][:24]}"
    )


def verify_command_replay(
    requested: CanonicalLifecycleCommand,
    stored: CanonicalLifecycleCommand,
    run: LifecycleRun,
) -> None:
    if requested.idempotency_key != stored.idempotency_key:
        raise LifecycleJournalIntegrityError("stored command idempotency key mismatch")
    if requested.command_hash != stored.command_hash:
        raise LifecycleIdempotencyConflict(
            "idempotency key is bound to a different command hash"
        )
    if requested.semantic_payload() != stored.semantic_payload():
        raise LifecycleIdempotencyConflict(
            "idempotency key is bound to different command semantics"
        )
    verify_stored_command(stored, run)


def verify_stored_command(
    stored: CanonicalLifecycleCommand,
    run: LifecycleRun,
) -> None:
    if (
        run.run_id != stored.run_id
        or run.command_hash != stored.command_hash
        or run.idempotency_key != stored.idempotency_key
        or run.run_type is not stored.run_type
        or run.decision_date != stored.decision_date
        or run.as_of_time != stored.as_of_time
        or run.input_manifest_id != stored.input_manifest_id
        or run.input_content_hash != stored.input_content_hash
        or run.configuration_manifest_hash != stored.configuration_manifest_hash
        or run.model_version_manifest_hash != stored.model_version_manifest_hash
        or run.source_run_id != stored.source_run_id
        or run.source_command_hash != stored.source_command_hash
        or run.source_history_hash != stored.source_history_hash
        or run.replay_report_hash != stored.replay_report_hash
    ):
        raise LifecycleJournalIntegrityError(
            "stored run projection does not bind its canonical command"
        )


def run_from_row(row: dict[str, Any]) -> LifecycleRun:
    run = _decode_record(str(row["run_json"]), LifecycleRun.from_canonical_dict)
    _verify_projection(
        row,
        {
            "run_id": str(run.run_id),
            "idempotency_key": run.idempotency_key,
            "command_hash": run.command_hash,
            "run_type": run.run_type.value,
            "decision_date": run.decision_date.isoformat(),
            "as_of_time": timestamp(run.as_of_time),
            "status": run.status.value,
            "current_stage": run.current_stage.value if run.current_stage else None,
            "input_manifest_id": (
                str(run.input_manifest_id) if run.input_manifest_id else None
            ),
            "input_content_hash": run.input_content_hash,
            "version": run.version,
            "claim_token": run.claim_token,
            "created_at": timestamp(run.created_at),
            "updated_at": timestamp(run.updated_at),
            "completed_at": timestamp(run.completed_at),
        },
        "lifecycle run",
    )
    verify_stored_command(command_from_row(row), run)
    return run


def command_from_row(row: dict[str, Any]) -> CanonicalLifecycleCommand:
    return _decode_record(
        str(row["command_json"]), CanonicalLifecycleCommand.from_canonical_dict
    )


def stage_from_row(row: dict[str, Any]) -> LifecycleStage:
    stage = _decode_record(
        str(row["stage_json"]), LifecycleStage.from_canonical_dict
    )
    _verify_projection(
        row,
        {
            "run_id": str(stage.run_id),
            "stage_name": stage.stage_name.value,
            "stage_status": stage.stage_status.value,
            "attempt_count": stage.attempt_count,
            "version": stage.version,
        },
        "lifecycle stage",
    )
    return stage


def attempt_from_row(row: dict[str, Any]) -> LifecycleAttempt:
    attempt = _decode_record(
        str(row["attempt_json"]), LifecycleAttempt.from_canonical_dict
    )
    _verify_projection(
        row,
        {
            "attempt_id": str(attempt.attempt_id),
            "run_id": str(attempt.run_id),
            "stage_name": attempt.stage_name.value,
            "attempt_number": attempt.attempt_number,
            "result": attempt.result.value,
            "claim_token": attempt.claim_token,
            "started_at": timestamp(attempt.started_at),
            "completed_at": timestamp(attempt.completed_at),
            "exception_type": attempt.exception_type,
            "exception_message": attempt.exception_message,
        },
        "lifecycle attempt",
    )
    return attempt


def receipt_from_row(row: dict[str, Any]) -> StageReceipt:
    receipt = _decode_record(
        str(row["receipt_json"]), StageReceipt.from_canonical_dict
    )
    _verify_projection(
        row,
        {
            "receipt_id": str(receipt.receipt_id),
            "run_id": str(receipt.run_id),
            "stage_name": receipt.stage_name.value,
            "attempt_number": receipt.attempt_number,
            "receipt_hash": receipt.receipt_hash,
            "stage_result": receipt.stage_result.value,
            "created_at": timestamp(receipt.created_at),
        },
        "lifecycle stage receipt",
    )
    return receipt


def event_from_row(row: dict[str, Any]) -> LifecycleEvent:
    event = _decode_record(
        str(row["event_json"]), LifecycleEvent.from_canonical_dict
    )
    _verify_projection(
        row,
        {
            "event_id": str(event.event_id),
            "run_id": str(event.run_id),
            "sequence_number": event.sequence_number,
            "event_type": event.event_type.value,
            "stage_name": event.stage_name.value if event.stage_name else None,
            "attempt_id": str(event.attempt_id) if event.attempt_id else None,
            "receipt_id": str(event.receipt_id) if event.receipt_id else None,
            "payload_hash": event.payload_hash,
            "created_at": timestamp(event.created_at),
            "claim_token": event.claim_token,
        },
        "lifecycle event",
    )
    payload = _decode_object(str(row["payload_json"]), "lifecycle event payload")
    expected_fields = {
        "schema_version", "run_id", "sequence_number", "event_type",
        "from_status", "to_status", "stage_name", "attempt_id", "receipt_id",
        "reason_codes", "claim_token", "extra",
    }
    if set(payload) != expected_fields:
        raise LifecycleJournalIntegrityError("lifecycle event payload fields mismatch")
    if not isinstance(payload["extra"], dict):
        raise LifecycleJournalIntegrityError(
            "lifecycle event extra payload must be an object"
        )
    expected_payload_projection: dict[str, object] = {
        "schema_version": "canonical-lifecycle-event-payload-v1",
        "run_id": str(event.run_id),
        "sequence_number": event.sequence_number,
        "event_type": event.event_type.value,
        "from_status": event.from_status.value if event.from_status else None,
        "to_status": event.to_status.value if event.to_status else None,
        "stage_name": event.stage_name.value if event.stage_name else None,
        "attempt_id": str(event.attempt_id) if event.attempt_id else None,
        "receipt_id": str(event.receipt_id) if event.receipt_id else None,
        "reason_codes": list(event.reason_codes),
        "claim_token": event.claim_token,
    }
    for key, value in expected_payload_projection.items():
        if payload[key] != value:
            raise LifecycleJournalIntegrityError(
                f"lifecycle event payload projection mismatch at {key}"
            )
    if canonical_hash(payload) != event.payload_hash:
        raise LifecycleJournalIntegrityError("lifecycle event payload hash mismatch")
    return event


def encode(payload: Mapping[str, Any]) -> str:
    return canonical_json(payload)


def timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def parse_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise LifecycleJournalIntegrityError("stored timestamp is invalid") from exc
    else:
        raise LifecycleJournalIntegrityError("stored timestamp is invalid")
    require_utc_second("stored timestamp", parsed)
    if isinstance(value, str) and timestamp(parsed) != value:
        raise LifecycleJournalIntegrityError("stored timestamp is not canonical")
    return parsed


def require_not_before(
    label: str,
    value: datetime,
    floor: datetime | None,
) -> None:
    if floor is not None and value < floor:
        raise ValueError(f"{label} cannot precede existing journal time")


def _decode_record(
    raw: str,
    loader: Callable[[Mapping[str, Any]], _RecordT],
) -> _RecordT:
    payload = _decode_object(raw, "stored journal record")
    try:
        record = loader(payload)
    except (TypeError, ValueError, KeyError) as exc:
        raise LifecycleJournalIntegrityError(
            "stored journal record violates its canonical contract"
        ) from exc
    if encode(record.to_canonical_dict()) != raw:
        raise LifecycleJournalIntegrityError("stored journal record round trip changed")
    return record


def _decode_object(raw: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LifecycleJournalIntegrityError(f"{label} JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise LifecycleJournalIntegrityError(f"{label} JSON must be an object")
    if encode(payload) != raw:
        raise LifecycleJournalIntegrityError(f"{label} JSON is not canonical")
    return payload


def _verify_projection(
    row: dict[str, Any],
    expected: Mapping[str, object],
    label: str,
) -> None:
    for column, value in expected.items():
        actual = row[column]
        if isinstance(actual, datetime):
            actual = timestamp(actual)
        elif isinstance(actual, date):
            actual = actual.isoformat()
        if actual != value:
            raise LifecycleJournalIntegrityError(
                f"{label} JSON/projection mismatch at {column}"
            )
