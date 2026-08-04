from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone

import pytest

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleAttemptId,
    LifecycleAttemptResult,
    LifecycleConfigurationReference,
    LifecycleEvent,
    LifecycleEventId,
    LifecycleEventType,
    LifecycleModelVersionReference,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
    LifecycleRetryState,
    LifecycleRun,
    LifecycleRunId,
    LifecycleStage,
    StageReceipt,
    configuration_manifest_hash,
    model_version_manifest_hash,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import canonical_hash


UTC = timezone.utc
T0 = datetime(2026, 8, 4, 6, 55, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


def _reference() -> LifecycleObjectReference:
    return LifecycleObjectReference(
        object_type=LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
        object_id=LifecycleObjectId("composite-1"),
        content_hash=HASH_A,
        reader_kind=LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER,
        locator="artifacts/composite-1",
        available_at=T0,
    )


def _configuration() -> LifecycleConfigurationReference:
    return LifecycleConfigurationReference(
        configuration_id=ArtifactId("configuration-1"),
        configuration_version="1.0.0",
        content_hash=HASH_B,
    )


def _model() -> LifecycleModelVersionReference:
    return LifecycleModelVersionReference(
        model_id=ModelId("model-1"),
        model_version="1.0.0",
        content_hash=HASH_C,
    )


def _run() -> LifecycleRun:
    configurations = (_configuration(),)
    models = (_model(),)
    return LifecycleRun(
        run_id=LifecycleRunId("lifecycle-run-1"),
        idempotency_key="request-1",
        command_hash=HASH_A,
        run_type=LifecycleRunType.CANONICAL_DECISION_LIFECYCLE,
        decision_date=date(2026, 8, 4),
        as_of_time=T0,
        status=LifecycleRunStatus.RUNNING,
        current_stage=LifecycleStageName.PLATFORM_RESEARCH,
        input_manifest_id=ArtifactId("input-manifest-1"),
        input_content_hash=HASH_B,
        completed_stages=(LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,),
        configuration_references=configurations,
        configuration_manifest_hash=configuration_manifest_hash(configurations),
        model_references=models,
        model_version_manifest_hash=model_version_manifest_hash(models),
        retry_state=LifecycleRetryState.NOT_REQUIRED,
        failure_reason=None,
        blocker_reason=None,
        created_at=T0,
        updated_at=T0 + timedelta(seconds=1),
        completed_at=None,
        version=2,
        claim_token=1,
    )


def test_reference_and_all_journal_records_round_trip_canonically() -> None:
    reference = _reference()
    run = _run()
    stage = LifecycleStage(
        run_id=run.run_id,
        stage_name=LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
        stage_status=LifecycleStageStatus.COMPLETED,
        attempt_count=1,
        input_references=(reference,),
        output_references=(reference,),
        started_at=T0,
        completed_at=T0 + timedelta(seconds=1),
        failure_reason=None,
        blocker_reason=None,
        version=2,
    )
    attempt = LifecycleAttempt(
        attempt_id=LifecycleAttemptId("attempt-1"),
        run_id=run.run_id,
        stage_name=stage.stage_name,
        attempt_number=1,
        started_at=T0,
        completed_at=T0 + timedelta(seconds=1),
        result=LifecycleAttemptResult.COMPLETED,
        exception_type=None,
        exception_message=None,
        claim_token=1,
    )
    receipt = StageReceipt.create(
        run_id=run.run_id,
        stage_name=stage.stage_name,
        attempt_number=1,
        input_hashes=(HASH_A,),
        output_hashes=(HASH_B,),
        model_versions=("model-1@1.0.0",),
        configuration_hashes=(HASH_C,),
        reason_codes=("VERIFIED",),
        stage_result=LifecycleStageStatus.COMPLETED,
        created_at=T0 + timedelta(seconds=1),
    )
    event = LifecycleEvent(
        event_id=LifecycleEventId("event-1"),
        run_id=run.run_id,
        sequence_number=1,
        event_type=LifecycleEventType.RUN_CREATED,
        from_status=None,
        to_status=LifecycleRunStatus.CREATED,
        stage_name=None,
        attempt_id=None,
        receipt_id=None,
        reason_codes=(),
        payload_hash=canonical_hash({"event": "created"}),
        created_at=T0,
        claim_token=0,
    )

    pairs = (
        (reference, LifecycleObjectReference),
        (run, LifecycleRun),
        (stage, LifecycleStage),
        (attempt, LifecycleAttempt),
        (receipt, StageReceipt),
        (event, LifecycleEvent),
    )
    for original, contract in pairs:
        restored = contract.from_canonical_dict(original.to_canonical_dict())
        assert restored == original
        assert restored.to_canonical_dict() == original.to_canonical_dict()
    with pytest.raises(FrozenInstanceError):
        run.version = 99  # type: ignore[misc]


def test_receipt_identity_excludes_attempt_and_wall_clock_audit_values() -> None:
    def build(attempt_number: int, created_at: datetime) -> StageReceipt:
        return StageReceipt.create(
            run_id=LifecycleRunId("lifecycle-run-1"),
            stage_name=LifecycleStageName.SIGNAL,
            attempt_number=attempt_number,
            input_hashes=(HASH_A,),
            output_hashes=(HASH_B,),
            model_versions=("signal-model@1",),
            configuration_hashes=(HASH_C,),
            reason_codes=("SIGNAL_READY",),
            stage_result=LifecycleStageStatus.COMPLETED,
            created_at=created_at,
        )

    first = build(1, T0)
    replay = build(2, T0 + timedelta(hours=1))
    assert first.receipt_hash == replay.receipt_hash
    assert first.receipt_id == replay.receipt_id
    assert first.attempt_number != replay.attempt_number
    assert first.created_at != replay.created_at


def test_receipt_rejects_semantic_hash_or_identity_tamper() -> None:
    receipt = StageReceipt.create(
        run_id=LifecycleRunId("run-1"),
        stage_name=LifecycleStageName.SIGNAL,
        attempt_number=1,
        input_hashes=(HASH_A,),
        output_hashes=(HASH_B,),
        model_versions=(),
        configuration_hashes=(),
        reason_codes=(),
        stage_result=LifecycleStageStatus.COMPLETED,
        created_at=T0,
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(receipt, output_hashes=(HASH_C,))
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(receipt, receipt_id=ArtifactId("wrong"))


def test_records_reject_non_utc_fractional_or_naive_times() -> None:
    reference = _reference()
    for invalid in (
        T0.replace(tzinfo=None),
        T0.replace(microsecond=1),
        T0.astimezone(timezone(timedelta(hours=8))),
    ):
        with pytest.raises(ValueError):
            replace(reference, available_at=invalid)


def test_records_reject_unsorted_ambiguous_references_and_invalid_versions() -> None:
    first = _reference()
    second = replace(
        first,
        object_id=LifecycleObjectId("composite-2"),
        content_hash=HASH_B,
    )
    with pytest.raises(ValueError, match="lifecycle order"):
        replace(
            _run(),
            completed_stages=(
                LifecycleStageName.PLATFORM_RESEARCH,
                LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
            ),
        )
    with pytest.raises(ValueError, match="different object IDs"):
        LifecycleStage(
            run_id=LifecycleRunId("run-1"),
            stage_name=LifecycleStageName.SIGNAL,
            stage_status=LifecycleStageStatus.PENDING,
            attempt_count=0,
            input_references=tuple(
                sorted((first, replace(second, content_hash=HASH_A)), key=lambda item: item.sort_key)
            ),
            output_references=(),
            started_at=None,
            completed_at=None,
            failure_reason=None,
            blocker_reason=None,
            version=1,
        )
    with pytest.raises(ValueError, match="version"):
        replace(_run(), version=0)


@pytest.mark.parametrize(
    ("status", "attempt_count", "failure", "blocker"),
    (
        (LifecycleStageStatus.PENDING, 1, None, None),
        (LifecycleStageStatus.FAILED, 1, None, None),
        (LifecycleStageStatus.WAITING, 1, None, None),
        (LifecycleStageStatus.COMPLETED, 1, "failure", None),
    ),
)
def test_stage_projection_rejects_incoherent_state(
    status: LifecycleStageStatus,
    attempt_count: int,
    failure: str | None,
    blocker: str | None,
) -> None:
    with pytest.raises(ValueError):
        LifecycleStage(
            run_id=LifecycleRunId("run-1"),
            stage_name=LifecycleStageName.SIGNAL,
            stage_status=status,
            attempt_count=attempt_count,
            input_references=(),
            output_references=(),
            started_at=T0 if attempt_count else None,
            completed_at=T0 if status is not LifecycleStageStatus.PENDING else None,
            failure_reason=failure,
            blocker_reason=blocker,
            version=1,
        )


def test_failed_attempt_requires_explicit_exception_and_positive_claim() -> None:
    with pytest.raises(ValueError, match="exception"):
        LifecycleAttempt(
            attempt_id=LifecycleAttemptId("attempt-1"),
            run_id=LifecycleRunId("run-1"),
            stage_name=LifecycleStageName.SIGNAL,
            attempt_number=1,
            started_at=T0,
            completed_at=T0,
            result=LifecycleAttemptResult.FAILED,
            exception_type=None,
            exception_message=None,
            claim_token=1,
        )
