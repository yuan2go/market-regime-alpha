from __future__ import annotations

import pytest

from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalResearchConflict,
    HistoricalRunStatus,
)
from market_regime_alpha.application.historical_research.contracts import (
    HistoricalResearchCommand,
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
    _receipt,
    _journal,
)


def _legacy_command() -> HistoricalResearchCommand:
    payload = _command().to_canonical_dict()
    payload.pop("runtime_contract_version")
    payload["schema_version"] = "historical-research-command/v1"
    payload.pop("run_id")
    payload.pop("command_hash")
    digest = canonical_hash(payload)
    return HistoricalResearchCommand.from_canonical_dict(
        {
            "run_id": f"historical-research-run-{digest[7:31]}",
            "command_hash": digest,
            **payload,
        }
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
    legacy = _legacy_command()
    journal = _journal(postgres_factory, MutableClock(CREATED_AT))
    journal.create_or_get(legacy)
    kernel = ResearchDecisionSessionKernel(DeterministicOwner())
    while claim := journal.claim_next(legacy.run_id):
        receipts = kernel.run_next(
            request=legacy.session_request(claim.trading_date),
            completed_prefix=claim.completed_prefix,
        )
        journal.record_stage(claim=claim, receipt=receipts[-1])
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
    legacy = _legacy_command()
    journal = _journal(postgres_factory, MutableClock(CREATED_AT))
    runner = HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(DeterministicOwner()),
    )
    journal.create_or_get(legacy)
    claim = journal.claim_next(legacy.run_id)
    assert claim is not None
    journal.record_stage(claim=claim, receipt=_receipt(legacy, claim))

    with pytest.raises(HistoricalResearchConflict, match="exact historical code"):
        runner.resume(run_id=legacy.run_id)
    with pytest.raises(HistoricalResearchConflict, match="exact historical code"):
        runner.run(command=legacy)
