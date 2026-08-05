from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from market_regime_alpha.features.materialization_run import (
    FeatureMaterializationExecutionMode,
    FeatureMaterializationTaskSpec,
    SQLiteFeatureMaterializationRunRepository,
)
from market_regime_alpha.market_data import Timeframe


UTC = timezone.utc
COMMAND_HASH = "sha256:" + "1" * 64
ARTIFACT_HASH = "sha256:" + "2" * 64


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def _task() -> FeatureMaterializationTaskSpec:
    return FeatureMaterializationTaskSpec(
        symbol="600000.SH",
        feature_id="feature-a",
        timeframe=Timeframe.DAILY,
    )


def _prepare(
    repository: SQLiteFeatureMaterializationRunRepository,
    *,
    mode: FeatureMaterializationExecutionMode,
) -> int:
    return repository.prepare(
        idempotency_key="run-1",
        command_hash=COMMAND_HASH,
        tasks=(_task(),),
        mode=mode,
    ).run_id


def test_expired_lease_is_recovered_with_monotonic_fencing_epoch(
    tmp_path: Path,
) -> None:
    clock = MutableClock(datetime(2026, 8, 5, 6, 40, tzinfo=UTC))
    repository = SQLiteFeatureMaterializationRunRepository(
        tmp_path / "run.sqlite3",
        clock=clock,
        lease_duration=timedelta(seconds=30),
    )
    run_id = _prepare(repository, mode=FeatureMaterializationExecutionMode.START_NEW)
    original = repository.claim_next(run_id=run_id)
    assert original is not None
    assert original.claim_epoch == 1
    assert original.task_version == 2

    clock.advance(timedelta(seconds=31))
    _prepare(repository, mode=FeatureMaterializationExecutionMode.RESUME_EXISTING)
    replacement = repository.claim_next(run_id=run_id)
    assert replacement is not None
    assert replacement.claim_epoch == 2
    assert replacement.task_version > original.task_version
    assert replacement.claim_token != original.claim_token

    with pytest.raises(ValueError, match="stale.*writer"):
        repository.complete_task(
            original,
            artifact_id="artifact-old",
            artifact_hash=ARTIFACT_HASH,
        )
    repository.complete_task(
        replacement,
        artifact_id="artifact-new",
        artifact_hash=ARTIFACT_HASH,
    )

    snapshot = repository.snapshot(run_id)
    event_types = tuple(item[1] for item in snapshot.events)
    assert "LEASE_EXPIRED" in event_types
    with sqlite3.connect(tmp_path / "run.sqlite3") as connection:
        attempts = tuple(
            connection.execute(
                "SELECT claim_epoch, status FROM feature_materialization_attempt "
                "ORDER BY attempt_number"
            )
        )
    assert attempts == ((1, "LEASE_EXPIRED"), (2, "COMPLETE"))


def test_active_lease_cannot_be_stolen_and_heartbeat_extends_it(
    tmp_path: Path,
) -> None:
    clock = MutableClock(datetime(2026, 8, 5, 6, 40, tzinfo=UTC))
    repository = SQLiteFeatureMaterializationRunRepository(
        tmp_path / "run.sqlite3",
        clock=clock,
        lease_duration=timedelta(seconds=30),
    )
    run_id = _prepare(repository, mode=FeatureMaterializationExecutionMode.START_NEW)
    claim = repository.claim_next(run_id=run_id)
    assert claim is not None

    clock.advance(timedelta(seconds=20))
    refreshed = repository.heartbeat(claim)
    assert refreshed.claim_epoch == claim.claim_epoch
    assert refreshed.task_version > claim.task_version
    assert repository.claim_next(run_id=run_id) is None

    clock.advance(timedelta(seconds=20))
    assert repository.claim_next(run_id=run_id) is None
    repository.complete_task(
        refreshed,
        artifact_id="artifact-a",
        artifact_hash=ARTIFACT_HASH,
    )


def test_migration_013_enforces_checks_indexes_and_append_only_history(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.sqlite3"
    repository = SQLiteFeatureMaterializationRunRepository(path)
    run_id = _prepare(repository, mode=FeatureMaterializationExecutionMode.START_NEW)
    claim = repository.claim_next(run_id=run_id)
    assert claim is not None

    with sqlite3.connect(path) as connection:
        migration = connection.execute(
            "SELECT version FROM feature_materialization_schema_migration "
            "WHERE version = 13"
        ).fetchone()
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert migration == (13,)
        assert {
            "feature_materialization_task_claimable_idx",
            "feature_materialization_task_lease_idx",
            "feature_materialization_attempt_task_idx",
            "feature_materialization_event_run_idx",
        }.issubset(indexes)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE feature_materialization_run SET status = 'UNKNOWN' "
                "WHERE run_id = ?",
                (run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE feature_materialization_run SET command_hash = ? WHERE run_id = ?",
                (ARTIFACT_HASH, run_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE feature_materialization_task SET claim_token = 'stolen' "
                "WHERE run_id = ? AND task_key = ?",
                (run_id, claim.task_key),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE feature_materialization_event SET payload_json = '{}' "
                "WHERE run_id = ?",
                (run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM feature_materialization_event WHERE run_id = ?",
                (run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO feature_materialization_event "
                "(run_id, task_key, event_type, event_time, payload_json) "
                "VALUES (?, NULL, 'INVALID_JSON', ?, 'not-json')",
                (run_id, datetime(2026, 8, 5, tzinfo=UTC).isoformat()),
            )

    repository.fail_task(claim, error_message="expected test failure")
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE feature_materialization_attempt SET error_message = 'changed' "
                "WHERE run_id = ?",
                (run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM feature_materialization_run WHERE run_id = ?",
                (run_id,),
            )


def test_migration_013_is_applied_once_across_repository_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.sqlite3"
    SQLiteFeatureMaterializationRunRepository(path)
    SQLiteFeatureMaterializationRunRepository(path)

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM feature_materialization_schema_migration "
            "WHERE version = 13"
        ).fetchone() == (1,)
