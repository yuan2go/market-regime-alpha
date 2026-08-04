from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
from threading import Event

import pytest

from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleJournalIntegrityError,
    StageTransition,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleRun,
    LifecycleRunId,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleStageName,
)
from market_regime_alpha.evidence.canonical import canonical_json

from .test_sqlite_repository import T0, _claimed_started, _command, _transition


def _settled_run(
    repository: SQLiteLifecycleRunRepository,
    tmp_path: Path,
    *,
    idempotency_key: str = "history-run",
) -> tuple[LifecycleRun, StageTransition]:
    run, stage, attempt = _claimed_started(
        repository, _command(tmp_path, idempotency_key=idempotency_key)
    )
    transition = _transition(run, stage, attempt)
    return repository.finish_stage(transition), transition


def test_history_is_complete_deterministic_and_retains_hashed_event_payloads(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, transition = _settled_run(repository, tmp_path)
    first = repository.history(run.run_id)
    second = repository.history(run.run_id)
    assert first == second
    assert first.receipts == (transition.receipt,)
    assert [item.sequence_number for item in first.events] == list(
        range(1, len(first.events) + 1)
    )
    assert len(first.event_payloads) == len(first.events)
    payloads = tuple(json.loads(item) for item in first.event_payloads)
    assert all(payload["run_id"] == str(run.run_id) for payload in payloads)
    assert any(payload["extra"].get("result") == "COMPLETED" for payload in payloads)
    assert any(
        payload["extra"].get("to_stage_status") == "COMPLETED"
        for payload in payloads
    )


def test_history_uses_one_snapshot_while_concurrent_writer_commits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "journal.sqlite3"
    reader = SQLiteLifecycleRunRepository(path)
    command = _command(tmp_path, idempotency_key="history-snapshot")
    created = reader.create_or_get(command, created_at=T0)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)

    writer = SQLiteLifecycleRunRepository(path)
    run_selected = Event()
    writer_committed = Event()
    original_select_run = reader._select_run

    def select_run_then_pause(
        connection: sqlite3.Connection,
        run_id: LifecycleRunId,
    ) -> sqlite3.Row:
        row = original_select_run(connection, run_id)
        run_selected.set()
        if not writer_committed.wait(timeout=5):
            raise TimeoutError("concurrent writer did not commit")
        return row

    monkeypatch.setattr(reader, "_select_run", select_run_then_pause)

    def claim_after_reader_snapshot() -> LifecycleRun:
        if not run_selected.wait(timeout=5):
            raise TimeoutError("history did not establish its read snapshot")
        claimed = writer.claim(
            created.run_id,
            expected_version=created.version,
            claimed_at=T0 + timedelta(seconds=1),
        )
        writer_committed.set()
        return claimed

    with ThreadPoolExecutor(max_workers=1) as executor:
        claimed_future = executor.submit(claim_after_reader_snapshot)
        history = reader.history(created.run_id)
        claimed = claimed_future.result(timeout=5)

    assert history.run.status is LifecycleRunStatus.CREATED
    assert len(history.events) == 1
    assert history.events[0].to_status is LifecycleRunStatus.CREATED
    assert claimed.status is LifecycleRunStatus.RUNNING
    current = writer.history(created.run_id)
    assert current.run.status is LifecycleRunStatus.RUNNING
    assert len(current.events) == 2


def test_history_fails_closed_on_event_payload_tamper(tmp_path: Path) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, _transition_record = _settled_run(repository, tmp_path)
    with sqlite3.connect(repository.path) as connection:
        connection.execute("DROP TRIGGER lifecycle_events_no_update")
        row = connection.execute(
            """
            SELECT event_id, payload_json FROM lifecycle_events
            WHERE run_id = ? AND event_type = 'ATTEMPT_FINISHED'
            """,
            (str(run.run_id),),
        ).fetchone()
        payload = json.loads(str(row[1]))
        payload["extra"]["result"] = "WAITING"
        connection.execute(
            "UPDATE lifecycle_events SET payload_json = ? WHERE event_id = ?",
            (canonical_json(payload), str(row[0])),
        )
    with pytest.raises(LifecycleJournalIntegrityError, match="payload hash"):
        repository.history(run.run_id)


