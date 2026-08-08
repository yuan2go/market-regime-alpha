from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import psycopg
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.trading_lifecycle import (
    ManualExecutionApplicationService,
)
from market_regime_alpha.core.identity import (
    PortfolioDecisionId,
    ThesisId,
)
from market_regime_alpha.execution import (
    ManualOrderState,
)
from market_regime_alpha.portfolio import (
    RISK_BUDGET_SCHEMA,
    IndependentRiskService,
    PortfolioAccountSnapshot,
    PortfolioDecision,
    PortfolioDecisionState,
    PortfolioOutputMode,
    RiskBudget,
    TargetPosition,
)
from tests.postgres_path_repositories import (
    PostgresManualExecutionRepository,
    postgres_cli_arguments,
    postgres_connection,
)
from market_regime_alpha.portfolio.lifecycle import PORTFOLIO_DECISION_SCHEMA
from market_regime_alpha.position import PositionProjector, PositionState


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=TZ)


def _budget() -> RiskBudget:
    return RiskBudget.create(
        profile_id="test_risk_profile_v1",
        maximum_gross_exposure=1.0,
        single_symbol_limit=1.0,
        theme_limit=1.0,
        liquidity_max_participation=1.0,
        minimum_cash_reserve=0.0,
        maximum_loss_budget=1.0,
        t_plus_one_enforced=True,
        risk_service_timeout_seconds=2.0,
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        schema_version=RISK_BUDGET_SCHEMA,
    )


def _authority(*, current: int = 0, available: int = 0, target: int = 100):
    budget = _budget()
    target_position = TargetPosition(
        thesis_id=ThesisId("thesis-execution-test"),
        symbol="000001.SZ",
        theme_id="theme-bank",
        current_quantity=current,
        available_quantity=available,
        target_quantity=target,
        trade_quantity=target - current,
        reference_price=10.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=1.0,
    )
    account = PortfolioAccountSnapshot(
        net_asset_value=100_000.0,
        available_cash=100_000.0,
        observed_at=NOW - timedelta(seconds=1),
        source_reference="synthetic-account-v1",
    )
    portfolio = PortfolioDecision(
        schema_version=PORTFOLIO_DECISION_SCHEMA,
        decision_id=PortfolioDecisionId(
            f"portfolio-execution-{current}-{available}-{target}"
        ),
        mode=PortfolioOutputMode.MANUAL_CONFIRMATION,
        state=PortfolioDecisionState.PROPOSED_FOR_RISK,
        risk_budget_id=budget.configuration_id,
        risk_budget_hash=budget.configuration_hash,
        risk_budget=budget,
        account_snapshot=account,
        target_positions=(target_position,),
        thesis_ids=(target_position.thesis_id,),
        version=0,
        actor="portfolio-operator",
        reason="synthetic execution authority",
        created_at=NOW,
        reason_codes=("PORTFOLIO_PROPOSED_FOR_INDEPENDENT_RISK",),
    )
    risk = IndependentRiskService().assess(
        portfolio,
        actor="risk-operator",
        reason="synthetic execution authority",
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
    )
    assert risk.approved_for_manual_intent
    return portfolio, risk, target_position


def _service(tmp_path):
    repository = PostgresManualExecutionRepository(tmp_path / "execution.postgres-scope")
    return ManualExecutionApplicationService(repository), repository


def _trade(service, *, current=0, available=0, target=100, key="create-trade"):
    portfolio, risk, target_position = _authority(
        current=current, available=available, target=target
    )
    record = service.create_trade(
        risk_decision=risk,
        portfolio_decision=portfolio,
        target_position=target_position,
        account_id="account-a",
        expected_price_lower=9.8,
        expected_price_upper=10.2,
        actor="human-trader-a",
        reason="manual record only",
        created_at=NOW + timedelta(seconds=2),
        idempotency_key=key,
    )
    return record


def test_partial_fill_duplicate_idempotency_and_full_position_rebuild(tmp_path) -> None:
    service, repository = _service(tmp_path)
    trade = _trade(service)
    partial, first = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="external-fill-1",
        quantity=40,
        price=10.0,
        fees=1.0,
        occurred_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=1, seconds=1),
        actor="human-trader-a",
        reason="first partial fill",
        idempotency_key="fill-command-1",
    )
    assert partial.state is ManualOrderState.PARTIALLY_FILLED
    duplicate, duplicate_fill = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="external-fill-1",
        quantity=40,
        price=10.0,
        fees=1.0,
        occurred_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=1, seconds=1),
        actor="human-trader-a",
        reason="first partial fill",
        idempotency_key="fill-command-1",
    )
    assert duplicate == partial
    assert duplicate_fill == first
    filled, _ = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="external-fill-2",
        quantity=60,
        price=10.1,
        fees=1.0,
        occurred_at=NOW + timedelta(minutes=2),
        recorded_at=NOW + timedelta(minutes=2, seconds=1),
        actor="human-trader-a",
        reason="final partial fill",
        idempotency_key="fill-command-2",
    )
    assert filled.state is ManualOrderState.FILLED
    snapshot = service.rebuild_position(
        account_id="account-a",
        symbol="000001.SZ",
        as_of=NOW + timedelta(minutes=3),
    )
    assert snapshot.state is PositionState.OPEN
    assert snapshot.total_quantity == 100
    assert len(repository.fills_for_trade(trade.manual_trade_id)) == 2
    restarted = ManualExecutionApplicationService(
        PostgresManualExecutionRepository(repository.path)
    ).rebuild_position(
        account_id="account-a",
        symbol="000001.SZ",
        as_of=NOW + timedelta(minutes=3),
    )
    assert restarted == snapshot
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/record_manual_fill.py",
            *postgres_cli_arguments(repository.path),
            "position",
            "--account-id",
            "account-a",
            "--symbol",
            "000001.SZ",
            "--as-of",
            (NOW + timedelta(minutes=3)).isoformat(),
        ],
        cwd=Path(__file__).parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(snapshot.snapshot_id) in completed.stdout


