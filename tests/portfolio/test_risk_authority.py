from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.trading_lifecycle import (
    PortfolioRiskApplicationService,
)
from market_regime_alpha.core.identity import ArtifactId, OpportunityId, ThesisId
from market_regime_alpha.decision import (
    DecisionEvidenceReference,
    InvalidationCondition,
    InvalidationKind,
    ThesisState,
    TradingThesis,
)
from market_regime_alpha.decision.thesis import TRADING_THESIS_SCHEMA
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.portfolio import (
    RISK_BUDGET_SCHEMA,
    CurrentPositionInput,
    PortfolioAccountSnapshot,
    PortfolioOutputMode,
    RiskBudget,
    RiskDecisionState,
    ThesisAllocationRequest,
)
from tests.postgres_path_repositories import (
    PostgresPortfolioDecisionRepository,
    postgres_cli_arguments,
)


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 20, 15, 10, tzinfo=TZ)


def _thesis(index: int, symbol: str) -> TradingThesis:
    evidence = DecisionEvidenceReference(
        artifact_type="PATH_FORECAST",
        artifact_id=ArtifactId(f"path-evidence-{index}"),
        content_hash=f"sha256:{index}" + "1" * 63,
        status="AVAILABLE_FOR_RESEARCH",
    )
    return TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId(f"thesis-risk-{index}"),
        opportunity_id=OpportunityId(f"opportunity-risk-{index}"),
        source_opportunity_version=0,
        symbol=symbol,
        supporting_evidence=(evidence,),
        invalidation_conditions=(
            InvalidationCondition(
                condition_id=f"condition-{index}",
                kind=InvalidationKind.PRICE,
                description="explicit synthetic invalidation",
                reason_code="SYNTHETIC_INVALIDATION",
            ),
        ),
        time_invalidation=NOW + timedelta(days=5),
        state=ThesisState.APPROVED,
        version=0,
        approved_by="approver-a",
        approval_reason="synthetic fixture",
        created_at=NOW - timedelta(minutes=5),
        updated_at=NOW - timedelta(minutes=5),
        last_actor="approver-a",
        last_reason="synthetic fixture",
    )


def _budget(**changes: object) -> RiskBudget:
    values: dict[str, object] = {
        "profile_id": "test_risk_profile_v1",
        "maximum_gross_exposure": 0.8,
        "single_symbol_limit": 0.4,
        "theme_limit": 0.5,
        "liquidity_max_participation": 0.1,
        "minimum_cash_reserve": 0.1,
        "maximum_loss_budget": 0.05,
        "t_plus_one_enforced": True,
        "risk_service_timeout_seconds": 2.0,
        "market_scope": "A_SHARE",
        "allowed_side": "LONG_ONLY",
        "schema_version": RISK_BUDGET_SCHEMA,
    }
    values.update(changes)
    return RiskBudget.create(**values)  # type: ignore[arg-type]


def _account(cash: float = 90_000.0) -> PortfolioAccountSnapshot:
    return PortfolioAccountSnapshot(
        net_asset_value=100_000.0,
        available_cash=cash,
        observed_at=NOW - timedelta(seconds=1),
        source_reference="synthetic-account-snapshot-v1",
    )


def _allocation(
    thesis: TradingThesis,
    *,
    theme: str = "theme-a",
    target: int = 200,
    price: float = 100.0,
    adv: float = 1_000_000.0,
    loss: float = 5.0,
) -> ThesisAllocationRequest:
    return ThesisAllocationRequest(
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        theme_id=theme,
        target_quantity=target,
        reference_price=price,
        average_daily_trade_value=adv,
        loss_per_share=loss,
    )


def _position(
    symbol: str, total: int = 0, available: int = 0
) -> CurrentPositionInput:
    return CurrentPositionInput(
        symbol=symbol,
        total_quantity=total,
        available_quantity=available,
        market_price=100.0,
    )


def _run(
    tmp_path,
    *,
    theses,
    allocations,
    positions,
    budget=None,
    account=None,
    completed_at=None,
    key="portfolio-risk-1",
):
    repository = PostgresPortfolioDecisionRepository(tmp_path / "portfolio.postgres-scope")
    service = PortfolioRiskApplicationService(repository)
    result = service.run(
        theses=theses,
        allocations=allocations,
        current_positions=positions,
        account_snapshot=account or _account(),
        risk_budget=budget or _budget(),
        mode=PortfolioOutputMode.MANUAL_CONFIRMATION,
        actor="risk-operator-a",
        reason="synthetic risk assessment",
        portfolio_created_at=NOW,
        risk_started_at=NOW,
        risk_completed_at=completed_at or NOW + timedelta(seconds=1),
        idempotency_key=key,
    )
    return result, repository


def test_approved_risk_is_independent_durable_and_manual_only(tmp_path) -> None:
    thesis = _thesis(1, "000001.SZ")
    (portfolio, risk), repository = _run(
        tmp_path,
        theses=(thesis,),
        allocations=(_allocation(thesis),),
        positions=(_position(thesis.symbol),),
    )

    assert risk.state is RiskDecisionState.APPROVED
    assert risk.approved_for_manual_intent
    assert risk.mode is PortfolioOutputMode.MANUAL_CONFIRMATION
    assert repository.get_portfolio(portfolio.decision_id) == portfolio
    assert repository.get_risk(risk.risk_decision_id) == risk
    assert len(risk.constraints) == 8
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_portfolio_risk.py",
            *postgres_cli_arguments(repository.path),
            "show-risk",
            "--risk-decision-id",
            str(risk.risk_decision_id),
        ],
        cwd=Path(__file__).parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(risk.risk_decision_id) in completed.stdout


