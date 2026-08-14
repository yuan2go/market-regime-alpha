"""Canonical Strategy Proposal to existing Manual Execution/Fill lifecycle."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.strategy_shadow.multi_strategy_lifecycle import (
    FillDerivedStrategyOutcome,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import (
    PostgresStrategyShadowRepository,
)
from market_regime_alpha.application.trading_lifecycle.manual_execution import (
    ManualExecutionApplicationService,
)
from market_regime_alpha.core.identity import ArtifactId, FillId, ManualTradeId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    STRATEGY_AUTHORIZED_MANUAL_TRADE_SCHEMA,
    Fill,
    ManualOrderState,
    ManualTradeAuthorityRoute,
    ManualTradeRecord,
    TradeSide,
)
from market_regime_alpha.execution.postgres_manual_repository import (
    PostgresManualExecutionRepository,
)
from market_regime_alpha.execution.strategy_intent import (
    StrategyExecutionAuthorization,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.strategies.contracts import (
    CanonicalStrategyAction,
    PriceFreshnessStatus,
)
from market_regime_alpha.strategies.postgres_repository import (
    PostgresMultiStrategyRepository,
)
from market_regime_alpha.strategies.sleeves import (
    FillAllocationBatch,
    allocate_observed_fill,
)


_BUY_ACTIONS = frozenset(
    {CanonicalStrategyAction.ENTER, CanonicalStrategyAction.ADD}
)
_SELL_ACTIONS = frozenset(
    {CanonicalStrategyAction.REDUCE, CanonicalStrategyAction.EXIT}
)


class StrategyExecutionApplicationService:
    """One application bridge; existing owners remain the facts of record."""

    def __init__(self, factory: PostgresConnectionFactory, *, account_id: str) -> None:
        if not account_id or account_id != account_id.strip():
            raise ValueError("Strategy execution account must be explicit")
        PostgresMigrator().apply_all(factory)
        self._account_id = account_id
        self._strategy = PostgresMultiStrategyRepository(
            factory, apply_migrations=False
        )
        self._account = PostgresDecisionSystemRepository(factory)
        self._shadow = PostgresStrategyShadowRepository(
            factory, apply_migrations=False
        )
        self._execution_repository = PostgresManualExecutionRepository(factory)
        self._manual = ManualExecutionApplicationService(
            self._execution_repository
        )

    def create_intent(
        self,
        *,
        portfolio_decision_id: ArtifactId,
        proposal_id: ArtifactId,
        trading_calendar_reference: RuntimeArtifactReference,
        lot_size: int,
        actor: str,
        reason: str,
        created_at: datetime,
        idempotency_key: str,
        operator_quantity: int | None = None,
        override_reason: str | None = None,
    ) -> ManualTradeRecord:
        existing = self._execution_repository.get_trade_for_idempotency_key(
            idempotency_key
        )
        if existing is not None:
            authorization = existing.strategy_execution_authorization
            if authorization is None or (
                authorization.account_id != self._account_id
                or existing.account_id != self._account_id
                or authorization.portfolio_decision_reference.artifact_id
                != portfolio_decision_id
                or authorization.proposal_reference.artifact_id != proposal_id
                or authorization.trading_calendar_reference
                != trading_calendar_reference
                or authorization.lot_size != lot_size
                or authorization.intended_quantity
                != (
                    authorization.recommended_quantity
                    if operator_quantity is None
                    else operator_quantity
                )
                or authorization.override_reason != override_reason
                or existing.actor != actor
                or existing.reason != reason
                or authorization.created_at != created_at
            ):
                raise ValueError(
                    "Strategy execution idempotency key was reused with different intent"
                )
            return existing
        portfolio = self._strategy.get_portfolio(portfolio_decision_id)
        proposal = self._strategy.get_proposal(proposal_id)
        line = next(
            (
                item
                for item in portfolio.lines
                if item.proposal_reference.artifact_id == proposal_id
            ),
            None,
        )
        if line is None or line.accepted_weight == 0:
            raise ValueError("Strategy execution requires an accepted Portfolio line")
        if (
            line.proposal_reference.content_hash != proposal.proposal_hash
            or line.strategy_version_reference
            != proposal.strategy_version_reference
            or line.symbol != proposal.symbol
            or line.action is not proposal.action
        ):
            raise ValueError("Portfolio line and Strategy Proposal mismatch")
        if proposal.action not in _BUY_ACTIONS | _SELL_ACTIONS:
            raise ValueError("Strategy Proposal is not executable")
        proposal_decision_time = self._strategy.get_proposal_decision_time(
            proposal_id
        )
        observation, reconciliation = (
            self._account.resolve_strategy_execution_account(
                account_id=self._account_id,
                decision_time=proposal_decision_time,
            )
        )
        decision_price = self._strategy.get_proposal_decision_price(proposal_id)
        reference_price = decision_price.price
        positions = self._shadow.resolve_multi_strategy_positions(
            account_id=observation.account_id,
            decision_time=proposal_decision_time,
            trading_calendar_reference=trading_calendar_reference,
        )
        position = next(
            (
                item
                for item in positions
                if item.strategy_version_id
                == proposal.strategy_version_reference.artifact_id
                and item.symbol == proposal.symbol
            ),
            None,
        )
        if proposal.action is CanonicalStrategyAction.ENTER:
            if (
                position is not None
                and self._execution_repository.proposal_effective_filled_quantity(
                    proposal_id
                )
                == 0
            ):
                raise ValueError("ENTER cannot create a second open Strategy sleeve")
            current_quantity = 0 if position is None else int(position.quantity)
            available_quantity = (
                0
                if position is None or position.available_quantity is None
                else int(position.available_quantity)
            )
        else:
            if position is None:
                raise ValueError("Strategy action requires an owner-resolved sleeve")
            if (
                position.current_price is None
                or position.price_freshness is not PriceFreshnessStatus.FRESH
            ):
                raise ValueError("Strategy execution requires a fresh owner-resolved price")
            if position.available_quantity is None:
                raise ValueError("Strategy available quantity is not owner-resolved")
            current_quantity = int(position.quantity)
            available_quantity = int(position.available_quantity)
        authorization = StrategyExecutionAuthorization.create(
            portfolio_decision_reference=RuntimeArtifactReference(
                "CROSS_STRATEGY_PORTFOLIO",
                portfolio.decision_id,
                portfolio.decision_hash,
            ),
            strategy_version_reference=proposal.strategy_version_reference,
            proposal_reference=RuntimeArtifactReference(
                "STRATEGY_PROPOSAL", proposal.proposal_id, proposal.proposal_hash
            ),
            account_observation_reference=RuntimeArtifactReference(
                "MANUAL_ACCOUNT_OBSERVATION",
                observation.observation_id,
                observation.content_hash,
            ),
            account_reconciliation_reference=RuntimeArtifactReference(
                "ACCOUNT_RECONCILIATION",
                reconciliation.reconciliation_id,
                reconciliation.content_hash,
            ),
            trading_calendar_reference=trading_calendar_reference,
            price_reference=decision_price.price_owner_reference,
            price_source_reference=decision_price.source_dataset_reference,
            price_observed_at=decision_price.observed_at,
            price_available_at=decision_price.available_at,
            account_id=observation.account_id,
            symbol=proposal.symbol,
            action=proposal.action.value,
            accepted_weight=line.accepted_weight,
            account_nav=observation.total_equity,
            available_cash=observation.available_cash,
            reference_price=reference_price,
            current_quantity=current_quantity,
            available_quantity=available_quantity,
            lot_size=lot_size,
            operator_quantity=operator_quantity,
            override_reason=override_reason,
            replacement_authority=(
                self._execution_repository.proposal_has_execution_history(
                    proposal_id
                )
            ),
            decision_time=proposal_decision_time,
            created_at=created_at,
        )
        semantic = {
            "schema_version": STRATEGY_AUTHORIZED_MANUAL_TRADE_SCHEMA,
            "authorization_id": str(authorization.authorization_id),
            "authorization_hash": authorization.authorization_hash,
            "actor": actor,
            "reason": reason,
            "idempotency_key": idempotency_key,
        }
        digest = canonical_hash(semantic)
        record = ManualTradeRecord(
            schema_version=STRATEGY_AUTHORIZED_MANUAL_TRADE_SCHEMA,
            manual_trade_id=ManualTradeId(f"strategy-manual-trade:{digest[7:]}"),
            risk_decision_id=None,
            risk_decision_hash=None,
            portfolio_decision_id=None,
            target_position_hash=None,
            account_id=authorization.account_id,
            symbol=authorization.symbol,
            side=(
                TradeSide.BUY
                if proposal.action in _BUY_ACTIONS
                else TradeSide.SELL
            ),
            intended_quantity=authorization.intended_quantity,
            expected_price_lower=float(reference_price),
            expected_price_upper=float(reference_price),
            state=ManualOrderState.RECORDED,
            filled_quantity=0,
            version=0,
            actor=actor,
            reason=reason,
            created_at=created_at,
            updated_at=created_at,
            last_actor=actor,
            last_reason=reason,
            authority_route=ManualTradeAuthorityRoute.STRATEGY,
            strategy_execution_authorization=authorization,
        )
        return self._execution_repository.create_strategy_trade(
            record,
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
    ) -> tuple[
        ManualTradeRecord,
        Fill,
        tuple[FillAllocationBatch, ...],
        tuple[FillDerivedStrategyOutcome, ...],
    ]:
        current = self._execution_repository.get_trade(trade_id)
        if (
            current.account_id != self._account_id
            or current.strategy_execution_authorization is None
        ):
            raise ValueError("ManualTrade does not match Strategy execution authority")
        trade, fill = self._manual.record_fill(
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
        _, batches, outcomes = self.recover_trade(
            trade_id,
            decision_time=recorded_at,
        )
        return trade, fill, batches, outcomes

    def mark_intent_state(
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
        current = self._execution_repository.get_trade(trade_id)
        if (
            current.account_id != self._account_id
            or current.strategy_execution_authorization is None
        ):
            raise ValueError("ManualTrade does not match Strategy execution authority")
        return self._manual.mark_order_state(
            trade_id,
            expected_version=expected_version,
            state=state,
            actor=actor,
            reason=reason,
            changed_at=changed_at,
            idempotency_key=idempotency_key,
        )

    def recover_trade(
        self,
        trade_id: ManualTradeId,
        *,
        decision_time: datetime,
    ) -> tuple[
        ManualTradeRecord,
        tuple[FillAllocationBatch, ...],
        tuple[FillDerivedStrategyOutcome, ...],
    ]:
        """Resume allocation and outcome settlement from persisted Fill facts."""
        trade = self._execution_repository.get_trade(trade_id)
        if trade.account_id != self._account_id:
            raise ValueError("ManualTrade does not match execution account")
        batches = self.reconcile_fill_allocations(trade_id)
        outcomes = self._shadow.settle_multi_strategy_outcomes(
            account_id=trade.account_id,
            decision_time=decision_time,
        )
        return trade, batches, outcomes

    def reconcile_fill_allocations(
        self, trade_id: ManualTradeId
    ) -> tuple[FillAllocationBatch, ...]:
        trade = self._execution_repository.get_trade(trade_id)
        authorization = trade.strategy_execution_authorization
        if authorization is None:
            raise ValueError("ManualTrade is not Strategy-authorized")
        batches: list[FillAllocationBatch] = []
        for fill in self._execution_repository.fills_for_trade(trade_id):
            batch = allocate_observed_fill(
                fill=fill,
                allocations=(
                    (
                        authorization.strategy_version_reference,
                        authorization.proposal_reference,
                        fill.quantity,
                    ),
                ),
            )
            batches.append(self._strategy.save_fill_allocation(batch))
        return tuple(batches)

    def inspect_proposal_execution(self, proposal_id: ArtifactId) -> dict[str, object]:
        return self._execution_repository.inspect_strategy_execution(
            account_id=self._account_id,
            proposal_id=proposal_id,
        )


__all__ = ["StrategyExecutionApplicationService"]
