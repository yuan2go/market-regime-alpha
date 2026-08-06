from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from market_regime_alpha.application.continuous_research.composition import (
    CONTINUOUS_CHILD_ORDER,
)
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousSessionPhase,
)
from market_regime_alpha.application.decision_system.contracts import (
    DecisionWindowState,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.replay import (
    replay_decision_system,
)
from market_regime_alpha.application.decision_system.runtime import (
    DECISION_RUNTIME_STAGE_ORDER,
    DecisionRuntimeInputs,
    DecisionSystemDelegate,
    DecisionSystemRuntimeService,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from tests.application.decision_system.support import (
    AS_OF,
    HASH_A,
    HASH_B,
    active_claim,
    candidate,
    lineage,
    observation,
    position,
    risk_configuration,
    tolerance,
)
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory
from tests.persistence.postgres.test_continuous_research_journal import (
    MutableClock,
    _command,
    _tick,
)


UTC = timezone.utc


def _request(claim, *, as_of: datetime = AS_OF) -> ChildExecutionRequest:
    return ChildExecutionRequest(
        trading_date=as_of.date(),
        as_of_time=as_of,
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        tick_sequence=claim.tick_sequence,
        claim_id=claim.claim_id,
        fencing_token=claim.fencing_token,
        tick_version=claim.tick_version,
        lease_expires_at=claim.lease_expires_at,
        provider_attempt_id=1,
        source_manifest_id=ArtifactId("source-manifest-a"),
        source_manifest_hash=HASH_A,
        evidence_commit_id=ArtifactId("evidence-commit-a"),
        evidence_commit_hash=HASH_B,
        decision_id=ArtifactId("change-decision-a"),
        decision_hash=HASH_A,
        input_references=(
            RuntimeArtifactReference(
                "EVIDENCE",
                ArtifactId("evidence-commit-a"),
                HASH_B,
            ),
            RuntimeArtifactReference(
                "STATE_SYSTEM_OUTPUT",
                ArtifactId("state-receipt-a"),
                HASH_B,
            ),
        ),
        configuration_references=(
            RuntimeArtifactReference(
                "CONFIGURATION",
                ArtifactId("decision-config-a"),
                HASH_A,
            ),
        ),
    )


def _inputs(claim, account_id: ArtifactId) -> DecisionRuntimeInputs:
    return DecisionRuntimeInputs(
        manual_observation_id=account_id,
        positions=(position(),),
        fill_ledger_head="fill-ledger-head-a",
        fill_ledger_complete=True,
        authoritative_total_equity=Decimal("100000.120000"),
        authoritative_available_cash=Decimal("80000.120000"),
        authoritative_frozen_cash=Decimal("0"),
        reconciliation_tolerance=tolerance(),
        reconciliation_revision=1,
        previous_reconciliation_id=None,
        strategy_configuration_id=ArtifactId("strategy-config-a"),
        strategy_configuration_hash=HASH_A,
        lineage=lineage(claim),
        candidates=(candidate(),),
        summary_revision=1,
        previous_summary_id=None,
        correction_of_summary_id=None,
        risk_configuration=risk_configuration(),
        finalize=True,
    )


def _execution_authority_counts(
    postgres_factory: PostgresConnectionFactory,
) -> tuple[int, ...]:
    with postgres_factory.connection(read_only=True) as connection:
        return tuple(
            int(
                connection.execute(
                    f"SELECT count(*) FROM {table}"  # noqa: S608 - fixed test allowlist
                ).fetchone()[0]
            )
            for table in (
                "execution_commands",
                "manual_trade_records",
                "manual_fills",
                "position_book_events",
                "trading_opportunities",
            )
        )


def test_decision_system_is_the_unique_final_continuous_child() -> None:
    assert tuple(ContinuousChildKind).count(ContinuousChildKind.DECISION_SYSTEM) == 1
    assert CONTINUOUS_CHILD_ORDER[-1] is ContinuousChildKind.DECISION_SYSTEM


def test_runtime_executes_ordered_decision_stages_and_reuses_receipt(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation())
    request = _request(claim)
    inputs = _inputs(claim, account.observation_id)
    delegate = DecisionSystemDelegate(
        DecisionSystemRuntimeService(repository),
        input_loader=lambda _: inputs,
    )
    before = _execution_authority_counts(postgres_factory)

    result = delegate.execute(request)
    replay = delegate.lookup(request)
    receipt = repository.get_runtime_receipt(
        run_id=request.run_id,
        tick_id=request.tick_id,
    )

    assert replay == result
    assert receipt.status == "COMPLETED"
    assert tuple(item.stage for item in receipt.stage_receipts) == (DECISION_RUNTIME_STAGE_ORDER)
    assert receipt.summary_id is not None
    final = repository.get_summary(receipt.summary_id)
    assert final.lifecycle_state is DecisionWindowState.FINALIZED
    assert final.revision == 2
    assert final.previous_summary_id is not None
    assert _execution_authority_counts(postgres_factory) == before
    restarted = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    first_replay = replay_decision_system(
        restarted,
        run_id=request.run_id,
        tick_id=request.tick_id,
    )
    second_replay = replay_decision_system(
        restarted,
        run_id=request.run_id,
        tick_id=request.tick_id,
    )
    assert first_replay == second_replay
    assert first_replay.verified_authority_count == 6
    assert first_replay.entry_authority_granted is False
    assert first_replay.broker_authority_granted is False


def test_runtime_records_window_not_open_as_fail_closed_receipt(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    before_window = datetime(2026, 8, 6, 6, 29, tzinfo=UTC)
    clock = MutableClock(before_window)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    request = _request(claim, as_of=before_window)
    delegate = DecisionSystemDelegate(
        DecisionSystemRuntimeService(repository),
        input_loader=lambda _: _inputs(claim, ArtifactId("missing-observation")),
    )

    result = delegate.execute(request)
    receipt = repository.get_runtime_receipt(
        run_id=request.run_id,
        tick_id=request.tick_id,
    )

    assert result.child_artifact_id is None
    assert receipt.status == "BLOCKED"
    assert receipt.stage_receipts[0].reason_codes == ("WINDOW_NOT_OPEN",)
    assert repository.authority_counts()["daily_decision_summary"] == 0


def test_concurrent_finalize_keeps_one_terminal_and_blocks_loser(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    journal, first_claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation())
    first_request = _request(first_claim)
    first_receipt = DecisionSystemRuntimeService(repository).execute(
        request=first_request,
        inputs=_inputs(first_claim, account.observation_id),
    )
    assert first_receipt.reconciliation_id is not None
    assert first_receipt.summary_id is not None

    command = _command()
    second_tick = journal.admit_tick(
        _tick(command, minute=44),
        session_phase=ContinuousSessionPhase.DECISION_WINDOW,
    )
    second_claim = journal.claim_tick(
        run_id=command.run_id,
        tick_id=second_tick.command.tick_id,
    )
    second_request = _request(second_claim)
    second_inputs = replace(
        _inputs(second_claim, account.observation_id),
        reconciliation_revision=2,
        previous_reconciliation_id=first_receipt.reconciliation_id,
        summary_revision=3,
        previous_summary_id=first_receipt.summary_id,
    )

    second_receipt = DecisionSystemRuntimeService(repository).execute(
        request=second_request,
        inputs=second_inputs,
    )

    assert second_receipt.status == "BLOCKED"
    assert second_receipt.stage_receipts[-1].reason_codes == ("FINAL_ALREADY_EXISTS_OR_SUMMARY_CAS_REJECTED",)
    with postgres_factory.connection(read_only=True) as connection:
        terminal_count = connection.execute(
            """
            SELECT count(*) FROM daily_decision_summary
            WHERE lifecycle_state IN ('FINALIZED', 'BLOCKED')
            """
        ).fetchone()[0]
    assert terminal_count == 1


def test_correction_appends_version_without_overwriting_original_final(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    journal, first_claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation())
    first = DecisionSystemRuntimeService(repository).execute(
        request=_request(first_claim),
        inputs=_inputs(first_claim, account.observation_id),
    )
    assert first.reconciliation_id is not None
    assert first.summary_id is not None
    original = repository.get_summary(first.summary_id)

    command = _command()
    second_tick = journal.admit_tick(
        _tick(command, minute=44),
        session_phase=ContinuousSessionPhase.DECISION_WINDOW,
    )
    second_claim = journal.claim_tick(
        run_id=command.run_id,
        tick_id=second_tick.command.tick_id,
    )
    corrected_inputs = replace(
        _inputs(second_claim, account.observation_id),
        reconciliation_revision=2,
        previous_reconciliation_id=first.reconciliation_id,
        summary_revision=3,
        previous_summary_id=first.summary_id,
        correction_of_summary_id=first.summary_id,
    )

    corrected_receipt = DecisionSystemRuntimeService(repository).execute(
        request=_request(second_claim),
        inputs=corrected_inputs,
    )

    assert corrected_receipt.status == "COMPLETED"
    assert corrected_receipt.summary_id is not None
    correction = repository.get_summary(corrected_receipt.summary_id)
    assert correction.lifecycle_state is DecisionWindowState.CORRECTED
    assert correction.correction_of_summary_id == original.summary_id
    assert correction.revision == 4
    assert repository.get_summary(original.summary_id) == original
