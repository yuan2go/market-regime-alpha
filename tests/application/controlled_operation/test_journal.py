from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from market_regime_alpha.application.controlled_operation.journal import (
    CONTROLLED_OPERATION_STAGE_ORDER,
    ChildRunReferenceKind,
    ControlledOperationCommand,
    DecisionTimeOperationReceipt,
    DecisionTimeOperationRunStatus,
    DecisionTimeOperationStageName,
    DecisionTimeOperationStageStatus,
    OperationArtifactReference,
    OperationChildRunReference,
)
from market_regime_alpha.application.controlled_operation.sqlite_journal import (
    ControlledOperationClaimRejected,
    ControlledOperationConflict,
    SQLiteDecisionTimeOperationJournal,
)
from market_regime_alpha.core.identity import ArtifactId


NOW = datetime(2026, 8, 5, 6, 40, tzinfo=timezone.utc)
DECISION = datetime(2026, 8, 5, 6, 55, tzinfo=timezone.utc)
HASH = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64


@dataclass
class MutableClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


def _command(*, code_revision: str = "fixture-head") -> ControlledOperationCommand:
    return ControlledOperationCommand.create(
        idempotency_key="controlled-2026-08-05",
        decision_date=DECISION.date(),
        decision_time=DECISION,
        policy_id=ArtifactId("policy-fixture"),
        policy_hash=HASH,
        trading_calendar_id=ArtifactId("calendar-fixture"),
        trading_calendar_hash=HASH,
        configuration_manifest_id=ArtifactId("configuration-fixture"),
        configuration_manifest_hash=HASH,
        model_manifest_id=ArtifactId("model-manifest-fixture"),
        model_manifest_hash=HASH,
        code_revision=code_revision,
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )


def _receipt(claim, *, with_child: bool = False) -> DecisionTimeOperationReceipt:
    return DecisionTimeOperationReceipt.create(
        run_id=claim.run_id,
        stage_name=claim.stage_name,
        attempt_number=claim.attempt_number,
        input_references=(
            OperationArtifactReference("INPUT", ArtifactId("input-fixture"), HASH),
        ),
        output_references=(
            OperationArtifactReference("OUTPUT", ArtifactId("output-fixture"), HASH_2),
        ),
        child_run_references=(
            (
                OperationChildRunReference(
                    ChildRunReferenceKind.DAILY_ACQUISITION_RUN,
                    "daily-run-fixture",
                    HASH,
                ),
            )
            if with_child
            else ()
        ),
        reason_codes=("STAGE_ENGINEERING_VERIFIED",),
        created_at=NOW,
    )


def _status_after(stage: DecisionTimeOperationStageName) -> DecisionTimeOperationRunStatus:
    if stage is DecisionTimeOperationStageName.STATIC_FEATURES:
        return DecisionTimeOperationRunStatus.STATIC_READY
    if stage is DecisionTimeOperationStageName.OPERATION_PACKAGE:
        return DecisionTimeOperationRunStatus.OUTCOME_PENDING
    if stage is DecisionTimeOperationStageName.OUTCOME_SETTLEMENT:
        return DecisionTimeOperationRunStatus.SETTLED
    if CONTROLLED_OPERATION_STAGE_ORDER.index(stage) < CONTROLLED_OPERATION_STAGE_ORDER.index(
        DecisionTimeOperationStageName.STATIC_FEATURES
    ):
        return DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS
    return DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING


def _complete_through(
    journal: SQLiteDecisionTimeOperationJournal,
    command: ControlledOperationCommand,
    stop: DecisionTimeOperationStageName,
) -> None:
    for stage in CONTROLLED_OPERATION_STAGE_ORDER:
        claim = journal.claim_stage(run_id=command.run_id, stage_name=stage)
        journal.complete_stage(
            claim=claim,
            receipt=_receipt(
                claim,
                with_child=stage is DecisionTimeOperationStageName.DAILY_SOURCE_FREEZE,
            ),
            run_status=_status_after(stage),
        )
        if stage is stop:
            return


def test_start_is_idempotent_and_command_conflict_fails_closed(tmp_path: Path) -> None:
    journal = SQLiteDecisionTimeOperationJournal(tmp_path / "journal.sqlite", clock=lambda: NOW)
    command = _command()

    first = journal.create_or_get(command)
    second = journal.create_or_get(command)

    assert first.command == second.command == command
    assert first.status is DecisionTimeOperationRunStatus.CREATED
    assert tuple(item.stage_name for item in first.stages) == CONTROLLED_OPERATION_STAGE_ORDER
    assert all(item.status is DecisionTimeOperationStageStatus.PENDING for item in first.stages)
    with pytest.raises(ControlledOperationConflict, match="idempotency conflict"):
        journal.create_or_get(_command(code_revision="different-head"))


