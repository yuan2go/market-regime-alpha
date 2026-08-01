#!/usr/bin/env python3
"""CLI for explicit-config Portfolio proposal and independent Risk assessment."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.application.trading_lifecycle import (
    PortfolioRiskApplicationService,
)
from market_regime_alpha.core.identity import RiskDecisionId, ThesisId
from market_regime_alpha.decision import TradingThesis
from market_regime_alpha.portfolio import (
    CurrentPositionInput,
    PortfolioAccountSnapshot,
    PortfolioOutputMode,
    RiskBudget,
    SQLitePortfolioDecisionRepository,
    ThesisAllocationRequest,
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _object(value)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("portfolio request value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("portfolio request value must be an array")
    return value


def _run(database: Path, payload: dict[str, Any]):
    account = _object(payload["account_snapshot"])
    service = PortfolioRiskApplicationService(
        SQLitePortfolioDecisionRepository(database)
    )
    return service.run(
        theses=tuple(
            TradingThesis.from_canonical_dict(_object(item))
            for item in _array(payload["theses"])
        ),
        allocations=tuple(
            _allocation(_object(item)) for item in _array(payload["allocations"])
        ),
        current_positions=tuple(
            _position(_object(item))
            for item in _array(payload["current_positions"])
        ),
        account_snapshot=PortfolioAccountSnapshot(
            net_asset_value=float(account["net_asset_value"]),
            available_cash=float(account["available_cash"]),
            observed_at=datetime.fromisoformat(str(account["observed_at"])),
            source_reference=str(account["source_reference"]),
        ),
        risk_budget=RiskBudget.from_canonical_dict(
            _object(payload["risk_budget"])
        ),
        mode=PortfolioOutputMode(str(payload["mode"])),
        actor=str(payload["actor"]),
        reason=str(payload["reason"]),
        portfolio_created_at=datetime.fromisoformat(
            str(payload["portfolio_created_at"])
        ),
        risk_started_at=datetime.fromisoformat(str(payload["risk_started_at"])),
        risk_completed_at=datetime.fromisoformat(
            str(payload["risk_completed_at"])
        ),
        idempotency_key=str(payload["idempotency_key"]),
    )


def _allocation(payload: dict[str, Any]) -> ThesisAllocationRequest:
    return ThesisAllocationRequest(
        thesis_id=ThesisId(str(payload["thesis_id"])),
        symbol=str(payload["symbol"]),
        theme_id=str(payload["theme_id"]),
        target_quantity=int(payload["target_quantity"]),
        reference_price=float(payload["reference_price"]),
        average_daily_trade_value=float(payload["average_daily_trade_value"]),
        loss_per_share=float(payload["loss_per_share"]),
    )


def _position(payload: dict[str, Any]) -> CurrentPositionInput:
    return CurrentPositionInput(
        symbol=str(payload["symbol"]),
        total_quantity=int(payload["total_quantity"]),
        available_quantity=int(payload["available_quantity"]),
        market_price=float(payload["market_price"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Portfolio and independent Risk CLI")
    parser.add_argument("--database", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--request", type=Path, required=True)
    show = subparsers.add_parser("show-risk")
    show.add_argument("--risk-decision-id", required=True)
    args = parser.parse_args()
    if args.command == "run":
        portfolio, risk = _run(args.database, _read(args.request))
        result = {
            "portfolio": portfolio.to_canonical_dict(),
            "risk": risk.to_canonical_dict(),
        }
    else:
        result = SQLitePortfolioDecisionRepository(args.database).get_risk(
            RiskDecisionId(args.risk_decision_id)
        ).to_canonical_dict()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
