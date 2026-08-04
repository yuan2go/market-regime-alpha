"""Transactional SQLite adapter for the canonical Lifecycle Runtime Journal."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleAttemptId,
    LifecycleAttemptResult,
    LifecycleEvent,
    LifecycleEventId,
    LifecycleEventType,
    LifecycleRetryState,
    LifecycleRun,
    LifecycleRunId,
    LifecycleStage,
    LifecycleStageName,
    LifecycleStageStatus,
    require_utc_second,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleClaimConflict,
    LifecycleConcurrentModification,
    LifecycleHistory,
    LifecycleJournalIntegrityError,
    LifecycleRunNotFound,
    LifecycleStageNotFound,
    LifecycleUnsafeResume,
    StageFailure,
    StageTransition,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    WAITING_LIFECYCLE_RUN_STATUSES,
    LifecycleRunStatus,
    validate_lifecycle_run_transition,
    validate_lifecycle_stage_progression,
    validate_lifecycle_stage_transition,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.application.canonical_lifecycle._sqlite_schema import (
    verify_lifecycle_schema,
)
from market_regime_alpha.application.canonical_lifecycle._sqlite_codec import (
    attempt_from_row as _attempt_from_row,
    attempt_id as _attempt_id,
    command_from_row as _command_from_row,
    encode as _encode,
    event_from_row as _event_from_row,
    parse_timestamp as _parse_timestamp,
    receipt_from_row as _receipt_from_row,
    require_not_before as _require_not_before,
    run_from_row as _run_from_row,
    stage_from_row as _stage_from_row,
    timestamp as _timestamp,
    verify_command_replay as _verify_command_replay,
    verify_stored_command as _verify_stored_command,
)


_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
_UP_MIGRATION = _MIGRATION_ROOT / "011_canonical_lifecycle_runtime_up.sql"
_FaultInjector = Callable[[str], None]


class SQLiteLifecycleRunRepository:
    """Durable, fenced and recoverable lifecycle state journal.

    Domain services remain responsible for their own objects.  This adapter
    atomically settles only the lifecycle attempt, receipt, projections and
    append-only history that point to those objects.
    """

    def __init__(
        self,
        path: Path,
        *,
        fault_injector: _FaultInjector | None = None,
        busy_timeout_seconds: float = 30.0,
    ) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        if fault_injector is not None and not callable(fault_injector):
            raise TypeError("fault_injector must be callable or None")
        if isinstance(busy_timeout_seconds, bool) or busy_timeout_seconds <= 0:
            raise ValueError("busy_timeout_seconds must be positive")
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fault_injector = fault_injector
        self._busy_timeout_seconds = float(busy_timeout_seconds)
        self._initialize()

    def create_or_get(
        self,
        command: CanonicalLifecycleCommand,
        *,
        created_at: datetime,
    ) -> LifecycleRun:
        if not isinstance(command, CanonicalLifecycleCommand):
            raise TypeError("command must be a CanonicalLifecycleCommand")
        require_utc_second("created_at", created_at)
        created = LifecycleRun(
            run_id=command.run_id,
            idempotency_key=command.idempotency_key,
            command_hash=command.command_hash,
            run_type=command.run_type,
            decision_date=command.decision_date,
            as_of_time=command.as_of_time,
            status=LifecycleRunStatus.CREATED,
            current_stage=None,
            input_manifest_id=command.input_manifest_id,
            input_content_hash=command.input_content_hash,
            completed_stages=(),
            configuration_references=command.configuration_references,
            configuration_manifest_hash=command.configuration_manifest_hash,
            model_references=command.model_references,
            model_version_manifest_hash=command.model_version_manifest_hash,
            retry_state=LifecycleRetryState.NOT_REQUIRED,
            failure_reason=None,
            blocker_reason=None,
            created_at=created_at,
            updated_at=created_at,
            completed_at=None,
            version=1,
            claim_token=0,
            source_run_id=command.source_run_id,
            source_command_hash=command.source_command_hash,
            source_history_hash=command.source_history_hash,
            replay_report_hash=command.replay_report_hash,
            schema_version=(
                LifecycleRun.LEGACY_SCHEMA_VERSION
                if command.schema_version
                == CanonicalLifecycleCommand.LEGACY_SCHEMA_VERSION
                else LifecycleRun.SCHEMA_VERSION
            ),
        )
        command_json = _encode(command.to_canonical_dict())
        run_json = _encode(created.to_canonical_dict())
        with self._transaction() as connection:
            inserted = False
            try:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO lifecycle_runs(
                        run_id, idempotency_key, command_hash, command_json,
                        run_type, decision_date, as_of_time, status, current_stage,
                        input_manifest_id, input_content_hash, run_json, version,
                        claim_token, created_at, updated_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 1, 0, ?, ?, NULL)
                    """,
                    (
                        str(created.run_id),
                        created.idempotency_key,
                        created.command_hash,
                        command_json,
                        created.run_type.value,
                        created.decision_date.isoformat(),
                        _timestamp(created.as_of_time),
                        created.status.value,
                        str(created.input_manifest_id) if created.input_manifest_id else None,
                        created.input_content_hash,
                        run_json,
                        _timestamp(created_at),
                        _timestamp(created_at),
                    ),
                )
                inserted = cursor.rowcount == 1
            except sqlite3.IntegrityError as exc:
                self._reload_idempotency_or_raise(connection, command, exc)
            row = connection.execute(
                "SELECT * FROM lifecycle_runs WHERE idempotency_key = ?",
                (command.idempotency_key,),
            ).fetchone()
            if row is None:
                collision = connection.execute(
                    "SELECT * FROM lifecycle_runs WHERE run_id = ?",
                    (str(command.run_id),),
                ).fetchone()
                if collision is not None:
                    raise LifecycleJournalIntegrityError(
                        "deterministic run ID collides with another idempotency key"
                    )
                raise LifecycleJournalIntegrityError("lifecycle run insert was not durable")
            stored_run = _run_from_row(row)
            stored_command = _command_from_row(row)
            _verify_command_replay(command, stored_command, stored_run)
            if inserted:
                for stage_name in LIFECYCLE_STAGE_ORDER:
                    pending = LifecycleStage(
                        run_id=stored_run.run_id,
                        stage_name=stage_name,
                        stage_status=LifecycleStageStatus.PENDING,
                        attempt_count=0,
                        input_references=(),
                        output_references=(),
                        started_at=None,
                        completed_at=None,
                        failure_reason=None,
                        blocker_reason=None,
                        version=1,
                    )
                    connection.execute(
                        """
                        INSERT INTO lifecycle_stages(
                            run_id, stage_name, stage_status, attempt_count,
                            stage_json, version
                        ) VALUES (?, ?, ?, 0, ?, 1)
                        """,
                        (
                            str(stored_run.run_id),
                            stage_name.value,
                            LifecycleStageStatus.PENDING.value,
                            _encode(pending.to_canonical_dict()),
                        ),
                    )
                self._append_event(
                    connection,
                    run=stored_run,
                    event_type=LifecycleEventType.RUN_CREATED,
                    created_at=created_at,
                    from_status=None,
                    to_status=LifecycleRunStatus.CREATED,
                )
        return stored_run

    def get_run(self, run_id: LifecycleRunId) -> LifecycleRun:
        _require_run_id(run_id)
        with self._connect() as connection:
            row = self._select_run(connection, run_id)
        return _run_from_row(row)

    def get_command(self, run_id: LifecycleRunId) -> CanonicalLifecycleCommand:
        """Reload the exact controlled inputs and controls needed for recovery."""

        _require_run_id(run_id)
        with self._connect() as connection:
            row = self._select_run(connection, run_id)
        run = _run_from_row(row)
        command = _command_from_row(row)
        _verify_stored_command(command, run)
        return command

    def get_stage(
        self,
        run_id: LifecycleRunId,
        stage: LifecycleStageName,
    ) -> LifecycleStage | None:
        _require_run_id(run_id)
        _require_stage_name(stage)
        with self._connect() as connection:
            self._select_run(connection, run_id)
            row = connection.execute(
                "SELECT * FROM lifecycle_stages WHERE run_id = ? AND stage_name = ?",
                (str(run_id), stage.value),
            ).fetchone()
        return _stage_from_row(row) if row is not None else None

    def claim(
        self,
        run_id: LifecycleRunId,
        *,
        expected_version: int,
        claimed_at: datetime,
    ) -> LifecycleRun:
        _require_run_id(run_id)
        _require_positive("expected_version", expected_version)
        require_utc_second("claimed_at", claimed_at)
        with self._transaction() as connection:
            row = self._select_run(connection, run_id)
            current = _run_from_row(row)
            _require_not_before("claimed_at", claimed_at, current.updated_at)
            if current.version != expected_version:
                raise LifecycleConcurrentModification("run version compare-and-set failed")
            if current.status in {
                LifecycleRunStatus.FAILED,
                LifecycleRunStatus.COMPLETED,
                LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
            }:
                raise LifecycleClaimConflict(
                    f"run cannot be claimed from {current.status.value}"
                )
            if current.status is not LifecycleRunStatus.RUNNING:
                validate_lifecycle_run_transition(
                    current.status, LifecycleRunStatus.RUNNING
                )
            updated = replace(
                current,
                status=LifecycleRunStatus.RUNNING,
                retry_state=LifecycleRetryState.NOT_REQUIRED,
                failure_reason=None,
                blocker_reason=None,
                updated_at=claimed_at,
                version=current.version + 1,
                claim_token=current.claim_token + 1,
            )
            self._update_run(
                connection,
                updated,
                expected_version=current.version,
                expected_claim_token=current.claim_token,
            )
            self._append_event(
                connection,
                run=updated,
                event_type=LifecycleEventType.RUN_CLAIMED,
                created_at=claimed_at,
                from_status=current.status,
                to_status=LifecycleRunStatus.RUNNING,
            )
        return updated

    def start_stage(
        self,
        run_id: LifecycleRunId,
        stage: LifecycleStageName,
        *,
        started_at: datetime,
        claim_token: int,
    ) -> LifecycleAttempt:
        _require_run_id(run_id)
        _require_stage_name(stage)
        _require_positive("claim_token", claim_token)
        require_utc_second("started_at", started_at)
        with self._transaction() as connection:
            run_row = self._select_run(connection, run_id)
            current_run = _run_from_row(run_row)
            _require_not_before("started_at", started_at, current_run.updated_at)
            self._assert_claim(current_run, claim_token)
            stage_row = connection.execute(
                "SELECT * FROM lifecycle_stages WHERE run_id = ? AND stage_name = ?",
                (str(run_id), stage.value),
            ).fetchone()
            current_stage = _stage_from_row(stage_row) if stage_row is not None else None
            if current_stage is None:
                raise LifecycleJournalIntegrityError(
                    f"run is missing initialized stage {stage.value}"
                )
            else:
                if current_stage.stage_status in {
                    LifecycleStageStatus.COMPLETED,
                    LifecycleStageStatus.BLOCKED,
                    LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
                }:
                    raise LifecycleConcurrentModification(
                        f"settled stage {stage.value} cannot run again"
                    )
                if current_stage.stage_status is LifecycleStageStatus.RUNNING:
                    self._settle_superseded_attempt(
                        connection,
                        run=current_run,
                        stage=current_stage,
                        new_claim_token=claim_token,
                        settled_at=started_at,
                    )
                    current_stage = _stage_from_row(
                        self._select_stage(connection, run_id, stage)
                    )
                validate_lifecycle_stage_progression(current_run.completed_stages, stage)
                validate_lifecycle_stage_transition(
                    current_stage.stage_status, LifecycleStageStatus.RUNNING
                )
                attempt_number = current_stage.attempt_count + 1
                stage_version = current_stage.version + 1
            attempt_id = _attempt_id(run_id, stage, attempt_number)
            attempt = LifecycleAttempt(
                attempt_id=attempt_id,
                run_id=run_id,
                stage_name=stage,
                attempt_number=attempt_number,
                started_at=started_at,
                completed_at=None,
                result=LifecycleAttemptResult.RUNNING,
                exception_type=None,
                exception_message=None,
                claim_token=claim_token,
            )
            running_stage = LifecycleStage(
                run_id=run_id,
                stage_name=stage,
                stage_status=LifecycleStageStatus.RUNNING,
                attempt_count=attempt_number,
                input_references=(),
                output_references=(),
                started_at=started_at,
                completed_at=None,
                failure_reason=None,
                blocker_reason=None,
                version=stage_version,
            )
            cursor = connection.execute(
                """
                UPDATE lifecycle_stages
                SET stage_status = ?, attempt_count = ?, stage_json = ?, version = ?
                WHERE run_id = ? AND stage_name = ? AND version = ?
                  AND stage_status IN ('PENDING', 'FAILED', 'WAITING')
                """,
                (
                    LifecycleStageStatus.RUNNING.value,
                    attempt_number,
                    _encode(running_stage.to_canonical_dict()),
                    stage_version,
                    str(run_id),
                    stage.value,
                    current_stage.version,
                ),
            )
            _require_rowcount(cursor, "stage start compare-and-set failed")
            connection.execute(
                """
                INSERT INTO lifecycle_attempts(
                    attempt_id, run_id, stage_name, attempt_number, result,
                    attempt_json, claim_token, started_at, completed_at,
                    exception_type, exception_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    str(attempt_id), str(run_id), stage.value, attempt_number,
                    attempt.result.value, _encode(attempt.to_canonical_dict()),
                    claim_token, _timestamp(started_at),
                ),
            )
            updated_run = replace(
                current_run,
                current_stage=stage,
                updated_at=started_at,
                version=current_run.version + 1,
            )
            self._update_run(
                connection,
                updated_run,
                expected_version=current_run.version,
                expected_claim_token=claim_token,
            )
            self._append_event(
                connection,
                run=updated_run,
                event_type=LifecycleEventType.STAGE_STATUS_CHANGED,
                created_at=started_at,
                stage_name=stage,
                extra_payload={
                    "from_stage_status": current_stage.stage_status.value,
                    "to_stage_status": LifecycleStageStatus.RUNNING.value,
                },
            )
            self._append_event(
                connection,
                run=updated_run,
                event_type=LifecycleEventType.ATTEMPT_STARTED,
                created_at=started_at,
                stage_name=stage,
                attempt_id=attempt_id,
                extra_payload={"attempt_number": attempt_number},
            )
        return attempt

    def finish_stage(self, transition: StageTransition) -> LifecycleRun:
        if not isinstance(transition, StageTransition):
            raise TypeError("transition must be a StageTransition")
        with self._transaction() as connection:
            run = _run_from_row(self._select_run(connection, transition.run_id))
            stage = _stage_from_row(
                self._select_stage(connection, transition.run_id, transition.stage_name)
            )
            self._validate_settlement_versions(
                run,
                stage,
                expected_run_version=transition.expected_run_version,
                expected_stage_version=transition.expected_stage_version,
                claim_token=transition.claim_token,
            )
            attempt = _attempt_from_row(
                self._select_attempt(connection, transition.attempt_id)
            )
            _require_not_before(
                "completed_at", transition.completed_at, run.updated_at
            )
            _require_not_before(
                "completed_at", transition.completed_at, stage.started_at
            )
            _require_not_before(
                "completed_at", transition.completed_at, attempt.started_at
            )
            self._validate_running_attempt(
                attempt,
                run_id=transition.run_id,
                stage=transition.stage_name,
                claim_token=transition.claim_token,
                attempt_number=transition.receipt.attempt_number,
            )
            validate_lifecycle_stage_transition(
                stage.stage_status, transition.receipt.stage_result
            )
            if transition.target_run_status is not run.status:
                validate_lifecycle_run_transition(run.status, transition.target_run_status)
            settled_attempt = replace(
                attempt,
                completed_at=transition.completed_at,
                result=LifecycleAttemptResult(transition.receipt.stage_result.value),
            )
            self._complete_attempt(connection, attempt, settled_attempt)
            self._fault("finish_after_attempt")
            existing_receipt_row = connection.execute(
                """
                SELECT * FROM lifecycle_stage_receipts
                WHERE receipt_id = ? OR (
                    run_id = ? AND stage_name = ? AND receipt_hash = ?
                )
                """,
                (
                    str(transition.receipt.receipt_id),
                    str(transition.run_id),
                    transition.stage_name.value,
                    transition.receipt.receipt_hash,
                ),
            ).fetchone()
            receipt_for_event = transition.receipt
            if existing_receipt_row is not None:
                stored_receipt = _receipt_from_row(existing_receipt_row)
                if (
                    stored_receipt.receipt_id != transition.receipt.receipt_id
                    or stored_receipt.receipt_hash != transition.receipt.receipt_hash
                    or stored_receipt.semantic_payload()
                    != transition.receipt.semantic_payload()
                ):
                    raise LifecycleJournalIntegrityError(
                        "stage receipt identity conflict"
                    )
                receipt_for_event = stored_receipt
            else:
                connection.execute(
                    """
                    INSERT INTO lifecycle_stage_receipts(
                        receipt_id, run_id, stage_name, attempt_number,
                        receipt_hash, receipt_json, stage_result, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(transition.receipt.receipt_id),
                        str(transition.run_id),
                        transition.stage_name.value,
                        transition.receipt.attempt_number,
                        transition.receipt.receipt_hash,
                        _encode(transition.receipt.to_canonical_dict()),
                        transition.receipt.stage_result.value,
                        _timestamp(transition.receipt.created_at),
                    ),
                )
            self._fault("finish_after_receipt")
            settled_stage = replace(
                stage,
                stage_status=transition.receipt.stage_result,
                input_references=transition.input_references,
                output_references=transition.output_references,
                completed_at=transition.completed_at,
                failure_reason=None,
                blocker_reason=(
                    transition.blocker_reason
                    if transition.receipt.stage_result
                    in {
                        LifecycleStageStatus.WAITING,
                        LifecycleStageStatus.BLOCKED,
                        LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
                    }
                    else None
                ),
                version=stage.version + 1,
            )
            self._update_stage(connection, stage, settled_stage)
            self._fault("finish_after_stage")
            completed_stages = run.completed_stages
            if transition.receipt.stage_result in {
                LifecycleStageStatus.COMPLETED,
                LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
            }:
                completed_stages = (*completed_stages, transition.stage_name)
            terminal = transition.target_run_status in {
                LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
                LifecycleRunStatus.COMPLETED,
            }
            run_blocker = (
                transition.blocker_reason
                if transition.target_run_status in WAITING_LIFECYCLE_RUN_STATUSES
                else None
            )
            updated_run = replace(
                run,
                status=transition.target_run_status,
                completed_stages=completed_stages,
                retry_state=LifecycleRetryState.NOT_REQUIRED,
                failure_reason=None,
                blocker_reason=run_blocker,
                updated_at=transition.completed_at,
                completed_at=transition.completed_at if terminal else None,
                version=run.version + 1,
            )
            self._update_run(
                connection,
                updated_run,
                expected_version=run.version,
                expected_claim_token=transition.claim_token,
            )
            self._fault("finish_after_run")
            self._append_event(
                connection,
                run=updated_run,
                event_type=LifecycleEventType.ATTEMPT_FINISHED,
                created_at=transition.completed_at,
                stage_name=transition.stage_name,
                attempt_id=transition.attempt_id,
                reason_codes=transition.receipt.reason_codes,
                extra_payload={"result": settled_attempt.result.value},
            )
            self._fault("finish_after_attempt_event")
            self._append_event(
                connection,
                run=updated_run,
                event_type=LifecycleEventType.RECEIPT_RECORDED,
                created_at=transition.completed_at,
                stage_name=transition.stage_name,
                receipt_id=receipt_for_event.receipt_id,
                reason_codes=transition.receipt.reason_codes,
            )
            self._fault("finish_after_receipt_event")
            self._append_event(
                connection,
                run=updated_run,
                event_type=LifecycleEventType.STAGE_STATUS_CHANGED,
                created_at=transition.completed_at,
                stage_name=transition.stage_name,
                reason_codes=transition.receipt.reason_codes,
                extra_payload={
                    "from_stage_status": LifecycleStageStatus.RUNNING.value,
                    "to_stage_status": transition.receipt.stage_result.value,
                },
            )
            self._fault("finish_after_stage_event")
            if run.status is not updated_run.status:
                self._append_event(
                    connection,
                    run=updated_run,
                    event_type=LifecycleEventType.RUN_STATUS_CHANGED,
                    created_at=transition.completed_at,
                    from_status=run.status,
                    to_status=updated_run.status,
                    stage_name=transition.stage_name,
                    reason_codes=transition.receipt.reason_codes,
                )
                self._fault("finish_after_run_event")
        return updated_run

    def mark_stage_failed(self, failure: StageFailure) -> LifecycleRun:
        if not isinstance(failure, StageFailure):
            raise TypeError("failure must be a StageFailure")
        with self._transaction() as connection:
            run = _run_from_row(self._select_run(connection, failure.run_id))
            stage = _stage_from_row(
                self._select_stage(connection, failure.run_id, failure.stage_name)
            )
            self._validate_settlement_versions(
                run,
                stage,
                expected_run_version=failure.expected_run_version,
                expected_stage_version=failure.expected_stage_version,
                claim_token=failure.claim_token,
            )
            attempt = _attempt_from_row(
                self._select_attempt(connection, failure.attempt_id)
            )
            _require_not_before("failed_at", failure.failed_at, run.updated_at)
            _require_not_before("failed_at", failure.failed_at, stage.started_at)
            _require_not_before("failed_at", failure.failed_at, attempt.started_at)
            self._validate_running_attempt(
                attempt,
                run_id=failure.run_id,
                stage=failure.stage_name,
                claim_token=failure.claim_token,
                attempt_number=stage.attempt_count,
            )
            validate_lifecycle_stage_transition(
                stage.stage_status, LifecycleStageStatus.FAILED
            )
            validate_lifecycle_run_transition(run.status, LifecycleRunStatus.FAILED)
            settled_attempt = replace(
                attempt,
                completed_at=failure.failed_at,
                result=LifecycleAttemptResult.FAILED,
                exception_type=failure.exception_type,
                exception_message=failure.exception_message,
            )
            self._complete_attempt(connection, attempt, settled_attempt)
            failure_reason = f"{failure.exception_type}: {failure.exception_message}"
            failed_stage = replace(
                stage,
                stage_status=LifecycleStageStatus.FAILED,
                input_references=failure.input_references,
                output_references=(),
                completed_at=failure.failed_at,
                failure_reason=failure_reason,
                blocker_reason=None,
                version=stage.version + 1,
            )
            self._update_stage(connection, stage, failed_stage)
            failed_run = replace(
                run,
                status=LifecycleRunStatus.FAILED,
                retry_state=LifecycleRetryState.AVAILABLE,
                failure_reason=failure_reason,
                blocker_reason=None,
                updated_at=failure.failed_at,
                completed_at=None,
                version=run.version + 1,
            )
            self._update_run(
                connection,
                failed_run,
                expected_version=run.version,
                expected_claim_token=failure.claim_token,
            )
            self._append_event(
                connection,
                run=failed_run,
                event_type=LifecycleEventType.ATTEMPT_FINISHED,
                created_at=failure.failed_at,
                stage_name=failure.stage_name,
                attempt_id=failure.attempt_id,
                reason_codes=("STAGE_EXCEPTION",),
                extra_payload={
                    "exception_type": failure.exception_type,
                    "result": LifecycleAttemptResult.FAILED.value,
                },
            )
            self._append_event(
                connection,
                run=failed_run,
                event_type=LifecycleEventType.STAGE_STATUS_CHANGED,
                created_at=failure.failed_at,
                stage_name=failure.stage_name,
                reason_codes=("STAGE_EXCEPTION",),
                extra_payload={
                    "from_stage_status": LifecycleStageStatus.RUNNING.value,
                    "to_stage_status": LifecycleStageStatus.FAILED.value,
                },
            )
            self._append_event(
                connection,
                run=failed_run,
                event_type=LifecycleEventType.RUN_STATUS_CHANGED,
                created_at=failure.failed_at,
                from_status=run.status,
                to_status=LifecycleRunStatus.FAILED,
                stage_name=failure.stage_name,
                reason_codes=("STAGE_EXCEPTION",),
            )
        return failed_run

    def resume(
        self,
        run_id: LifecycleRunId,
        *,
        resumed_at: datetime,
    ) -> LifecycleRun:
        _require_run_id(run_id)
        require_utc_second("resumed_at", resumed_at)
        with self._transaction() as connection:
            failed = _run_from_row(self._select_run(connection, run_id))
            _require_not_before("resumed_at", resumed_at, failed.updated_at)
            if failed.status is not LifecycleRunStatus.FAILED:
                raise LifecycleUnsafeResume(
                    f"only FAILED runs can resume, got {failed.status.value}"
                )
            validate_lifecycle_run_transition(
                LifecycleRunStatus.FAILED, LifecycleRunStatus.RETRYING
            )
            retrying = replace(
                failed,
                status=LifecycleRunStatus.RETRYING,
                retry_state=LifecycleRetryState.IN_PROGRESS,
                failure_reason=None,
                updated_at=resumed_at,
                version=failed.version + 1,
            )
            self._update_run(
                connection,
                retrying,
                expected_version=failed.version,
                expected_claim_token=failed.claim_token,
            )
            self._append_event(
                connection,
                run=retrying,
                event_type=LifecycleEventType.RUN_STATUS_CHANGED,
                created_at=resumed_at,
                from_status=LifecycleRunStatus.FAILED,
                to_status=LifecycleRunStatus.RETRYING,
                stage_name=failed.current_stage,
                reason_codes=("RUN_RESUMED",),
            )
            validate_lifecycle_run_transition(
                LifecycleRunStatus.RETRYING, LifecycleRunStatus.RUNNING
            )
            running = replace(
                retrying,
                status=LifecycleRunStatus.RUNNING,
                retry_state=LifecycleRetryState.NOT_REQUIRED,
                version=retrying.version + 1,
                claim_token=retrying.claim_token + 1,
            )
            self._update_run(
                connection,
                running,
                expected_version=retrying.version,
                expected_claim_token=retrying.claim_token,
            )
            self._append_event(
                connection,
                run=running,
                event_type=LifecycleEventType.RUN_CLAIMED,
                created_at=resumed_at,
                from_status=LifecycleRunStatus.RETRYING,
                to_status=LifecycleRunStatus.RUNNING,
                stage_name=failed.current_stage,
                reason_codes=("RUN_RESUMED",),
            )
        return running

    def history(self, run_id: LifecycleRunId) -> LifecycleHistory:
        _require_run_id(run_id)
        stage_order = {stage.value: index for index, stage in enumerate(LIFECYCLE_STAGE_ORDER)}
        with self._connect() as connection:
            run = _run_from_row(self._select_run(connection, run_id))
            stage_rows = connection.execute(
                "SELECT * FROM lifecycle_stages WHERE run_id = ?",
                (str(run_id),),
            ).fetchall()
            attempt_rows = connection.execute(
                "SELECT * FROM lifecycle_attempts WHERE run_id = ?",
                (str(run_id),),
            ).fetchall()
            receipt_rows = connection.execute(
                """
                SELECT * FROM lifecycle_stage_receipts
                WHERE run_id = ? ORDER BY created_at, receipt_id
                """,
                (str(run_id),),
            ).fetchall()
            event_rows = connection.execute(
                """
                SELECT * FROM lifecycle_events
                WHERE run_id = ? ORDER BY sequence_number
                """,
                (str(run_id),),
            ).fetchall()
        stages = tuple(
            sorted(
                (_stage_from_row(row) for row in stage_rows),
                key=lambda item: stage_order[item.stage_name.value],
            )
        )
        attempts = tuple(
            sorted(
                (_attempt_from_row(row) for row in attempt_rows),
                key=lambda item: (stage_order[item.stage_name.value], item.attempt_number),
            )
        )
        receipts = tuple(_receipt_from_row(row) for row in receipt_rows)
        events = tuple(_event_from_row(row) for row in event_rows)
        return LifecycleHistory(
            run=run,
            stages=stages,
            attempts=attempts,
            receipts=receipts,
            events=events,
            event_payloads=tuple(str(row["payload_json"]) for row in event_rows),
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            try:
                connection.executescript(_UP_MIGRATION.read_text(encoding="utf-8"))
                verify_lifecycle_schema(connection)
            except sqlite3.DatabaseError as exc:
                raise LifecycleJournalIntegrityError(
                    "migration 011 could not establish the authoritative schema"
                ) from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.path,
            timeout=self._busy_timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            f"PRAGMA busy_timeout = {int(self._busy_timeout_seconds * 1000)}"
        )
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def _select_run(
        self, connection: sqlite3.Connection, run_id: LifecycleRunId
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM lifecycle_runs WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        if row is None:
            raise LifecycleRunNotFound(str(run_id))
        return row

    def _select_stage(
        self,
        connection: sqlite3.Connection,
        run_id: LifecycleRunId,
        stage: LifecycleStageName,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM lifecycle_stages WHERE run_id = ? AND stage_name = ?",
            (str(run_id), stage.value),
        ).fetchone()
        if row is None:
            raise LifecycleStageNotFound(f"{run_id}:{stage.value}")
        return row

    def _select_attempt(
        self, connection: sqlite3.Connection, attempt_id: LifecycleAttemptId
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM lifecycle_attempts WHERE attempt_id = ?",
            (str(attempt_id),),
        ).fetchone()
        if row is None:
            raise LifecycleConcurrentModification(f"unknown attempt {attempt_id}")
        return row

    def _assert_claim(self, run: LifecycleRun, claim_token: int) -> None:
        if run.status is not LifecycleRunStatus.RUNNING:
            raise LifecycleClaimConflict("stage mutation requires a RUNNING run")
        if run.claim_token != claim_token:
            raise LifecycleClaimConflict("stale lifecycle claim token")

    def _validate_settlement_versions(
        self,
        run: LifecycleRun,
        stage: LifecycleStage,
        *,
        expected_run_version: int,
        expected_stage_version: int,
        claim_token: int,
    ) -> None:
        self._assert_claim(run, claim_token)
        if run.version != expected_run_version:
            raise LifecycleConcurrentModification("run version compare-and-set failed")
        if stage.version != expected_stage_version:
            raise LifecycleConcurrentModification("stage version compare-and-set failed")
        if stage.stage_status is not LifecycleStageStatus.RUNNING:
            raise LifecycleConcurrentModification("stage is not RUNNING")

    def _validate_running_attempt(
        self,
        attempt: LifecycleAttempt,
        *,
        run_id: LifecycleRunId,
        stage: LifecycleStageName,
        claim_token: int,
        attempt_number: int,
    ) -> None:
        if (
            attempt.run_id != run_id
            or attempt.stage_name is not stage
            or attempt.attempt_number != attempt_number
        ):
            raise LifecycleConcurrentModification("attempt scope mismatch")
        if attempt.result is not LifecycleAttemptResult.RUNNING:
            raise LifecycleConcurrentModification("attempt is already settled")
        if attempt.claim_token != claim_token:
            raise LifecycleClaimConflict("attempt belongs to a stale claim")

    def _complete_attempt(
        self,
        connection: sqlite3.Connection,
        current: LifecycleAttempt,
        settled: LifecycleAttempt,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE lifecycle_attempts
            SET result = ?, attempt_json = ?, completed_at = ?,
                exception_type = ?, exception_message = ?
            WHERE attempt_id = ? AND result = 'RUNNING' AND claim_token = ?
            """,
            (
                settled.result.value,
                _encode(settled.to_canonical_dict()),
                _timestamp(settled.completed_at),
                settled.exception_type,
                settled.exception_message,
                str(current.attempt_id),
                current.claim_token,
            ),
        )
        _require_rowcount(cursor, "attempt completion compare-and-set failed")

    def _update_stage(
        self,
        connection: sqlite3.Connection,
        current: LifecycleStage,
        updated: LifecycleStage,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE lifecycle_stages
            SET stage_status = ?, attempt_count = ?, stage_json = ?, version = ?
            WHERE run_id = ? AND stage_name = ? AND version = ?
              AND stage_status = ?
            """,
            (
                updated.stage_status.value,
                updated.attempt_count,
                _encode(updated.to_canonical_dict()),
                updated.version,
                str(current.run_id),
                current.stage_name.value,
                current.version,
                current.stage_status.value,
            ),
        )
        _require_rowcount(cursor, "stage projection compare-and-set failed")

    def _update_run(
        self,
        connection: sqlite3.Connection,
        updated: LifecycleRun,
        *,
        expected_version: int,
        expected_claim_token: int,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE lifecycle_runs
            SET status = ?, current_stage = ?, run_json = ?, version = ?,
                claim_token = ?, updated_at = ?, completed_at = ?
            WHERE run_id = ? AND version = ? AND claim_token = ?
            """,
            (
                updated.status.value,
                updated.current_stage.value if updated.current_stage else None,
                _encode(updated.to_canonical_dict()),
                updated.version,
                updated.claim_token,
                _timestamp(updated.updated_at),
                _timestamp(updated.completed_at),
                str(updated.run_id),
                expected_version,
                expected_claim_token,
            ),
        )
        _require_rowcount(cursor, "run projection compare-and-set failed")

    def _settle_superseded_attempt(
        self,
        connection: sqlite3.Connection,
        *,
        run: LifecycleRun,
        stage: LifecycleStage,
        new_claim_token: int,
        settled_at: datetime,
    ) -> None:
        row = connection.execute(
            """
            SELECT * FROM lifecycle_attempts
            WHERE run_id = ? AND stage_name = ? AND attempt_number = ?
            """,
            (str(run.run_id), stage.stage_name.value, stage.attempt_count),
        ).fetchone()
        if row is None:
            raise LifecycleJournalIntegrityError("RUNNING stage has no current attempt")
        attempt = _attempt_from_row(row)
        if attempt.claim_token == new_claim_token:
            raise LifecycleConcurrentModification("stage already has a running attempt")
        if attempt.claim_token > new_claim_token:
            raise LifecycleClaimConflict("attempt carries a future claim token")
        settled_attempt = replace(
            attempt,
            completed_at=settled_at,
            result=LifecycleAttemptResult.FAILED,
            exception_type="LifecycleClaimSuperseded",
            exception_message="attempt was abandoned by a newer fenced claim",
        )
        self._complete_attempt(connection, attempt, settled_attempt)
        failed_stage = replace(
            stage,
            stage_status=LifecycleStageStatus.FAILED,
            completed_at=settled_at,
            failure_reason=(
                "LifecycleClaimSuperseded: attempt was abandoned by a newer fenced claim"
            ),
            version=stage.version + 1,
        )
        self._update_stage(connection, stage, failed_stage)
        self._append_event(
            connection,
            run=run,
            event_type=LifecycleEventType.ATTEMPT_FINISHED,
            created_at=settled_at,
            stage_name=stage.stage_name,
            attempt_id=attempt.attempt_id,
            reason_codes=("CLAIM_SUPERSEDED",),
            extra_payload={"result": LifecycleAttemptResult.FAILED.value},
        )
        self._append_event(
            connection,
            run=run,
            event_type=LifecycleEventType.STAGE_STATUS_CHANGED,
            created_at=settled_at,
            stage_name=stage.stage_name,
            reason_codes=("CLAIM_SUPERSEDED",),
            extra_payload={
                "from_stage_status": LifecycleStageStatus.RUNNING.value,
                "to_stage_status": LifecycleStageStatus.FAILED.value,
            },
        )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        run: LifecycleRun,
        event_type: LifecycleEventType,
        created_at: datetime,
        from_status: LifecycleRunStatus | None = None,
        to_status: LifecycleRunStatus | None = None,
        stage_name: LifecycleStageName | None = None,
        attempt_id: LifecycleAttemptId | None = None,
        receipt_id: ArtifactId | None = None,
        reason_codes: tuple[str, ...] = (),
        extra_payload: Mapping[str, Any] | None = None,
    ) -> LifecycleEvent:
        previous = connection.execute(
            """
            SELECT created_at FROM lifecycle_events
            WHERE run_id = ? ORDER BY sequence_number DESC LIMIT 1
            """,
            (str(run.run_id),),
        ).fetchone()
        if previous is not None:
            prior_created_at = _parse_timestamp(str(previous["created_at"]))
            _require_not_before("event created_at", created_at, prior_created_at)
        sequence = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(sequence_number), 0) + 1
                FROM lifecycle_events WHERE run_id = ?
                """,
                (str(run.run_id),),
            ).fetchone()[0]
        )
        semantic = {
            "schema_version": "canonical-lifecycle-event-payload-v1",
            "run_id": str(run.run_id),
            "sequence_number": sequence,
            "event_type": event_type.value,
            "from_status": from_status.value if from_status else None,
            "to_status": to_status.value if to_status else None,
            "stage_name": stage_name.value if stage_name else None,
            "attempt_id": str(attempt_id) if attempt_id else None,
            "receipt_id": str(receipt_id) if receipt_id else None,
            "reason_codes": list(reason_codes),
            "claim_token": run.claim_token,
            "extra": dict(extra_payload or {}),
        }
        digest = canonical_hash(semantic)
        event = LifecycleEvent(
            event_id=LifecycleEventId(
                f"lifecycle-event-{digest.split(':', 1)[1][:24]}"
            ),
            run_id=run.run_id,
            sequence_number=sequence,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            stage_name=stage_name,
            attempt_id=attempt_id,
            receipt_id=receipt_id,
            reason_codes=reason_codes,
            payload_hash=digest,
            created_at=created_at,
            claim_token=run.claim_token,
        )
        connection.execute(
            """
            INSERT INTO lifecycle_events(
                event_id, run_id, sequence_number, event_type, stage_name,
                attempt_id, receipt_id, event_json, payload_json, payload_hash,
                created_at, claim_token
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.event_id), str(event.run_id), event.sequence_number,
                event.event_type.value,
                event.stage_name.value if event.stage_name else None,
                str(event.attempt_id) if event.attempt_id else None,
                str(event.receipt_id) if event.receipt_id else None,
                _encode(event.to_canonical_dict()), _encode(semantic), event.payload_hash,
                _timestamp(event.created_at), event.claim_token,
            ),
        )
        return event

    def _reload_idempotency_or_raise(
        self,
        connection: sqlite3.Connection,
        command: CanonicalLifecycleCommand,
        cause: sqlite3.IntegrityError,
    ) -> None:
        row = connection.execute(
            "SELECT * FROM lifecycle_runs WHERE idempotency_key = ?",
            (command.idempotency_key,),
        ).fetchone()
        if row is None:
            raise LifecycleJournalIntegrityError(
                "lifecycle insert failed without a reloadable idempotency row"
            ) from cause
        _verify_command_replay(command, _command_from_row(row), _run_from_row(row))

    def _fault(self, point: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(point)


def _require_run_id(value: LifecycleRunId) -> None:
    if not isinstance(value, LifecycleRunId):
        raise TypeError("run_id must be a LifecycleRunId")


def _require_stage_name(value: LifecycleStageName) -> None:
    if not isinstance(value, LifecycleStageName):
        raise TypeError("stage must be a LifecycleStageName")


def _require_positive(label: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


def _require_rowcount(cursor: sqlite3.Cursor, message: str) -> None:
    if cursor.rowcount != 1:
        raise LifecycleConcurrentModification(message)
