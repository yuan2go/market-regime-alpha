from __future__ import annotations

from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalRunStatus,
)
from market_regime_alpha.application.historical_research.runner import (
    HistoricalResearchRunner,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchDecisionSessionKernel,
    ResearchSessionStage,
    SessionStageComputation,
    SessionStageStatus,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from tests.application.historical_research.test_contracts import CREATED_AT, _command
from tests.application.research_session.test_kernel import DeterministicOwner
from tests.persistence.postgres.test_historical_research_journal import (
    MutableClock,
    _journal,
)


def test_historical_runner_resumes_and_replays_without_mutation(postgres_factory) -> None:
    clock = MutableClock(CREATED_AT)
    journal = _journal(postgres_factory, clock)
    runner = HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(DeterministicOwner()),
    )
    command = _command()

    partial = runner.run(command=command, max_stage_commits=4)
    resumed = runner.resume(run_id=command.run_id)
    replay = runner.replay(run_id=command.run_id)
    repeated = runner.run(command=command)

    assert partial.status is HistoricalRunStatus.RUNNING
    assert sum(len(item.receipts) for item in partial.sessions) == 4
    assert resumed.status is HistoricalRunStatus.COMPLETE
    assert sum(len(item.receipts) for item in resumed.sessions) == 18
    assert replay.matched is True
    assert replay.mismatches == ()
    assert repeated == resumed
    assert journal.get_run(command.run_id) == resumed


def test_historical_runner_records_blocks_and_continues_calendar(postgres_factory) -> None:
    class BlockedDecisionOwner(DeterministicOwner):
        def compute_stage(self, *, request, stage, input_references):
            if stage is ResearchSessionStage.DECISION:
                return SessionStageComputation(
                    status=SessionStageStatus.BLOCKED,
                    output_references=(),
                    input_references=input_references,
                    completed_at=CREATED_AT,
                    reason_codes=("HISTORICAL_DECISION_FACT_MISSING",),
                )
            return super().compute_stage(
                request=request,
                stage=stage,
                input_references=input_references,
            )

    journal = _journal(postgres_factory, MutableClock(CREATED_AT))
    result = HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(BlockedDecisionOwner()),
    ).run(command=_command())

    assert result.status is HistoricalRunStatus.COMPLETE_WITH_BLOCKS
    assert tuple(len(item.receipts) for item in result.sessions) == (2, 2, 2)
    assert all(
        item.receipts[-1].reason_codes
        == ("HISTORICAL_DECISION_FACT_MISSING",)
        for item in result.sessions
    )


def test_historical_replay_reports_owner_output_substitution(postgres_factory) -> None:
    journal = _journal(postgres_factory, MutableClock(CREATED_AT))
    command = _command()
    HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(DeterministicOwner()),
    ).run(command=command)

    class SubstitutedOwner(DeterministicOwner):
        def compute_stage(self, *, request, stage, input_references):
            result = super().compute_stage(
                request=request,
                stage=stage,
                input_references=input_references,
            )
            if stage is not ResearchSessionStage.DECISION:
                return result
            changed = result.output_references[0]
            return SessionStageComputation(
                status=result.status,
                output_references=(
                    type(changed)(
                        changed.artifact_kind,
                        changed.artifact_id,
                        canonical_hash({"substituted": True}),
                    ),
                ),
                input_references=result.input_references,
                completed_at=result.completed_at,
                reason_codes=result.reason_codes,
            )

    report = HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(SubstitutedOwner()),
    ).replay(run_id=command.run_id)

    assert report.matched is False
    assert len(report.mismatches) == command.session_count
    assert all(item.stage is ResearchSessionStage.DECISION for item in report.mismatches)
