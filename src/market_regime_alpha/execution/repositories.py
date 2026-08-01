"""Repository Protocol for manual intent and append-only Fill authority."""

from __future__ import annotations

from typing import Protocol

from market_regime_alpha.core.identity import ManualTradeId
from market_regime_alpha.execution.manual import Fill, ManualTradeRecord
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