def test_stage_order_active_lease_epoch_and_stale_worker_fencing(tmp_path: Path) -> None:
    clock = MutableClock(NOW)
    journal = SQLiteDecisionTimeOperationJournal(
        tmp_path / "journal.sqlite",
        clock=clock,
        lease_duration=timedelta(seconds=30),
    )
    command = _command()
    journal.create_or_get(command)

    with pytest.raises(ControlledOperationClaimRejected, match="prior"):
        journal.claim_stage(
            run_id=command.run_id,
            stage_name=DecisionTimeOperationStageName.DAILY_SOURCE_FREEZE,
        )
    old_claim = journal.claim_stage(
        run_id=command.run_id,
        stage_name=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
    )
    with pytest.raises(ControlledOperationClaimRejected, match="active lease"):
        journal.claim_stage(
            run_id=command.run_id,
            stage_name=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
        )

    clock.advance(timedelta(seconds=31))
    resumed = journal.resume(command.run_id)
    failed = resumed.stages[0]
    assert failed.status is DecisionTimeOperationStageStatus.FAILED
    assert failed.last_error == "LEASE_EXPIRED"
    new_claim = journal.claim_stage(
        run_id=command.run_id,
        stage_name=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
    )
    assert new_claim.claim_epoch == old_claim.claim_epoch + 1
    assert new_claim.stage_version > old_claim.stage_version
    with pytest.raises(ControlledOperationClaimRejected, match="fencing"):
        journal.complete_stage(
            claim=old_claim,
            receipt=_receipt(old_claim),
            run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
        )
    settled = journal.complete_stage(
        claim=new_claim,
        receipt=_receipt(new_claim),
        run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
    )
    assert settled.stages[0].status is DecisionTimeOperationStageStatus.COMPLETED
    assert any(event[1] == "LEASE_EXPIRED" for event in settled.events)


def test_child_run_references_and_append_only_database_rules(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite"
    journal = SQLiteDecisionTimeOperationJournal(path, clock=lambda: NOW)
    command = _command()
    journal.create_or_get(command)
    _complete_through(
        journal,
        command,
        DecisionTimeOperationStageName.DAILY_SOURCE_FREEZE,
    )
    snapshot = journal.get(command.run_id)

    assert snapshot.child_run_references == (
        OperationChildRunReference(
            ChildRunReferenceKind.DAILY_ACQUISITION_RUN,
            "daily-run-fixture",
            HASH,
        ),
    )
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE controlled_operation_event SET payload_json = '{}' ")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM controlled_operation_receipt")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE controlled_operation_stage SET status = 'FAILED' "
                "WHERE stage_name = 'CALENDAR_UNIVERSE_FREEZE'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="identity is immutable"):
            connection.execute(
                "UPDATE controlled_operation_run SET command_hash = ?",
                (HASH_2,),
            )


@pytest.mark.parametrize(
    "failure_point",
    [
        "AFTER_RECEIPT_INSERT",
        "AFTER_CHILD_REFERENCES",
        "AFTER_ATTEMPT_SETTLED",
        "AFTER_STAGE_SETTLED",
    ],
)
def test_settlement_hard_crash_is_atomic_and_resume_publishes_one_receipt(
    tmp_path: Path, failure_point: str
) -> None:
    path = tmp_path / "journal.sqlite"
    clock = MutableClock(NOW)

    def fail(point: str) -> None:
        if point == failure_point:
            raise RuntimeError(f"crash:{point}")

    journal = SQLiteDecisionTimeOperationJournal(
        path,
        clock=clock,
        lease_duration=timedelta(seconds=10),
        fault_injector=fail,
    )
    command = _command()
    journal.create_or_get(command)
    claim = journal.claim_stage(
        run_id=command.run_id,
        stage_name=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
    )
    with pytest.raises(RuntimeError, match="crash"):
        journal.complete_stage(
            claim=claim,
            receipt=_receipt(claim),
            run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
        )

    clock.advance(timedelta(seconds=11))
    recovered = SQLiteDecisionTimeOperationJournal(
        path,
        clock=clock,
        lease_duration=timedelta(seconds=10),
    )
    recovered.resume(command.run_id)
    retry = recovered.claim_stage(
        run_id=command.run_id,
        stage_name=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
    )
    final = recovered.complete_stage(
        claim=retry,
        receipt=_receipt(retry),
        run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
    )
    assert final.stages[0].status is DecisionTimeOperationStageStatus.COMPLETED
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM controlled_operation_receipt"
        ).fetchone()[0] == 1
        attempts = connection.execute(
            "SELECT status FROM controlled_operation_attempt ORDER BY attempt_number"
        ).fetchall()
    assert attempts == [("LEASE_EXPIRED",), ("COMPLETED",)]


def test_full_stage_history_settles_once_and_cannot_resume(tmp_path: Path) -> None:
    journal = SQLiteDecisionTimeOperationJournal(tmp_path / "journal.sqlite", clock=lambda: NOW)
    command = _command()
    journal.create_or_get(command)
    _complete_through(
        journal,
        command,
        DecisionTimeOperationStageName.OUTCOME_SETTLEMENT,
    )
    snapshot = journal.get(command.run_id)

    assert snapshot.status is DecisionTimeOperationRunStatus.SETTLED
    assert snapshot.current_stage is None
    assert all(item.status is DecisionTimeOperationStageStatus.COMPLETED for item in snapshot.stages)
    assert len(tuple(item.receipt for item in snapshot.stages if item.receipt is not None)) == len(
        CONTROLLED_OPERATION_STAGE_ORDER
    )
    with pytest.raises(ControlledOperationClaimRejected, match="cannot resume"):
        journal.resume(command.run_id)


def test_migration_014_checks_indexes_foreign_keys_and_triggers(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite"
    SQLiteDecisionTimeOperationJournal(path, clock=lambda: NOW)
    with sqlite3.connect(path) as connection:
        migration = connection.execute(
            "SELECT version FROM controlled_operation_schema_migration"
        ).fetchall()
        indexes = {
            item[0]
            for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' "
                "AND name LIKE 'controlled_operation_%'"
            )
        }
        triggers = {
            item[0]
            for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND name LIKE 'controlled_operation_%'"
            )
        }
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(controlled_operation_child_run)"
        ).fetchall()
    assert migration == [(14,)]
    assert "controlled_operation_stage_lease_idx" in indexes
    assert "controlled_operation_event_history_idx" in indexes
    assert "controlled_operation_events_no_update" in triggers
    assert "controlled_operation_claim_owner_guard" in triggers
    assert foreign_keys
