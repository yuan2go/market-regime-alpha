"""Durable SQLite authority for recoverable Feature Materialization runs."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any, Iterator, Mapping
from uuid import uuid4

from market_regime_alpha.evidence.canonical import canonical_json, require_sha256, require_text
from market_regime_alpha.features.v2_contracts import FeatureMaterializationReceipt
from market_regime_alpha.market_data import Timeframe


FEATURE_MATERIALIZATION_RUN_SCHEMA = "feature-materialization-run-sqlite-v1"
FEATURE_MATERIALIZATION_RUN_MIGRATION = Path(__file__).resolve().parent / "migrations" / "012_feature_materialization_run_up.sql"
_SCHEMA_LOCK = Lock()


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
    attempt_number: int


@dataclass(frozen=True, slots=True)
class FeatureMaterializationRunSnapshot:
    run_id: int
    idempotency_key: str
    command_hash: str
    status: FeatureMaterializationRunStatus
    version: int
    tasks: tuple[tuple[str, FeatureMaterializationTaskStatus, str | None, str | None], ...]
    receipt: FeatureMaterializationReceipt | None
    events: tuple[tuple[int, str, str | None, str], ...]


class SQLiteFeatureMaterializationRunRepository:
    """Independent run/task/event authority using BEGIN IMMEDIATE and CAS tokens."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with _SCHEMA_LOCK, self._connect() as connection:
            connection.executescript(FEATURE_MATERIALIZATION_RUN_MIGRATION.read_text(encoding="utf-8"))

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
        if not tasks or tuple(sorted(item.task_key for item in tasks)) != tuple(sorted(set(item.task_key for item in tasks))):
            raise ValueError("materialization tasks must be non-empty and unique")
        with self._immediate() as connection:
            row = connection.execute(
                "SELECT run_id, command_hash, status FROM feature_materialization_run WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                if mode is not FeatureMaterializationExecutionMode.START_NEW:
                    raise ValueError("Feature materialization run does not exist")
                now = _now_text()
                cursor = connection.execute(
                    "INSERT INTO feature_materialization_run "
                    "(schema_version, idempotency_key, command_hash, status, version, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 1, ?, ?)",
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
                    raise RuntimeError("Feature materialization run insert returned no identity")
                run_id = int(cursor.lastrowid)
                connection.executemany(
                    "INSERT INTO feature_materialization_task "
                    "(run_id, task_key, symbol, feature_id, timeframe, status, version) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1)",
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
                        "SELECT task_key FROM feature_materialization_task WHERE run_id = ? ORDER BY task_key",
                        (run_id,),
                    )
                )
                if stored_keys != tuple(sorted(item.task_key for item in tasks)):
                    raise ValueError("Feature materialization task scope conflict")
                status = FeatureMaterializationRunStatus(str(row["status"]))
                if mode is FeatureMaterializationExecutionMode.RETURN_IF_COMPLETE:
                    if status is not FeatureMaterializationRunStatus.COMPLETE:
                        raise ValueError("Feature materialization run is not complete")
                elif status is FeatureMaterializationRunStatus.COMPLETE:
                    raise ValueError("completed run cannot be resumed")
                else:
                    connection.execute(
                        "UPDATE feature_materialization_run SET status = ?, version = version + 1, updated_at = ? WHERE run_id = ?",
                        (
                            FeatureMaterializationRunStatus.RUNNING.value,
                            _now_text(),
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
        with self._immediate() as connection:
            if stale_after is not None:
                cutoff = (datetime.now(timezone.utc) - stale_after).isoformat()
                stale = tuple(
                    connection.execute(
                        "SELECT task_key, claim_token FROM feature_materialization_task WHERE run_id = ? AND status = ? AND claimed_at < ?",
                        (
                            run_id,
                            FeatureMaterializationTaskStatus.IN_PROGRESS.value,
                            cutoff,
                        ),
                    )
                )
                for item in stale:
                    connection.execute(
                        "UPDATE feature_materialization_task SET status = ?, claim_token = NULL, "
                        "claimed_at = NULL, version = version + 1, last_error = ? "
                        "WHERE run_id = ? AND task_key = ? AND claim_token = ?",
                        (
                            FeatureMaterializationTaskStatus.FAILED.value,
                            "STALE_CLAIM_RECOVERED",
                            run_id,
                            item["task_key"],
                            item["claim_token"],
                        ),
                    )
                    self._event(
                        connection,
                        run_id=run_id,
                        task_key=str(item["task_key"]),
                        event_type="STALE_CLAIM_RECOVERED",
                        payload={},
                    )
            row = connection.execute(
                "SELECT task_key, symbol, feature_id, timeframe, version FROM "
                "feature_materialization_task WHERE run_id = ? AND status IN (?, ?) "
                "ORDER BY task_key LIMIT 1",
                (
                    run_id,
                    FeatureMaterializationTaskStatus.PENDING.value,
                    FeatureMaterializationTaskStatus.FAILED.value,
                ),
            ).fetchone()
            if row is None:
                return None
            task_key = str(row["task_key"])
            token = uuid4().hex
            cursor = connection.execute(
                "UPDATE feature_materialization_task SET status = ?, version = version + 1, "
                "claim_token = ?, claimed_at = ?, last_error = NULL "
                "WHERE run_id = ? AND task_key = ? AND version = ? AND status IN (?, ?)",
                (
                    FeatureMaterializationTaskStatus.IN_PROGRESS.value,
                    token,
                    _now_text(),
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
                    "SELECT COUNT(*) + 1 FROM feature_materialization_attempt WHERE run_id = ? AND task_key = ?",
                    (run_id, task_key),
                ).fetchone()[0]
            )
            connection.execute(
                "INSERT INTO feature_materialization_attempt "
                "(run_id, task_key, attempt_number, claim_token, started_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, task_key, attempt_number, token, _now_text(), "STARTED"),
            )
            self._event(
                connection,
                run_id=run_id,
                task_key=task_key,
                event_type="TASK_CLAIMED",
                payload={"attempt_number": attempt_number, "claim_token": token},
            )
            return ClaimedFeatureMaterializationTask(
                run_id=run_id,
                task_key=task_key,
                symbol=str(row["symbol"]),
                feature_id=str(row["feature_id"]),
                timeframe=Timeframe(str(row["timeframe"])),
                claim_token=token,
                attempt_number=attempt_number,
            )

    def complete_task(
        self,
        claim: ClaimedFeatureMaterializationTask,
        *,
        artifact_id: str,
        artifact_hash: str,
    ) -> None:
        require_text("artifact_id", artifact_id)
        require_sha256("artifact_hash", artifact_hash)
        with self._immediate() as connection:
            cursor = connection.execute(
                "UPDATE feature_materialization_task SET status = ?, version = version + 1, "
                "claim_token = NULL, claimed_at = NULL, artifact_id = ?, artifact_hash = ? "
                "WHERE run_id = ? AND task_key = ? AND status = ? AND claim_token = ?",
                (
                    FeatureMaterializationTaskStatus.COMPLETE.value,
                    artifact_id,
                    artifact_hash,
                    claim.run_id,
                    claim.task_key,
                    FeatureMaterializationTaskStatus.IN_PROGRESS.value,
                    claim.claim_token,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("stale Feature materialization task writer rejected")
            self._complete_attempt(connection, claim=claim, status="COMPLETE", error=None)
            self._event(
                connection,
                run_id=claim.run_id,
                task_key=claim.task_key,
                event_type="TASK_COMPLETED",
                payload={"artifact_id": artifact_id, "artifact_hash": artifact_hash},
            )

    def fail_task(self, claim: ClaimedFeatureMaterializationTask, *, error_message: str) -> None:
        require_text("error_message", error_message)
        with self._immediate() as connection:
            cursor = connection.execute(
                "UPDATE feature_materialization_task SET status = ?, version = version + 1, "
                "claim_token = NULL, claimed_at = NULL, last_error = ? "
                "WHERE run_id = ? AND task_key = ? AND status = ? AND claim_token = ?",
                (
                    FeatureMaterializationTaskStatus.FAILED.value,
                    error_message,
                    claim.run_id,
                    claim.task_key,
                    FeatureMaterializationTaskStatus.IN_PROGRESS.value,
                    claim.claim_token,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("stale Feature materialization task writer rejected")
            self._complete_attempt(connection, claim=claim, status="FAILED", error=error_message)
            connection.execute(
                "UPDATE feature_materialization_run SET status = ?, version = version + 1, updated_at = ? WHERE run_id = ?",
                (FeatureMaterializationRunStatus.FAILED.value, _now_text(), claim.run_id),
            )
            self._event(
                connection,
                run_id=claim.run_id,
                task_key=claim.task_key,
                event_type="TASK_FAILED",
                payload={"error_message": error_message},
            )

    def finalize(self, *, run_id: int, receipt: FeatureMaterializationReceipt) -> None:
        receipt.verify_identity()
        with self._immediate() as connection:
            incomplete = int(
                connection.execute(
                    "SELECT COUNT(*) FROM feature_materialization_task WHERE run_id = ? AND status != ?",
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
                    raise ValueError("completed Feature materialization receipt is immutable")
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
                    _now_text(),
                ),
            )
            connection.execute(
                "UPDATE feature_materialization_run SET status = ?, version = version + 1, updated_at = ? WHERE run_id = ?",
                (FeatureMaterializationRunStatus.COMPLETE.value, _now_text(), run_id),
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
                "SELECT artifact_id, artifact_hash FROM feature_materialization_task WHERE run_id = ? AND status = ? ORDER BY task_key",
                (run_id, FeatureMaterializationTaskStatus.COMPLETE.value),
            )
            return tuple((str(row[0]), str(row[1])) for row in rows)

    def snapshot(self, run_id: int) -> FeatureMaterializationRunSnapshot:
        """One SQLite read snapshot for run, tasks, receipt, and event history."""

        with self._connect() as connection:
            connection.execute("BEGIN")
            run = connection.execute("SELECT * FROM feature_materialization_run WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                raise ValueError("Feature materialization run does not exist")
            tasks = tuple(
                (
                    str(item["task_key"]),
                    FeatureMaterializationTaskStatus(str(item["status"])),
                    str(item["artifact_id"]) if item["artifact_id"] is not None else None,
                    str(item["artifact_hash"]) if item["artifact_hash"] is not None else None,
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
                FeatureMaterializationReceipt.from_canonical_dict(_json_object(str(receipt_row["receipt_json"])))
                if receipt_row is not None
                else None
            )
            events = tuple(
                (
                    int(item["event_id"]),
                    str(item["event_type"]),
                    str(item["task_key"]) if item["task_key"] is not None else None,
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
            "AND claim_token = ? AND status = 'STARTED'",
            (
                status,
                _now_text(),
                error,
                claim.run_id,
                claim.task_key,
                claim.attempt_number,
                claim.claim_token,
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
            "INSERT INTO feature_materialization_event (run_id, task_key, event_type, event_time, payload_json) VALUES (?, ?, ?, ?, ?)",
            (run_id, task_key, event_type, _now_text(), canonical_json(payload)),
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


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_object(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("stored Feature materialization receipt is invalid")
    return payload


__all__ = [
    "ClaimedFeatureMaterializationTask",
    "FeatureMaterializationExecutionMode",
    "FEATURE_MATERIALIZATION_RUN_MIGRATION",
    "FeatureMaterializationRunSnapshot",
    "FeatureMaterializationRunStatus",
    "FeatureMaterializationTaskSpec",
    "FeatureMaterializationTaskStatus",
    "SQLiteFeatureMaterializationRunRepository",
]
