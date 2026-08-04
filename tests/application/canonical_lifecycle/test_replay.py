from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sqlite3

import pytest

from market_regime_alpha.application.canonical_lifecycle.durable_replay import (
    lifecycle_history_hash,
    run_durable_lifecycle_replay,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleRunId,
)
from market_regime_alpha.application.canonical_lifecycle.replay import (
    LifecycleReplayStatus,
    receipt_semantic_fingerprint,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleIdempotencyConflict,
)
from tests.application.canonical_lifecycle.test_lifecycle_integration import (
    _confirmation_command_for_references,
    _execution_counts,
    _risk_command,
    _risk_continuation_as_of,
    _risk_references,
    _risk_runner,
    _table_names,
)
from tests.application.canonical_lifecycle.test_lifecycle_integration import (
    _TickingClock,
    _canonical_command,
    _canonical_fixture,
    _canonical_runner,
)
from tests.execution.risk_reduction_confirmation_support import (
    build_confirmation_fixture,
)


pytest_plugins = ("tests.daily_decision.conftest",)


class _FailFirstReplaySettlement:
    def __init__(self) -> None:
        self.raised = False

    def __call__(self, point: str) -> None:
        if point == "finish_after_attempt" and not self.raised:
            self.raised = True
            raise RuntimeError("injected durable replay journal crash")


def test_durable_replay_journals_blocked_entry_source_without_mutating_it(
    tmp_path: Path,
) -> None:
    fixture, manifest_path = _canonical_fixture(tmp_path / "source")
    repository = SQLiteLifecycleRunRepository(tmp_path / "lifecycle.sqlite3")
    source_output = tmp_path / "source-runtime"
    command = _canonical_command(
        fixture,
        manifest_path=manifest_path,
        idempotency_key="source-canonical-run",
        output_root=source_output,
    )
    source = _canonical_runner(
        fixture,
        repository=repository,
        output_root=source_output,
        clock_start=fixture.as_of_time + timedelta(hours=2),
    ).run(command)
    assert source.run.status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    source_before = repository.history(source.run.run_id)
    source_hash = lifecycle_history_hash(source_before)
    clock = _TickingClock(fixture.as_of_time + timedelta(hours=4))

    first = run_durable_lifecycle_replay(
        repository=repository,
        source_run_id=source.run.run_id,
        idempotency_key="durable-replay-1",
        clock=clock,
        output_directory=tmp_path / "replay-runtime",
    )

    assert first.replay_run.run_type is LifecycleRunType.REPLAY
    assert first.replay_run.source_run_id == source.run.run_id
    assert first.replay_run.source_command_hash == source.run.command_hash
    assert first.replay_run.source_history_hash == source_hash
    assert first.replay_run.status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    assert first.report.status is LifecycleReplayStatus.STABLE
    assert first.report_path.is_file()
    replay_history = repository.history(first.replay_run.run_id)
    assert [item.stage_name for item in replay_history.receipts] == [
        LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
        LifecycleStageName.PLATFORM_RESEARCH,
        LifecycleStageName.SIGNAL,
        LifecycleStageName.PATH_FORECAST,
        LifecycleStageName.ENTRY_ASSESSMENT,
    ]
    assert replay_history.stages[4].stage_status is LifecycleStageStatus.BLOCKED
    source_receipts = {item.stage_name: item for item in source_before.receipts}
    assert all(
        receipt_semantic_fingerprint(receipt)
        == receipt_semantic_fingerprint(source_receipts[receipt.stage_name])
        for receipt in replay_history.receipts
    )
    assert any(
        check.subject == "RECEIPT:PLATFORM_RESEARCH"
        and check.detail == "CROSS_RUN_RECEIPT_SEMANTIC_FINGERPRINT_MATCH"
        for check in first.report.checks
    )
    assert any(
        check.subject.startswith("OBJECT:PLATFORM_RESEARCH_ARTIFACT:")
        and check.detail == "PLATFORM_RESEARCH_PURE_REPLAY_STABLE"
        for check in first.report.checks
    )
    assert any(
        check.subject.startswith("OBJECT:SIGNAL_ARTIFACT:")
        and check.detail == "SIGNAL_PURE_REPLAY_STABLE"
        for check in first.report.checks
    )
    assert any(
        check.subject.startswith("OBJECT:PATH_FORECAST_ARTIFACT:")
        and check.detail == "PATH_FORECAST_PURE_REPLAY_STABLE"
        for check in first.report.checks
    )
    assert lifecycle_history_hash(repository.history(source.run.run_id)) == source_hash

    attempts_before = replay_history.attempts
    second = run_durable_lifecycle_replay(
        repository=repository,
        source_run_id=source.run.run_id,
        idempotency_key="durable-replay-1",
        clock=clock,
        output_directory=tmp_path / "replay-runtime",
    )
    assert second.replay_run.run_id == first.replay_run.run_id
    assert second.report.report_hash == first.report.report_hash
    assert repository.history(second.replay_run.run_id).attempts == attempts_before


