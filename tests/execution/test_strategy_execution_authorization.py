from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, ManualTradeId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    STRATEGY_AUTHORIZED_MANUAL_TRADE_SCHEMA,
    ManualOrderState,
    ManualTradeAuthorityRoute,
    ManualTradeRecord,
    TradeSide,
)
from market_regime_alpha.execution.strategy_intent import (
    StrategyExecutionAuthorization,
)


NOW = datetime(2026, 8, 14, 15, 5, tzinfo=ZoneInfo("Asia/Shanghai"))


def _reference(kind: str, identity: str) -> RuntimeArtifactReference:
    digest = canonical_hash({"kind": kind, "identity": identity})
    return RuntimeArtifactReference(
        kind,
        ArtifactId(f"{identity}:{digest[7:]}"),
        digest,
    )


def _authorization(**overrides: object) -> StrategyExecutionAuthorization:
    values: dict[str, object] = {
        "portfolio_decision_reference": _reference("CROSS_STRATEGY_PORTFOLIO", "portfolio"),
        "strategy_version_reference": _reference("STRATEGY_VERSION", "swing"),
        "proposal_reference": _reference("STRATEGY_PROPOSAL", "proposal"),
        "account_observation_reference": _reference("MANUAL_ACCOUNT_OBSERVATION", "account"),
        "trading_calendar_reference": _reference("TRADING_CALENDAR", "calendar"),
        "account_id": "account-a",
        "symbol": "000001.SZ",
        "action": "ENTER",
        "accepted_weight": Decimal("0.20"),
        "account_nav": Decimal("100000"),
        "available_cash": Decimal("50000"),
        "reference_price": Decimal("10.03"),
        "current_quantity": 0,
        "available_quantity": 0,
        "lot_size": 100,
        "operator_quantity": None,
        "override_reason": None,
        "decision_time": NOW,
        "created_at": NOW,
    }
    values.update(overrides)
    return StrategyExecutionAuthorization.create(**values)  # type: ignore[arg-type]


def test_enter_weight_is_rounded_down_to_an_a_share_lot() -> None:
    authorization = _authorization()

    assert authorization.recommended_quantity == 1900
    assert authorization.intended_quantity == 1900
    assert authorization.authorized_notional == Decimal("20000.00")
    assert authorization.residual_cash == Decimal("943.00")
    assert authorization.operator_override is False
    assert StrategyExecutionAuthorization.from_canonical_dict(
        authorization.to_canonical_dict()
    ) == authorization


def test_operator_override_is_explicit_and_cannot_expand_authority() -> None:
    authorization = _authorization(
        operator_quantity=1500,
        override_reason="operator lowered exposure after liquidity review",
    )

    assert authorization.recommended_quantity == 1900
    assert authorization.intended_quantity == 1500
    assert authorization.operator_override is True
    assert authorization.override_reason == (
        "operator lowered exposure after liquidity review"
    )

    with pytest.raises(ValueError, match="cannot exceed"):
        _authorization(operator_quantity=2000, override_reason="invalid expansion")
    with pytest.raises(ValueError, match="lot"):
        _authorization(operator_quantity=1550, override_reason="invalid odd lot")


def test_buy_quantity_is_capped_by_available_cash_before_lot_rounding() -> None:
    authorization = _authorization(available_cash=Decimal("5010"))

    assert authorization.recommended_quantity == 400
    assert authorization.residual_cash == Decimal("998.00")


def test_t_plus_one_available_quantity_bounds_reduce_and_exit() -> None:
    with pytest.raises(ValueError, match="NOT_EXECUTABLE_QUANTITY"):
        _authorization(
            action="REDUCE",
            accepted_weight=Decimal("-0.05"),
            current_quantity=180,
            available_quantity=80,
        )

    exit_authorization = _authorization(
        action="EXIT",
        accepted_weight=Decimal("-0.20"),
        current_quantity=180,
        available_quantity=80,
    )
    assert exit_authorization.recommended_quantity == 80
    assert exit_authorization.intended_quantity == 80


def test_exit_override_cannot_silently_turn_exit_into_reduce() -> None:
    with pytest.raises(ValueError, match="EXIT quantity"):
        _authorization(
            action="EXIT",
            accepted_weight=Decimal("-0.20"),
            current_quantity=180,
            available_quantity=180,
            operator_quantity=100,
            override_reason="invalid partial exit intent",
        )


def test_strategy_authorization_is_immutable_manual_execution_intent_lineage() -> None:
    authorization = _authorization()
    record = ManualTradeRecord(
        schema_version=STRATEGY_AUTHORIZED_MANUAL_TRADE_SCHEMA,
        manual_trade_id=ManualTradeId("strategy-manual-trade-a"),
        risk_decision_id=None,
        risk_decision_hash=None,
        portfolio_decision_id=None,
        target_position_hash=None,
        account_id=authorization.account_id,
        symbol=authorization.symbol,
        side=TradeSide.BUY,
        intended_quantity=authorization.intended_quantity,
        expected_price_lower=10.0,
        expected_price_upper=10.1,
        state=ManualOrderState.RECORDED,
        filled_quantity=0,
        version=0,
        actor="operator",
        reason="accept canonical Strategy Proposal",
        created_at=NOW,
        updated_at=NOW,
        last_actor="operator",
        last_reason="accept canonical Strategy Proposal",
        authority_route=ManualTradeAuthorityRoute.STRATEGY,
        strategy_execution_authorization=authorization,
    )

    assert ManualTradeRecord.from_canonical_dict(record.to_canonical_dict()) == record

    with pytest.raises(ValueError, match="authorization mismatch"):
        replace(
            record,
            manual_trade_id=ManualTradeId("strategy-manual-trade-wrong"),
            intended_quantity=authorization.intended_quantity + 100,
        )
