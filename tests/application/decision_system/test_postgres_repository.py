from __future__ import annotations

from datetime import timedelta

import pytest

from market_regime_alpha.application.decision_system.portfolio import (
    build_research_portfolio_proposal,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    DecisionSystemConflict,
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.reconciliation import (
    reconcile_account,
)
from market_regime_alpha.application.decision_system.risk import IndependentRiskService
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from tests.application.decision_system.support import (
    AS_OF,
    active_claim,
    observation,
    position,
    risk_configuration,
    summary,
    tolerance,
)
from tests.persistence.postgres.test_continuous_research_journal import (
    MutableClock,
    NOW,
)
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


def _report(account):
    return reconcile_account(
        observation=account,
        positions=(position(),),
        fill_ledger_head="fill-ledger-head-a",
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
    assert repository.get_manual_observation(account.observation_id).total_equity.as_tuple() == account.total_equity.as_tuple()

    report = _report(account)
    assert repository.save_reconciliation(report, claim=claim) == report
    preview = summary(
        claim=claim,
        observation_id=account.observation_id,
        reconciliation_id=report.reconciliation_id,
    )
    assert repository.save_summary(preview, claim=claim) == preview
    configuration = risk_configuration()
    proposal = build_research_portfolio_proposal(
        summary=preview,
        observation=account,
        reconciliation=report,
        configuration=configuration,
        idempotency_key="proposal-1",
    )
    assert repository.save_proposal(proposal, claim=claim) == proposal
    risk = IndependentRiskService(repository).decide(
        proposal_id=proposal.proposal_id,
        configuration=configuration,
        as_of_time=AS_OF,
        idempotency_key="risk-1",
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
    }


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

    with pytest.raises(DecisionSystemConflict, match="claim|fencing|lease"):
        repository.save_reconciliation(_report(account), claim=stale_claim)
    assert repository.save_reconciliation(_report(account), claim=replacement_claim).manual_observation_id == account.observation_id
