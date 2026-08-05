"""Durable SQLite authority for recoverable Feature Materialization runs."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any, Callable, Iterator, Mapping
from uuid import uuid4

from market_regime_alpha.evidence.canonical import (
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.features.v2_contracts import FeatureMaterializationReceipt
from market_regime_alpha.market_data import Timeframe


FEATURE_MATERIALIZATION_RUN_SCHEMA = "feature-materialization-run-sqlite-v2"
FEATURE_MATERIALIZATION_RUN_MIGRATION = (
    Path(__file__).resolve().parent
    / "migrations"
    / "012_feature_materialization_run_up.sql"
)
FEATURE_MATERIALIZATION_RUN_HARDENING_MIGRATION = (
    Path(__file__).resolve().parent
    / "migrations"
    / "013_feature_materialization_run_hardening_up.sql"
)
DEFAULT_FEATURE_TASK_LEASE = timedelta(minutes=5)
Clock = Callable[[], datetime]
_SCHEMA_LOCK = Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FeatureMaterializationExecutionMode(str, Enum):
    START_NEW = "START_NEW"
    RESUME_EXISTING = "RESUME_EXISTING"
    RETURN_IF_COMPLETE = "RETURN_IF_COMPLETE"


class FeatureMaterializationRunStatus(str, Enum):
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    COMPLETE = "COMPLETE"


class FeatureMaterializationTaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True, slots=True)
class FeatureMaterializationTaskSpec:
    symbol: str
    feature_id: str
    timeframe: Timeframe

    @property
    def task_key(self) -> str:
        return f"{self.symbol}|{self.feature_id}|{self.timeframe.value}"


@dataclass(frozen=True, slots=True)
class ClaimedFeatureMaterializationTask:
    run_id: int
    task_key: str
    symbol: str
    feature_id: str
    timeframe: Timeframe
    claim_token: str
    claim_epoch: int
    task_version: int
    attempt_number: int
    lease_acquired_at: datetime
    lease_expires_at: datetime
    heartbeat_at: datetime


@dataclass(frozen=True, slots=True)
class FeatureMaterializationRunSnapshot:
    run_id: int
    idempotency_key: str
    command_hash: str
    status: FeatureMaterializationRunStatus
    version: int
    tasks: tuple[
        tuple[str, FeatureMaterializationTaskStatus, str | None, str | None], ...
    ]
    receipt: FeatureMaterializationReceipt | None
    events: tuple[tuple[int, str, str | None, str], ...]


class SQLiteFeatureMaterializationRunRepository:
    """Run/task authority with leases and token/epoch/version fencing."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Clock = _utc_now,
        lease_duration: timedelta = DEFAULT_FEATURE_TASK_LEASE,
    ) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not isinstance(lease_duration, timedelta) or lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self._path = path
        self._clock = clock
        self._lease_duration = lease_duration
        path.parent.mkdir(parents=True, exist_ok=True)
        with _SCHEMA_LOCK, self._connect() as connection:
            connection.executescript(
                FEATURE_MATERIALIZATION_RUN_MIGRATION.read_text(encoding="utf-8")
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS feature_materialization_schema_migration "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = connection.execute(
                "SELECT 1 FROM feature_materialization_schema_migration WHERE version = 13"
            ).fetchone()
            if applied is None:
                connection.executescript(
                    FEATURE_MATERIALIZATION_RUN_HARDENING_MIGRATION.read_text(
                        encoding="utf-8"
                    )
                )

    def prepare(
        self,
        *,
        idempotency_key: str,
        command_hash: str,
        tasks: tuple[FeatureMaterializationTaskSpec, ...],
        mode: FeatureMaterializationExecutionMode,
    ) -> FeatureMaterializationRunSnapshot:
        require_text("idempotency_key", idempotency_key)
        require_sha256("command_hash", command_hash)
        task_keys = tuple(sorted(item.task_key for item in tasks))
        if not tasks or task_keys != tuple(sorted(set(task_keys))):
            raise ValueError("materialization tasks must be non-empty and unique")
        with self._immediate() as connection:
            row = connection.execute(
                "SELECT run_id, command_hash, status FROM feature_materialization_run "
                "WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                if mode is not FeatureMaterializationExecutionMode.START_NEW:
                    raise ValueError("Feature materialization run does not exist")
                now = self._now_text()
                cursor = connection.execute(
                    "INSERT INTO feature_materialization_run "
                    "(schema_version, idempotency_key, command_hash, status, version, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
                    (
                        FEATURE_MATERIALIZATION_RUN_SCHEMA,
                        idempotency_key,
                        command_hash,
                        FeatureMaterializationRunStatus.RUNNING.value,
                        now,
                        now,
                    ),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError(
                        "Feature materialization run insert returned no identity"
                    )
                run_id = int(cursor.lastrowid)
                connection.executemany(
                    "INSERT INTO feature_materialization_task "
                    "(run_id, task_key, symbol, feature_id, timeframe, status, "
                    "version, claim_epoch) VALUES (?, ?, ?, ?, ?, ?, 1, 0)",
                    (
                        (
                            run_id,
                            item.task_key,
                            item.symbol,
                            item.feature_id,
                            item.timeframe.value,
                            FeatureMaterializationTaskStatus.PENDING.value,
                        )
                        for item in tasks
                    ),
                )
                self._event(
                    connection,
                    run_id=run_id,
                    event_type="RUN_CREATED",
                    payload={"task_count": len(tasks), "mode": mode.value},
                )
            else:
                run_id = int(row["run_id"])
                if str(row["command_hash"]) != command_hash:
                    raise ValueError("idempotency key semantic conflict")
                if mode is FeatureMaterializationExecutionMode.START_NEW:
                    raise ValueError("Feature materialization run already exists")
                stored_keys = tuple(
                    str(item["task_key"])
                    for item in connection.execute(
                        "SELECT task_key FROM feature_materialization_task "
                        "WHERE run_id = ? ORDER BY task_key",
                        (run_id,),
                    )
                )
                if stored_keys != task_keys:
                    raise ValueError("Feature materialization task scope conflict")
                status = FeatureMaterializationRunStatus(str(row["status"]))
                if mode is FeatureMaterializationExecutionMode.RETURN_IF_COMPLETE:
                    if status is not FeatureMaterializationRunStatus.COMPLETE:
                        raise ValueError("Feature materialization run is not complete")
                elif status is FeatureMaterializationRunStatus.COMPLETE:
                    raise ValueError("completed run cannot be resumed")
                else:
                    self._recover_expired(connection, run_id=run_id)
                    connection.execute(
                        "UPDATE feature_materialization_run SET status = ?, "
                        "version = version + 1, updated_at = ? WHERE run_id = ?",
                        (
                            FeatureMaterializationRunStatus.RUNNING.value,
                            self._now_text(),
                            run_id,
                        ),
                    )
                    self._event(
                        connection,
                        run_id=run_id,
                        event_type="RUN_RESUMED",
                        payload={"mode": mode.value},
                    )
        return self.snapshot(run_id)

    def claim_next(
        self,
        *,
        run_id: int,
        stale_after: timedelta | None = None,
    ) -> ClaimedFeatureMaterializationTask | None:
        claims = self.claim_batch(run_id=run_id, limit=1, stale_after=stale_after)
        return claims[0] if claims else None

    def claim_batch(
        self,
        *,
        run_id: int,
        limit: int,
        stale_after: timedelta | None = None,
    ) -> tuple[ClaimedFeatureMaterializationTask, ...]:
        if isinstance(limit, bool) or not 1 <= limit <= 256:
            raise ValueError("claim batch limit must be between one and 256")
        if stale_after is not None and stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive")
        with self._immediate() as connection:
            self._recover_expired(
                connection,
                run_id=run_id,
                stale_after=stale_after,
            )
            rows = tuple(
                connection.execute(
                    "SELECT task_key, symbol, feature_id, timeframe, version, "
                    "claim_epoch FROM feature_materialization_task "
                    "WHERE run_id = ? AND status IN (?, ?) "
                    "ORDER BY task_key LIMIT ?",
                    (
                        run_id,
                        FeatureMaterializationTaskStatus.PENDING.value,
                        FeatureMaterializationTaskStatus.FAILED.value,
                        limit,
                    ),
                )
            )
            claims: list[ClaimedFeatureMaterializationTask] = []
            for row in rows:
                claims.append(self._claim_row(connection, run_id=run_id, row=row))
            return tuple(claims)

    def heartbeat(
        self, claim: ClaimedFeatureMaterializationTask
    ) -> ClaimedFeatureMaterializationTask:
        now = self._now()
        expires = now + self._lease_duration
        with self._immediate() as connection:
            cursor = connection.execute(
                "UPDATE feature_materialization_task SET version = version + 1, "
                "heartbeat_at = ?, lease_expires_at = ? WHERE run_id = ? "
                "AND task_key = ? AND status = ? AND claim_token = ? "
                "AND claim_epoch = ? AND version = ? AND lease_expires_at > ?",
                (
                    self._format_time(now),
                    self._format_time(expires),
                    claim.run_id,
                    claim.task_key,
                    FeatureMaterializationTaskStatus.IN_PROGRESS.value,
                    claim.claim_token,
                    claim.claim_epoch,
                    claim.task_version,
                    self._format_time(now),
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("stale Feature materialization task writer rejected")
            next_version = claim.task_version + 1
            attempt = connection.execute(
                "UPDATE feature_materialization_attempt SET task_version = ?, "
                "heartbeat_at = ?, lease_expires_at = ? WHERE run_id = ? "
                "AND task_key = ? AND attempt_number = ? AND claim_token = ? "
                "AND claim_epoch = ? AND status = 'STARTED'",
                (
                    next_version,
                    self._format_time(now),
                    self._format_time(expires),
                    claim.run_id,
                    claim.task_key,
                    claim.attempt_number,
                    claim.claim_token,
                    claim.claim_epoch,
                ),
            )
            if attempt.rowcount != 1:
                raise ValueError("Feature materialization attempt CAS failed")
            self._event(
                connection,
                run_id=claim.run_id,
                task_key=claim.task_key,
                event_type="TASK_HEARTBEAT",
                payload={
                    "claim_epoch": claim.claim_epoch,
                    "task_version": next_version,
                    "lease_expires_at": self._format_time(expires),
                },
            )
        return replace(
            claim,
            task_version=next_version,
            heartbeat_at=now,
            lease_expires_at=expires,
        )

    def complete_task(
        self,
        claim: ClaimedFeatureMaterializationTask,
        *,
        artifact_id: str,
        artifact_hash: str,
        publication_reused: bool = False,
    ) -> None:
        require_text("artifact_id", artifact_id)
        require_sha256("artifact_hash", artifact_hash)
        with self._immediate() as connection:
            cursor = connection.execute(
                "UPDATE feature_materialization_task SET status = ?, "
                "version = version + 1, claim_token = NULL, claimed_at = NULL, "
                "lease_acquired_at = NULL, lease_expires_at = NULL, heartbeat_at = NULL, "
                "artifact_id = ?, artifact_hash = ? WHERE run_id = ? AND task_key = ? "
                "AND status = ? AND claim_token = ? AND claim_epoch = ? AND version = ?",
                (
                    FeatureMaterializationTaskStatus.COMPLETE.value,
                    artifact_id,
                    artifact_hash,
                    claim.run_id,
                    claim.task_key,
                    FeatureMaterializationTaskStatus.IN_PROGRESS.value,
                    claim.claim_token,
                    claim.claim_epoch,
                    claim.task_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("stale Feature materialization task writer rejected")
            self._complete_attempt(
                connection,
                claim=claim,
                status="COMPLETE",
                error=None,
            )
            self._event(
                connection,
                run_id=claim.run_id,
                task_key=claim.task_key,
                event_type="TASK_COMPLETED",
                payload={
                    "artifact_id": artifact_id,
                    "artifact_hash": artifact_hash,
                    "claim_epoch": claim.claim_epoch,
                    "task_version": claim.task_version,
                    "publication_reused": publication_reused,
                },
            )

    def fail_task(
        self,
        claim: ClaimedFeatureMaterializationTask,
        *,
        error_message: str,
    ) -> None:
        require_text("error_message", error_message)
        with self._immediate() as connection:
            cursor = connection.execute(
                "UPDATE feature_materialization_task SET status = ?, "
                "version = version + 1, claim_token = NULL, claimed_at = NULL, "
                "lease_acquired_at = NULL, lease_expires_at = NULL, heartbeat_at = NULL, "
                "last_error = ? WHERE run_id = ? AND task_key = ? AND status = ? "
                "AND claim_token = ? AND claim_epoch = ? AND version = ?",
                (
                    FeatureMaterializationTaskStatus.FAILED.value,
                    error_message,
                    claim.run_id,
                    claim.task_key,
                    FeatureMaterializationTaskStatus.IN_PROGRESS.value,
                    claim.claim_token,
                    claim.claim_epoch,
                    claim.task_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("stale Feature materialization task writer rejected")
            self._complete_attempt(
                connection,
                claim=claim,
                status="FAILED",
                error=error_message,
            )
            connection.execute(
                "UPDATE feature_materialization_run SET status = ?, "
                "version = version + 1, updated_at = ? WHERE run_id = ?",
                (
                    FeatureMaterializationRunStatus.FAILED.value,
                    self._now_text(),
                    claim.run_id,
                ),
            )
            self._event(
                connection,
                run_id=claim.run_id,
                task_key=claim.task_key,
                event_type="TASK_FAILED",
                payload={
                    "error_message": error_message,
                    "claim_epoch": claim.claim_epoch,
                    "task_version": claim.task_version,
                },
            )

    def finalize(
        self,
        *,
        run_id: int,
        receipt: FeatureMaterializationReceipt,
    ) -> None:
        receipt.verify_identity()
        with self._immediate() as connection:
            incomplete = int(
                connection.execute(
                    "SELECT COUNT(*) FROM feature_materialization_task "
                    "WHERE run_id = ? AND status != ?",
                    (run_id, FeatureMaterializationTaskStatus.COMPLETE.value),
                ).fetchone()[0]
            )
            if incomplete:
                raise ValueError("Feature materialization run has incomplete tasks")
            existing = connection.execute(
                "SELECT receipt_hash FROM feature_materialization_receipt WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["receipt_hash"]) != receipt.content_hash:
                    raise ValueError(
                        "completed Feature materialization receipt is immutable"
                    )
                return
            connection.execute(
                "INSERT INTO feature_materialization_receipt "
                "(run_id, receipt_id, receipt_hash, receipt_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    str(receipt.receipt_id),
                    receipt.content_hash,
                    canonical_json(receipt.to_canonical_dict()),
                    self._now_text(),
                ),
            )
            connection.execute(
                "UPDATE feature_materialization_run SET status = ?, "
                "version = version + 1, updated_at = ? WHERE run_id = ?",
                (
                    FeatureMaterializationRunStatus.COMPLETE.value,
                    self._now_text(),
                    run_id,
                ),
            )
            self._event(
                connection,
                run_id=run_id,
                event_type="RUN_COMPLETED",
                payload={
                    "receipt_id": str(receipt.receipt_id),
                    "receipt_hash": receipt.content_hash,
                },
            )

    def completed_artifacts(self, run_id: int) -> tuple[tuple[str, str], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT artifact_id, artifact_hash FROM feature_materialization_task "
                "WHERE run_id = ? AND status = ? ORDER BY task_key",
                (run_id, FeatureMaterializationTaskStatus.COMPLETE.value),
            )
            return tuple((str(row[0]), str(row[1])) for row in rows)

    def record_bundle_published(
        self,
        *,
        run_id: int,
        bundle_id: str,
        bundle_hash: str,
    ) -> None:
        require_text("bundle_id", bundle_id)
        require_sha256("bundle_hash", bundle_hash)
        with self._immediate() as connection:
            run = connection.execute(
                "SELECT status FROM feature_materialization_run WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None or str(run["status"]) == FeatureMaterializationRunStatus.COMPLETE.value:
                raise ValueError("Feature materialization run rejects Bundle publication event")
            self._event(
                connection,
                run_id=run_id,
                event_type="BUNDLE_PUBLISHED",
                payload={"bundle_id": bundle_id, "bundle_hash": bundle_hash},
            )

    def snapshot(self, run_id: int) -> FeatureMaterializationRunSnapshot:
        """Read run, tasks, receipt, and events in one SQLite snapshot."""

        with self._connect() as connection:
            connection.execute("BEGIN")
            run = connection.execute(
                "SELECT * FROM feature_materialization_run WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise ValueError("Feature materialization run does not exist")
            tasks = tuple(
                (
                    str(item["task_key"]),
                    FeatureMaterializationTaskStatus(str(item["status"])),
                    str(item["artifact_id"])
                    if item["artifact_id"] is not None
                    else None,
                    str(item["artifact_hash"])
                    if item["artifact_hash"] is not None
                    else None,
                )
                for item in connection.execute(
                    "SELECT task_key, status, artifact_id, artifact_hash FROM "
                    "feature_materialization_task WHERE run_id = ? ORDER BY task_key",
                    (run_id,),
                )
            )
            receipt_row = connection.execute(
                "SELECT receipt_json FROM feature_materialization_receipt WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            receipt = (
                FeatureMaterializationReceipt.from_canonical_dict(
                    _json_object(str(receipt_row["receipt_json"]))
                )
                if receipt_row is not None
                else None
            )
            events = tuple(
                (
                    int(item["event_id"]),
                    str(item["event_type"]),
                    str(item["task_key"])
                    if item["task_key"] is not None
                    else None,
                    str(item["payload_json"]),
                )
                for item in connection.execute(
                    "SELECT event_id, event_type, task_key, payload_json FROM "
                    "feature_materialization_event WHERE run_id = ? ORDER BY event_id",
                    (run_id,),
                )
            )
            connection.rollback()
        return FeatureMaterializationRunSnapshot(
            run_id=run_id,
            idempotency_key=str(run["idempotency_key"]),
            command_hash=str(run["command_hash"]),
            status=FeatureMaterializationRunStatus(str(run["status"])),
            version=int(run["version"]),
            tasks=tasks,
            receipt=receipt,
            events=events,
        )

    def _claim_row(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: int,
        row: sqlite3.Row,
    ) -> ClaimedFeatureMaterializationTask:
        now = self._now()
        expires = now + self._lease_duration
        token = uuid4().hex
        task_key = str(row["task_key"])
        claim_epoch = int(row["claim_epoch"]) + 1
        task_version = int(row["version"]) + 1
        cursor = connection.execute(
            "UPDATE feature_materialization_task SET status = ?, version = ?, "
            "claim_token = ?, claim_epoch = ?, claimed_at = ?, lease_acquired_at = ?, "
            "lease_expires_at = ?, heartbeat_at = ?, last_error = NULL "
            "WHERE run_id = ? AND task_key = ? AND version = ? AND status IN (?, ?)",
            (
                FeatureMaterializationTaskStatus.IN_PROGRESS.value,
                task_version,
                token,
                claim_epoch,
                self._format_time(now),
                self._format_time(now),
                self._format_time(expires),
                self._format_time(now),
                run_id,
                task_key,
                int(row["version"]),
                FeatureMaterializationTaskStatus.PENDING.value,
                FeatureMaterializationTaskStatus.FAILED.value,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Feature materialization task CAS claim failed")
        attempt_number = int(
            connection.execute(
                "SELECT COUNT(*) + 1 FROM feature_materialization_attempt "
                "WHERE run_id = ? AND task_key = ?",
                (run_id, task_key),
            ).fetchone()[0]
        )
        connection.execute(
            "INSERT INTO feature_materialization_attempt "
            "(run_id, task_key, attempt_number, claim_token, claim_epoch, task_version, "
            "started_at, lease_expires_at, heartbeat_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'STARTED')",
            (
                run_id,
                task_key,
                attempt_number,
                token,
                claim_epoch,
                task_version,
                self._format_time(now),
                self._format_time(expires),
                self._format_time(now),
            ),
        )
        self._event(
            connection,
            run_id=run_id,
            task_key=task_key,
            event_type="TASK_CLAIMED",
            payload={
                "attempt_number": attempt_number,
                "claim_token": token,
                "claim_epoch": claim_epoch,
                "task_version": task_version,
                "lease_expires_at": self._format_time(expires),
            },
        )
        return ClaimedFeatureMaterializationTask(
            run_id=run_id,
            task_key=task_key,
            symbol=str(row["symbol"]),
            feature_id=str(row["feature_id"]),
            timeframe=Timeframe(str(row["timeframe"])),
            claim_token=token,
            claim_epoch=claim_epoch,
            task_version=task_version,
            attempt_number=attempt_number,
            lease_acquired_at=now,
            lease_expires_at=expires,
            heartbeat_at=now,
        )

    def _recover_expired(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: int,
        stale_after: timedelta | None = None,
    ) -> None:
        now = self._now()
        if stale_after is None:
            predicate = "lease_expires_at <= ?"
            cutoff = self._format_time(now)
            event_type = "LEASE_EXPIRED"
        else:
            predicate = "claimed_at < ?"
            cutoff = self._format_time(now - stale_after)
            event_type = "STALE_CLAIM_RECOVERED"
        stale = tuple(
            connection.execute(
                "SELECT task_key, claim_token, claim_epoch, version FROM "
                "feature_materialization_task WHERE run_id = ? AND status = ? AND "
                + predicate,
                (
                    run_id,
                    FeatureMaterializationTaskStatus.IN_PROGRESS.value,
                    cutoff,
                ),
            )
        )
        for item in stale:
            token = str(item["claim_token"])
            epoch = int(item["claim_epoch"])
            version = int(item["version"])
            task_key = str(item["task_key"])
            attempt = connection.execute(
                "UPDATE feature_materialization_attempt SET status = 'LEASE_EXPIRED', "
                "completed_at = ?, error_message = 'LEASE_EXPIRED' WHERE run_id = ? "
                "AND task_key = ? AND claim_token = ? AND claim_epoch = ? "
                "AND task_version = ? AND status = 'STARTED'",
                (
                    self._format_time(now),
                    run_id,
                    task_key,
                    token,
                    epoch,
                    version,
                ),
            )
            if attempt.rowcount != 1:
                raise ValueError("Feature materialization attempt CAS failed")
            task = connection.execute(
                "UPDATE feature_materialization_task SET status = 'FAILED', "
                "version = version + 1, claim_token = NULL, claimed_at = NULL, "
                "lease_acquired_at = NULL, lease_expires_at = NULL, heartbeat_at = NULL, "
                "last_error = 'LEASE_EXPIRED' WHERE run_id = ? AND task_key = ? "
                "AND status = 'IN_PROGRESS' AND claim_token = ? AND claim_epoch = ? "
                "AND version = ?",
                (run_id, task_key, token, epoch, version),
            )
            if task.rowcount != 1:
                raise ValueError("stale Feature materialization task recovery rejected")
            self._event(
                connection,
                run_id=run_id,
                task_key=task_key,
                event_type=event_type,
                payload={
                    "claim_epoch": epoch,
                    "task_version": version,
                    "lease_expired_at": self._format_time(now),
                },
            )

    def _complete_attempt(
        self,
        connection: sqlite3.Connection,
        *,
        claim: ClaimedFeatureMaterializationTask,
        status: str,
        error: str | None,
    ) -> None:
        cursor = connection.execute(
            "UPDATE feature_materialization_attempt SET status = ?, completed_at = ?, "
            "error_message = ? WHERE run_id = ? AND task_key = ? AND attempt_number = ? "
            "AND claim_token = ? AND claim_epoch = ? AND task_version = ? "
            "AND status = 'STARTED'",
            (
                status,
                self._now_text(),
                error,
                claim.run_id,
                claim.task_key,
                claim.attempt_number,
                claim.claim_token,
                claim.claim_epoch,
                claim.task_version,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("Feature materialization attempt CAS failed")

    def _event(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: int,
        event_type: str,
        payload: Mapping[str, Any],
        task_key: str | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO feature_materialization_event "
            "(run_id, task_key, event_type, event_time, payload_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                task_key,
                event_type,
                self._now_text(),
                canonical_json(payload),
            ),
        )

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
        connection = sqlite3.connect(self._path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock must return datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return an aware datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    def _now_text(self) -> str:
        return self._format_time(self._now())


def _json_object(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("stored Feature materialization receipt is invalid")
    return payload


__all__ = [
    "ClaimedFeatureMaterializationTask",
    "DEFAULT_FEATURE_TASK_LEASE",
    "FeatureMaterializationExecutionMode",
    "FEATURE_MATERIALIZATION_RUN_HARDENING_MIGRATION",
    "FEATURE_MATERIALIZATION_RUN_MIGRATION",
    "FeatureMaterializationRunSnapshot",
    "FeatureMaterializationRunStatus",
    "FeatureMaterializationTaskSpec",
    "FeatureMaterializationTaskStatus",
    "SQLiteFeatureMaterializationRunRepository",
]
