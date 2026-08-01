"""Complete-account Risk orchestration sourced from Fill-derived Position books."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from market_regime_alpha.application.trading_lifecycle.complete_account_risk import (
    CompleteAccountPortfolioRiskApplicationService,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.decision.opportunity import TradingOpportunity
from market_regime_alpha.decision.thesis import TradingThesis
from market_regime_alpha.execution.repositories import (
    TraceableManualExecutionRepository,
)
from market_regime_alpha.portfolio.account_authority import (
    AccountReconciliationState,
    AuthoritativeAccountPortfolioSnapshot,
    CompleteAccountPortfolioDecision,
    CompleteAccountRiskConfiguration,
    CompleteAccountRiskDecision,
)
from market_regime_alpha.portfolio.lifecycle import (
    PortfolioOutputMode,
    ThesisAllocationRequest,
)
from market_regime_alpha.portfolio.position_authority import (
    PositionAuthorityAccountSnapshotBuilder,
    PositionRiskValuationInput,
)
from market_regime_alpha.portfolio.repositories import (
    CompleteAccountPortfolioRiskRepository,
)
from market_regime_alpha.position.authority import (
    PositionProjector,
    PositionSnapshot,
    SymbolTradingSessionStatus,
)


class PositionAuthoritativePortfolioRiskApplicationService:
    """Prevent caller-authored available quantity in the hardened Risk path."""

    def __init__(
        self,
        *,
        execution_repository: TraceableManualExecutionRepository,
        risk_repository: CompleteAccountPortfolioRiskRepository,
    ) -> None:
        self._execution = execution_repository
        self._risk = CompleteAccountPortfolioRiskApplicationService(risk_repository)

    def run(
        self,
        *,
        opportunities: tuple[TradingOpportunity, ...],
        theses: tuple[TradingThesis, ...],
        allocations: tuple[ThesisAllocationRequest, ...],
        account_id: str,
        account_as_of: datetime,
        account_source_reference: str,
        net_asset_value: float,
        available_cash: float,
        reconciliation_state: AccountReconciliationState,
        account_version: int,
        valuations: tuple[PositionRiskValuationInput, ...],
        calendar: TradingCalendarArtifact,
        symbol_session_statuses: Mapping[
            str, tuple[SymbolTradingSessionStatus, ...]
        ],
        configuration: CompleteAccountRiskConfiguration | None,
        mode: PortfolioOutputMode,
        actor: str,
        reason: str,
        portfolio_created_at: datetime,
        risk_started_at: datetime,
        risk_completed_at: datetime,
        idempotency_key: str,
    ) -> tuple[
        AuthoritativeAccountPortfolioSnapshot,
        tuple[PositionSnapshot, ...],
        CompleteAccountPortfolioDecision,
        CompleteAccountRiskDecision,
    ]:
        books = self._execution.open_position_books(account_id)
        positions = tuple(
            PositionProjector().project_book_t_plus_one(
                book=book,
                trades=self._execution.trades_for_book(book.position_book_id),
                fills=self._execution.fills_for_book(book.position_book_id),
                calendar=calendar,
                symbol_session_statuses=symbol_session_statuses.get(book.symbol, ()),
                as_of=account_as_of,
            )
            for book in books
        )
        account = PositionAuthorityAccountSnapshotBuilder().build(
            account_id=account_id,
            as_of=account_as_of,
            source_reference=account_source_reference,
            net_asset_value=net_asset_value,
            available_cash=available_cash,
            open_books=books,
            position_snapshots=positions,
            valuations=valuations,
            reconciliation_state=reconciliation_state,
            version=account_version,
        )
        portfolio, risk = self._risk.run_traceable(
            opportunities=opportunities,
            theses=theses,
            allocations=allocations,
            account_snapshot=account,
            configuration=configuration,
            mode=mode,
            actor=actor,
            reason=reason,
            portfolio_created_at=portfolio_created_at,
            risk_started_at=risk_started_at,
            risk_completed_at=risk_completed_at,
            idempotency_key=idempotency_key,
        )
        return account, positions, portfolio, risk
