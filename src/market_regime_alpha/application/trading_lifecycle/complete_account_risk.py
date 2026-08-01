"""Application orchestration for complete-account Portfolio and Risk."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.decision.thesis import TradingThesis
from market_regime_alpha.decision.opportunity import (
    OpportunityState,
    TradingOpportunity,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.portfolio.account_authority import (
    AuthoritativeAccountPortfolioSnapshot,
    CompleteAccountPortfolioConstructionService,
    CompleteAccountPortfolioDecision,
    CompleteAccountRiskConfiguration,
    CompleteAccountRiskDecision,
    CompleteAccountRiskService,
)
from market_regime_alpha.portfolio.lifecycle import (
    PortfolioOutputMode,
    ThesisAllocationRequest,
)
from market_regime_alpha.portfolio.repositories import (
    CompleteAccountPortfolioRiskRepository,
)


class CompleteAccountPortfolioRiskApplicationService:
    def __init__(self, repository: CompleteAccountPortfolioRiskRepository) -> None:
        self._repository = repository
        self._portfolio = CompleteAccountPortfolioConstructionService()
        self._risk = CompleteAccountRiskService()

    def run(
        self,
        *,
        theses: tuple[TradingThesis, ...],
        allocations: tuple[ThesisAllocationRequest, ...],
        account_snapshot: AuthoritativeAccountPortfolioSnapshot,
        configuration: CompleteAccountRiskConfiguration | None,
        mode: PortfolioOutputMode,
        actor: str,
        reason: str,
        portfolio_created_at: datetime,
        risk_started_at: datetime,
        risk_completed_at: datetime,
        idempotency_key: str,
    ) -> tuple[CompleteAccountPortfolioDecision, CompleteAccountRiskDecision]:
        if configuration is None:
            raise ValueError(
                "versioned complete-account Risk configuration is required; "
                "no default exists"
            )
        portfolio = self._portfolio.construct(
            theses=theses,
            allocations=allocations,
            account_snapshot=account_snapshot,
            configuration=configuration,
            mode=mode,
            actor=actor,
            reason=reason,
            created_at=portfolio_created_at,
        )
        risk = self._risk.assess(
            portfolio,
            actor=actor,
            reason=reason,
            started_at=risk_started_at,
            completed_at=risk_completed_at,
        )
        command = {
            "account_snapshot_id": str(account_snapshot.snapshot_id),
            "account_snapshot_hash": account_snapshot.content_hash,
            "portfolio": portfolio.to_canonical_dict(),
            "risk": risk.to_canonical_dict(),
        }
        return self._repository.save_assessment(
            account_snapshot,
            portfolio,
            risk,
            idempotency_key=idempotency_key,
            command_hash=canonical_hash(command),
        )

    def run_traceable(
        self,
        *,
        opportunities: tuple[TradingOpportunity, ...],
        theses: tuple[TradingThesis, ...],
        allocations: tuple[ThesisAllocationRequest, ...],
        account_snapshot: AuthoritativeAccountPortfolioSnapshot,
        configuration: CompleteAccountRiskConfiguration | None,
        mode: PortfolioOutputMode,
        actor: str,
        reason: str,
        portfolio_created_at: datetime,
        risk_started_at: datetime,
        risk_completed_at: datetime,
        idempotency_key: str,
    ) -> tuple[CompleteAccountPortfolioDecision, CompleteAccountRiskDecision]:
        """H2 entry point requiring the exact non-expired Opportunity chain."""

        opportunity_by_id = {
            item.opportunity_id: item for item in opportunities
        }
        if len(opportunity_by_id) != len(opportunities):
            raise ValueError("traceable Risk requires unique Opportunities")
        if len(opportunities) != len(theses):
            raise ValueError("every traceable Thesis requires one Opportunity")
        for thesis in theses:
            opportunity = opportunity_by_id.get(thesis.opportunity_id)
            if opportunity is None:
                raise ValueError("traceable Risk Thesis omits its Opportunity")
            if (
                opportunity.state is not OpportunityState.CONFIRMED_TO_THESIS
                or opportunity.symbol != thesis.symbol
                or portfolio_created_at > opportunity.valid_until
            ):
                raise ValueError("expired or invalid Opportunity cannot create Risk")
        return self.run(
            theses=theses,
            allocations=allocations,
            account_snapshot=account_snapshot,
            configuration=configuration,
            mode=mode,
            actor=actor,
            reason=reason,
            portfolio_created_at=portfolio_created_at,
            risk_started_at=risk_started_at,
            risk_completed_at=risk_completed_at,
            idempotency_key=idempotency_key,
        )
