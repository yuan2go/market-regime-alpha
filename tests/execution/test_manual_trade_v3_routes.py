from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import (
    ArtifactId,
    ManualTradeId,
    OpportunityId,
    PortfolioDecisionId,
    PositionBookId,
    PositionSnapshotId,
    RiskDecisionId,
    ThesisId,
)
from market_regime_alpha.execution.manual import (
    ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
    ManualOrderState,
    ManualTradeAuthorityRoute,
    ManualTradeRecord,
    TradeSide,
)


NOW = datetime(2026, 8, 4, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _base_trade(**overrides: object) -> ManualTradeRecord:
    values: dict[str, object] = {
        "schema_version": ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
        "manual_trade_id": ManualTradeId("manual-trade-v3"),
        "risk_decision_id": RiskDecisionId("risk-decision"),
        "risk_decision_hash": _sha("a"),
        "portfolio_decision_id": PortfolioDecisionId("portfolio-decision"),
        "target_position_hash": _sha("b"),
        "account_id": "account-a",
        "symbol": "000001.SZ",
        "side": TradeSide.BUY,
        "intended_quantity": 100,
        "expected_price_lower": 9.9,
        "expected_price_upper": 10.1,
        "state": ManualOrderState.RECORDED,
        "filled_quantity": 0,
        "version": 0,
        "actor": "operator-a",
        "reason": "manual confirmation",
        "created_at": NOW,
        "updated_at": NOW,
        "last_actor": "operator-a",
        "last_reason": "manual confirmation",
        "position_book_id": PositionBookId("position-book-a"),
        "thesis_id": ThesisId("thesis-a"),
        "opportunity_id": OpportunityId("opportunity-a"),
        "post_trade_snapshot_id": ArtifactId("post-trade-account-a"),
        "post_trade_snapshot_hash": _sha("c"),
        "authority_route": ManualTradeAuthorityRoute.INCREASING,
    }
    values.update(overrides)
    return ManualTradeRecord(**values)  # type: ignore[arg-type]


def _reducing_trade(**overrides: object) -> ManualTradeRecord:
    values: dict[str, object] = {
        "risk_decision_id": None,
        "risk_decision_hash": None,
        "portfolio_decision_id": None,
        "target_position_hash": None,
        "side": TradeSide.SELL,
        "intended_quantity": 40,
        "post_trade_snapshot_id": None,
        "post_trade_snapshot_hash": None,
        "authority_route": ManualTradeAuthorityRoute.REDUCING,
        "risk_reducing_decision_id": ArtifactId("reducing-decision-a"),
        "risk_reducing_decision_hash": _sha("d"),
        "risk_reduction_confirmation_id": ArtifactId("confirmation-a"),
        "risk_reduction_confirmation_hash": _sha("e"),
        "source_position_snapshot_id": PositionSnapshotId("position-a"),
        "source_position_snapshot_hash": _sha("f"),
        "source_position_snapshot_version": 3,
        "target_quantity": 60,
        "order_quantity": 40,
    }
    values.update(overrides)
    return _base_trade(**values)


def test_manual_trade_v3_increasing_route_round_trips() -> None:
    trade = _base_trade()

    restored = ManualTradeRecord.from_canonical_dict(trade.to_canonical_dict())

    assert restored == trade
    assert restored.authority_route is ManualTradeAuthorityRoute.INCREASING


def test_manual_trade_v3_increasing_route_rejects_sell() -> None:
    with pytest.raises(ValueError, match="INCREASING route requires BUY"):
        _base_trade(side=TradeSide.SELL)


def test_manual_trade_v3_reducing_route_round_trips() -> None:
    trade = _reducing_trade()

    restored = ManualTradeRecord.from_canonical_dict(trade.to_canonical_dict())

    assert restored == trade
    assert restored.authority_route is ManualTradeAuthorityRoute.REDUCING
    assert restored.risk_decision_id is None


@pytest.mark.parametrize(
    ("route", "changes", "message"),
    [
        (
            "increasing",
            {"risk_reducing_decision_id": ArtifactId("reducing-too")},
            "cannot carry reducing authority",
        ),
        (
            "increasing",
            {"risk_decision_id": None},
            "requires complete increasing authority",
        ),
        (
            "reducing",
            {"risk_decision_id": RiskDecisionId("increasing-too")},
            "cannot carry increasing authority",
        ),
        (
            "reducing",
            {"risk_reduction_confirmation_id": None},
            "requires complete reducing authority",
        ),
    ],
)
def test_manual_trade_v3_enforces_route_authority_exclusivity(
    route: str, changes: dict[str, object], message: str
) -> None:
    constructor = _base_trade if route == "increasing" else _reducing_trade

    with pytest.raises(ValueError, match=message):
        constructor(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"side": TradeSide.BUY},
        {"intended_quantity": 39},
        {"order_quantity": 0},
    ],
)
def test_manual_trade_v3_reducing_route_requires_sell_order_semantics(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="reducing ManualTradeRecord"):
        _reducing_trade(**changes)


def test_manual_trade_v3_rejects_canonical_field_tamper() -> None:
    payload = _reducing_trade().to_canonical_dict()
    payload["unexpected"] = "tamper"

    with pytest.raises(ValueError, match="fields mismatch"):
        ManualTradeRecord.from_canonical_dict(payload)


def test_manual_trade_v3_transition_preserves_route_authority() -> None:
    trade = _reducing_trade()

    transitioned = replace(
        trade,
        state=ManualOrderState.PARTIALLY_FILLED,
        filled_quantity=20,
        version=1,
        updated_at=NOW,
    )

    assert transitioned.authority_route is ManualTradeAuthorityRoute.REDUCING
    assert transitioned.risk_reducing_decision_id == ArtifactId(
        "reducing-decision-a"
    )
