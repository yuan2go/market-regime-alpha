"""Repository Protocol for immutable versioned Portfolio and Risk decisions."""

from __future__ import annotations

from typing import Protocol

from market_regime_alpha.core.identity import PortfolioDecisionId, RiskDecisionId
from market_regime_alpha.portfolio.lifecycle import PortfolioDecision, RiskDecision


class PortfolioDecisionRepository(Protocol):
    def save_portfolio(
        self,
        decision: PortfolioDecision,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> PortfolioDecision: ...

    def save_risk(
        self,
        decision: RiskDecision,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> RiskDecision: ...

    def get_portfolio(self, decision_id: PortfolioDecisionId) -> PortfolioDecision: ...

    def get_risk(self, risk_decision_id: RiskDecisionId) -> RiskDecision: ...
