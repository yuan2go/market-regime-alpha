"""Strict canonical restoration for durable Portfolio and Risk decisions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from market_regime_alpha.core.identity import (
    ArtifactId,
    PortfolioDecisionId,
    RiskDecisionId,
    ThesisId,
)
from market_regime_alpha.portfolio.lifecycle import (
    CurrentPositionInput,
    PortfolioAccountSnapshot,
    PortfolioConstraint,
    PortfolioConstraintType,
    PortfolioDecision,
    PortfolioDecisionState,
    PortfolioOutputMode,
    RiskBudget,
    RiskDecision,
    RiskDecisionState,
    TargetPosition,
)


def portfolio_decision_from_dict(payload: dict[str, Any]) -> PortfolioDecision:
    expected = {
        "schema_version",
        "decision_id",
        "mode",
        "state",
        "risk_budget_id",
        "risk_budget_hash",
        "risk_budget",
        "account_snapshot",
        "target_positions",
        "thesis_ids",
        "version",
        "actor",
        "reason",
        "created_at",
        "reason_codes",
    }
    targets = _array(payload.get("target_positions"))
    theses = _array(payload.get("thesis_ids"))
    reasons = _array(payload.get("reason_codes"))
    if set(payload) != expected:
        raise ValueError("PortfolioDecision fields mismatch")
    account = _object(payload["account_snapshot"])
    return PortfolioDecision(
        schema_version=str(payload["schema_version"]),
        decision_id=PortfolioDecisionId(str(payload["decision_id"])),
        mode=PortfolioOutputMode(str(payload["mode"])),
        state=PortfolioDecisionState(str(payload["state"])),
        risk_budget_id=ArtifactId(str(payload["risk_budget_id"])),
        risk_budget_hash=str(payload["risk_budget_hash"]),
        risk_budget=RiskBudget.from_canonical_dict(_object(payload["risk_budget"])),
        account_snapshot=PortfolioAccountSnapshot(
            net_asset_value=float(account["net_asset_value"]),
            available_cash=float(account["available_cash"]),
            observed_at=datetime.fromisoformat(str(account["observed_at"])),
            source_reference=str(account["source_reference"]),
        ),
        target_positions=tuple(_target(_object(item)) for item in targets),
        thesis_ids=tuple(ThesisId(str(item)) for item in theses),
        version=int(payload["version"]),
        actor=str(payload["actor"]),
        reason=str(payload["reason"]),
        created_at=datetime.fromisoformat(str(payload["created_at"])),
        reason_codes=tuple(str(item) for item in reasons),
    )


def risk_decision_from_dict(payload: dict[str, Any]) -> RiskDecision:
    expected = {
        "schema_version",
        "risk_decision_id",
        "portfolio_decision_id",
        "portfolio_decision_version",
        "risk_budget_id",
        "risk_budget_hash",
        "risk_budget",
        "mode",
        "state",
        "constraints",
        "version",
        "actor",
        "reason",
        "started_at",
        "completed_at",
        "reason_codes",
    }
    constraints = _array(payload.get("constraints"))
    reasons = _array(payload.get("reason_codes"))
    if set(payload) != expected:
        raise ValueError("RiskDecision fields mismatch")
    return RiskDecision(
        schema_version=str(payload["schema_version"]),
        risk_decision_id=RiskDecisionId(str(payload["risk_decision_id"])),
        portfolio_decision_id=PortfolioDecisionId(
            str(payload["portfolio_decision_id"])
        ),
        portfolio_decision_version=int(payload["portfolio_decision_version"]),
        risk_budget_id=ArtifactId(str(payload["risk_budget_id"])),
        risk_budget_hash=str(payload["risk_budget_hash"]),
        risk_budget=RiskBudget.from_canonical_dict(_object(payload["risk_budget"])),
        mode=PortfolioOutputMode(str(payload["mode"])),
        state=RiskDecisionState(str(payload["state"])),
        constraints=tuple(_constraint(_object(item)) for item in constraints),
        version=int(payload["version"]),
        actor=str(payload["actor"]),
        reason=str(payload["reason"]),
        started_at=datetime.fromisoformat(str(payload["started_at"])),
        completed_at=datetime.fromisoformat(str(payload["completed_at"])),
        reason_codes=tuple(str(item) for item in reasons),
    )


def _target(payload: dict[str, Any]) -> TargetPosition:
    expected = {
        "thesis_id",
        "symbol",
        "theme_id",
        "current_quantity",
        "available_quantity",
        "target_quantity",
        "trade_quantity",
        "reference_price",
        "average_daily_trade_value",
        "loss_per_share",
    }
    if set(payload) != expected:
        raise ValueError("TargetPosition fields mismatch")
    return TargetPosition(
        thesis_id=ThesisId(str(payload["thesis_id"])),
        symbol=str(payload["symbol"]),
        theme_id=str(payload["theme_id"]),
        current_quantity=int(payload["current_quantity"]),
        available_quantity=int(payload["available_quantity"]),
        target_quantity=int(payload["target_quantity"]),
        trade_quantity=int(payload["trade_quantity"]),
        reference_price=float(payload["reference_price"]),
        average_daily_trade_value=float(payload["average_daily_trade_value"]),
        loss_per_share=float(payload["loss_per_share"]),
    )


def _constraint(payload: dict[str, Any]) -> PortfolioConstraint:
    expected = {
        "constraint_type",
        "passed",
        "observed_value",
        "limit_value",
        "reason_code",
        "symbols",
    }
    symbols = _array(payload.get("symbols"))
    if set(payload) != expected or not isinstance(payload["passed"], bool):
        raise ValueError("PortfolioConstraint fields mismatch")
    return PortfolioConstraint(
        constraint_type=PortfolioConstraintType(str(payload["constraint_type"])),
        passed=payload["passed"],
        observed_value=float(payload["observed_value"]),
        limit_value=float(payload["limit_value"]),
        reason_code=str(payload["reason_code"]),
        symbols=tuple(str(item) for item in symbols),
    )


def current_position_from_dict(payload: dict[str, Any]) -> CurrentPositionInput:
    return CurrentPositionInput(
        symbol=str(payload["symbol"]),
        total_quantity=int(payload["total_quantity"]),
        available_quantity=int(payload["available_quantity"]),
        market_price=float(payload["market_price"]),
    )


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("portfolio value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("portfolio value must be an array")
    return value
