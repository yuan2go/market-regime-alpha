from __future__ import annotations

from decimal import Decimal

import pytest

from market_regime_alpha.application.decision_system.contracts import (
    IndependentRiskResult,
    ProposalStatus,
    ReconciliationDifferenceType,
    ReconciliationStatus,
)
from market_regime_alpha.application.decision_system.portfolio import (
    build_research_portfolio_proposal,
)
from market_regime_alpha.application.decision_system.reconciliation import (
    ReconciliationBlocked,
    reconcile_account,
    require_open_add_calibrated,
)
from market_regime_alpha.application.decision_system.risk import IndependentRiskService
from tests.application.decision_system.support import (
    AS_OF,
    candidate,
    observation,
    position,
    risk_configuration,
    summary,
    tolerance,
)


def _reconciliation(**overrides):
    account = overrides.pop("observation", observation())
    values = {
        "observation": account,
        "positions": (position(),),
        "fill_ledger_head": "fill-ledger-head-a",
        "fill_ledger_complete": True,
        "tolerance": tolerance(),
        "authoritative_total_equity": account.total_equity,
        "authoritative_available_cash": account.available_cash,
        "authoritative_frozen_cash": account.frozen_cash,
        "as_of_time": AS_OF,
        "revision": 1,
        "previous_reconciliation_id": None,
        "idempotency_key": "reconciliation-1",
        "created_at": AS_OF,
    }
    values.update(overrides)
    return reconcile_account(**values)


def test_reconciliation_exact_match_and_open_add_gate() -> None:
    report = _reconciliation()

    assert report.status is ReconciliationStatus.RECONCILED
    assert report.differences == ()
    require_open_add_calibrated(report)


@pytest.mark.parametrize(
    ("overrides", "difference_type"),
    (
        ({"authoritative_total_equity": Decimal("100001")}, ReconciliationDifferenceType.TOTAL_EQUITY_DIFFERENCE),
        ({"authoritative_available_cash": Decimal("79000")}, ReconciliationDifferenceType.CASH_DIFFERENCE),
        ({"positions": (position(total_quantity=90, available_quantity=70),)}, ReconciliationDifferenceType.SYMBOL_QUANTITY_DIFFERENCE),
        ({"positions": (position(available_quantity=70, frozen_quantity=30),)}, ReconciliationDifferenceType.T_PLUS_ONE_DIFFERENCE),
        ({"positions": ()}, ReconciliationDifferenceType.SYSTEM_MISSING_POSITION),
        ({"observation": observation(positions=()), "positions": (position(),)}, ReconciliationDifferenceType.MANUAL_MISSING_POSITION),
        ({"positions": (position(total_quantity=200, available_quantity=180),)}, ReconciliationDifferenceType.CORPORATE_ACTION_SUSPECTED),
        ({"fill_ledger_complete": False}, ReconciliationDifferenceType.DATA_INSUFFICIENT),
    ),
)
def test_reconciliation_detects_authority_differences(
    overrides: dict[str, object],
    difference_type: ReconciliationDifferenceType,
) -> None:
    report = _reconciliation(**overrides)

    assert difference_type in {item.difference_type for item in report.differences}
    with pytest.raises(ReconciliationBlocked):
        require_open_add_calibrated(report)


def test_portfolio_is_research_only_and_applies_caps() -> None:
    account = observation()
    report = _reconciliation(observation=account)
    preview = summary(
        claim=type("Claim", (), {"run_id": "run-a", "tick_id": "tick-a"})(),
        observation_id=account.observation_id,
        reconciliation_id=report.reconciliation_id,
    )

    proposal = build_research_portfolio_proposal(
        summary=preview,
        observation=account,
        reconciliation=report,
        configuration=risk_configuration(),
        idempotency_key="proposal-1",
    )

    assert proposal.status is ProposalStatus.PROPOSED
    assert proposal.lines[0].proposed_research_weight <= Decimal("0.10")
    assert proposal.lines[0].research_amount == (proposal.lines[0].proposed_research_weight * account.total_equity)
    assert not hasattr(proposal, "order")
    assert not hasattr(proposal, "fill")


