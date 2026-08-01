"""Application service for human intent, Fill recording and Position rebuild."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.core.identity import FillId, ManualTradeId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    FILL_SCHEMA,
    MANUAL_TRADE_SCHEMA,
    ExecutionDeviation,
    Fill,
    FillKind,
    ManualOrderState,
    ManualTradeRecord,
    TradeSide,
    transition_manual_trade,
)
from market_regime_alpha.execution.repositories import ManualExecutionRepository
from market_regime_alpha.portfolio.lifecycle import (
    PortfolioDecision,
    RiskDecision,
    RiskDecisionState,
    TargetPosition,
)
from market_regime_alpha.position.authority import PositionProjector, PositionSnapshot


class ManualExecutionApplicationService:
    def __init__(self, repository: ManualExecutionRepository) -> None:
        self._repository = repository

    def create_trade(
        self,
        *,
        risk_decision: RiskDecision,
        portfolio_decision: PortfolioDecision,
        target_position: TargetPosition,
        account_id: str,
        expected_price_lower: float,
        expected_price_upper: float,
        actor: str,
        reason: str,
        created_at: datetime,
        idempotency_key: str,
    ) -> ManualTradeRecord:
        if risk_decision.state is not RiskDecisionState.APPROVED:
            raise ValueError("Manual trade requires approved RiskDecision")
        trade_quantity = target_position.trade_quantity
        if trade_quantity == 0:
            raise ValueError("zero TargetPosition delta creates no manual trade")
        semantic = {
            "risk_decision_id": str(risk_decision.risk_decision_id),
            "portfolio_decision_id": str(portfolio_decision.decision_id),
            "target_position": target_position.to_canonical_dict(),
            "account_id": account_id,
            "expected_price_lower": expected_price_lower,
            "expected_price_upper": expected_price_upper,
            "actor": actor,
            "reason": reason,
            "created_at": created_at.isoformat(),
        }
        digest = canonical_hash(semantic).split(":", 1)[1]
        record = ManualTradeRecord(
            schema_version=MANUAL_TRADE_SCHEMA,
            manual_trade_id=ManualTradeId(f"manual-trade-{digest[:24]}"),
            risk_decision_id=risk_decision.risk_decision_id,
            risk_decision_hash=canonical_hash(risk_decision.to_canonical_dict()),
            portfolio_decision_id=portfolio_decision.decision_id,
            target_position_hash=canonical_hash(target_position.to_canonical_dict()),
            account_id=account_id,
            symbol=target_position.symbol,
            side=TradeSide.BUY if trade_quantity > 0 else TradeSide.SELL,
            intended_quantity=abs(trade_quantity),
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
        )
        return self._repository.create_trade(
            record,
            risk_decision=risk_decision,
            portfolio_decision=portfolio_decision,
            target_position=target_position,
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
        trade = self._repository.get_trade(trade_id)
        semantic = {
            "manual_trade_id": str(trade_id),
            "external_fill_id": external_fill_id,
            "quantity": quantity,
            "price": price,
            "fees": fees,
            "occurred_at": occurred_at.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "actor": actor,
            "reason": reason,
            "correction_of_fill_id": (
                str(correction_of_fill_id)
                if correction_of_fill_id is not None
                else None
            ),
        }
        digest = canonical_hash(semantic).split(":", 1)[1]
        fill = Fill(
            schema_version=FILL_SCHEMA,
            fill_id=FillId(f"fill-{digest[:24]}"),
            manual_trade_id=trade_id,
            account_id=trade.account_id,
            symbol=trade.symbol,
            side=trade.side,
            quantity=quantity,
            price=price,
            fees=fees,
            occurred_at=occurred_at,
            recorded_at=recorded_at,
            actor=actor,
            reason=reason,
            external_fill_id=external_fill_id,
            fill_kind=(
                FillKind.CORRECTION
                if correction_of_fill_id is not None
                else FillKind.EXECUTION
            ),
            correction_of_fill_id=correction_of_fill_id,
        )
        return self._repository.append_fill(
            fill,
            idempotency_key=idempotency_key,
            command_hash=canonical_hash(semantic),
        )

    def mark_order_state(
        self,
        trade_id: ManualTradeId,
        *,
        expected_version: int,
        state: ManualOrderState,
        actor: str,
        reason: str,
        changed_at: datetime,
        idempotency_key: str,
    ) -> ManualTradeRecord:
        if state not in {
            ManualOrderState.CANCELLED,
            ManualOrderState.REJECTED,
            ManualOrderState.UNKNOWN,
        }:
            raise ValueError("manual status command is invalid")
        current = self._repository.get_trade(trade_id)
        if current.version != expected_version:
            raise ValueError("stale ManualTradeRecord version")
        if current.state not in {
            ManualOrderState.RECORDED,
            ManualOrderState.PARTIALLY_FILLED,
            ManualOrderState.UNKNOWN,
        }:
            raise ValueError("manual status command cannot replace fill-derived terminal state")
        updated = transition_manual_trade(
            current,
            state=state,
            filled_quantity=current.filled_quantity,
            actor=actor,
            reason=reason,
            changed_at=changed_at,
        )
        command = {
            "trade_id": str(trade_id),
            "expected_version": expected_version,
            "state": state.value,
            "actor": actor,
            "reason": reason,
            "changed_at": changed_at.isoformat(),
        }
        return self._repository.transition_trade(
            updated,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            command_hash=canonical_hash(command),
        )

    def rebuild_position(
        self, *, account_id: str, symbol: str, as_of: datetime
    ) -> PositionSnapshot:
        fills = self._repository.all_fills(account_id, symbol)
        return PositionProjector().project(
            account_id=account_id,
            symbol=symbol,
            fills=fills,
            as_of=as_of,
        )

    def execution_deviation(self, trade_id: ManualTradeId) -> ExecutionDeviation:
        trade = self._repository.get_trade(trade_id)
        fills = self._repository.fills_for_trade(trade_id)
        executions = {item.fill_id: item for item in fills if item.fill_kind is FillKind.EXECUTION}
        corrections = {
            item.correction_of_fill_id: item
            for item in fills
            if item.fill_kind is FillKind.CORRECTION
        }
        effective = tuple(
            corrections.get(fill_id, fill) for fill_id, fill in executions.items()
        )
        quantity = sum(item.quantity for item in effective)
        vwap = (
            sum(item.quantity * item.price for item in effective) / quantity
            if quantity
            else None
        )
        expected_mid = (trade.expected_price_lower + trade.expected_price_upper) / 2
        return ExecutionDeviation(
            manual_trade_id=trade_id,
            intended_quantity=trade.intended_quantity,
            effective_filled_quantity=quantity,
            quantity_deviation=quantity - trade.intended_quantity,
            volume_weighted_price=vwap,
            expected_mid_price=expected_mid,
            price_deviation=(vwap - expected_mid) if vwap is not None else None,
        )
