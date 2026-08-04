from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from market_regime_alpha.application.canonical_lifecycle.runner import (
    CanonicalDecisionLifecycleRunner,
    LifecycleStageExecutionError,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleStageName,
    LifecycleStageStatus,
)
from tests.application.canonical_lifecycle.test_runner import (
    RecordingHandler,
    TickClock,
    _command,
    _completed_result,
    _handlers,
)


class DomainCrash(RuntimeError):
    pass


@dataclass
class RecoverableFaultHandler:
    stage_name: LifecycleStageName
    fault: str
    mutation_kind: StageMutationKind = StageMutationKind.IDEMPOTENT_MUTATION
    recover_calls: int = 0
    execute_calls: int = 0
    domain_committed: bool = False
    fault_raised: bool = False

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        self.recover_calls += 1
        if self.fault == "before_domain_call" and not self.fault_raised:
            self.fault_raised = True
            raise DomainCrash("before domain call")
        if self.domain_committed:
            return _completed_result(context)
        return None

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        self.execute_calls += 1
        if self.fault == "during_domain_call" and not self.fault_raised:
            self.fault_raised = True
            raise DomainCrash("during domain call")
        if self.fault == "after_domain_commit" and not self.fault_raised:
            self.domain_committed = True
            self.fault_raised = True
            raise DomainCrash("after domain commit before receipt")
        self.domain_committed = True
        return _completed_result(context)


def _recovery_handlers(
    target: RecoverableFaultHandler,
) -> tuple[RecordingHandler | RecoverableFaultHandler, ...]:
    calls: list[tuple[str, LifecycleStageName]] = []
    defaults = _handlers(calls)
    return (target, *defaults[1:])


@pytest.mark.parametrize(
    ("fault", "message", "execute_count_after_failure", "is_recovered"),
    (
        ("before_domain_call", "before domain call", 0, False),
        ("during_domain_call", "during domain call", 1, False),
        (
            "after_domain_commit",
            "after domain commit before receipt",
            1,
            True,
        ),
    ),
)
def test_failed_stage_records_exact_error_and_resumes_safely(
    tmp_path: Path,
    fault: str,
    message: str,
    execute_count_after_failure: int,
    is_recovered: bool,
) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / f"{fault}.sqlite3")
    handler = RecoverableFaultHandler(
        stage_name=LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
        fault=fault,
    )
    runner = CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=_recovery_handlers(handler),
        clock=TickClock(),
    )
    command = _command(idempotency_key=f"recovery-{fault}")

    with pytest.raises(LifecycleStageExecutionError) as captured:
        runner.run(command)

    assert captured.value.exception_type == "DomainCrash"
    assert captured.value.exception_message == message
    assert not captured.value.journal_settled
    failed_history = repository.history(command.run_id)
    assert failed_history.run.status is LifecycleRunStatus.FAILED
    assert failed_history.stages[0].stage_status is LifecycleStageStatus.FAILED
    assert failed_history.stages[0].attempt_count == 1
    assert failed_history.attempts[0].exception_type == "DomainCrash"
    assert failed_history.attempts[0].exception_message == message
    assert failed_history.receipts == ()
    assert handler.execute_calls == execute_count_after_failure

    # Calling run again is idempotent observation, not implicit recovery.
    replay = runner.run(command)
    assert replay.run.status is LifecycleRunStatus.FAILED
    assert repository.history(command.run_id).stages[0].attempt_count == 1

    resumed = runner.resume(
        command.run_id,
        stop_after_stage=LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
    )

    resumed_history = repository.history(command.run_id)
    assert resumed.run.status is LifecycleRunStatus.RUNNING
    assert resumed.stopped_after_stage is LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE
    assert resumed_history.stages[0].stage_status is LifecycleStageStatus.COMPLETED
    assert resumed_history.stages[0].attempt_count == 2
    assert len(resumed_history.attempts) == 2
    assert len(resumed_history.receipts) == 1
    assert (
        LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE in resumed.recovered_stages
    ) is is_recovered
    expected_execute_count = execute_count_after_failure + (not is_recovered)
    assert handler.execute_calls == expected_execute_count


class DeliveryCrash(RuntimeError):
    pass


class OneShotAfterStageCrash:
    def __init__(self) -> None:
        self.raised = False

    def __call__(self, stage_name: LifecycleStageName, _run: object) -> None:
        if not self.raised:
            self.raised = True
            raise DeliveryCrash(f"after receipt for {stage_name.value}")


def test_crash_after_receipt_never_reexecutes_completed_stage(tmp_path: Path) -> None:
    repository = SQLiteLifecycleRunRepository(tmp_path / "delivery.sqlite3")
    calls: list[tuple[str, LifecycleStageName]] = []
    handlers = _handlers(calls)
    command = _command(idempotency_key="delivery-crash")
    clock = TickClock()
    crashing_runner = CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=handlers,
        clock=clock,
        after_stage_hook=OneShotAfterStageCrash(),
    )

    with pytest.raises(LifecycleStageExecutionError) as captured:
        crashing_runner.run(command)

    assert captured.value.journal_settled
    assert captured.value.exception_type == "DeliveryCrash"
    committed = repository.history(command.run_id)
    assert committed.run.status is LifecycleRunStatus.RUNNING
    assert committed.stages[0].stage_status is LifecycleStageStatus.COMPLETED
    assert committed.stages[0].attempt_count == 1
    first_stage_receipts = tuple(
        receipt
        for receipt in committed.receipts
        if receipt.stage_name is LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE
    )
    assert len(first_stage_receipts) == 1

    clean_runner = CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=handlers,
        clock=clock,
    )
    resumed = clean_runner.resume(
        command.run_id,
        stop_after_stage=LifecycleStageName.PLATFORM_RESEARCH,
    )

    assert resumed.stopped_after_stage is LifecycleStageName.PLATFORM_RESEARCH
    assert handlers[0].execute_calls == 1
    assert handlers[0].recover_calls == 1
    final_history = repository.history(command.run_id)
    assert final_history.stages[0].attempt_count == 1
    assert (
        sum(
            receipt.stage_name is LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE
            for receipt in final_history.receipts
        )
        == 1
    )


def test_handler_return_type_failure_is_journaled_and_typed(tmp_path: Path) -> None:
    class InvalidHandler(RecoverableFaultHandler):
        def execute(self, context: LifecycleStageContext) -> object:
            self.execute_calls += 1
            return object()

    repository = SQLiteLifecycleRunRepository(tmp_path / "invalid.sqlite3")
    invalid = InvalidHandler(
        stage_name=LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
        fault="none",
    )
    runner = CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=_recovery_handlers(invalid),
        clock=TickClock(),
    )
    command = _command(idempotency_key="invalid-result")

    with pytest.raises(LifecycleStageExecutionError) as captured:
        runner.run(command)

    assert captured.value.exception_type == "TypeError"
    assert captured.value.exception_message == (
        "stage handler must return StageExecutionResult"
    )
    history = repository.history(command.run_id)
    assert history.run.status is LifecycleRunStatus.FAILED
    assert history.attempts[0].exception_type == "TypeError"
