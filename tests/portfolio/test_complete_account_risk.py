from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.trading_lifecycle import (
    CompleteAccountPortfolioRiskApplicationService,
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
from market_regime_alpha.portfolio import (
    RISK_BUDGET_SCHEMA,
    AccountPortfolioCompleteness,
    AccountPosition,
    AccountReconciliationState,
    AuthoritativeAccountPortfolioSnapshot,
    CompleteAccountRiskConfiguration,
    PortfolioOutputMode,
    RiskBudget,
    RiskDecisionState,
    SQLiteCompleteAccountPortfolioRiskRepository,
    ThesisAllocationRequest,
)
from market_regime_alpha.portfolio.sqlite_account_authority import (
    COMPLETE_ACCOUNT_RISK_DOWN_MIGRATION,
)
from market_regime_alpha.portfolio.risk_routes import RiskIncreasingDecision


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 20, 14, 55, tzinfo=TZ)


def _thesis(symbol: str, index: int = 1) -> TradingThesis:
    evidence = DecisionEvidenceReference(
        artifact_type="PATH_FORECAST",
        artifact_id=ArtifactId(f"path-complete-account-{index}"),
        content_hash=f"sha256:{index}" + "1" * 63,
        status="AVAILABLE_FOR_RESEARCH",
    )
    return TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId(f"thesis-complete-account-{index}"),
        opportunity_id=OpportunityId(f"opportunity-complete-account-{index}"),
        source_opportunity_version=0,
        symbol=symbol,
        supporting_evidence=(evidence,),
        invalidation_conditions=(
            InvalidationCondition(
                condition_id=f"condition-{index}",
                kind=InvalidationKind.PRICE,
                description="synthetic invalidation",
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


def _risk_configuration(**changes: object) -> CompleteAccountRiskConfiguration:
    values: dict[str, object] = {
        "profile_id": "test_risk_profile_v1",
        "maximum_gross_exposure": 0.8,
        "single_symbol_limit": 0.75,
        "theme_limit": 0.9,
        "liquidity_max_participation": 0.1,
        "minimum_cash_reserve": 0.0,
        "maximum_loss_budget": 0.2,
        "t_plus_one_enforced": True,
        "risk_service_timeout_seconds": 2.0,
        "market_scope": "A_SHARE",
        "allowed_side": "LONG_ONLY",
        "schema_version": RISK_BUDGET_SCHEMA,
    }
    maximum_age = float(changes.pop("maximum_account_snapshot_age_seconds", 60.0))
    values.update(changes)
    budget = RiskBudget.create(**values)  # type: ignore[arg-type]
    return CompleteAccountRiskConfiguration.create(
        profile_id="test_complete_account_risk_v1",
        risk_budget=budget,
        maximum_account_snapshot_age_seconds=maximum_age,
        schema_version="complete-account-risk-configuration-v1",
    )


def test_unallocated_existing_position_enters_post_trade_gross_risk(tmp_path) -> None:
    thesis = _thesis("000001.SZ")
    account = AuthoritativeAccountPortfolioSnapshot.create(
        account_id="account-a",
        as_of=NOW - timedelta(seconds=1),
        source_reference="synthetic-reconciled-account-v1",
        net_asset_value=100_000.0,
        available_cash=30_000.0,
        all_positions=(
            AccountPosition(
                symbol="000099.SZ",
                theme_id="theme-existing",
                total_quantity=700,
                available_quantity=700,
                market_price=100.0,
                loss_per_share=5.0,
                source_position_snapshot_id=ArtifactId("position-existing-a"),
                source_position_snapshot_hash="sha256:" + "a" * 64,
            ),
        ),
        completeness=AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
        reconciliation_state=AccountReconciliationState.RECONCILED,
        version=3,
    )
    allocation = ThesisAllocationRequest(
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        theme_id="theme-new",
        target_quantity=200,
        reference_price=100.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=5.0,
    )
    service = CompleteAccountPortfolioRiskApplicationService(
        SQLiteCompleteAccountPortfolioRiskRepository(
            tmp_path / "complete-account.sqlite3"
        )
    )

    portfolio, risk = service.run(
        theses=(thesis,),
        allocations=(allocation,),
        account_snapshot=account,
        configuration=_risk_configuration(),
        mode=PortfolioOutputMode.MANUAL_CONFIRMATION,
        actor="risk-operator-a",
        reason="synthetic complete-account assessment",
        portfolio_created_at=NOW,
        risk_started_at=NOW,
        risk_completed_at=NOW + timedelta(seconds=1),
        idempotency_key="complete-account-gross-1",
    )

    assert {item.symbol for item in portfolio.post_trade.positions} == {
        "000001.SZ",
        "000099.SZ",
    }
    assert risk.state is RiskDecisionState.REJECTED
    assert "MAXIMUM_GROSS_EXPOSURE_EXCEEDED" in risk.reason_codes


def test_unallocated_existing_positions_enter_theme_and_loss_risk(tmp_path) -> None:
    thesis = _thesis("000001.SZ")
    positions = tuple(
        AccountPosition(
            symbol=symbol,
            theme_id="theme-shared",
            total_quantity=quantity,
            available_quantity=quantity,
            market_price=100.0,
            loss_per_share=loss,
            source_position_snapshot_id=ArtifactId(f"position-{symbol}"),
            source_position_snapshot_hash="sha256:" + digest * 64,
        )
        for symbol, quantity, loss, digest in (
            ("000098.SZ", 250, 20.0, "b"),
            ("000099.SZ", 250, 20.0, "c"),
        )
    )
    account = AuthoritativeAccountPortfolioSnapshot.create(
        account_id="account-a",
        as_of=NOW - timedelta(seconds=1),
        source_reference="synthetic-complete-account-theme-loss",
        net_asset_value=100_000.0,
        available_cash=50_000.0,
        all_positions=positions,
        completeness=AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
        reconciliation_state=AccountReconciliationState.RECONCILED,
        version=1,
    )
    allocation = ThesisAllocationRequest(
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        theme_id="theme-shared",
        target_quantity=100,
        reference_price=100.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=20.0,
    )
    service = CompleteAccountPortfolioRiskApplicationService(
        SQLiteCompleteAccountPortfolioRiskRepository(tmp_path / "risk.sqlite3")
    )

    _, risk = service.run(
        theses=(thesis,),
        allocations=(allocation,),
        account_snapshot=account,
        configuration=_risk_configuration(
            theme_limit=0.55,
            maximum_loss_budget=0.1,
        ),
        mode=PortfolioOutputMode.SIMULATION,
        actor="risk-operator-a",
        reason="complete account theme and loss",
        portfolio_created_at=NOW,
        risk_started_at=NOW,
        risk_completed_at=NOW + timedelta(seconds=1),
        idempotency_key="complete-account-theme-loss",
    )

    assert risk.state is RiskDecisionState.REJECTED
    assert "THEME_LIMIT_EXCEEDED" in risk.reason_codes
    assert "MAXIMUM_LOSS_BUDGET_EXCEEDED" in risk.reason_codes


def test_incomplete_stale_or_unreconciled_account_fails_closed(tmp_path) -> None:
    thesis = _thesis("000001.SZ")
    allocation = ThesisAllocationRequest(
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        theme_id="theme-a",
        target_quantity=100,
        reference_price=100.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=5.0,
    )
    cases = (
        (
            AccountPortfolioCompleteness.PARTIAL,
            AccountReconciliationState.RECONCILED,
            NOW - timedelta(seconds=1),
            "ACCOUNT_PORTFOLIO_INCOMPLETE",
        ),
        (
            AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
            AccountReconciliationState.RECONCILIATION_REQUIRED,
            NOW - timedelta(seconds=1),
            "ACCOUNT_RECONCILIATION_REQUIRED",
        ),
        (
            AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
            AccountReconciliationState.RECONCILED,
            NOW - timedelta(seconds=61),
            "ACCOUNT_SNAPSHOT_STALE",
        ),
    )

    for index, (completeness, reconciliation, as_of, expected) in enumerate(cases):
        account = AuthoritativeAccountPortfolioSnapshot.create(
            account_id="account-a",
            as_of=as_of,
            source_reference=f"synthetic-account-case-{index}",
            net_asset_value=100_000.0,
            available_cash=100_000.0,
            all_positions=(),
            completeness=completeness,
            reconciliation_state=reconciliation,
            version=index,
        )
        service = CompleteAccountPortfolioRiskApplicationService(
            SQLiteCompleteAccountPortfolioRiskRepository(
                tmp_path / f"risk-{index}.sqlite3"
            )
        )

        _, risk = service.run(
            theses=(thesis,),
            allocations=(allocation,),
            account_snapshot=account,
            configuration=_risk_configuration(),
            mode=PortfolioOutputMode.SIMULATION,
            actor="risk-operator-a",
            reason="fail closed account input",
            portfolio_created_at=NOW,
            risk_started_at=NOW,
            risk_completed_at=NOW + timedelta(seconds=1),
            idempotency_key=f"fail-closed-account-{index}",
        )

        assert risk.state is RiskDecisionState.DATA_INSUFFICIENT
        assert risk.reason_codes == (expected,)


@pytest.mark.parametrize("target_quantity", (100, 0))
def test_pure_reduction_and_full_close_use_complete_account(
    tmp_path, target_quantity: int
) -> None:
    thesis = _thesis("000001.SZ")
    account = AuthoritativeAccountPortfolioSnapshot.create(
        account_id="account-a",
        as_of=NOW - timedelta(seconds=1),
        source_reference=f"synthetic-reduction-{target_quantity}",
        net_asset_value=100_000.0,
        available_cash=80_000.0,
        all_positions=(
            AccountPosition(
                symbol=thesis.symbol,
                theme_id="theme-a",
                total_quantity=200,
                available_quantity=200,
                market_price=100.0,
                loss_per_share=5.0,
                source_position_snapshot_id=ArtifactId("position-reduction-a"),
                source_position_snapshot_hash="sha256:" + "d" * 64,
            ),
        ),
        completeness=AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
        reconciliation_state=AccountReconciliationState.RECONCILED,
        version=2,
    )
    allocation = ThesisAllocationRequest(
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        theme_id="theme-a",
        target_quantity=target_quantity,
        reference_price=100.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=5.0,
    )
    service = CompleteAccountPortfolioRiskApplicationService(
        SQLiteCompleteAccountPortfolioRiskRepository(
            tmp_path / f"reduce-{target_quantity}.sqlite3"
        )
    )

    portfolio, risk = service.run(
        theses=(thesis,),
        allocations=(allocation,),
        account_snapshot=account,
        configuration=_risk_configuration(),
        mode=PortfolioOutputMode.MANUAL_CONFIRMATION,
        actor="risk-operator-a",
        reason="strict risk reduction fixture",
        portfolio_created_at=NOW,
        risk_started_at=NOW,
        risk_completed_at=NOW + timedelta(seconds=1),
        idempotency_key=f"reduce-{target_quantity}",
    )

    assert risk.state is RiskDecisionState.APPROVED
    assert portfolio.post_trade.available_cash == 100_000.0 - target_quantity * 100.0
    assert [item.total_quantity for item in portfolio.post_trade.positions] == (
        [target_quantity] if target_quantity else []
    )


def test_empty_account_idempotency_and_sqlite_restart(tmp_path) -> None:
    thesis = _thesis("000001.SZ")
    account = AuthoritativeAccountPortfolioSnapshot.create(
        account_id="account-empty",
        as_of=NOW - timedelta(seconds=1),
        source_reference="synthetic-empty-account",
        net_asset_value=100_000.0,
        available_cash=100_000.0,
        all_positions=(),
        completeness=AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
        reconciliation_state=AccountReconciliationState.RECONCILED,
        version=0,
    )
    allocation = ThesisAllocationRequest(
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        theme_id="theme-a",
        target_quantity=100,
        reference_price=100.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=5.0,
    )
    path = tmp_path / "restart.sqlite3"
    repository = SQLiteCompleteAccountPortfolioRiskRepository(path)
    service = CompleteAccountPortfolioRiskApplicationService(repository)
    arguments = {
        "theses": (thesis,),
        "allocations": (allocation,),
        "account_snapshot": account,
        "configuration": _risk_configuration(),
        "mode": PortfolioOutputMode.MANUAL_CONFIRMATION,
        "actor": "risk-operator-a",
        "reason": "empty account entry fixture",
        "portfolio_created_at": NOW,
        "risk_started_at": NOW,
        "risk_completed_at": NOW + timedelta(seconds=1),
        "idempotency_key": "empty-account-idempotency",
    }

    first = service.run(**arguments)  # type: ignore[arg-type]
    duplicate = service.run(**arguments)  # type: ignore[arg-type]
    restarted = SQLiteCompleteAccountPortfolioRiskRepository(path)

    assert duplicate == first
    assert first[1].state is RiskDecisionState.APPROVED
    delta = first[0].post_trade.proposed_deltas[0]
    increasing = RiskIncreasingDecision.create(
        portfolio=first[0],
        risk=first[1],
        delta=delta,
        created_at=NOW + timedelta(seconds=2),
    )
    assert increasing.risk_decision_id == first[1].risk_decision_id

    class RejectedRisk:
        state = RiskDecisionState.REJECTED

    with pytest.raises(
        ValueError, match="increasing risk requires approved complete-account Risk"
    ):
        RiskIncreasingDecision.create(
            portfolio=first[0],
            risk=RejectedRisk(),  # type: ignore[arg-type]
            delta=delta,
            created_at=NOW + timedelta(seconds=2),
        )
    assert restarted.get_account_snapshot(str(account.snapshot_id)) == account
    assert (
        restarted.get_complete_account_portfolio(first[0].decision_id)
        == first[0]
    )
    assert restarted.get_complete_account_risk(first[1].risk_decision_id) == first[1]

    changed = {**arguments, "reason": "different command semantics"}
    with pytest.raises(ValueError, match="idempotency key reused"):
        service.run(**changed)  # type: ignore[arg-type]


def test_complete_account_migration_has_isolated_down_path(tmp_path) -> None:
    path = tmp_path / "migration.sqlite3"
    SQLiteCompleteAccountPortfolioRiskRepository(path)

    with sqlite3.connect(path) as connection:
        connection.executescript(
            COMPLETE_ACCOUNT_RISK_DOWN_MIGRATION.read_text(encoding="utf-8")
        )
        names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "complete_account_risk_decisions" not in names
    assert "complete_account_portfolio_decisions" not in names
    assert "authoritative_account_portfolio_snapshots" not in names
    assert "daily_runs" not in names


def test_complete_account_cli_runs_and_restores_risk(tmp_path) -> None:
    thesis = _thesis("000001.SZ")
    account = AuthoritativeAccountPortfolioSnapshot.create(
        account_id="account-cli",
        as_of=NOW - timedelta(seconds=1),
        source_reference="synthetic-cli-account",
        net_asset_value=100_000.0,
        available_cash=100_000.0,
        all_positions=(),
        completeness=AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
        reconciliation_state=AccountReconciliationState.RECONCILED,
        version=0,
    )
    allocation = ThesisAllocationRequest(
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        theme_id="theme-a",
        target_quantity=100,
        reference_price=100.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=5.0,
    )
    request = {
        "theses": [thesis.to_canonical_dict()],
        "allocations": [
            {
                "thesis_id": str(allocation.thesis_id),
                "symbol": allocation.symbol,
                "theme_id": allocation.theme_id,
                "target_quantity": allocation.target_quantity,
                "reference_price": allocation.reference_price,
                "average_daily_trade_value": allocation.average_daily_trade_value,
                "loss_per_share": allocation.loss_per_share,
            }
        ],
        "account_snapshot": account.to_canonical_dict(),
        "configuration": _risk_configuration().to_canonical_dict(),
        "mode": PortfolioOutputMode.MANUAL_CONFIRMATION.value,
        "actor": "risk-operator-a",
        "reason": "CLI complete-account fixture",
        "portfolio_created_at": NOW.isoformat(),
        "risk_started_at": NOW.isoformat(),
        "risk_completed_at": (NOW + timedelta(seconds=1)).isoformat(),
        "idempotency_key": "complete-account-cli",
    }
    request_path = tmp_path / "request.json"
    database = tmp_path / "cli.sqlite3"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    root = Path(__file__).parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_portfolio_risk.py",
            "--database",
            str(database),
            "run-full-account",
            "--request",
            str(request_path),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    risk_id = str(result["risk"]["risk_decision_id"])

    restored = subprocess.run(
        [
            sys.executable,
            "scripts/run_portfolio_risk.py",
            "--database",
            str(database),
            "show-full-account-risk",
            "--risk-decision-id",
            risk_id,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(restored.stdout)["risk_decision_id"] == risk_id
