"""Repository Protocol for manual intent and append-only Fill authority."""

from __future__ import annotations

from typing import Protocol

from market_regime_alpha.core.identity import ManualTradeId, PositionBookId
from market_regime_alpha.decision.opportunity import TradingOpportunity
from market_regime_alpha.decision.thesis import TradingThesis
from market_regime_alpha.execution.manual import Fill, ManualTradeRecord
from market_regime_alpha.execution.position_book import PositionBook
from market_regime_alpha.portfolio.account_authority import (
    CompleteAccountPortfolioDecision,
    CompleteAccountRiskDecision,
    ProposedTradeDelta,
)
from market_regime_alpha.portfolio.lifecycle import (
    PortfolioDecision,
    RiskDecision,
    TargetPosition,
)


class ManualExecutionRepository(Protocol):
    def create_trade(
        self,
        record: ManualTradeRecord,
        *,
        risk_decision: RiskDecision,
        portfolio_decision: PortfolioDecision,
        target_position: TargetPosition,
        idempotency_key: str,
        command_hash: str,
    ) -> ManualTradeRecord: ...

    def append_fill(
        self,
        fill: Fill,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> tuple[ManualTradeRecord, Fill]: ...

    def transition_trade(
        self,
        record: ManualTradeRecord,
        *,
        expected_version: int,
        idempotency_key: str,
        command_hash: str,
    ) -> ManualTradeRecord: ...

    def get_trade(self, trade_id: ManualTradeId) -> ManualTradeRecord: ...

    def fills_for_trade(self, trade_id: ManualTradeId) -> tuple[Fill, ...]: ...

    def all_fills(self, account_id: str, symbol: str) -> tuple[Fill, ...]: ...


class TraceableManualExecutionRepository(ManualExecutionRepository, Protocol):
    def create_traceable_trade(
        self,
        record: ManualTradeRecord,
        *,
        book: PositionBook,
        opportunity: TradingOpportunity,
        thesis: TradingThesis,
        risk_decision: CompleteAccountRiskDecision,
        portfolio_decision: CompleteAccountPortfolioDecision,
        trade_delta: ProposedTradeDelta,
        idempotency_key: str,
        command_hash: str,
    ) -> tuple[PositionBook, ManualTradeRecord]: ...

    def get_position_book(self, book_id: PositionBookId) -> PositionBook: ...

    def trades_for_book(
        self, book_id: PositionBookId
    ) -> tuple[ManualTradeRecord, ...]: ...

    def fills_for_book(self, book_id: PositionBookId) -> tuple[Fill, ...]: ...

    def open_position_books(self, account_id: str) -> tuple[PositionBook, ...]: ...

    def close_position_book(
        self,
        book: PositionBook,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> PositionBook: ...
