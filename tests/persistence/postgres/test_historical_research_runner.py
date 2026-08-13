from __future__ import annotations

import pytest

from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalResearchConflict,
    HistoricalRunStatus,
    PRE_E3_RUNTIME_CONTRACT,
)
from market_regime_alpha.core.identity import ArtifactId
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


def _mark_as_migrated_pre_e3(postgres_factory, run_id: ArtifactId) -> None:
    """Model migration 081's durable classification of an already-existing run."""

    with postgres_factory.connection() as connection:
        connection.execute(
            "ALTER TABLE historical_research_run "
            "DISABLE TRIGGER historical_research_run_identity_immutable"
        )
        connection.execute(
            "UPDATE historical_research_run SET runtime_contract_version = %s "
            "WHERE run_id = %s",
            (PRE_E3_RUNTIME_CONTRACT, str(run_id)),
        )
        connection.execute(
            "ALTER TABLE historical_research_run "
            "ENABLE TRIGGER historical_research_run_identity_immutable"
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


def test_pre_e3_terminal_run_uses_explicit_immutable_receipt_verification(
    postgres_factory,
) -> None:
    legacy = _command()
    journal = _journal(postgres_factory, MutableClock(CREATED_AT))
    runner = HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(DeterministicOwner()),
    )
    terminal = runner.run(command=legacy)
    _mark_as_migrated_pre_e3(postgres_factory, legacy.run_id)
    terminal = journal.get_run(legacy.run_id)

    class MustNotRecomputeOwner(DeterministicOwner):
        def compute_stage(self, **_):
            raise AssertionError("pre-E3 replay must not apply current semantics")

    verifier = HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(MustNotRecomputeOwner()),
    )
    report = verifier.replay(run_id=legacy.run_id)

    assert terminal.status is HistoricalRunStatus.COMPLETE
    assert report.matched is True
    assert report.replay_mode == "IMMUTABLE_PRE_E3_RECEIPT_VERIFICATION"
    assert verifier.resume(run_id=legacy.run_id) == terminal


def test_pre_e3_incomplete_resume_fails_closed_without_exact_code(postgres_factory) -> None:
    legacy = _command()
    journal = _journal(postgres_factory, MutableClock(CREATED_AT))
    runner = HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(DeterministicOwner()),
    )
    runner.run(command=legacy, max_stage_commits=1)
    _mark_as_migrated_pre_e3(postgres_factory, legacy.run_id)

    with pytest.raises(HistoricalResearchConflict, match="exact historical code"):
        runner.resume(run_id=legacy.run_id)
    with pytest.raises(HistoricalResearchConflict, match="exact historical code"):
        runner.run(command=legacy)
