from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from market_regime_alpha.application.decision_system.authority import (
    FillDerivedAccountAuthority,
    PositionSettlementEvidence,
)
from market_regime_alpha.application.trading_lifecycle import (
    TraceableManualExecutionApplicationService,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.execution.postgres_repository import (
    PostgresTraceableManualExecutionRepository,
)
from market_regime_alpha.application.decision_system.portfolio import (
    build_research_portfolio_proposal,
)
from market_regime_alpha.application.decision_system.contracts import (
    IndependentRiskDecision,
    IndependentRiskResult,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    DecisionSystemConflict,
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.reconciliation import (
    reconcile_account,
)
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.position import (
    SymbolTradingSessionStatus,
    SymbolTradingState,
)
from tests.application.decision_system.support import (
    AS_OF,
    active_claim,
    observation,
    position,
    HASH_A,
    risk_configuration,
    summary,
    tolerance,
)
from tests.application.decision_system.test_research_summary import (
    _stages as research_stages,
    _summary as research_summary,
)
from tests.persistence.postgres.test_continuous_research_journal import (
    MutableClock,
    NOW,
)
from tests.execution.test_traceable_execution_chain import (
    NOW as TRACE_NOW,
    _authority as _trace_authority,
    _create_trade as _create_traceable_trade,
)
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


def _report(account):
    return reconcile_account(
        observation=account,
        positions=(position(),),
        fill_ledger_head=HASH_A,
        fill_ledger_complete=True,
        tolerance=tolerance(),
        authoritative_total_equity=account.total_equity,
        authoritative_available_cash=account.available_cash,
        authoritative_frozen_cash=account.frozen_cash,
        as_of_time=AS_OF,
        revision=1,
        previous_reconciliation_id=None,
        idempotency_key="reconciliation-1",
        created_at=AS_OF,
    )


def test_postgres_round_trip_is_idempotent_and_decimal_exact(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = observation()

    assert repository.record_manual_observation(account) == account
    assert repository.record_manual_observation(account) == account
    assert repository.get_manual_observation(account.observation_id) == account
    assert repository.get_manual_observation(account.observation_id).total_equity == account.total_equity

    assert repository.record_reconciliation_tolerance(tolerance(), claim=claim) == tolerance()
    report = _report(account)
    assert repository.save_reconciliation(report, claim=claim) == report
    preview = summary(
        claim=claim,
        observation_id=account.observation_id,
        reconciliation_id=report.reconciliation_id,
    )
    assert repository.save_summary(preview, claim=claim) == preview
    configuration = risk_configuration()
    assert repository.record_risk_configuration(configuration, claim=claim) == configuration
    proposal = build_research_portfolio_proposal(
        summary=preview,
        observation=account,
        reconciliation=report,
        positions=(position(),),
        configuration=configuration,
        idempotency_key="proposal-1",
    )
    assert repository.save_proposal(proposal, claim=claim) == proposal
    risk = IndependentRiskDecision.create(
        proposal_id=proposal.proposal_id,
        account_id=proposal.account_id,
        trading_date=proposal.trading_date,
        as_of_time=AS_OF,
        result=IndependentRiskResult.RESEARCH_APPROVED,
        approved_research_weight=sum(
            (item.proposed_research_weight for item in proposal.lines),
            start=Decimal("0"),
        ),
        reason_codes=("INDEPENDENT_RESEARCH_RISK_CHECKS_PASSED",),
        risk_configuration_id=configuration.configuration_id,
        risk_configuration_hash=configuration.configuration_hash,
        idempotency_key="risk-1",
        created_at=AS_OF,
    )
    assert repository.save_risk_decision(risk, claim=claim) == risk

    assert repository.authority_counts() == {
        "manual_account_observation": 1,
        "manual_position_observation": 1,
        "account_reconciliation": 1,
        "reconciliation_difference": 0,
        "daily_decision_summary": 1,
        "daily_summary_candidate": 1,
        "research_portfolio_proposal": 1,
        "research_portfolio_line": 1,
        "independent_risk_decision": 1,
        "decision_runtime_receipt": 0,
        "research_daily_summary": 0,
        "research_summary_stage": 0,
        "decision_risk_configuration": 1,
        "reconciliation_tolerance_configuration": 1,
        "decision_position_settlement_evidence": 0,
        "decision_fill_account_authority": 0,
    }


def test_research_summary_is_fenced_idempotent_and_restart_readable(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    value = research_summary(
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        trading_date=claim.lease_acquired_at.date(),
        decision_time=AS_OF,
        stages=research_stages(available_at=AS_OF, missing="ETF_ROTATION"),
    )

    assert repository.save_research_summary(value, claim=claim) == value
    assert repository.save_research_summary(value, claim=claim) == value
    restarted = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    assert restarted.get_research_summary(value.summary_id) == value
    assert restarted.get_research_summary_for_tick(
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        runtime_mode=RuntimeAuthorityMode.RESEARCH,
    ) == value


def test_research_summary_rejects_caller_declared_selection_receipt(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _, claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    value = research_summary(
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        trading_date=claim.lease_acquired_at.date(),
        decision_time=AS_OF,
        stages=research_stages(available_at=AS_OF, rejected="SIGNAL"),
    )

    with pytest.raises(DecisionSystemConflict, match="does not exist"):
        repository.save_research_summary(value, claim=claim)


def test_stale_fence_cannot_write_research_summary(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    journal, stale_claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    value = research_summary(
        run_id=stale_claim.run_id,
        tick_id=stale_claim.tick_id,
        trading_date=stale_claim.lease_acquired_at.date(),
        decision_time=AS_OF,
        stages=research_stages(available_at=AS_OF),
    )
    clock.advance(timedelta(minutes=3))
    fresh_claim = journal.claim_tick(
        run_id=stale_claim.run_id,
        tick_id=stale_claim.tick_id,
    )

    with pytest.raises(DecisionSystemConflict, match="stale|claim|fence"):
        repository.save_research_summary(value, claim=stale_claim)
    assert repository.save_research_summary(value, claim=fresh_claim) == value


def test_manual_account_revision_is_append_only_cas(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresDecisionSystemRepository(postgres_factory)
    first = repository.record_manual_observation(observation())
    second = observation(
        revision=2,
        previous=first.observation_id,
        idempotency_key="manual-account-2",
        available_quantity=100,
        frozen_quantity=0,
    )

    assert repository.record_manual_observation(second) == second
    assert (
        repository.get_manual_observation_revision(
            account_id=first.account_id,
            trading_date=first.trading_date,
            revision=1,
        )
        == first
    )
    with pytest.raises(DecisionSystemConflict, match="revision CAS"):
        repository.record_manual_observation(observation(idempotency_key="manual-account-stale"))


def test_expired_worker_cannot_commit_decision_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    journal, stale_claim = active_claim(postgres_factory, clock)
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    account = repository.record_manual_observation(observation())
    clock.advance(timedelta(minutes=3))
    replacement_claim = journal.claim_tick(
        run_id=stale_claim.run_id,
        tick_id=stale_claim.tick_id,
    )
    fill_authority = FillDerivedAccountAuthority.create(
        account_id=account.account_id,
        as_of_time=AS_OF,
        positions=(position(),),
        fill_ledger_head=HASH_A,
        fill_ledger_complete=True,
    )
    repository.record_reconciliation_tolerance(tolerance(), claim=replacement_claim)

    with pytest.raises(DecisionSystemConflict, match="claim|fencing|lease"):
        repository.save_reconciliation(_report(account), claim=stale_claim)
    with pytest.raises(DecisionSystemConflict, match="claim|fencing|lease"):
        repository.record_fill_derived_account_authority(
            fill_authority,
            claim=stale_claim,
        )
    assert repository.record_fill_derived_account_authority(
        fill_authority,
        claim=replacement_claim,
    ) == fill_authority
    assert repository.get_recorded_fill_derived_account_authority(
        account_id=account.account_id,
        as_of_time=AS_OF,
    ) == fill_authority
    assert repository.save_reconciliation(_report(account), claim=replacement_claim).manual_observation_id == account.observation_id


def test_postgres_fill_authority_uses_explicit_t_plus_one_settlement_evidence(
    postgres_factory: PostgresConnectionFactory,
    tmp_path,
) -> None:
    clock = MutableClock(NOW)
    _, claim = active_claim(postgres_factory, clock)
    trace_service = TraceableManualExecutionApplicationService(
        PostgresTraceableManualExecutionRepository(postgres_factory)
    )
    authority = _trace_authority(tmp_path, index=901)
    book, trade = _create_traceable_trade(
        trace_service,
        authority,
        "decision-t-plus-one-trade",
    )
    trace_service.record_fill(
        trade.manual_trade_id,
        external_fill_id="decision-t-plus-one-fill",
        quantity=100,
        price=10.0,
        fees=1.0,
        occurred_at=TRACE_NOW + timedelta(minutes=1),
        recorded_at=TRACE_NOW + timedelta(minutes=1, seconds=1),
        actor="manual-operator",
        reason="Decision T+1 PostgreSQL proof",
        idempotency_key="decision-t-plus-one-fill-command",
    )
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("decision-calendar-dataset"),
        market="CN_A_SHARE",
        calendar_version="decision-t-plus-one-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            TradingSession(
                TRACE_NOW.date(),
                TRACE_NOW.replace(hour=15, minute=0, second=0),
            ),
            TradingSession(
                (TRACE_NOW + timedelta(days=1)).date(),
                (TRACE_NOW + timedelta(days=1)).replace(
                    hour=15, minute=0, second=0
                ),
            ),
            TradingSession(
                AS_OF.date(),
                AS_OF.astimezone(TRACE_NOW.tzinfo).replace(
                    hour=15, minute=0, second=0
                ),
            ),
        ),
    )
    status = SymbolTradingSessionStatus.create(
        symbol=book.symbol,
        session_date=AS_OF.date(),
        state=SymbolTradingState.TRADABLE,
        source_artifact_id=ArtifactId("decision-session-status-source"),
        source_artifact_hash=HASH_A,
        availability_time=AS_OF - timedelta(minutes=1),
        reason_code="EXPLICIT_SESSION_STATUS",
    )
    settlement = PositionSettlementEvidence.create(
        account_id=book.account_id,
        as_of_time=AS_OF,
        trading_calendar=calendar,
        symbol_session_statuses=(status,),
    )
    repository = PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    assert repository.record_position_settlement_evidence(
        settlement,
        claim=claim,
    ) == settlement
    assert repository.get_position_settlement_evidence(
        settlement.evidence_id
    ) == settlement
    restored = repository.load_fill_derived_account_authority(
        account_id=book.account_id,
        as_of_time=AS_OF,
        settlement_evidence=settlement,
    )

    assert restored.settlement_evidence_id == settlement.evidence_id
    assert restored.positions[0].total_quantity == 100
    assert restored.positions[0].available_quantity == 100
    assert restored.positions[0].frozen_quantity == 0
    assert restored.positions[0].complete is True

    unknown_status = SymbolTradingSessionStatus.create(
        symbol=book.symbol,
        session_date=AS_OF.date(),
        state=SymbolTradingState.UNKNOWN,
        source_artifact_id=ArtifactId("decision-unknown-status-source"),
        source_artifact_hash=HASH_A,
        availability_time=AS_OF - timedelta(minutes=1),
        reason_code="SESSION_STATUS_UNKNOWN",
    )
    unknown_settlement = PositionSettlementEvidence.create(
        account_id=book.account_id,
        as_of_time=AS_OF,
        trading_calendar=calendar,
        symbol_session_statuses=(unknown_status,),
    )
    incomplete = repository.load_fill_derived_account_authority(
        account_id=book.account_id,
        as_of_time=AS_OF,
        settlement_evidence=unknown_settlement,
    )
    assert incomplete.positions[0].available_quantity == 0
    assert incomplete.positions[0].frozen_quantity == 100
    assert incomplete.positions[0].complete is False