def test_theme_concentration_rejection_has_structured_reason(tmp_path) -> None:
    first = _thesis(1, "000001.SZ")
    second = _thesis(2, "000002.SZ")
    (portfolio, risk), _ = _run(
        tmp_path,
        theses=(first, second),
        allocations=(
            _allocation(first, target=300),
            _allocation(second, target=300),
        ),
        positions=(_position(first.symbol), _position(second.symbol)),
    )

    assert portfolio.target_positions
    assert risk.state is RiskDecisionState.REJECTED
    assert "THEME_LIMIT_EXCEEDED" in risk.reason_codes


def test_available_cash_rejection_is_fail_closed(tmp_path) -> None:
    thesis = _thesis(1, "000001.SZ")
    (_, risk), _ = _run(
        tmp_path,
        theses=(thesis,),
        allocations=(_allocation(thesis, target=300),),
        positions=(_position(thesis.symbol),),
        account=_account(cash=20_000.0),
    )

    assert risk.state is RiskDecisionState.REJECTED
    assert "AVAILABLE_CASH_INSUFFICIENT" in risk.reason_codes


@pytest.mark.parametrize(
    ("allocation_changes", "expected_reason"),
    (
        ({"target": 900}, "MAXIMUM_GROSS_EXPOSURE_EXCEEDED"),
        ({"target": 500}, "SINGLE_SYMBOL_LIMIT_EXCEEDED"),
        ({"adv": 100_000.0}, "LIQUIDITY_LIMIT_EXCEEDED"),
        ({"loss": 30.0}, "MAXIMUM_LOSS_BUDGET_EXCEEDED"),
    ),
)
def test_each_portfolio_hard_limit_has_structured_rejection(
    tmp_path, allocation_changes, expected_reason
) -> None:
    thesis = _thesis(1, "000001.SZ")
    (_, risk), _ = _run(
        tmp_path,
        theses=(thesis,),
        allocations=(_allocation(thesis, **allocation_changes),),
        positions=(_position(thesis.symbol),),
        key=f"risk-{expected_reason}",
    )

    assert risk.state is RiskDecisionState.REJECTED
    assert expected_reason in risk.reason_codes


def test_t_plus_one_rejects_unavailable_sell_quantity(tmp_path) -> None:
    thesis = _thesis(1, "000001.SZ")
    (_, risk), _ = _run(
        tmp_path,
        theses=(thesis,),
        allocations=(_allocation(thesis, target=0),),
        positions=(_position(thesis.symbol, total=1000, available=100),),
    )

    assert risk.state is RiskDecisionState.REJECTED
    assert "T_PLUS_ONE_AVAILABLE_QUANTITY_EXCEEDED" in risk.reason_codes


def test_risk_timeout_fails_closed(tmp_path) -> None:
    thesis = _thesis(1, "000001.SZ")
    (_, risk), _ = _run(
        tmp_path,
        theses=(thesis,),
        allocations=(_allocation(thesis),),
        positions=(_position(thesis.symbol),),
        completed_at=NOW + timedelta(seconds=3),
    )

    assert risk.state is RiskDecisionState.TIMEOUT
    assert not risk.approved_for_manual_intent
    assert risk.reason_codes == ("RISK_SERVICE_TIMEOUT_FAIL_CLOSED",)


def test_conflicting_theses_cannot_reach_risk_approval(tmp_path) -> None:
    first = _thesis(1, "000001.SZ")
    second = _thesis(2, "000001.SZ")
    (portfolio, risk), _ = _run(
        tmp_path,
        theses=(first, second),
        allocations=(_allocation(first), _allocation(second, target=100)),
        positions=(_position(first.symbol),),
    )

    assert portfolio.state.value == "CONFLICTED"
    assert portfolio.target_positions == ()
    assert risk.state is RiskDecisionState.REJECTED
    assert risk.reason_codes == ("CONFLICTING_THESES_FOR_SYMBOL",)


def test_missing_risk_configuration_has_no_implicit_default(tmp_path) -> None:
    thesis = _thesis(1, "000001.SZ")
    repository = PostgresPortfolioDecisionRepository(tmp_path / "portfolio.postgres-scope")
    service = PortfolioRiskApplicationService(repository)

    with pytest.raises(ValueError, match="no default exists"):
        service.run(
            theses=(thesis,),
            allocations=(_allocation(thesis),),
            current_positions=(_position(thesis.symbol),),
            account_snapshot=_account(),
            risk_budget=None,
            mode=PortfolioOutputMode.SIMULATION,
            actor="risk-operator-a",
            reason="missing config",
            portfolio_created_at=NOW,
            risk_started_at=NOW,
            risk_completed_at=NOW + timedelta(seconds=1),
            idempotency_key="missing-budget",
        )


def test_repository_recomputes_and_rejects_forged_risk_approval(tmp_path) -> None:
    thesis = _thesis(1, "000001.SZ")
    (portfolio, rejected), repository = _run(
        tmp_path,
        theses=(thesis,),
        allocations=(_allocation(thesis, target=300),),
        positions=(_position(thesis.symbol),),
        account=_account(cash=20_000.0),
    )
    forged_constraints = tuple(
        replace(item, passed=True, reason_code="CONSTRAINT_PASSED")
        for item in rejected.constraints
    )
    forged = replace(
        rejected,
        state=RiskDecisionState.APPROVED,
        constraints=forged_constraints,
        reason_codes=("ALL_HARD_RISK_CONSTRAINTS_PASSED",),
    )

    with pytest.raises(ValueError, match="cannot bypass independent risk"):
        repository.save_risk(
            forged,
            idempotency_key="forged-risk",
            command_hash=canonical_hash(forged.to_canonical_dict()),
        )
    assert repository.get_portfolio(portfolio.decision_id) == portfolio
