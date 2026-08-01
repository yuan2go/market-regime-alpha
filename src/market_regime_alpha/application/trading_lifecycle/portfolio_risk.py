"""Application orchestration that persists proposal before independent risk."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.decision.thesis import TradingThesis
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.portfolio.lifecycle import (
    CurrentPositionInput,
    PortfolioAccountSnapshot,
    PortfolioDecision,
    PortfolioOutputMode,
    RiskBudget,
    RiskDecision,
    ThesisAllocationRequest,
)
from market_regime_alpha.portfolio.repositories import PortfolioDecisionRepository
from market_regime_alpha.portfolio.services import (
    IndependentRiskService,
    PortfolioConstructionService,
)


class PortfolioRiskApplicationService:
    def __init__(self, repository: PortfolioDecisionRepository) -> None:
        self._repository = repository
        self._portfolio = PortfolioConstructionService()
        self._risk = IndependentRiskService()

    def run(
        self,
        *,
        theses: tuple[TradingThesis, ...],
        allocations: tuple[ThesisAllocationRequest, ...],
        current_positions: tuple[CurrentPositionInput, ...],
        account_snapshot: PortfolioAccountSnapshot,
        risk_budget: RiskBudget | None,
        mode: PortfolioOutputMode,
        actor: str,
        reason: str,
        portfolio_created_at: datetime,
        risk_started_at: datetime,
        risk_completed_at: datetime,
        idempotency_key: str,
    ) -> tuple[PortfolioDecision, RiskDecision]:
        if risk_budget is None:
            raise ValueError("versioned RiskBudget is required; no default exists")
        portfolio = self._portfolio.construct(
            theses=theses,
            allocations=allocations,
            current_positions=current_positions,
            account_snapshot=account_snapshot,
            risk_budget=risk_budget,
            mode=mode,
            actor=actor,
            reason=reason,
            created_at=portfolio_created_at,
        )
        portfolio_hash = canonical_hash(portfolio.to_canonical_dict())
        stored_portfolio = self._repository.save_portfolio(
            portfolio,
            idempotency_key=f"{idempotency_key}:portfolio",
            command_hash=portfolio_hash,
        )
        risk = self._risk.assess(
            stored_portfolio,
            actor=actor,
            reason=reason,
            started_at=risk_started_at,
            completed_at=risk_completed_at,
        )
        stored_risk = self._repository.save_risk(
            risk,
            idempotency_key=f"{idempotency_key}:risk",
            command_hash=canonical_hash(risk.to_canonical_dict()),
        )
        return stored_portfolio, stored_risk
