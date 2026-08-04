"""Application orchestration for the traceable manual-execution chain."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.application.trading_lifecycle.manual_execution import (
    ManualExecutionApplicationService,
)
from market_regime_alpha.core.identity import FillId, ManualTradeId, PositionBookId
from market_regime_alpha.decision.opportunity import TradingOpportunity
from market_regime_alpha.decision.thesis import TradingThesis
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
    ExecutionDeviation,
    Fill,
    ManualOrderState,
    ManualTradeRecord,
    ManualTradeAuthorityRoute,
    TradeSide,
)
from market_regime_alpha.execution.position_book import PositionBook
from market_regime_alpha.execution.repositories import (
    TraceableManualExecutionRepository,
)
from market_regime_alpha.portfolio.account_authority import (
    CompleteAccountPortfolioDecision,
    CompleteAccountRiskDecision,
    ProposedTradeDelta,
)
from market_regime_alpha.portfolio.lifecycle import RiskDecisionState
from market_regime_alpha.position.authority import (
    T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
    PositionProjector,
    PositionSnapshot,
    PositionState,
    SymbolTradingSessionStatus,
)


class TraceableManualExecutionApplicationService:
    def __init__(self, repository: TraceableManualExecutionRepository) -> None:
        self._repository = repository
        self._manual = ManualExecutionApplicationService(repository)

    def create_trade(
        self,
        *,
        opportunity: TradingOpportunity,
        thesis: TradingThesis,
        portfolio_decision: CompleteAccountPortfolioDecision,
        risk_decision: CompleteAccountRiskDecision,
        trade_delta: ProposedTradeDelta,
        account_id: str,
        expected_price_lower: float,
        expected_price_upper: float,
        actor: str,
        reason: str,
        created_at: datetime,
        idempotency_key: str,
    ) -> tuple[PositionBook, ManualTradeRecord]:
        if risk_decision.state is not RiskDecisionState.APPROVED:
            raise ValueError("traceable manual trade requires approved RiskDecision")
        if trade_delta.trade_quantity <= 0:
            raise ValueError("INCREASING route requires positive OPEN/ADD trade delta")
        book = PositionBook.open(
            account_id=account_id,
            symbol=trade_delta.symbol,
            opportunity_id=opportunity.opportunity_id,
            thesis_id=thesis.thesis_id,
            thesis_version=thesis.version,
            opened_at=created_at,
            actor=actor,
            reason=reason,
        )
        semantic = {
            "opportunity": opportunity.to_canonical_dict(),
            "thesis": thesis.to_canonical_dict(),
            "portfolio_decision": portfolio_decision.to_canonical_dict(),
            "risk_decision": risk_decision.to_canonical_dict(),
            "trade_delta": trade_delta.to_canonical_dict(),
            "position_book_id": str(book.position_book_id),
            "account_id": account_id,
            "expected_price_lower": expected_price_lower,
            "expected_price_upper": expected_price_upper,
            "actor": actor,
            "reason": reason,
            "created_at": created_at.isoformat(),
        }
        digest = canonical_hash(semantic).split(":", 1)[1]
        record = ManualTradeRecord(
            schema_version=ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
            manual_trade_id=ManualTradeId(f"manual-trade-trace-{digest[:24]}"),
            risk_decision_id=risk_decision.risk_decision_id,
            risk_decision_hash=canonical_hash(risk_decision.to_canonical_dict()),
            portfolio_decision_id=portfolio_decision.decision_id,
            target_position_hash=canonical_hash(trade_delta.to_canonical_dict()),
            account_id=account_id,
            symbol=trade_delta.symbol,
            side=(
                TradeSide.BUY
                if trade_delta.trade_quantity > 0
                else TradeSide.SELL
            ),
            intended_quantity=abs(trade_delta.trade_quantity),
            expected_price_lower=expected_price_lower,
            expected_price_upper=expected_price_upper,
            state=ManualOrderState.RECORDED,
            filled_quantity=0,
            version=0,
            actor=actor,
            reason=reason,
            created_at=created_at,
            updated_at=created_at,
            last_actor=actor,
            last_reason=reason,
            position_book_id=book.position_book_id,
            thesis_id=thesis.thesis_id,
            opportunity_id=opportunity.opportunity_id,
            post_trade_snapshot_id=portfolio_decision.post_trade.snapshot_id,
            post_trade_snapshot_hash=portfolio_decision.post_trade.content_hash,
            authority_route=ManualTradeAuthorityRoute.INCREASING,
        )
        return self._repository.create_traceable_trade(
            record,
            book=book,
            opportunity=opportunity,
            thesis=thesis,
            risk_decision=risk_decision,
            portfolio_decision=portfolio_decision,
            trade_delta=trade_delta,
            idempotency_key=idempotency_key,
            command_hash=canonical_hash(semantic),
        )

    def record_fill(
        self,
        trade_id: ManualTradeId,
        *,
        external_fill_id: str,
        quantity: int,
        price: float,
        fees: float,
        occurred_at: datetime,
        recorded_at: datetime,
        actor: str,
        reason: str,
        idempotency_key: str,
        correction_of_fill_id: FillId | None = None,
    ) -> tuple[ManualTradeRecord, Fill]:
        return self._manual.record_fill(
            trade_id,
            external_fill_id=external_fill_id,
            quantity=quantity,
            price=price,
            fees=fees,
            occurred_at=occurred_at,
            recorded_at=recorded_at,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            correction_of_fill_id=correction_of_fill_id,
        )

    def rebuild_position(
        self, book_id: PositionBookId, *, as_of: datetime
    ) -> PositionSnapshot:
        book = self._repository.get_position_book(book_id)
        trades = self._repository.trades_for_book(book_id)
        fills = self._repository.fills_for_book(book_id)
        return PositionProjector().project_book(
            book=book,
            trades=trades,
            fills=fills,
            as_of=as_of,
        )

    def rebuild_a_share_position(
        self,
        book_id: PositionBookId,
        *,
        calendar: TradingCalendarArtifact,
        symbol_session_statuses: tuple[SymbolTradingSessionStatus, ...],
        as_of: datetime,
    ) -> PositionSnapshot:
        book = self._repository.get_position_book(book_id)
        return PositionProjector().project_book_t_plus_one(
            book=book,
            trades=self._repository.trades_for_book(book_id),
            fills=self._repository.fills_for_book(book_id),
            calendar=calendar,
            symbol_session_statuses=symbol_session_statuses,
            as_of=as_of,
        )

    def close_position_book(
        self,
        book_id: PositionBookId,
        *,
        expected_version: int,
        final_position: PositionSnapshot,
        trading_calendar: TradingCalendarArtifact | None = None,
        symbol_trading_statuses: tuple[SymbolTradingSessionStatus, ...] = (),
        actor: str,
        reason: str,
        closed_at: datetime,
        idempotency_key: str,
    ) -> PositionBook:
        book = self._repository.get_position_book(book_id)
        if final_position.state is not PositionState.CLOSED:
            raise ValueError("PositionBook closes only with a CLOSED Position authority")
        if (
            final_position.position_book_id != book_id
            or final_position.thesis_id != book.thesis_id
            or final_position.opportunity_id != book.opportunity_id
        ):
            raise ValueError("final Position does not belong to PositionBook")
        if final_position.schema_version == T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA:
            if trading_calendar is None or not symbol_trading_statuses:
                raise ValueError(
                    "T+1 final Position requires TradingCalendar and symbol session evidence"
                )
            replay = self.rebuild_a_share_position(
                book_id,
                calendar=trading_calendar,
                symbol_session_statuses=symbol_trading_statuses,
                as_of=final_position.as_of,
            )
        else:
            replay = self.rebuild_position(book_id, as_of=final_position.as_of)
        if replay != final_position:
            raise ValueError("final Position differs from Fill-derived replay")
        closed = book.close(closed_at=closed_at, actor=actor, reason=reason)
        return self._repository.close_position_book(
            closed,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )

    def execution_deviation(self, trade_id: ManualTradeId) -> ExecutionDeviation:
        return self._manual.execution_deviation(trade_id)
