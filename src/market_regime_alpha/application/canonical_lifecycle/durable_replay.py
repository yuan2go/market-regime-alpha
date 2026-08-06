"""Durable replay orchestration isolated from lifecycle business handlers.

Replay is an audit operation.  It recomputes pure Artifacts, reloads durable
objects through explicit Readers, and journals that verification under a new
``REPLAY`` run.  It never invokes the canonical Runner or a domain mutation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectReference,
    LifecycleRun,
    LifecycleRunId,
    LifecycleStage,
    StageReceipt,
    require_utc_second,
)
from market_regime_alpha.application.canonical_lifecycle.replay import (
    LifecycleReplayCheck,
    LifecycleReplayReport,
    ReplayCheckStatus,
    load_lifecycle_replay_report,
    publish_lifecycle_replay_report,
    receipt_semantic_fingerprint,
    verify_lifecycle_replay,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleHistory,
    LifecycleIdempotencyConflict,
    LifecycleJournalIntegrityError,
    LifecycleRunRepository,
    StageFailure,
    StageTransition,
)
from market_regime_alpha.application.canonical_lifecycle.replay_snapshot import (
    lifecycle_history_hash,
    load_or_recover_source_snapshot as _load_or_recover_source_snapshot,
    publish_source_history_snapshot as _publish_source_history_snapshot,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    TERMINAL_LIFECYCLE_STAGE_STATUSES,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.core.identity import ManualTradeId
from market_regime_alpha.evidence.canonical import require_sha256


Clock = Callable[[], datetime]
ManualTradeLoader = Callable[[ManualTradeId], object]


@dataclass(frozen=True, slots=True)
class DurableLifecycleReplayResult:
    """One content-addressed report plus its independent journal authority."""

    replay_run: LifecycleRun
    source_run_id: LifecycleRunId
    source_command_hash: str
    source_history_hash: str
    report: LifecycleReplayReport
    report_path: Path

    def __post_init__(self) -> None:
        if self.replay_run.run_type is not LifecycleRunType.REPLAY:
            raise ValueError("durable replay result requires a REPLAY run")
        if self.replay_run.source_run_id != self.source_run_id:
            raise ValueError("replay run source identity mismatch")
        if self.replay_run.source_command_hash != self.source_command_hash:
            raise ValueError("replay run source command mismatch")
        if self.replay_run.source_history_hash != self.source_history_hash:
            raise ValueError("replay run source history mismatch")
        if self.replay_run.replay_report_hash != self.report.report_hash:
            raise ValueError("replay run report hash mismatch")
        require_sha256("source_command_hash", self.source_command_hash)
        require_sha256("source_history_hash", self.source_history_hash)
        if self.report.run_id != self.source_run_id:
            raise ValueError("replay report must bind the source run")
        if self.report.command_hash != self.source_command_hash:
            raise ValueError("replay report must bind the source command")
        if self.report.journal_hash != self.source_history_hash:
            raise ValueError("replay report must bind the source journal")
        if self.report_path.parent.name != self.report.report_hash.split(":", 1)[1]:
            raise ValueError("report path must be content-addressed")


def run_durable_lifecycle_replay(
    *,
    repository: LifecycleRunRepository,
    source_run_id: LifecycleRunId,
    idempotency_key: str,
    clock: Clock,
    output_directory: Path | None = None,
    manual_trade_loader: ManualTradeLoader | None = None,
) -> DurableLifecycleReplayResult:
    """Create or reuse an audit-only replay run for one captured source view."""

    if not isinstance(source_run_id, LifecycleRunId):
        raise TypeError("source_run_id must be a LifecycleRunId")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key must be non-empty")
    if not callable(clock):
        raise TypeError("clock must be callable")
    existing = repository.get_run_by_idempotency_key(idempotency_key)
    if existing is None:
        source_command = repository.get_command(source_run_id)
        source_history = repository.history(source_run_id)
        _validate_source_view(source_run_id, source_command, source_history)
        source_history_hash = lifecycle_history_hash(source_history)
        report = _build_durable_report(
            source_command=source_command,
            source_history=source_history,
            manual_trade_loader=manual_trade_loader,
        )
        if report.journal_hash != source_history_hash:
            raise LifecycleJournalIntegrityError(
                "replay report source history mismatch"
            )
        replay_root = (
            output_directory.resolve()
            if output_directory is not None
            else source_command.output_directory / "replay"
        )
        _publish_source_history_snapshot(
            root=replay_root,
            source_command=source_command,
            source_history=source_history,
        )
        report_path = publish_lifecycle_replay_report(
            root=replay_root,
            report=report,
        )
        replay_command = _build_replay_command(
            source_run_id=source_run_id,
            source_command=source_command,
            source_history_hash=source_history_hash,
            report=report,
            idempotency_key=idempotency_key,
            replay_root=replay_root,
        )
        replay_run = repository.create_or_get(
            replay_command,
            created_at=_now(clock),
        )
    else:
        (
            replay_command,
            replay_run,
            source_command,
            source_history,
            report,
            report_path,
        ) = _load_existing_replay(
            repository=repository,
            existing=existing,
            source_run_id=source_run_id,
            idempotency_key=idempotency_key,
        )
    operation_clock = _MonotonicReplayClock(
        delegate=clock,
        last_value=replay_run.updated_at,
    )
    if replay_run.status in {
        LifecycleRunStatus.COMPLETED,
        LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
        LifecycleRunStatus.WAITING_FOR_ENTRY_CONFIRMATION,
        LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION,
        LifecycleRunStatus.WAITING_FOR_FILL,
        LifecycleRunStatus.WAITING_FOR_T1,
    }:
        return _result(replay_run, report, report_path)
    if replay_run.status is LifecycleRunStatus.FAILED:
        replay_run = repository.resume(
            replay_run.run_id,
            resumed_at=_now(operation_clock),
        )

    claimed = repository.claim(
        replay_run.run_id,
        expected_version=replay_run.version,
        claimed_at=_now(operation_clock),
    )
    source_receipts = {item.stage_name: item for item in source_history.receipts}
    failure_stage = _first_failed_stage(source_history, report)
    for stage_name in LIFECYCLE_STAGE_ORDER:
        replay_history = repository.history(claimed.run_id)
        replay_stage = _stage(replay_history, stage_name)
        if replay_stage.stage_status in TERMINAL_LIFECYCLE_STAGE_STATUSES:
            claimed = replay_history.run
            continue
        source_receipt = source_receipts.get(stage_name)
        source_stage = _stage(source_history, stage_name)
        if source_receipt is None:
            claimed = _settle_unexecuted_source_stage(
                repository=repository,
                replay_history=replay_history,
                replay_stage=replay_stage,
                source_stage=source_stage,
                clock=operation_clock,
            )
            continue
        if failure_stage is stage_name:
            claimed = _fail_replay_stage(
                repository=repository,
                replay_history=replay_history,
                replay_stage=replay_stage,
                source_stage=source_stage,
                clock=operation_clock,
            )
            break
        claimed = _mirror_source_receipt(
            repository=repository,
            replay_history=replay_history,
            replay_stage=replay_stage,
            source_history=source_history,
            source_stage=source_stage,
            source_receipt=source_receipt,
            clock=operation_clock,
        )
        if claimed.status is not LifecycleRunStatus.RUNNING:
            break

    return _result(repository.get_run(replay_command.run_id), report, report_path)


def _validate_source_view(
    source_run_id: LifecycleRunId,
    source_command: CanonicalLifecycleCommand,
    source_history: LifecycleHistory,
) -> None:
    if source_history.run.run_type is LifecycleRunType.REPLAY:
        raise ValueError("a durable replay cannot use another REPLAY run as source")
    if (
        source_command.run_id != source_run_id
        or source_history.run.run_id != source_run_id
        or source_command.command_hash != source_history.run.command_hash
    ):
        raise LifecycleJournalIntegrityError(
            "source command and run identity are inconsistent"
        )


def _build_replay_command(
    *,
    source_run_id: LifecycleRunId,
    source_command: CanonicalLifecycleCommand,
    source_history_hash: str,
    report: LifecycleReplayReport,
    idempotency_key: str,
    replay_root: Path,
) -> CanonicalLifecycleCommand:
    return CanonicalLifecycleCommand(
        run_type=LifecycleRunType.REPLAY,
        decision_date=source_command.decision_date,
        as_of_time=source_command.as_of_time,
        idempotency_key=idempotency_key,
        input_manifest_id=source_command.input_manifest_id,
        input_content_hash=source_command.input_content_hash,
        input_manifest_locator=source_command.input_manifest_locator,
        input_references=source_command.input_references,
        configuration_references=source_command.configuration_references,
        model_references=source_command.model_references,
        stop_after_stage=None,
        output_directory=replay_root,
        source_run_id=source_run_id,
        source_command_hash=source_command.command_hash,
        source_history_hash=source_history_hash,
        replay_report_hash=report.report_hash,
    )


def _load_existing_replay(
    *,
    repository: LifecycleRunRepository,
    existing: LifecycleRun,
    source_run_id: LifecycleRunId,
    idempotency_key: str,
) -> tuple[
    CanonicalLifecycleCommand,
    LifecycleRun,
    CanonicalLifecycleCommand,
    LifecycleHistory,
    LifecycleReplayReport,
    Path,
]:
    if (
        existing.run_type is not LifecycleRunType.REPLAY
        or existing.source_run_id != source_run_id
        or existing.idempotency_key != idempotency_key
    ):
        raise LifecycleIdempotencyConflict(
            "replay idempotency key is already bound to different semantics"
        )
    replay_command = repository.get_command(existing.run_id)
    if (
        replay_command.run_type is not LifecycleRunType.REPLAY
        or replay_command.source_run_id != source_run_id
        or replay_command.command_hash != existing.command_hash
        or replay_command.source_history_hash != existing.source_history_hash
        or replay_command.replay_report_hash != existing.replay_report_hash
    ):
        raise LifecycleJournalIntegrityError(
            "stored replay command and run identity are inconsistent"
        )
    source_command, source_history = _load_or_recover_source_snapshot(
        repository=repository,
        replay_command=replay_command,
    )
    _validate_source_view(source_run_id, source_command, source_history)
    if lifecycle_history_hash(source_history) != existing.source_history_hash:
        raise LifecycleJournalIntegrityError(
            "stored replay source snapshot hash mismatch"
        )
    assert existing.replay_report_hash is not None
    report_path = (
        replay_command.output_directory
        / "replay-reports"
        / existing.replay_report_hash.split(":", 1)[1]
        / "report.json"
    )
    try:
        report = load_lifecycle_replay_report(report_path)
    except (OSError, TypeError, ValueError) as exc:
        raise LifecycleJournalIntegrityError(
            "stored replay report is unavailable or invalid"
        ) from exc
    if (
        report.report_hash != existing.replay_report_hash
        or report.run_id != source_run_id
        or report.command_hash != source_command.command_hash
        or report.journal_hash != existing.source_history_hash
    ):
        raise LifecycleJournalIntegrityError(
            "stored replay report does not bind the captured source snapshot"
        )
    return (
        replay_command,
        existing,
        source_command,
        source_history,
        report,
        report_path,
    )


def _build_durable_report(
    *,
    source_command: CanonicalLifecycleCommand,
    source_history: LifecycleHistory,
    manual_trade_loader: ManualTradeLoader | None,
) -> LifecycleReplayReport:
    base = verify_lifecycle_replay(
        repository=_HistoryBoundRepository(source_command, source_history),
        run_id=source_history.run.run_id,
        manual_trade_loader=manual_trade_loader,
    )
    checks_by_subject = {item.subject: item for item in base.checks}
    if len(checks_by_subject) != len(base.checks):
        raise LifecycleJournalIntegrityError("replay checks have duplicate subjects")
    receipt_checks = tuple(
        _receipt_check(
            source_command=source_command,
            source_stage=_stage(source_history, receipt.stage_name),
            source_receipt=receipt,
            object_checks=checks_by_subject,
        )
        for receipt in source_history.receipts
    )
    return LifecycleReplayReport.create(
        run_id=source_history.run.run_id,
        command_hash=source_command.command_hash,
        journal_hash=lifecycle_history_hash(source_history),
        checks=tuple((*checks_by_subject.values(), *receipt_checks)),
    )


class _HistoryBoundRepository:
    """Minimal immutable view used by the existing replay verifier."""

    def __init__(
        self,
        command: CanonicalLifecycleCommand,
        history: LifecycleHistory,
    ) -> None:
        self._command = command
        self._history = history

    def get_command(self, run_id: LifecycleRunId) -> CanonicalLifecycleCommand:
        if run_id != self._history.run.run_id:
            raise KeyError(str(run_id))
        return self._command

    def history(self, run_id: LifecycleRunId) -> LifecycleHistory:
        if run_id != self._history.run.run_id:
            raise KeyError(str(run_id))
        return self._history


def _receipt_check(
    *,
    source_command: CanonicalLifecycleCommand,
    source_stage: LifecycleStage,
    source_receipt: StageReceipt,
    object_checks: dict[str, LifecycleReplayCheck],
) -> LifecycleReplayCheck:
    expected = receipt_semantic_fingerprint(source_receipt)
    relevant = [
        object_checks[_reference_subject(reference)]
        for reference in (*source_stage.input_references, *source_stage.output_references)
    ]
    configuration_checks = {
        reference.content_hash: object_checks.get(
            "CONFIGURATION:"
            f"{reference.configuration_kind.value}:"
            f"{reference.configuration_id}"
        )
        for reference in source_command.configuration_references
    }
    relevant.extend(
        check
        for content_hash in source_receipt.configuration_hashes
        if (check := configuration_checks.get(content_hash)) is not None
    )
    subject = f"RECEIPT:{source_receipt.stage_name.value}"
    if any(item.status is ReplayCheckStatus.FAILED for item in relevant):
        return LifecycleReplayCheck(
            subject=subject,
            status=ReplayCheckStatus.FAILED,
            expected_hash=expected,
            observed_hash=None,
            detail="RECEIPT_INPUT_OR_OUTPUT_REPLAY_FAILED",
        )
    if any(item.status is ReplayCheckStatus.NOT_COMPARABLE for item in relevant):
        return LifecycleReplayCheck(
            subject=subject,
            status=ReplayCheckStatus.NOT_COMPARABLE,
            expected_hash=expected,
            observed_hash=None,
            detail="RECEIPT_FINGERPRINT_NOT_COMPARABLE",
        )
    return LifecycleReplayCheck(
        subject=subject,
        status=ReplayCheckStatus.REPLAY_STABLE,
        expected_hash=expected,
        observed_hash=expected,
        detail="CROSS_RUN_RECEIPT_SEMANTIC_FINGERPRINT_MATCH",
    )


def _first_failed_stage(
    source_history: LifecycleHistory,
    report: LifecycleReplayReport,
) -> LifecycleStageName | None:
    failed_subjects = {
        item.subject
        for item in report.checks
        if item.status is ReplayCheckStatus.FAILED
    }
    if not failed_subjects:
        return None
    for stage_name in LIFECYCLE_STAGE_ORDER:
        if f"RECEIPT:{stage_name.value}" in failed_subjects:
            return stage_name
    return next(
        (
            item.stage_name
            for item in source_history.receipts
        ),
        LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
    )


def _mirror_source_receipt(
    *,
    repository: LifecycleRunRepository,
    replay_history: LifecycleHistory,
    replay_stage: LifecycleStage,
    source_history: LifecycleHistory,
    source_stage: LifecycleStage,
    source_receipt: StageReceipt,
    clock: Clock,
) -> LifecycleRun:
    attempt = repository.start_stage(
        replay_history.run.run_id,
        replay_stage.stage_name,
        started_at=_now(clock),
        claim_token=replay_history.run.claim_token,
    )
    running_history = repository.history(replay_history.run.run_id)
    running_stage = _stage(running_history, replay_stage.stage_name)
    completed_at = _now(clock)
    receipt = StageReceipt.create(
        run_id=running_history.run.run_id,
        stage_name=source_receipt.stage_name,
        attempt_number=attempt.attempt_number,
        input_hashes=source_receipt.input_hashes,
        output_hashes=source_receipt.output_hashes,
        model_versions=source_receipt.model_versions,
        configuration_hashes=source_receipt.configuration_hashes,
        reason_codes=source_receipt.reason_codes,
        stage_result=source_receipt.stage_result,
        created_at=completed_at,
    )
    if receipt_semantic_fingerprint(receipt) != receipt_semantic_fingerprint(
        source_receipt
    ):
        raise LifecycleJournalIntegrityError(
            "cross-run receipt semantic fingerprint mismatch"
        )
    target_status = _target_status(
        source_history=source_history,
        source_stage=source_stage,
    )
    blocker_reason = (
        source_stage.blocker_reason
        if (
            source_receipt.stage_result
            in {
                LifecycleStageStatus.WAITING,
                LifecycleStageStatus.BLOCKED,
                LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
            }
            or target_status
            in {
                LifecycleRunStatus.WAITING_FOR_ENTRY_CONFIRMATION,
                LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
                LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION,
                LifecycleRunStatus.WAITING_FOR_FILL,
                LifecycleRunStatus.WAITING_FOR_T1,
            }
        )
        else None
    )
    if blocker_reason is None and target_status is not LifecycleRunStatus.RUNNING:
        blocker_reason = source_history.run.blocker_reason
    return repository.finish_stage(
        StageTransition(
            run_id=running_history.run.run_id,
            stage_name=running_stage.stage_name,
            attempt_id=attempt.attempt_id,
            expected_run_version=running_history.run.version,
            expected_stage_version=running_stage.version,
            claim_token=running_history.run.claim_token,
            target_run_status=target_status,
            receipt=receipt,
            input_references=source_stage.input_references,
            output_references=source_stage.output_references,
            blocker_reason=blocker_reason,
            completed_at=completed_at,
        )
    )


def _settle_unexecuted_source_stage(
    *,
    repository: LifecycleRunRepository,
    replay_history: LifecycleHistory,
    replay_stage: LifecycleStage,
    source_stage: LifecycleStage,
    clock: Clock,
) -> LifecycleRun:
    attempt = repository.start_stage(
        replay_history.run.run_id,
        replay_stage.stage_name,
        started_at=_now(clock),
        claim_token=replay_history.run.claim_token,
    )
    running_history = repository.history(replay_history.run.run_id)
    running_stage = _stage(running_history, replay_stage.stage_name)
    completed_at = _now(clock)
    final_stage = replay_stage.stage_name is LIFECYCLE_STAGE_ORDER[-1]
    receipt = StageReceipt.create(
        run_id=running_history.run.run_id,
        stage_name=replay_stage.stage_name,
        attempt_number=attempt.attempt_number,
        input_hashes=(),
        output_hashes=(),
        model_versions=(),
        configuration_hashes=(),
        reason_codes=tuple(
            sorted(
                {
                    "REPLAY_SOURCE_STAGE_NOT_SETTLED",
                    f"SOURCE_STAGE_STATUS_{source_stage.stage_status.value}",
                }
            )
        ),
        stage_result=LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
        created_at=completed_at,
    )
    return repository.finish_stage(
        StageTransition(
            run_id=running_history.run.run_id,
            stage_name=running_stage.stage_name,
            attempt_id=attempt.attempt_id,
            expected_run_version=running_history.run.version,
            expected_stage_version=running_stage.version,
            claim_token=running_history.run.claim_token,
            target_run_status=(
                LifecycleRunStatus.COMPLETED
                if final_stage
                else LifecycleRunStatus.RUNNING
            ),
            receipt=receipt,
            input_references=(),
            output_references=(),
            blocker_reason="Source stage was not settled and was not replayed",
            completed_at=completed_at,
        )
    )


def _fail_replay_stage(
    *,
    repository: LifecycleRunRepository,
    replay_history: LifecycleHistory,
    replay_stage: LifecycleStage,
    source_stage: LifecycleStage,
    clock: Clock,
) -> LifecycleRun:
    attempt = repository.start_stage(
        replay_history.run.run_id,
        replay_stage.stage_name,
        started_at=_now(clock),
        claim_token=replay_history.run.claim_token,
    )
    running_history = repository.history(replay_history.run.run_id)
    running_stage = _stage(running_history, replay_stage.stage_name)
    return repository.mark_stage_failed(
        StageFailure(
            run_id=running_history.run.run_id,
            stage_name=running_stage.stage_name,
            attempt_id=attempt.attempt_id,
            expected_run_version=running_history.run.version,
            expected_stage_version=running_stage.version,
            claim_token=running_history.run.claim_token,
            input_references=source_stage.input_references,
            exception_type="ReplayVerificationFailed",
            exception_message=(
                "recorded input, output, configuration, or receipt did not replay"
            ),
            failed_at=_now(clock),
        )
    )


def _target_status(
    *, source_history: LifecycleHistory, source_stage: LifecycleStage
) -> LifecycleRunStatus:
    source_run = source_history.run
    if source_run.current_stage is source_stage.stage_name and source_run.status not in {
        LifecycleRunStatus.RUNNING,
        LifecycleRunStatus.CREATED,
    }:
        return source_run.status
    if source_stage.stage_name is LIFECYCLE_STAGE_ORDER[-1]:
        return LifecycleRunStatus.COMPLETED
    return LifecycleRunStatus.RUNNING


def _all_references(
    command: CanonicalLifecycleCommand,
    history: LifecycleHistory,
) -> tuple[LifecycleObjectReference, ...]:
    values: dict[tuple[str, str, str], LifecycleObjectReference] = {}
    for reference in command.input_references:
        values[reference.sort_key] = reference
    for stage in history.stages:
        for reference in (*stage.input_references, *stage.output_references):
            existing = values.setdefault(reference.sort_key, reference)
            if existing != reference:
                raise LifecycleJournalIntegrityError(
                    "source journal carries conflicting references"
                )
    return tuple(sorted(values.values(), key=lambda item: item.sort_key))


def _reference_subject(reference: LifecycleObjectReference) -> str:
    return f"OBJECT:{reference.object_type.value}:{reference.object_id}"


def _stage(history: LifecycleHistory, name: LifecycleStageName) -> LifecycleStage:
    matches = tuple(item for item in history.stages if item.stage_name is name)
    if len(matches) != 1:
        raise LifecycleJournalIntegrityError(
            f"journal must contain exactly one {name.value} stage"
        )
    return matches[0]


def _now(clock: Clock) -> datetime:
    value = clock()
    require_utc_second("clock", value)
    return value


@dataclass(slots=True)
class _MonotonicReplayClock:
    """Advance from durable journal time without consulting wall-clock state."""

    delegate: Clock
    last_value: datetime

    def __call__(self) -> datetime:
        observed = self.delegate()
        require_utc_second("clock", observed)
        minimum = self.last_value + timedelta(seconds=1)
        self.last_value = max(observed, minimum)
        return self.last_value


def _result(
    replay_run: LifecycleRun,
    report: LifecycleReplayReport,
    report_path: Path,
) -> DurableLifecycleReplayResult:
    assert replay_run.source_run_id is not None
    assert replay_run.source_command_hash is not None
    assert replay_run.source_history_hash is not None
    return DurableLifecycleReplayResult(
        replay_run=replay_run,
        source_run_id=replay_run.source_run_id,
        source_command_hash=replay_run.source_command_hash,
        source_history_hash=replay_run.source_history_hash,
        report=report,
        report_path=report_path,
    )
