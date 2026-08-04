from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
    LifecycleRun,
    LifecycleStage,
    StageReceipt,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleClaimConflict,
    LifecycleConcurrentModification,
    LifecycleIdempotencyConflict,
    StageFailure,
    StageTransition,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.core.identity import ArtifactId


UTC = timezone.utc
T0 = datetime(2026, 8, 4, 6, 55, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _command(
    tmp_path: Path,
    *,
    idempotency_key: str = "lifecycle-request-1",
    input_hash: str = HASH_A,
    output_directory: Path | None = None,
) -> CanonicalLifecycleCommand:
    return CanonicalLifecycleCommand(
        run_type=LifecycleRunType.CANONICAL_DECISION_LIFECYCLE,
        decision_date=date(2026, 8, 4),
        as_of_time=T0,
        idempotency_key=idempotency_key,
        input_manifest_id=ArtifactId("composite-input-1"),
        input_content_hash=input_hash,
        input_manifest_locator=tmp_path / "input-manifest.json",
        input_references=_input_references(),
        configuration_references=(),
        model_references=(),
        stop_after_stage=None,
        output_directory=output_directory or tmp_path / "artifacts",
        authority_database_locator=None,
    )


def _reference(char: str = "b") -> LifecycleObjectReference:
    return LifecycleObjectReference(
        object_type=LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
        object_id=LifecycleObjectId(f"composite-{char}"),
        content_hash="sha256:" + char * 64,
        reader_kind=LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER,
        locator=f"artifacts/composite-{char}",
        available_at=T0,
    )


def _input_references() -> tuple[LifecycleObjectReference, ...]:
    return tuple(
        sorted(
            (
                _reference("d"),
                LifecycleObjectReference(
                    object_type=LifecycleObjectType.SOURCE_MANIFEST,
                    object_id=LifecycleObjectId("source-manifest-e"),
                    content_hash="sha256:" + "e" * 64,
                    reader_kind=LifecycleReaderKind.SOURCE_MANIFEST_READER,
                    locator="artifacts/source-manifest-e.json",
                    available_at=T0,
                ),
            ),
            key=lambda item: item.sort_key,
        )
    )


def _claimed_started(
    repository: SQLiteLifecycleRunRepository,
    command: CanonicalLifecycleCommand,
    *,
    stage: LifecycleStageName = LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
) -> tuple[LifecycleRun, LifecycleStage, LifecycleAttempt]:
    run = repository.create_or_get(command, created_at=T0)
    run = repository.claim(
        run.run_id, expected_version=run.version, claimed_at=T0 + timedelta(seconds=1)
    )
    attempt = repository.start_stage(
        run.run_id,
        stage,
        started_at=T0 + timedelta(seconds=2),
        claim_token=run.claim_token,
    )
    current_run = repository.get_run(run.run_id)
    current_stage = repository.get_stage(run.run_id, stage)
    assert current_stage is not None
    return current_run, current_stage, attempt


def _transition(
    run: LifecycleRun,
    stage: LifecycleStage,
    attempt: LifecycleAttempt,
    *,
    completed_at: datetime = T0 + timedelta(seconds=3),
    target_run_status: LifecycleRunStatus = LifecycleRunStatus.RUNNING,
) -> StageTransition:
    input_reference = _reference()
    receipt = StageReceipt.create(
        run_id=run.run_id,
        stage_name=stage.stage_name,
        attempt_number=attempt.attempt_number,
        input_hashes=(input_reference.content_hash,),
        output_hashes=(),
        model_versions=(),
        configuration_hashes=(),
        reason_codes=("STAGE_VERIFIED",),
        stage_result=LifecycleStageStatus.COMPLETED,
        created_at=completed_at,
    )
    return StageTransition(
        run_id=run.run_id,
        stage_name=stage.stage_name,
        attempt_id=attempt.attempt_id,
        expected_run_version=run.version,
        expected_stage_version=stage.version,
        claim_token=run.claim_token,
        target_run_status=target_run_status,
        receipt=receipt,
        input_references=(input_reference,),
        output_references=(),
        blocker_reason=(
            "EXTERNAL_AUTHORITY_PENDING"
            if target_run_status is LifecycleRunStatus.WAITING_FOR_FILL
            else None
        ),
        completed_at=completed_at,
    )


def test_create_or_get_is_idempotent_and_initializes_every_pending_stage(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    command = _command(tmp_path)
    first = repository.create_or_get(command, created_at=T0)
    replay_control = replace(
        command,
        output_directory=(tmp_path / "other-output").resolve(),
        stop_after_stage=LifecycleStageName.SIGNAL,
    )
    second = repository.create_or_get(
        replay_control, created_at=T0 + timedelta(hours=1)
    )
    assert second == first
    assert repository.get_command(first.run_id).semantic_payload() == command.semantic_payload()
    history = repository.history(first.run_id)
    assert tuple(item.stage_name for item in history.stages) == LIFECYCLE_STAGE_ORDER
    assert all(item.stage_status is LifecycleStageStatus.PENDING for item in history.stages)
    assert len(history.events) == 1


def test_same_idempotency_key_with_different_command_hash_is_rejected(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    repository.create_or_get(_command(tmp_path), created_at=T0)
    with pytest.raises(LifecycleIdempotencyConflict):
        repository.create_or_get(
            _command(tmp_path, input_hash=HASH_B),
            created_at=T0 + timedelta(seconds=1),
        )


def test_concurrent_create_or_get_creates_one_run_and_one_creation_event(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    command = _command(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as executor:
        runs = tuple(
            executor.map(
                lambda _: repository.create_or_get(command, created_at=T0),
                range(24),
            )
        )
    assert {item.run_id for item in runs} == {command.run_id}
    with sqlite3.connect(repository.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM lifecycle_runs").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM lifecycle_stages").fetchone() == (
            len(LIFECYCLE_STAGE_ORDER),
        )
        assert connection.execute("SELECT COUNT(*) FROM lifecycle_events").fetchone() == (1,)


def test_claim_uses_version_and_monotonic_fencing_token(tmp_path: Path) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    created = repository.create_or_get(_command(tmp_path), created_at=T0)
    first = repository.claim(
        created.run_id, expected_version=created.version, claimed_at=T0 + timedelta(seconds=1)
    )
    with pytest.raises(LifecycleConcurrentModification):
        repository.claim(
            created.run_id,
            expected_version=created.version,
            claimed_at=T0 + timedelta(seconds=2),
        )
    second = repository.claim(
        first.run_id,
        expected_version=first.version,
        claimed_at=T0 + timedelta(seconds=2),
    )
    assert second.claim_token == first.claim_token + 1
    with pytest.raises(LifecycleClaimConflict):
        repository.start_stage(
            second.run_id,
            LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
            started_at=T0 + timedelta(seconds=3),
            claim_token=first.claim_token,
        )


def test_finish_stage_atomically_settles_attempt_receipt_stage_run_and_history(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, stage, attempt = _claimed_started(repository, _command(tmp_path))
    transition = _transition(run, stage, attempt)
    settled = repository.finish_stage(transition)
    assert settled.completed_stages == (LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,)
    history = repository.history(settled.run_id)
    assert history.attempts[0].result.value == "COMPLETED"
    assert history.receipts == (transition.receipt,)
    assert history.stages[0].stage_status is LifecycleStageStatus.COMPLETED
    assert [item.sequence_number for item in history.events] == list(
        range(1, len(history.events) + 1)
    )
    with pytest.raises(LifecycleConcurrentModification, match="cannot run again"):
        repository.start_stage(
            settled.run_id,
            LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
            started_at=T0 + timedelta(seconds=4),
            claim_token=settled.claim_token,
        )


@pytest.mark.parametrize(
    "fault_point",
    (
        "finish_after_attempt",
        "finish_after_receipt",
        "finish_after_stage",
        "finish_after_run",
        "finish_after_attempt_event",
        "finish_after_receipt_event",
        "finish_after_stage_event",
    ),
)
def test_finish_stage_fault_injection_rolls_back_every_journal_mutation(
    tmp_path: Path,
    fault_point: str,
) -> None:
    path = tmp_path / f"{fault_point}.sqlite3"
    armed = False

    def inject(point: str) -> None:
        if armed and point == fault_point:
            raise RuntimeError(f"injected at {point}")

    repository = SQLiteLifecycleRunRepository(path, fault_injector=inject)
    run, stage, attempt = _claimed_started(repository, _command(tmp_path))
    transition = _transition(run, stage, attempt)
    armed = True
    with pytest.raises(RuntimeError, match="injected"):
        repository.finish_stage(transition)
    history = repository.history(run.run_id)
    assert history.attempts[0].result.value == "RUNNING"
    assert history.receipts == ()
    assert history.stages[0].stage_status is LifecycleStageStatus.RUNNING
    assert history.run.version == run.version
    recovered = SQLiteLifecycleRunRepository(path).finish_stage(transition)
    assert recovered.completed_stages == (LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,)


def test_completed_stage_can_stop_the_run_waiting_without_corrupting_stage_reason(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, stage, attempt = _claimed_started(repository, _command(tmp_path))
    transition = _transition(
        run,
        stage,
        attempt,
        target_run_status=LifecycleRunStatus.WAITING_FOR_FILL,
    )
    settled = repository.finish_stage(transition)
    assert settled.blocker_reason == "EXTERNAL_AUTHORITY_PENDING"
    stored_stage = repository.get_stage(settled.run_id, stage.stage_name)
    assert stored_stage is not None
    assert stored_stage.stage_status is LifecycleStageStatus.COMPLETED
    assert stored_stage.blocker_reason is None


def test_repeated_semantically_identical_wait_reuses_immutable_receipt(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, stage, attempt = _claimed_started(repository, _command(tmp_path))
    reference = _reference()

    def wait_transition(
        *,
        current_run: LifecycleRun,
        current_stage: LifecycleStage,
        current_attempt: LifecycleAttempt,
        completed_at: datetime,
    ) -> StageTransition:
        receipt = StageReceipt.create(
            run_id=current_run.run_id,
            stage_name=current_stage.stage_name,
            attempt_number=current_attempt.attempt_number,
            input_hashes=(reference.content_hash,),
            output_hashes=(),
            model_versions=(),
            configuration_hashes=(),
            reason_codes=("ENTRY_CONFIRMATION_PENDING",),
            stage_result=LifecycleStageStatus.WAITING,
            created_at=completed_at,
        )
        return StageTransition(
            run_id=current_run.run_id,
            stage_name=current_stage.stage_name,
            attempt_id=current_attempt.attempt_id,
            expected_run_version=current_run.version,
            expected_stage_version=current_stage.version,
            claim_token=current_run.claim_token,
            target_run_status=LifecycleRunStatus.WAITING_FOR_ENTRY_CONFIRMATION,
            receipt=receipt,
            input_references=(reference,),
            output_references=(),
            blocker_reason="ENTRY_CONFIRMATION_PENDING",
            completed_at=completed_at,
        )

    first_transition = wait_transition(
        current_run=run,
        current_stage=stage,
        current_attempt=attempt,
        completed_at=T0 + timedelta(seconds=3),
    )
    waiting = repository.finish_stage(first_transition)
    reclaimed = repository.claim(
        waiting.run_id,
        expected_version=waiting.version,
        claimed_at=T0 + timedelta(seconds=4),
    )
    second_attempt = repository.start_stage(
        reclaimed.run_id,
        stage.stage_name,
        started_at=T0 + timedelta(seconds=5),
        claim_token=reclaimed.claim_token,
    )
    second_run = repository.get_run(reclaimed.run_id)
    second_stage = repository.get_stage(reclaimed.run_id, stage.stage_name)
    assert second_stage is not None
    second_transition = wait_transition(
        current_run=second_run,
        current_stage=second_stage,
        current_attempt=second_attempt,
        completed_at=T0 + timedelta(seconds=6),
    )
    assert second_transition.receipt.receipt_id == first_transition.receipt.receipt_id
    repository.finish_stage(second_transition)
    history = repository.history(waiting.run_id)
    assert len(history.receipts) == 1
    assert [item.result.value for item in history.attempts] == ["WAITING", "WAITING"]
    assert sum(item.event_type.value == "RECEIPT_RECORDED" for item in history.events) == 2


def test_receipt_must_bind_exact_input_and_output_reference_hashes(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, stage, attempt = _claimed_started(repository, _command(tmp_path))
    transition = _transition(run, stage, attempt)
    with pytest.raises(ValueError, match="input_hashes"):
        replace(transition, input_references=(_reference("c"),))


def test_failure_resume_increments_attempt_and_never_reexecutes_completed_stage(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, stage, attempt = _claimed_started(repository, _command(tmp_path))
    failed = repository.mark_stage_failed(
        StageFailure(
            run_id=run.run_id,
            stage_name=stage.stage_name,
            attempt_id=attempt.attempt_id,
            expected_run_version=run.version,
            expected_stage_version=stage.version,
            claim_token=run.claim_token,
            input_references=(_reference(),),
            exception_type="ResearchServiceError",
            exception_message="temporary unavailable evidence",
            failed_at=T0 + timedelta(seconds=3),
        )
    )
    assert failed.status is LifecycleRunStatus.FAILED
    resumed = repository.resume(failed.run_id, resumed_at=T0 + timedelta(seconds=4))
    retry = repository.start_stage(
        resumed.run_id,
        stage.stage_name,
        started_at=T0 + timedelta(seconds=5),
        claim_token=resumed.claim_token,
    )
    retry_run = repository.get_run(resumed.run_id)
    retry_stage = repository.get_stage(resumed.run_id, stage.stage_name)
    assert retry_stage is not None
    assert retry.attempt_number == 2
    settled = repository.finish_stage(
        _transition(
            retry_run,
            retry_stage,
            retry,
            completed_at=T0 + timedelta(seconds=6),
        )
    )
    history = repository.history(settled.run_id)
    assert [item.result.value for item in history.attempts] == ["FAILED", "COMPLETED"]
    assert len(history.receipts) == 1


def test_new_claim_fences_and_audits_an_abandoned_running_attempt(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, _stage, first_attempt = _claimed_started(repository, _command(tmp_path))
    reclaimed = repository.claim(
        run.run_id,
        expected_version=run.version,
        claimed_at=T0 + timedelta(seconds=3),
    )
    second_attempt = repository.start_stage(
        reclaimed.run_id,
        LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
        started_at=T0 + timedelta(seconds=4),
        claim_token=reclaimed.claim_token,
    )
    history = repository.history(reclaimed.run_id)
    assert first_attempt.attempt_id == history.attempts[0].attempt_id
    assert history.attempts[0].result.value == "FAILED"
    assert history.attempts[0].exception_type == "LifecycleClaimSuperseded"
    assert second_attempt.attempt_number == 2
    assert history.attempts[1].result.value == "RUNNING"


def test_journal_rejects_backward_audit_time(tmp_path: Path) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    created = repository.create_or_get(_command(tmp_path), created_at=T0)
    with pytest.raises(ValueError, match="cannot precede"):
        repository.claim(
            created.run_id,
            expected_version=created.version,
            claimed_at=T0 - timedelta(seconds=1),
        )
    claimed = repository.claim(
        created.run_id,
        expected_version=created.version,
        claimed_at=T0 + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="cannot precede"):
        repository.start_stage(
            claimed.run_id,
            LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
            started_at=T0,
            claim_token=claimed.claim_token,
        )


def test_database_guards_run_identity_and_terminal_history(tmp_path: Path) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run, stage, attempt = _claimed_started(repository, _command(tmp_path))
    transition = _transition(run, stage, attempt)
    repository.finish_stage(transition)
    with sqlite3.connect(repository.path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError, match="command identity"):
            connection.execute(
                "UPDATE lifecycle_runs SET command_hash = ? WHERE run_id = ?",
                (HASH_B, str(run.run_id)),
            )
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute(
                "DELETE FROM lifecycle_runs WHERE run_id = ?", (str(run.run_id),)
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE lifecycle_attempts SET result = result WHERE attempt_id = ?",
                (str(attempt.attempt_id),),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE lifecycle_stages SET version = version + 1 "
                "WHERE run_id = ? AND stage_name = ?",
                (str(run.run_id), stage.stage_name.value),
            )
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute(
                "DELETE FROM lifecycle_stages WHERE run_id = ? AND stage_name = ?",
                (str(run.run_id), LifecycleStageName.SIGNAL.value),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM lifecycle_stage_receipts WHERE receipt_id = ?",
                (str(transition.receipt.receipt_id),),
            )


def test_event_composite_foreign_keys_reject_cross_run_attempt_linkage(
    tmp_path: Path,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "journal.sqlite3")
    run1, _stage1, _attempt1 = _claimed_started(
        repository, _command(tmp_path, idempotency_key="run-1")
    )
    run2, _stage2, attempt2 = _claimed_started(
        repository, _command(tmp_path, idempotency_key="run-2")
    )
    assert run1.run_id != run2.run_id
    with sqlite3.connect(repository.path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        sequence = connection.execute(
            "SELECT MAX(sequence_number) + 1 FROM lifecycle_events WHERE run_id = ?",
            (str(run1.run_id),),
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute(
                """
                INSERT INTO lifecycle_events(
                    event_id, run_id, sequence_number, event_type, stage_name,
                    attempt_id, receipt_id, event_json, payload_json,
                    payload_hash, created_at, claim_token
                ) VALUES (?, ?, ?, 'ATTEMPT_STARTED', ?, ?, NULL, '{}', '{}', ?, ?, ?)
                """,
                (
                    "cross-run-event",
                    str(run1.run_id),
                    sequence,
                    LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE.value,
                    str(attempt2.attempt_id),
                    HASH_A,
                    (T0 + timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
                    run1.claim_token,
                ),
            )
