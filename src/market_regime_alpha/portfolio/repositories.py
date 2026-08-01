"""Repository Protocol for immutable versioned Portfolio and Risk decisions."""

from __future__ import annotations

from typing import Protocol

from market_regime_alpha.core.identity import PortfolioDecisionId, RiskDecisionId
from market_regime_alpha.portfolio.account_authority import (
    AuthoritativeAccountPortfolioSnapshot,
    CompleteAccountPortfolioDecision,
    CompleteAccountRiskDecision,
)
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


class CompleteAccountPortfolioRiskRepository(Protocol):
    """Storage-neutral atomic authority for one full-account assessment."""

    def save_assessment(
        self,
        account_snapshot: AuthoritativeAccountPortfolioSnapshot,
        portfolio: CompleteAccountPortfolioDecision,
        risk: CompleteAccountRiskDecision,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> tuple[CompleteAccountPortfolioDecision, CompleteAccountRiskDecision]: ...

    def get_account_snapshot(
        self, snapshot_id: str
    ) -> AuthoritativeAccountPortfolioSnapshot: ...

    def get_complete_account_portfolio(
        self, decision_id: PortfolioDecisionId
    ) -> CompleteAccountPortfolioDecision: ...

    def get_complete_account_risk(
        self, risk_decision_id: RiskDecisionId
    ) -> CompleteAccountRiskDecision: ...
