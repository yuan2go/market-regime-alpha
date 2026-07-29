"""SQLite implementation of the DailyRun Runtime Journal Protocol."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from market_regime_alpha.application.daily_loop.commands import (
    DailyRunCommand,
    DailyRunId,
    DailyRunIdentity,
    RunRequestId,
)
from market_regime_alpha.application.daily_loop.errors import (
    RuntimeJournalConflictError,
)
from market_regime_alpha.application.daily_loop.repositories import (
    DailyRunRecord,
    StageReceipt,
)
from market_regime_alpha.application.daily_loop.state import (
    TERMINAL_DAILY_RUN_STATUSES,
    DailyRunStatus,
    validate_daily_run_transition,
)


class SQLiteDailyRunRepository:
    """Durable journal; immutable files remain the Evidence Authority."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_or_get(
        self,
        command: DailyRunCommand,
        *,
        created_at: datetime,
    ) -> DailyRunRecord:
        _require_aware("created_at", created_at)
        command_json = _canonical_json(command.to_canonical_dict())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_runs (
                    run_request_id,
                    request_json,
                    daily_run_id,
                    daily_run_identity_json,
                    status,
                    resume_status,
                    failure_reason,
                    version,
                    created_at,
                    updated_at
                ) VALUES (?, ?, NULL, NULL, ?, NULL, NULL, 0, ?, ?)
                """,
                (
                    str(command.run_request_id),
                    command_json,
                    DailyRunStatus.CREATED.value,
                    created_at.isoformat(),
                    created_at.isoformat(),
                ),
            )
            row = self._select(connection, command.run_request_id)
        record = _record_from_row(row)
        if record.command != command:
            raise RuntimeJournalConflictError(
                "RunRequestId collision with different command semantics"
            )
        return record

    def get(self, run_request_id: RunRequestId) -> DailyRunRecord:
        with self._connect() as connection:
            row = self._select(connection, run_request_id)
        return _record_from_row(row)

    def get_by_daily_run_id(self, daily_run_id: DailyRunId) -> DailyRunRecord:
        if not isinstance(daily_run_id, DailyRunId):
            raise TypeError("daily_run_id must be a DailyRunId")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM daily_runs
                WHERE daily_run_id = ?
                """,
                (str(daily_run_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(daily_run_id))
        return _record_from_row(row)

    def begin_source_acquisition(
        self,
        run_request_id: RunRequestId,
        *,
        changed_at: datetime,
    ) -> bool:
        _require_aware("changed_at", changed_at)
        with self._connect() as connection:
            row = self._select(connection, run_request_id)
            current = DailyRunStatus(str(row["status"]))
            if current is not DailyRunStatus.CREATED:
                return False
            cursor = connection.execute(
                """
                UPDATE daily_runs
                SET status = ?, version = version + 1, updated_at = ?
                WHERE run_request_id = ? AND status = ? AND version = ?
                """,
                (
                    DailyRunStatus.SOURCE_ACQUIRING.value,
                    changed_at.isoformat(),
                    str(run_request_id),
                    DailyRunStatus.CREATED.value,
                    int(row["version"]),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeJournalConflictError(
                    "source acquisition claim compare-and-set failed"
                )
        return True

    def bind_source_frozen(
        self,
        run_request_id: RunRequestId,
        *,
        identity: DailyRunIdentity,
        changed_at: datetime,
    ) -> DailyRunRecord:
        _require_aware("changed_at", changed_at)
        if identity.run_request_id != run_request_id:
            raise ValueError("DailyRunIdentity binds a different RunRequest")
        with self._connect() as connection:
            row = self._select(connection, run_request_id)
            command = DailyRunCommand.from_canonical_dict(
                _json_object(str(row["request_json"]))
            )
            if identity.run_request_hash != command.content_hash:
                raise ValueError("DailyRunIdentity run_request_hash mismatch")
            existing_json = row["daily_run_identity_json"]
            if existing_json is not None:
                existing = DailyRunIdentity.from_canonical_dict(
                    _json_object(str(existing_json))
                )
                if existing != identity:
                    raise RuntimeJournalConflictError(
                        "DailyRunId mapping is immutable"
                    )
                return _record_from_row(row)
            current = DailyRunStatus(str(row["status"]))
            if current is not DailyRunStatus.SOURCE_ACQUIRING:
                raise RuntimeJournalConflictError(
                    "Source Freeze requires SOURCE_ACQUIRING"
                )
            cursor = connection.execute(
                """
                UPDATE daily_runs
                SET daily_run_id = ?,
                    daily_run_identity_json = ?,
                    status = ?,
                    version = version + 1,
                    updated_at = ?
                WHERE run_request_id = ?
                  AND status = ?
                  AND daily_run_id IS NULL
                  AND version = ?
                """,
                (
                    str(identity.daily_run_id),
                    _canonical_json(identity.to_canonical_dict()),
                    DailyRunStatus.SOURCE_FROZEN.value,
                    changed_at.isoformat(),
                    str(run_request_id),
                    DailyRunStatus.SOURCE_ACQUIRING.value,
                    int(row["version"]),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeJournalConflictError(
                    "Source Freeze compare-and-set failed"
                )
            updated = self._select(connection, run_request_id)
        return _record_from_row(updated)

    def transition(
        self,
        run_request_id: RunRequestId,
        *,
        expected_status: DailyRunStatus,
        target_status: DailyRunStatus,
        changed_at: datetime,
    ) -> DailyRunRecord:
        _require_aware("changed_at", changed_at)
        if target_status is DailyRunStatus.SOURCE_FROZEN:
            raise ValueError(
                "SOURCE_FROZEN must be entered through bind_source_frozen"
            )
        validate_daily_run_transition(expected_status, target_status)
        with self._connect() as connection:
            row = self._select(connection, run_request_id)
            current = DailyRunStatus(str(row["status"]))
            if current is target_status:
                return _record_from_row(row)
            if current is not expected_status:
                raise RuntimeJournalConflictError(
                    "DailyRunStatus compare-and-set failed"
                )
            cursor = connection.execute(
                """
                UPDATE daily_runs
                SET status = ?, version = version + 1, updated_at = ?
                WHERE run_request_id = ? AND status = ? AND version = ?
                """,
                (
                    target_status.value,
                    changed_at.isoformat(),
                    str(run_request_id),
                    expected_status.value,
                    int(row["version"]),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeJournalConflictError(
                    "DailyRunStatus compare-and-set failed"
                )
            updated = self._select(connection, run_request_id)
        return _record_from_row(updated)

    def mark_failed(
        self,
        run_request_id: RunRequestId,
        *,
        reason: str,
        changed_at: datetime,
    ) -> DailyRunRecord:
        _require_aware("changed_at", changed_at)
        if not isinstance(reason, str) or not reason or reason != reason.strip():
            raise ValueError("failure reason must be a non-empty trimmed string")
        with self._connect() as connection:
            row = self._select(connection, run_request_id)
            current = DailyRunStatus(str(row["status"]))
            if current in TERMINAL_DAILY_RUN_STATUSES:
                raise RuntimeJournalConflictError(
                    f"cannot fail terminal status {current.value}"
                )
            if current is DailyRunStatus.FAILED:
                record = _record_from_row(row)
                if record.failure_reason != reason:
                    raise RuntimeJournalConflictError(
                        "FAILED reason is already recorded"
                    )
                return record
            cursor = connection.execute(
                """
                UPDATE daily_runs
                SET status = ?,
                    resume_status = ?,
                    failure_reason = ?,
                    version = version + 1,
                    updated_at = ?
                WHERE run_request_id = ? AND status = ? AND version = ?
                """,
                (
                    DailyRunStatus.FAILED.value,
                    current.value,
                    reason,
                    changed_at.isoformat(),
                    str(run_request_id),
                    current.value,
                    int(row["version"]),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeJournalConflictError("mark FAILED compare-and-set failed")
            updated = self._select(connection, run_request_id)
        return _record_from_row(updated)

    def resume_failed(
        self,
        run_request_id: RunRequestId,
        *,
        changed_at: datetime,
    ) -> DailyRunRecord:
        _require_aware("changed_at", changed_at)
        with self._connect() as connection:
            row = self._select(connection, run_request_id)
            if DailyRunStatus(str(row["status"])) is not DailyRunStatus.FAILED:
                raise RuntimeJournalConflictError("run is not FAILED")
            resume_raw = row["resume_status"]
            if resume_raw is None:
                raise RuntimeJournalConflictError("FAILED run has no resume status")
            cursor = connection.execute(
                """
                UPDATE daily_runs
                SET status = ?,
                    resume_status = NULL,
                    failure_reason = NULL,
                    version = version + 1,
                    updated_at = ?
                WHERE run_request_id = ? AND status = ? AND version = ?
                """,
                (
                    str(resume_raw),
                    changed_at.isoformat(),
                    str(run_request_id),
                    DailyRunStatus.FAILED.value,
                    int(row["version"]),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeJournalConflictError("resume compare-and-set failed")
            updated = self._select(connection, run_request_id)
        return _record_from_row(updated)

    def record_stage_receipt(self, receipt: StageReceipt) -> StageReceipt:
        payload = _canonical_json(receipt.to_canonical_dict())
        with self._connect() as connection:
            self._select(connection, receipt.run_request_id)
            connection.execute(
                """
                INSERT OR IGNORE INTO stage_receipts (
                    run_request_id,
                    stage,
                    receipt_json,
                    content_hash
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    str(receipt.run_request_id),
                    receipt.stage.value,
                    payload,
                    receipt.content_hash,
                ),
            )
            row = connection.execute(
                """
                SELECT receipt_json
                FROM stage_receipts
                WHERE run_request_id = ? AND stage = ?
                """,
                (str(receipt.run_request_id), receipt.stage.value),
            ).fetchone()
        if row is None:
            raise RuntimeJournalConflictError("stage receipt write failed")
        stored = StageReceipt.from_canonical_dict(
            _json_object(str(row["receipt_json"]))
        )
        if stored != receipt:
            raise RuntimeJournalConflictError("stage receipt conflict")
        return stored

    def get_stage_receipt(
        self,
        run_request_id: RunRequestId,
        stage: DailyRunStatus,
    ) -> StageReceipt | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT receipt_json
                FROM stage_receipts
                WHERE run_request_id = ? AND stage = ?
                """,
                (str(run_request_id), stage.value),
            ).fetchone()
        if row is None:
            return None
        return StageReceipt.from_canonical_dict(
            _json_object(str(row["receipt_json"]))
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_runs (
                    run_request_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    daily_run_id TEXT UNIQUE,
                    daily_run_identity_json TEXT,
                    status TEXT NOT NULL,
                    resume_status TEXT,
                    failure_reason TEXT,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS stage_receipts (
                    run_request_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    PRIMARY KEY (run_request_id, stage),
                    FOREIGN KEY (run_request_id)
                        REFERENCES daily_runs(run_request_id)
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _select(
        connection: sqlite3.Connection,
        run_request_id: RunRequestId,
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT *
            FROM daily_runs
            WHERE run_request_id = ?
            """,
            (str(run_request_id),),
        ).fetchone()
        if row is None:
            raise KeyError(str(run_request_id))
        return row


def _record_from_row(row: sqlite3.Row) -> DailyRunRecord:
    identity_json = row["daily_run_identity_json"]
    resume_raw = row["resume_status"]
    failure_reason = row["failure_reason"]
    return DailyRunRecord(
        command=DailyRunCommand.from_canonical_dict(
            _json_object(str(row["request_json"]))
        ),
        status=DailyRunStatus(str(row["status"])),
        daily_run_identity=(
            DailyRunIdentity.from_canonical_dict(
                _json_object(str(identity_json))
            )
            if identity_json is not None
            else None
        ),
        resume_status=(
            DailyRunStatus(str(resume_raw)) if resume_raw is not None else None
        ),
        failure_reason=(
            str(failure_reason) if failure_reason is not None else None
        ),
        version=int(row["version"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_object(raw: str) -> dict[str, Any]:
    value: Any = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Runtime Journal JSON must contain an object")
    return value


def _require_aware(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