def test_durable_replay_tamper_fails_closed_without_mutating_source(
    tmp_path: Path,
) -> None:
    fixture, manifest_path = _canonical_fixture(tmp_path / "source")
    repository = SQLiteLifecycleRunRepository(tmp_path / "lifecycle.sqlite3")
    source_output = tmp_path / "source-runtime"
    command = _canonical_command(
        fixture,
        manifest_path=manifest_path,
        idempotency_key="tamper-source",
        output_root=source_output,
    )
    source = _canonical_runner(
        fixture,
        repository=repository,
        output_root=source_output,
        clock_start=fixture.as_of_time + timedelta(hours=2),
    ).run(command)
    source_before = repository.history(source.run.run_id)
    source_hash = lifecycle_history_hash(source_before)
    signal_reference = source_before.stages[2].output_references[0]
    assert signal_reference.locator is not None
    (Path(signal_reference.locator) / "manifest.json").write_text(
        "{}", encoding="utf-8"
    )

    replay = run_durable_lifecycle_replay(
        repository=repository,
        source_run_id=source.run.run_id,
        idempotency_key="tamper-replay",
        clock=_TickingClock(fixture.as_of_time + timedelta(hours=4)),
        output_directory=tmp_path / "replay-runtime",
    )

    assert replay.report.status is LifecycleReplayStatus.FAILED
    assert replay.replay_run.status is LifecycleRunStatus.FAILED
    history = repository.history(replay.replay_run.run_id)
    assert history.stages[2].stage_status is LifecycleStageStatus.FAILED
    assert history.attempts[-1].exception_type == "ReplayVerificationFailed"
    assert lifecycle_history_hash(repository.history(source.run.run_id)) == source_hash


def test_durable_replay_resumes_an_interrupted_journal_attempt(
    tmp_path: Path,
) -> None:
    fixture, manifest_path = _canonical_fixture(tmp_path / "source")
    journal_path = tmp_path / "lifecycle.sqlite3"
    source_repository = SQLiteLifecycleRunRepository(journal_path)
    source_output = tmp_path / "source-runtime"
    command = _canonical_command(
        fixture,
        manifest_path=manifest_path,
        idempotency_key="replay-recovery-source",
        output_root=source_output,
    )
    source = _canonical_runner(
        fixture,
        repository=source_repository,
        output_root=source_output,
        clock_start=fixture.as_of_time + timedelta(hours=2),
    ).run(command)
    source_hash = lifecycle_history_hash(
        source_repository.history(source.run.run_id)
    )
    failure = _FailFirstReplaySettlement()
    crashing_repository = SQLiteLifecycleRunRepository(
        journal_path,
        fault_injector=failure,
    )

    with pytest.raises(RuntimeError, match="durable replay journal crash"):
        run_durable_lifecycle_replay(
            repository=crashing_repository,
            source_run_id=source.run.run_id,
            idempotency_key="durable-replay-recovery",
            clock=_TickingClock(fixture.as_of_time + timedelta(hours=4)),
            output_directory=tmp_path / "replay-runtime",
        )

    with sqlite3.connect(journal_path) as connection:
        replay_run_id = str(
            connection.execute(
                "SELECT run_id FROM lifecycle_runs WHERE run_type = 'REPLAY'"
            ).fetchone()[0]
        )
    interrupted = crashing_repository.history(LifecycleRunId(replay_run_id))
    assert interrupted.run.status is LifecycleRunStatus.RUNNING
    assert interrupted.stages[0].stage_status is LifecycleStageStatus.RUNNING
    assert interrupted.stages[0].attempt_count == 1

    recovered = run_durable_lifecycle_replay(
        repository=SQLiteLifecycleRunRepository(journal_path),
        source_run_id=source.run.run_id,
        idempotency_key="durable-replay-recovery",
        clock=_TickingClock(fixture.as_of_time + timedelta(hours=4)),
        output_directory=tmp_path / "replay-runtime",
    )

    assert str(recovered.replay_run.run_id) == replay_run_id
    assert recovered.replay_run.status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    recovered_history = SQLiteLifecycleRunRepository(journal_path).history(
        recovered.replay_run.run_id
    )
    assert recovered_history.stages[0].attempt_count == 2
    assert sum(
        receipt.stage_name is LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE
        for receipt in recovered_history.receipts
    ) == 1
    assert lifecycle_history_hash(
        source_repository.history(source.run.run_id)
    ) == source_hash