def test_fill_correction_is_append_only_and_rebuilds_effective_position(tmp_path) -> None:
    service, repository = _service(tmp_path)
    trade = _trade(service)
    _, original = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="external-original",
        quantity=100,
        price=10.0,
        fees=0.0,
        occurred_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=1, seconds=1),
        actor="human-trader-a",
        reason="original fill",
        idempotency_key="original-fill",
    )
    corrected_trade, correction = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="external-correction",
        quantity=80,
        price=11.0,
        fees=0.0,
        occurred_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=2),
        actor="human-trader-a",
        reason="correct quantity and price",
        idempotency_key="correction-fill",
        correction_of_fill_id=original.fill_id,
    )
    assert corrected_trade.state is ManualOrderState.PARTIALLY_FILLED
    assert correction.correction_of_fill_id == original.fill_id
    snapshot = service.rebuild_position(
        account_id="account-a",
        symbol="000001.SZ",
        as_of=NOW + timedelta(minutes=3),
    )
    assert snapshot.total_quantity == 80
    assert snapshot.average_cost == 11.0
    assert snapshot.effective_fill_ids == (correction.fill_id,)
    with postgres_connection(repository.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM manual_fills").fetchone()[0] == 2
        with pytest.raises(psycopg.Error, match="append-only"):
            connection.execute("UPDATE manual_fills SET symbol = 'x'")


@pytest.mark.parametrize(
    "state",
    (ManualOrderState.CANCELLED, ManualOrderState.REJECTED, ManualOrderState.UNKNOWN),
)
def test_cancel_reject_and_unknown_do_not_create_position(tmp_path, state) -> None:
    service, repository = _service(tmp_path)
    trade = _trade(service, key=f"create-{state.value}")
    updated = service.mark_order_state(
        trade.manual_trade_id,
        expected_version=0,
        state=state,
        actor="human-trader-a",
        reason=f"mark {state.value}",
        changed_at=NOW + timedelta(minutes=1),
        idempotency_key=f"state-{state.value}",
    )
    assert updated.state is state
    assert repository.fills_for_trade(trade.manual_trade_id) == ()
    with pytest.raises(ValueError, match="requires at least one Fill"):
        service.rebuild_position(
            account_id="account-a",
            symbol="000001.SZ",
            as_of=NOW + timedelta(minutes=2),
        )


def test_sell_without_authoritative_buy_lot_requires_reconciliation(tmp_path) -> None:
    service, _ = _service(tmp_path)
    trade = _trade(service, current=100, available=100, target=0)
    service.record_fill(
        trade.manual_trade_id,
        external_fill_id="external-sell",
        quantity=100,
        price=10.0,
        fees=1.0,
        occurred_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=1, seconds=1),
        actor="human-trader-a",
        reason="manual sell",
        idempotency_key="sell-fill",
    )
    snapshot = service.rebuild_position(
        account_id="account-a",
        symbol="000001.SZ",
        as_of=NOW + timedelta(minutes=2),
    )
    assert snapshot.state is PositionState.RECONCILIATION_REQUIRED
    assert "SELL_QUANTITY_EXCEEDS_AUTHORITATIVE_LOTS" in snapshot.reason_codes


def test_duplicate_external_fill_under_new_key_never_double_counts(tmp_path) -> None:
    service, _ = _service(tmp_path)
    trade = _trade(service)
    kwargs = {
        "external_fill_id": "same-external-fill",
        "quantity": 40,
        "price": 10.0,
        "fees": 0.0,
        "occurred_at": NOW + timedelta(minutes=1),
        "recorded_at": NOW + timedelta(minutes=1, seconds=1),
        "actor": "human-trader-a",
        "reason": "duplicate check",
    }
    service.record_fill(trade.manual_trade_id, idempotency_key="key-one", **kwargs)
    with pytest.raises(ValueError, match="already exists"):
        service.record_fill(trade.manual_trade_id, idempotency_key="key-two", **kwargs)


def test_rejected_risk_cannot_create_manual_trade(tmp_path) -> None:
    service, _ = _service(tmp_path)
    portfolio, _, target = _authority()
    rejected = IndependentRiskService().assess(
        portfolio,
        actor="risk-operator",
        reason="timeout fixture",
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=3),
    )

    with pytest.raises(ValueError, match="approved RiskDecision"):
        service.create_trade(
            risk_decision=rejected,
            portfolio_decision=portfolio,
            target_position=target,
            account_id="account-a",
            expected_price_lower=9.8,
            expected_price_upper=10.2,
            actor="human-trader-a",
            reason="must fail",
            created_at=NOW + timedelta(seconds=4),
            idempotency_key="rejected-risk-trade",
        )


def test_position_projector_cannot_create_actual_position_without_fill() -> None:
    with pytest.raises(ValueError, match="requires at least one Fill"):
        PositionProjector().project(
            account_id="account-a",
            symbol="000001.SZ",
            fills=(),
            as_of=NOW,
        )