def test_portfolio_fails_closed_for_model_orderability_and_liquidity() -> None:
    account = observation()
    report = _reconciliation(observation=account)
    claim = type("Claim", (), {"run_id": "run-a", "tick_id": "tick-a"})()

    for item, expected in (
        (candidate(model_qualification="UNQUALIFIED"), ProposalStatus.MODEL_NOT_QUALIFIED),
        (candidate(orderability="UNKNOWN"), ProposalStatus.ORDERABILITY_UNKNOWN),
    ):
        preview = summary(
            claim=claim,
            observation_id=account.observation_id,
            reconciliation_id=report.reconciliation_id,
            candidates=(item,),
        )
        proposal = build_research_portfolio_proposal(
            summary=preview,
            observation=account,
            reconciliation=report,
            configuration=risk_configuration(),
            idempotency_key=f"proposal-{expected.value}",
        )
        assert proposal.status is expected

    preview = summary(
        claim=claim,
        observation_id=account.observation_id,
        reconciliation_id=report.reconciliation_id,
        candidates=(candidate(liquidity=Decimal("0.10")),),
    )
    proposal = build_research_portfolio_proposal(
        summary=preview,
        observation=account,
        reconciliation=report,
        configuration=risk_configuration(),
        idempotency_key="proposal-liquidity",
    )
    assert proposal.status is ProposalStatus.NO_ACTION
    assert proposal.lines[0].liquidity_constraint == "LIQUIDITY_INSUFFICIENT"


class _Reader:
    def __init__(self, proposal, preview, account, report) -> None:
        self.proposal = proposal
        self.preview = preview
        self.account = account
        self.report = report
        self.reads: list[str] = []

    def get_proposal(self, _):
        self.reads.append("proposal")
        return self.proposal

    def get_summary(self, _):
        self.reads.append("summary")
        return self.preview

    def get_manual_observation(self, _):
        self.reads.append("observation")
        return self.account

    def get_reconciliation(self, _):
        self.reads.append("reconciliation")
        return self.report


def test_independent_risk_reloads_all_authority_inputs() -> None:
    account = observation()
    report = _reconciliation(observation=account)
    preview = summary(
        claim=type("Claim", (), {"run_id": "run-a", "tick_id": "tick-a"})(),
        observation_id=account.observation_id,
        reconciliation_id=report.reconciliation_id,
    )
    configuration = risk_configuration()
    proposal = build_research_portfolio_proposal(
        summary=preview,
        observation=account,
        reconciliation=report,
        configuration=configuration,
        idempotency_key="proposal-risk",
    )
    reader = _Reader(proposal, preview, account, report)

    decision = IndependentRiskService(reader).decide(
        proposal_id=proposal.proposal_id,
        configuration=configuration,
        as_of_time=AS_OF,
        idempotency_key="risk-1",
    )

    assert reader.reads == ["proposal", "summary", "observation", "reconciliation"]
    assert decision.result is IndependentRiskResult.RESEARCH_APPROVED
    assert not hasattr(decision, "trading_authorization")


def test_independent_risk_blocks_stale_and_lineage_mismatch() -> None:
    account = observation()
    report = _reconciliation(observation=account)
    preview = summary(
        claim=type("Claim", (), {"run_id": "run-a", "tick_id": "tick-a"})(),
        observation_id=account.observation_id,
        reconciliation_id=report.reconciliation_id,
    )
    configuration = risk_configuration()
    proposal = build_research_portfolio_proposal(
        summary=preview,
        observation=account,
        reconciliation=report,
        configuration=configuration,
        idempotency_key="proposal-risk-stale",
    )
    reader = _Reader(proposal, preview, account, report)

    decision = IndependentRiskService(reader).decide(
        proposal_id=proposal.proposal_id,
        configuration=configuration,
        as_of_time=AS_OF.replace(hour=8),
        idempotency_key="risk-stale",
    )
    assert decision.result is IndependentRiskResult.ACCOUNT_NOT_CALIBRATED

    reader.preview = summary(
        claim=type("Claim", (), {"run_id": "run-a", "tick_id": "tick-a"})(),
        observation_id=account.observation_id,
        reconciliation_id=report.reconciliation_id,
        account_id="different-account",
        idempotency_key="different-account-summary",
    )
    with pytest.raises(ValueError, match="Account lineage"):
        IndependentRiskService(reader).decide(
            proposal_id=proposal.proposal_id,
            configuration=configuration,
            as_of_time=AS_OF,
            idempotency_key="risk-bad-lineage",
        )