def test_history_fails_closed_on_json_projection_tamper(tmp_path: Path) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, _transition_record = _settled_run(repository, tmp_path)
    with sqlite3.connect(repository.path) as connection:
        connection.execute("DROP TRIGGER lifecycle_events_no_update")
        row = connection.execute(
            """
            SELECT event_id, event_json FROM lifecycle_events
            WHERE run_id = ? ORDER BY sequence_number DESC LIMIT 1
            """,
            (str(run.run_id),),
        ).fetchone()
        event = json.loads(str(row[1]))
        event["claim_token"] += 1
        connection.execute(
            "UPDATE lifecycle_events SET event_json = ? WHERE event_id = ?",
            (canonical_json(event), str(row[0])),
        )
    with pytest.raises(LifecycleJournalIntegrityError, match="projection mismatch"):
        repository.history(run.run_id)


def test_history_fails_closed_on_run_projection_tamper(tmp_path: Path) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, _transition_record = _settled_run(repository, tmp_path)
    with sqlite3.connect(repository.path) as connection:
        connection.execute(
            "UPDATE lifecycle_runs SET status = 'POSITION_OPEN' WHERE run_id = ?",
            (str(run.run_id),),
        )
    with pytest.raises(LifecycleJournalIntegrityError, match="projection mismatch"):
        repository.history(run.run_id)


def test_history_fails_closed_on_run_json_projection_tamper(tmp_path: Path) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, _transition_record = _settled_run(repository, tmp_path)
    with sqlite3.connect(repository.path) as connection:
        row = connection.execute(
            "SELECT run_json FROM lifecycle_runs WHERE run_id = ?",
            (str(run.run_id),),
        ).fetchone()
        payload = json.loads(str(row[0]))
        payload["current_stage"] = LifecycleStageName.SIGNAL.value
        connection.execute(
            "UPDATE lifecycle_runs SET run_json = ? WHERE run_id = ?",
            (canonical_json(payload), str(run.run_id)),
        )
    with pytest.raises(LifecycleJournalIntegrityError, match="projection mismatch"):
        repository.history(run.run_id)


def test_get_command_fails_closed_on_command_json_rebinding(tmp_path: Path) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    command = _command(tmp_path)
    run = repository.create_or_get(command, created_at=T0)
    other = _command(tmp_path, input_hash="sha256:" + "f" * 64)
    with sqlite3.connect(repository.path) as connection:
        connection.execute("DROP TRIGGER lifecycle_runs_identity_immutable")
        connection.execute(
            "UPDATE lifecycle_runs SET command_json = ? WHERE run_id = ?",
            (canonical_json(other.to_canonical_dict()), str(run.run_id)),
        )
    with pytest.raises(LifecycleJournalIntegrityError, match="does not bind"):
        repository.get_command(run.run_id)


def test_event_receipt_foreign_key_rejects_cross_run_stage_linkage(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    first, _first_transition = _settled_run(
        repository, tmp_path, idempotency_key="receipt-run-1"
    )
    second, second_transition = _settled_run(
        repository, tmp_path, idempotency_key="receipt-run-2"
    )
    assert first.run_id != second.run_id
    with sqlite3.connect(repository.path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        sequence = connection.execute(
            "SELECT MAX(sequence_number) + 1 FROM lifecycle_events WHERE run_id = ?",
            (str(first.run_id),),
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute(
                """
                INSERT INTO lifecycle_events(
                    event_id, run_id, sequence_number, event_type, stage_name,
                    attempt_id, receipt_id, event_json, payload_json,
                    payload_hash, created_at, claim_token
                ) VALUES (?, ?, ?, 'RECEIPT_RECORDED', ?, NULL, ?, '{}', '{}', ?, ?, ?)
                """,
                (
                    "cross-run-receipt-event",
                    str(first.run_id),
                    sequence,
                    LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE.value,
                    str(second_transition.receipt.receipt_id),
                    "sha256:" + "a" * 64,
                    (T0 + timedelta(seconds=10)).isoformat().replace("+00:00", "Z"),
                    first.claim_token,
                ),
            )
