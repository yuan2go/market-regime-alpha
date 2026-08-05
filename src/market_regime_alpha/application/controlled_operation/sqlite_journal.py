"""SQLite implementation of the fenced Controlled operation parent journal."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any, Callable, Iterator, Mapping
from uuid import uuid4

from market_regime_alpha.application.controlled_operation.journal import (
    CONTROLLED_OPERATION_STAGE_ORDER,
    ChildRunReferenceKind,
    ClaimedDecisionTimeOperationStage,
    ControlledOperationCommand,
    DecisionTimeOperationReceipt,
    DecisionTimeOperationRunSnapshot,
    DecisionTimeOperationRunStatus,
    DecisionTimeOperationStageName,
    DecisionTimeOperationStageSnapshot,
    DecisionTimeOperationStageStatus,
    OperationChildRunReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_json


CONTROLLED_OPERATION_MIGRATION = (
    Path(__file__).resolve().parent
    / "migrations"
    / "014_controlled_decision_time_operation_up.sql"
)
DEFAULT_CONTROLLED_OPERATION_LEASE = timedelta(minutes=2)
Clock = Callable[[], datetime]
FaultInjector = Callable[[str], None]
_SCHEMA_LOCK = Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class ControlledOperationConflict(ValueError):
    pass


class ControlledOperationClaimRejected(ValueError):
    pass


class SQLiteDecisionTimeOperationJournal:
    """Parent orchestration authority; child domain state stays by reference."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Clock = _utc_now,
        lease_duration: timedelta = DEFAULT_CONTROLLED_OPERATION_LEASE,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if fault_injector is not None and not callable(fault_injector):
            raise TypeError("fault_injector must be callable")
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._lease_duration = lease_duration
        self._fault_injector = fault_injector
        with _SCHEMA_LOCK, self._connect() as connection:
            connection.executescript(CONTROLLED_OPERATION_MIGRATION.read_text(encoding="utf-8"))

    def create_or_get(
        self, command: ControlledOperationCommand
    ) -> DecisionTimeOperationRunSnapshot:
        command.verify_identity()
        with self._immediate() as connection:
            row = connection.execute(
                "SELECT run_id, command_hash FROM controlled_operation_run "
                "WHERE idempotency_key = ?",
                (command.idempotency_key,),
            ).fetchone()
            if row is None:
                now = self._now_text()
                connection.execute(
                    "INSERT INTO controlled_operation_run "
                    "(run_id, idempotency_key, command_hash, command_json, decision_date, "
                    "status, current_stage, version, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'CREATED', NULL, 1, ?, ?)",
                    (
                        str(command.run_id),
                        command.idempotency_key,
                        command.command_hash,
                        canonical_json(command.to_canonical_dict()),
                        command.decision_date.isoformat(),
                        now,
                        now,
                    ),
                )
                connection.executemany(
                    "INSERT INTO controlled_operation_stage "
                    "(run_id, stage_name, status, version, claim_epoch) "
                    "VALUES (?, ?, 'PENDING', 1, 0)",
                    (
                        (str(command.run_id), stage.value)
                        for stage in CONTROLLED_OPERATION_STAGE_ORDER
                    ),
                )
                self._event(
                    connection,
                    run_id=command.run_id,
                    event_type="RUN_CREATED",
                    payload={"command_hash": command.command_hash},
                )
            elif (
                str(row["command_hash"]) != command.command_hash
                or str(row["run_id"]) != str(command.run_id)
            ):
                raise ControlledOperationConflict("Controlled operation idempotency conflict")
        return self.get(command.run_id)

    def resume(self, run_id: ArtifactId) -> DecisionTimeOperationRunSnapshot:
        with self._immediate() as connection:
            run = self._require_run(connection, run_id)
            if str(run["status"]) == DecisionTimeOperationRunStatus.SETTLED.value:
                raise ControlledOperationClaimRejected("settled Controlled operation cannot resume")
            self._recover_expired(connection, run_id=run_id)
            self._event(
                connection,
                run_id=run_id,
                event_type="RUN_RESUMED",
                payload={"version": int(run["version"])},
            )
        return self.get(run_id)

    def claim_stage(
        self,
        *,
        run_id: ArtifactId,
        stage_name: DecisionTimeOperationStageName,
    ) -> ClaimedDecisionTimeOperationStage:
        with self._immediate() as connection:
            run = self._require_run(connection, run_id)
            if str(run["status"]) == DecisionTimeOperationRunStatus.SETTLED.value:
                raise ControlledOperationClaimRejected("settled Controlled operation is immutable")
            self._recover_expired(connection, run_id=run_id)
            self._require_prior_stages(connection, run_id=run_id, stage_name=stage_name)
            row = connection.execute(
                "SELECT * FROM controlled_operation_stage WHERE run_id = ? AND stage_name = ?",
                (str(run_id), stage_name.value),
            ).fetchone()
            if row is None:
                raise KeyError(f"Controlled operation stage is missing: {stage_name.value}")
            status = DecisionTimeOperationStageStatus(str(row["status"]))
            if status is DecisionTimeOperationStageStatus.COMPLETED:
                raise ControlledOperationClaimRejected("completed stage cannot be claimed")
            if status is DecisionTimeOperationStageStatus.IN_PROGRESS:
                raise ControlledOperationClaimRejected("stage has an active lease")
            now = self._now()
            expires = now + self._lease_duration
            claim_id = uuid4().hex
            claim_epoch = int(row["claim_epoch"]) + 1
            stage_version = int(row["version"]) + 1
            cursor = connection.execute(
                "UPDATE controlled_operation_stage SET status = 'IN_PROGRESS', version = ?, "
                "claim_id = ?, claim_epoch = ?, lease_acquired_at = ?, lease_expires_at = ?, "
                "heartbeat_at = ?, last_error = NULL WHERE run_id = ? AND stage_name = ? "
                "AND version = ? AND status IN ('PENDING', 'FAILED')",
                (
                    stage_version,
                    claim_id,
                    claim_epoch,
                    self._format_time(now),
                    self._format_time(expires),
                    self._format_time(now),
                    str(run_id),
                    stage_name.value,
                    int(row["version"]),
                ),
            )
            if cursor.rowcount != 1:
                raise ControlledOperationClaimRejected("Controlled operation stage CAS rejected")
            attempt_number = int(
                connection.execute(
                    "SELECT COUNT(*) + 1 FROM controlled_operation_attempt "
                    "WHERE run_id = ? AND stage_name = ?",
                    (str(run_id), stage_name.value),
                ).fetchone()[0]
            )
            connection.execute(
                "INSERT INTO controlled_operation_attempt "
                "(run_id, stage_name, attempt_number, claim_id, claim_epoch, "
                "stage_version, started_at, lease_expires_at, heartbeat_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'STARTED')",
                (
                    str(run_id),
                    stage_name.value,
                    attempt_number,
                    claim_id,
                    claim_epoch,
                    stage_version,
                    self._format_time(now),
                    self._format_time(expires),
                    self._format_time(now),
                ),
            )
            connection.execute(
                "UPDATE controlled_operation_run SET current_stage = ?, version = version + 1, "
                "updated_at = ? WHERE run_id = ?",
                (stage_name.value, self._format_time(now), str(run_id)),
            )
            self._event(
                connection,
                run_id=run_id,
                stage_name=stage_name,
                event_type="STAGE_CLAIMED",
                payload={
                    "attempt_number": attempt_number,
                    "claim_id": claim_id,
                    "claim_epoch": claim_epoch,
                    "stage_version": stage_version,
                    "lease_expires_at": self._format_time(expires),
                },
            )
            return ClaimedDecisionTimeOperationStage(
                run_id=run_id,
                stage_name=stage_name,
                claim_id=claim_id,
                claim_epoch=claim_epoch,
                stage_version=stage_version,
                attempt_number=attempt_number,
                lease_acquired_at=now,
                lease_expires_at=expires,
                heartbeat_at=now,
            )

    def heartbeat(
        self, claim: ClaimedDecisionTimeOperationStage
    ) -> ClaimedDecisionTimeOperationStage:
        now = self._now()
        expires = now + self._lease_duration
        with self._immediate() as connection:
            cursor = connection.execute(
                "UPDATE controlled_operation_stage SET heartbeat_at = ?, lease_expires_at = ? "
                "WHERE run_id = ? AND stage_name = ? AND status = 'IN_PROGRESS' "
                "AND claim_id = ? AND claim_epoch = ? AND version = ? "
                "AND lease_expires_at > ?",
                (
                    self._format_time(now),
                    self._format_time(expires),
                    str(claim.run_id),
                    claim.stage_name.value,
                    claim.claim_id,
                    claim.claim_epoch,
                    claim.stage_version,
                    self._format_time(now),
                ),
            )
            if cursor.rowcount != 1:
                raise ControlledOperationClaimRejected("heartbeat fencing rejected")
            connection.execute(
                "UPDATE controlled_operation_attempt SET heartbeat_at = ?, lease_expires_at = ? "
                "WHERE run_id = ? AND stage_name = ? AND attempt_number = ? "
                "AND claim_id = ? AND claim_epoch = ? AND stage_version = ? "
                "AND status = 'STARTED'",
                (
                    self._format_time(now),
                    self._format_time(expires),
                    str(claim.run_id),
                    claim.stage_name.value,
                    claim.attempt_number,
                    claim.claim_id,
                    claim.claim_epoch,
                    claim.stage_version,
                ),
            )
            self._event(
                connection,
                run_id=claim.run_id,
                stage_name=claim.stage_name,
                event_type="STAGE_HEARTBEAT",
                payload={"claim_epoch": claim.claim_epoch, "lease_expires_at": self._format_time(expires)},
            )
        return ClaimedDecisionTimeOperationStage(
            run_id=claim.run_id,
            stage_name=claim.stage_name,
            claim_id=claim.claim_id,
            claim_epoch=claim.claim_epoch,
            stage_version=claim.stage_version,
            attempt_number=claim.attempt_number,
            lease_acquired_at=claim.lease_acquired_at,
            lease_expires_at=expires,
            heartbeat_at=now,
        )

    def complete_stage(
        self,
        *,
        claim: ClaimedDecisionTimeOperationStage,
        receipt: DecisionTimeOperationReceipt,
        run_status: DecisionTimeOperationRunStatus,
    ) -> DecisionTimeOperationRunSnapshot:
        receipt.verify_identity()
        if (
            receipt.run_id != claim.run_id
            or receipt.stage_name is not claim.stage_name
            or receipt.attempt_number != claim.attempt_number
        ):
            raise ControlledOperationConflict("Receipt does not match claimed stage")
        if run_status in {
            DecisionTimeOperationRunStatus.CREATED,
            DecisionTimeOperationRunStatus.FAILED,
        }:
            raise ValueError("completed stage requires a forward run status")
        if (
            run_status is DecisionTimeOperationRunStatus.SETTLED
            and claim.stage_name is not DecisionTimeOperationStageName.OUTCOME_SETTLEMENT
        ):
            raise ValueError("only Outcome Settlement can settle an operation")
        if (
            claim.stage_name is DecisionTimeOperationStageName.OUTCOME_SETTLEMENT
            and run_status is not DecisionTimeOperationRunStatus.SETTLED
        ):
            raise ValueError("Outcome Settlement must settle the operation")
        now = self._now()
        with self._immediate() as connection:
            self._require_active_claim(connection, claim, now=now)
            connection.execute(
                "INSERT INTO controlled_operation_receipt "
                "(receipt_id, receipt_hash, run_id, stage_name, attempt_number, "
                "receipt_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(receipt.receipt_id),
                    receipt.content_hash,
                    str(claim.run_id),
                    claim.stage_name.value,
                    claim.attempt_number,
                    canonical_json(receipt.to_canonical_dict()),
                    self._format_time(receipt.created_at),
                ),
            )
            self._inject("AFTER_RECEIPT_INSERT")
            connection.executemany(
                "INSERT INTO controlled_operation_child_run "
                "(run_id, stage_name, reference_kind, child_run_id, child_receipt_hash, receipt_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    (
                        str(claim.run_id),
                        claim.stage_name.value,
                        item.reference_kind.value,
                        item.child_run_id,
                        item.child_receipt_hash,
                        str(receipt.receipt_id),
                    )
                    for item in receipt.child_run_references
                ),
            )
            self._inject("AFTER_CHILD_REFERENCES")
            attempt = connection.execute(
                "UPDATE controlled_operation_attempt SET status = 'COMPLETED', "
                "completed_at = ?, error_message = NULL WHERE run_id = ? AND stage_name = ? "
                "AND attempt_number = ? AND claim_id = ? AND claim_epoch = ? "
                "AND stage_version = ? AND status = 'STARTED'",
                (
                    self._format_time(now),
                    str(claim.run_id),
                    claim.stage_name.value,
                    claim.attempt_number,
                    claim.claim_id,
                    claim.claim_epoch,
                    claim.stage_version,
                ),
            )
            if attempt.rowcount != 1:
                raise ControlledOperationClaimRejected("attempt settlement fencing rejected")
            self._inject("AFTER_ATTEMPT_SETTLED")
            stage = connection.execute(
                "UPDATE controlled_operation_stage SET status = 'COMPLETED', "
                "version = version + 1, claim_id = NULL, lease_acquired_at = NULL, "
                "lease_expires_at = NULL, heartbeat_at = NULL, receipt_id = ?, "
                "receipt_hash = ?, last_error = NULL WHERE run_id = ? AND stage_name = ? "
                "AND status = 'IN_PROGRESS' AND claim_id = ? AND claim_epoch = ? "
                "AND version = ?",
                (
                    str(receipt.receipt_id),
                    receipt.content_hash,
                    str(claim.run_id),
                    claim.stage_name.value,
                    claim.claim_id,
                    claim.claim_epoch,
                    claim.stage_version,
                ),
            )
            if stage.rowcount != 1:
                raise ControlledOperationClaimRejected("stage settlement fencing rejected")
            self._inject("AFTER_STAGE_SETTLED")
            next_stage = self._next_incomplete_stage(connection, claim.run_id)
            connection.execute(
                "UPDATE controlled_operation_run SET status = ?, current_stage = ?, "
                "version = version + 1, updated_at = ?, settled_at = ? WHERE run_id = ?",
                (
                    run_status.value,
                    next_stage.value if next_stage is not None else None,
                    self._format_time(now),
                    self._format_time(now)
                    if run_status is DecisionTimeOperationRunStatus.SETTLED
                    else None,
                    str(claim.run_id),
                ),
            )
            self._event(
                connection,
                run_id=claim.run_id,
                stage_name=claim.stage_name,
                event_type="RECEIPT_RECORDED",
                payload={"receipt_id": str(receipt.receipt_id), "receipt_hash": receipt.content_hash},
            )
            self._event(
                connection,
                run_id=claim.run_id,
                stage_name=claim.stage_name,
                event_type="STAGE_COMPLETED",
                payload={"claim_epoch": claim.claim_epoch, "run_status": run_status.value},
            )
        return self.get(claim.run_id)

    def fail_stage(
        self,
        *,
        claim: ClaimedDecisionTimeOperationStage,
        error: str,
        run_status: DecisionTimeOperationRunStatus = DecisionTimeOperationRunStatus.FAILED,
    ) -> DecisionTimeOperationRunSnapshot:
        if run_status not in {
            DecisionTimeOperationRunStatus.FAILED,
            DecisionTimeOperationRunStatus.DATA_BLOCKED,
            DecisionTimeOperationRunStatus.DEADLINE_MISSED,
        }:
            raise ValueError("failed stage requires a failed or blocked run status")
        message = error.strip()[:512]
        if not message:
            raise ValueError("stage failure error is required")
        now = self._now()
        with self._immediate() as connection:
            self._require_active_claim(connection, claim, now=now)
            attempt = connection.execute(
                "UPDATE controlled_operation_attempt SET status = 'FAILED', completed_at = ?, "
                "error_message = ? WHERE run_id = ? AND stage_name = ? AND attempt_number = ? "
                "AND claim_id = ? AND claim_epoch = ? AND stage_version = ? AND status = 'STARTED'",
                (
                    self._format_time(now), message, str(claim.run_id), claim.stage_name.value,
                    claim.attempt_number, claim.claim_id, claim.claim_epoch, claim.stage_version,
                ),
            )
            if attempt.rowcount != 1:
                raise ControlledOperationClaimRejected("attempt failure fencing rejected")
            stage = connection.execute(
                "UPDATE controlled_operation_stage SET status = 'FAILED', version = version + 1, "
                "claim_id = NULL, lease_acquired_at = NULL, lease_expires_at = NULL, "
                "heartbeat_at = NULL, last_error = ? WHERE run_id = ? AND stage_name = ? "
                "AND status = 'IN_PROGRESS' AND claim_id = ? AND claim_epoch = ? AND version = ?",
                (
                    message, str(claim.run_id), claim.stage_name.value, claim.claim_id,
                    claim.claim_epoch, claim.stage_version,
                ),
            )
            if stage.rowcount != 1:
                raise ControlledOperationClaimRejected("stage failure fencing rejected")
            connection.execute(
                "UPDATE controlled_operation_run SET status = ?, current_stage = ?, "
                "version = version + 1, updated_at = ? WHERE run_id = ?",
                (run_status.value, claim.stage_name.value, self._format_time(now), str(claim.run_id)),
            )
            self._event(
                connection,
                run_id=claim.run_id,
                stage_name=claim.stage_name,
                event_type="STAGE_FAILED",
                payload={"error": message, "claim_epoch": claim.claim_epoch},
            )
        return self.get(claim.run_id)

    def set_run_status(
        self,
        *,
        run_id: ArtifactId,
        expected_version: int,
        status: DecisionTimeOperationRunStatus,
        reason: str,
    ) -> DecisionTimeOperationRunSnapshot:
        if status is DecisionTimeOperationRunStatus.SETTLED:
            raise ValueError("SETTLED is only assigned by Outcome Settlement")
        message = reason.strip()
        if not message:
            raise ValueError("run status reason is required")
        with self._immediate() as connection:
            self._require_run(connection, run_id)
            cursor = connection.execute(
                "UPDATE controlled_operation_run SET status = ?, version = version + 1, "
                "updated_at = ? WHERE run_id = ? AND version = ? AND status != 'SETTLED'",
                (status.value, self._now_text(), str(run_id), expected_version),
            )
            if cursor.rowcount != 1:
                raise ControlledOperationConflict("Controlled operation run CAS rejected")
            self._event(
                connection,
                run_id=run_id,
                event_type="RUN_STATUS_CHANGED",
                payload={"status": status.value, "reason": message},
            )
        return self.get(run_id)

    def get(self, run_id: ArtifactId) -> DecisionTimeOperationRunSnapshot:
        with self._connect() as connection:
            run = self._require_run(connection, run_id)
            command = ControlledOperationCommand.from_canonical_dict(
                _json_object(str(run["command_json"]))
            )
            receipt_rows = {
                str(item["stage_name"]): item
                for item in connection.execute(
                    "SELECT stage_name, receipt_json FROM controlled_operation_receipt "
                    "WHERE run_id = ?",
                    (str(run_id),),
                )
            }
            stage_rows = {
                DecisionTimeOperationStageName(str(item["stage_name"])): item
                for item in connection.execute(
                    "SELECT stage_name, status, version, claim_epoch, last_error "
                    "FROM controlled_operation_stage WHERE run_id = ?",
                    (str(run_id),),
                )
            }
            stages = tuple(
                DecisionTimeOperationStageSnapshot(
                    stage_name=stage_name,
                    status=DecisionTimeOperationStageStatus(str(item["status"])),
                    version=int(item["version"]),
                    claim_epoch=int(item["claim_epoch"]),
                    receipt=(
                        DecisionTimeOperationReceipt.from_canonical_dict(
                            _json_object(str(receipt_rows[str(item["stage_name"])]["receipt_json"]))
                        )
                        if str(item["stage_name"]) in receipt_rows
                        else None
                    ),
                    last_error=(str(item["last_error"]) if item["last_error"] is not None else None),
                )
                for stage_name in CONTROLLED_OPERATION_STAGE_ORDER
                for item in (stage_rows[stage_name],)
            )
            children = tuple(
                OperationChildRunReference(
                    reference_kind=_child_kind(str(item["reference_kind"])),
                    child_run_id=str(item["child_run_id"]),
                    child_receipt_hash=str(item["child_receipt_hash"]),
                )
                for item in connection.execute(
                    "SELECT reference_kind, child_run_id, child_receipt_hash "
                    "FROM controlled_operation_child_run WHERE run_id = ? "
                    "ORDER BY reference_kind, child_run_id",
                    (str(run_id),),
                )
            )
            events = tuple(
                (
                    int(item["event_id"]),
                    str(item["event_type"]),
                    str(item["stage_name"]) if item["stage_name"] is not None else None,
                    str(item["payload_json"]),
                )
                for item in connection.execute(
                    "SELECT event_id, event_type, stage_name, payload_json "
                    "FROM controlled_operation_event WHERE run_id = ? ORDER BY event_id",
                    (str(run_id),),
                )
            )
        return DecisionTimeOperationRunSnapshot(
            command=command,
            status=DecisionTimeOperationRunStatus(str(run["status"])),
            current_stage=(
                DecisionTimeOperationStageName(str(run["current_stage"]))
                if run["current_stage"] is not None
                else None
            ),
            version=int(run["version"]),
            stages=stages,
            child_run_references=children,
            events=events,
        )

    def _recover_expired(self, connection: sqlite3.Connection, *, run_id: ArtifactId) -> None:
        now = self._now()
        rows = tuple(
            connection.execute(
                "SELECT stage_name, version, claim_id, claim_epoch FROM "
                "controlled_operation_stage WHERE run_id = ? AND status = 'IN_PROGRESS' "
                "AND lease_expires_at <= ?",
                (str(run_id), self._format_time(now)),
            )
        )
        for row in rows:
            stage_name = DecisionTimeOperationStageName(str(row["stage_name"]))
            attempt = connection.execute(
                "UPDATE controlled_operation_attempt SET status = 'LEASE_EXPIRED', "
                "completed_at = ?, error_message = 'LEASE_EXPIRED' WHERE run_id = ? "
                "AND stage_name = ? AND claim_id = ? AND claim_epoch = ? "
                "AND stage_version = ? AND status = 'STARTED'",
                (
                    self._format_time(now), str(run_id), stage_name.value,
                    str(row["claim_id"]), int(row["claim_epoch"]), int(row["version"]),
                ),
            )
            if attempt.rowcount != 1:
                raise ControlledOperationConflict("expired Attempt recovery CAS rejected")
            stage = connection.execute(
                "UPDATE controlled_operation_stage SET status = 'FAILED', version = version + 1, "
                "claim_id = NULL, lease_acquired_at = NULL, lease_expires_at = NULL, "
                "heartbeat_at = NULL, last_error = 'LEASE_EXPIRED' WHERE run_id = ? "
                "AND stage_name = ? AND status = 'IN_PROGRESS' AND claim_id = ? "
                "AND claim_epoch = ? AND version = ?",
                (
                    str(run_id), stage_name.value, str(row["claim_id"]),
                    int(row["claim_epoch"]), int(row["version"]),
                ),
            )
            if stage.rowcount != 1:
                raise ControlledOperationConflict("expired Stage recovery CAS rejected")
            connection.execute(
                "UPDATE controlled_operation_run SET status = 'FAILED', current_stage = ?, "
                "version = version + 1, updated_at = ? WHERE run_id = ?",
                (stage_name.value, self._format_time(now), str(run_id)),
            )
            self._event(
                connection,
                run_id=run_id,
                stage_name=stage_name,
                event_type="LEASE_EXPIRED",
                payload={"claim_epoch": int(row["claim_epoch"]), "expired_at": self._format_time(now)},
            )

    def _require_prior_stages(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: ArtifactId,
        stage_name: DecisionTimeOperationStageName,
    ) -> None:
        preceding = CONTROLLED_OPERATION_STAGE_ORDER[: CONTROLLED_OPERATION_STAGE_ORDER.index(stage_name)]
        if not preceding:
            return
        statuses = {
            DecisionTimeOperationStageName(str(item["stage_name"])): str(item["status"])
            for item in connection.execute(
                "SELECT stage_name, status FROM controlled_operation_stage WHERE run_id = ?",
                (str(run_id),),
            )
        }
        incomplete = tuple(
            stage.value
            for stage in preceding
            if statuses.get(stage) != DecisionTimeOperationStageStatus.COMPLETED.value
        )
        if incomplete:
            raise ControlledOperationClaimRejected(
                f"prior Controlled operation stages are incomplete: {','.join(incomplete)}"
            )

    def _require_active_claim(
        self,
        connection: sqlite3.Connection,
        claim: ClaimedDecisionTimeOperationStage,
        *,
        now: datetime,
    ) -> None:
        row = connection.execute(
            "SELECT 1 FROM controlled_operation_stage WHERE run_id = ? AND stage_name = ? "
            "AND status = 'IN_PROGRESS' AND claim_id = ? AND claim_epoch = ? AND version = ? "
            "AND lease_expires_at > ?",
            (
                str(claim.run_id), claim.stage_name.value, claim.claim_id,
                claim.claim_epoch, claim.stage_version, self._format_time(now),
            ),
        ).fetchone()
        if row is None:
            raise ControlledOperationClaimRejected("active claim fencing rejected")

    def _next_incomplete_stage(
        self, connection: sqlite3.Connection, run_id: ArtifactId
    ) -> DecisionTimeOperationStageName | None:
        statuses = {
            DecisionTimeOperationStageName(str(item["stage_name"])): str(item["status"])
            for item in connection.execute(
                "SELECT stage_name, status FROM controlled_operation_stage WHERE run_id = ?",
                (str(run_id),),
            )
        }
        return next(
            (
                stage
                for stage in CONTROLLED_OPERATION_STAGE_ORDER
                if statuses[stage] != DecisionTimeOperationStageStatus.COMPLETED.value
            ),
            None,
        )

    def _require_run(self, connection: sqlite3.Connection, run_id: ArtifactId) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM controlled_operation_run WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"Controlled operation run not found: {run_id}")
        return row

    def _event(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: ArtifactId,
        event_type: str,
        payload: Mapping[str, Any],
        stage_name: DecisionTimeOperationStageName | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO controlled_operation_event "
            "(run_id, stage_name, event_type, event_time, payload_json) VALUES (?, ?, ?, ?, ?)",
            (
                str(run_id), stage_name.value if stage_name is not None else None,
                event_type, self._now_text(), canonical_json(payload),
            ),
        )

    def _inject(self, point: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(point)

    @contextmanager
    def _immediate(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock must return datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return an aware datetime")
        return value.astimezone(timezone.utc).replace(microsecond=0)

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()

    def _now_text(self) -> str:
        return self._format_time(self._now())


def _json_object(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("stored Controlled operation JSON must be an object")
    return payload


def _child_kind(value: str) -> ChildRunReferenceKind:
    return ChildRunReferenceKind(value)


__all__ = [
    "CONTROLLED_OPERATION_MIGRATION",
    "DEFAULT_CONTROLLED_OPERATION_LEASE",
    "ControlledOperationClaimRejected",
    "ControlledOperationConflict",
    "SQLiteDecisionTimeOperationJournal",
]