def test_replay_idempotency_key_rejects_a_different_source_run(
    tmp_path: Path,
) -> None:
    fixture, manifest_path = _canonical_fixture(tmp_path / "source")
    repository = SQLiteLifecycleRunRepository(tmp_path / "lifecycle.sqlite3")
    output = tmp_path / "source-runtime"
    clock = _TickingClock(fixture.as_of_time + timedelta(hours=2))
    first_source = _canonical_runner(
        fixture,
        repository=repository,
        output_root=output,
        clock_start=fixture.as_of_time + timedelta(hours=2),
    ).run(
        _canonical_command(
            fixture,
            manifest_path=manifest_path,
            idempotency_key="source-one",
            output_root=output,
        )
    )
    second_source = _canonical_runner(
        fixture,
        repository=repository,
        output_root=output,
        clock_start=fixture.as_of_time + timedelta(hours=3),
    ).run(
        _canonical_command(
            fixture,
            manifest_path=manifest_path,
            idempotency_key="source-two",
            output_root=output,
        )
    )
    run_durable_lifecycle_replay(
        repository=repository,
        source_run_id=first_source.run.run_id,
        idempotency_key="one-replay-key",
        clock=clock,
        output_directory=tmp_path / "replay-one",
    )

    with pytest.raises(LifecycleIdempotencyConflict):
        run_durable_lifecycle_replay(
            repository=repository,
            source_run_id=second_source.run.run_id,
            idempotency_key="one-replay-key",
            clock=clock,
            output_directory=tmp_path / "replay-two",
        )


def test_manual_trade_replay_uses_read_only_repository_and_creates_nothing(
    tmp_path: Path,
    daily_decision_fixture,
) -> None:
    authority = build_confirmation_fixture(tmp_path / "authority", daily_decision_fixture)
    references = _risk_references(authority, tmp_path)
    as_of = _risk_continuation_as_of(authority)
    command = _risk_command(
        authority=authority,
        references=references,
        as_of=as_of,
        idempotency_key="risk-source",
        root=tmp_path,
    )
    journal = SQLiteLifecycleRunRepository(tmp_path / "risk-journal.sqlite3")
    runner = _risk_runner(authority=authority, repository=journal, as_of=as_of)
    waiting = runner.run(command)
    assert waiting.run.status is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
    confirmed = authority.repository.confirm_risk_reduction(
        _confirmation_command_for_references(authority, references)
    )
    assert confirmed.manual_trade is not None
    source = runner.resume(command.run_id)
    assert source.run.status is LifecycleRunStatus.WAITING_FOR_FILL
    counts_before = _execution_counts(authority.repository)
    assert authority.repository.fills_for_trade(
        confirmed.manual_trade.manual_trade_id
    ) == ()

    replay = run_durable_lifecycle_replay(
        repository=journal,
        source_run_id=source.run.run_id,
        idempotency_key="manual-trade-replay",
        clock=_TickingClock(as_of + timedelta(hours=1)),
        output_directory=tmp_path / "risk-replay",
    )

    manual_check = next(
        item
        for item in replay.report.checks
        if item.subject.startswith("OBJECT:MANUAL_TRADE:")
    )
    assert manual_check.detail == "MANUAL_TRADE_REPOSITORY_OBJECT_VERIFIED_READ_ONLY"
    assert _execution_counts(authority.repository) == counts_before
    assert authority.repository.fills_for_trade(
        confirmed.manual_trade.manual_trade_id
    ) == ()
    assert not any(
        "broker" in table.lower() or "order" in table.lower()
        for table in _table_names(authority.repository.path)
    )
