"""PostgreSQL-native manual execution ledger with append-only Fill enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from typing import Any, Callable
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId, FillId, ManualTradeId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    Fill,
    FillKind,
    ManualOrderState,
    ManualTradeAuthorityRoute,
    ManualTradeRecord,
    STRATEGY_AUTHORIZED_MANUAL_TRADE_SCHEMA,
    TradeSide,
    validate_manual_trade_transition,
)
from market_regime_alpha.execution.strategy_intent import (
    StrategyExecutionAuthorization,
)
from market_regime_alpha.portfolio.lifecycle import (
    PortfolioDecision,
    RiskDecision,
    RiskDecisionState,
    TargetPosition,
)
from market_regime_alpha.portfolio.services import IndependentRiskService
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.native_repository import (
    NativePostgresRepository,
    PostgresConnection,
    acquire_scope_lock,
)
from market_regime_alpha.strategies.contracts import StrategyDecisionPrice
from market_regime_alpha.strategies.sleeves import (
    FillAllocationBatch,
    effective_fill_allocation_batches,
    project_strategy_sleeves,
)


class ExecutionVersionConflictError(RuntimeError):
    pass


class PostgresManualExecutionRepository(NativePostgresRepository):
    """Native PostgreSQL append-only manual Fill ledger."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        super().__init__(factory)

    def create_trade(
        self,
        record: ManualTradeRecord,
        *,
        risk_decision: RiskDecision,
        portfolio_decision: PortfolioDecision,
        target_position: TargetPosition,
        idempotency_key: str,
        command_hash: str,
    ) -> ManualTradeRecord:
        _validate_authority(record, risk_decision, portfolio_decision, target_position)
        return self._create_record(
            record,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )

    def create_strategy_trade(
        self,
        record: ManualTradeRecord,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> ManualTradeRecord:
        if (
            record.schema_version != STRATEGY_AUTHORIZED_MANUAL_TRADE_SCHEMA
            or record.authority_route is not ManualTradeAuthorityRoute.STRATEGY
        ):
            raise ValueError("Strategy trade requires V4 STRATEGY authority")
        return self._create_record(
            record,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
            authority_validator=lambda connection: _validate_strategy_authority(connection, record),
        )

    def _create_record(
        self,
        record: ManualTradeRecord,
        *,
        idempotency_key: str,
        command_hash: str,
        authority_validator: Callable[[PostgresConnection], None] | None = None,
    ) -> ManualTradeRecord:
        if record.state is not ManualOrderState.RECORDED or record.version != 0:
            raise ValueError("new ManualTradeRecord must be RECORDED version 0")
        with self._connect() as connection:
            _acquire_strategy_scopes(connection, record)
            acquire_scope_lock(
                connection,
                namespace="manual-trade",
                identity=record.manual_trade_id,
            )
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash, record.manual_trade_id)
                    result = _load_trade(
                        connection,
                        record.manual_trade_id,
                        int(command["result_version"]),
                    )
                    connection.commit()
                    return result
                if authority_validator is not None:
                    authority_validator(connection)
                existing = connection.execute(
                    "SELECT aggregate_json FROM manual_trade_records WHERE manual_trade_id = %s",
                    (str(record.manual_trade_id),),
                ).fetchone()
                if existing is not None:
                    current = ManualTradeRecord.from_canonical_dict(_object_json(str(existing["aggregate_json"])))
                    if current != record:
                        raise ValueError("ManualTradeRecord identity conflict")
                else:
                    connection.execute(
                        """
                        INSERT INTO manual_trade_records(
                            manual_trade_id, risk_decision_id, account_id, symbol,
                            side, state, filled_quantity, aggregate_json, version,
                            authority_route, strategy_authorization_id,
                            strategy_authorization_hash,
                            strategy_portfolio_decision_id,
                            strategy_portfolio_decision_hash,
                            strategy_proposal_id, strategy_proposal_hash,
                            strategy_version_id, strategy_version_hash,
                            strategy_account_observation_id,
                            strategy_account_observation_hash,
                            strategy_calendar_id, strategy_calendar_hash,
                            strategy_execution_authority_version,
                            strategy_reconciliation_id,
                            strategy_reconciliation_hash,
                            strategy_price_owner_id,
                            strategy_price_owner_hash,
                            strategy_price_source_id,
                            strategy_price_source_hash,
                            strategy_price_observed_at,
                            strategy_price_available_at,
                            strategy_authorized_quantity
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, 0, %s, 0,
                            %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        """,
                        _trade_projection_values(record),
                    )
                    _insert_trade_event(connection, record, idempotency_key)
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    record=record,
                    fill=None,
                )
                connection.commit()
                return record
            except Exception:
                connection.rollback()
                raise

    def append_fill(
        self,
        fill: Fill,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> tuple[ManualTradeRecord, Fill]:
        with self._connect() as connection:
            _acquire_trade_scopes(connection, fill.manual_trade_id)
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash, fill.manual_trade_id)
                    stored_fill = _load_fill(connection, FillId(str(command["fill_id"])))
                    record = _load_trade(
                        connection,
                        fill.manual_trade_id,
                        int(command["result_version"]),
                    )
                    connection.commit()
                    return record, stored_fill
                current = _load_trade(connection, fill.manual_trade_id)
                self._validate_loaded_trade(connection, current)
                if fill.account_id != current.account_id or fill.symbol != current.symbol:
                    raise ValueError("Fill scope does not match ManualTradeRecord")
                if fill.side is not current.side:
                    raise ValueError("Fill side does not match ManualTradeRecord")
                if (
                    current.state is ManualOrderState.REJECTED
                    and fill.fill_kind is FillKind.EXECUTION
                ):
                    raise ValueError("rejected trade cannot accept execution Fill")
                if current.state is ManualOrderState.FILLED and fill.fill_kind is FillKind.EXECUTION:
                    raise ValueError("filled trade accepts correction records only")
                existing_fill = connection.execute(
                    "SELECT fill_json FROM manual_fills WHERE fill_id = %s OR external_fill_id = %s",
                    (str(fill.fill_id), fill.external_fill_id),
                ).fetchone()
                if existing_fill is not None:
                    stored = Fill.from_canonical_dict(_object_json(str(existing_fill["fill_json"])))
                    if stored != fill:
                        raise ValueError("duplicate Fill identity has conflicting semantics")
                    raise ValueError("Fill already exists under a different idempotency key")
                existing_fills = _fills_for_trade(connection, fill.manual_trade_id)
                if fill.fill_kind is FillKind.CORRECTION:
                    assert fill.correction_of_fill_id is not None
                    originals = {item.fill_id: item for item in existing_fills}
                    original = originals.get(fill.correction_of_fill_id)
                    if original is None or original.fill_kind is not FillKind.EXECUTION:
                        raise ValueError("correction target must be an execution Fill")
                    if any(item.correction_of_fill_id == fill.correction_of_fill_id for item in existing_fills):
                        raise ValueError("execution Fill already has a correction")
                connection.execute(
                    """
                    INSERT INTO manual_fills(
                        fill_id, external_fill_id, manual_trade_id, account_id,
                        symbol, fill_kind, correction_of_fill_id, fill_json,
                        recorded_at, idempotency_key
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(fill.fill_id),
                        fill.external_fill_id,
                        str(fill.manual_trade_id),
                        fill.account_id,
                        fill.symbol,
                        fill.fill_kind.value,
                        (str(fill.correction_of_fill_id) if fill.correction_of_fill_id is not None else None),
                        _json(fill.to_canonical_dict()),
                        fill.recorded_at.isoformat(),
                        idempotency_key,
                    ),
                )
                all_fills = (*existing_fills, fill)
                effective_quantity = _effective_quantity(all_fills)
                state: ManualOrderState
                if current.state in {
                    ManualOrderState.CANCELLED,
                    ManualOrderState.REJECTED,
                }:
                    state = current.state
                elif effective_quantity < current.intended_quantity:
                    state = ManualOrderState.PARTIALLY_FILLED
                elif effective_quantity == current.intended_quantity:
                    state = ManualOrderState.FILLED
                else:
                    state = ManualOrderState.RECONCILIATION_REQUIRED
                updated = ManualTradeRecord.from_canonical_dict(
                    {
                        **current.to_canonical_dict(),
                        "state": state.value,
                        "filled_quantity": effective_quantity,
                        "version": current.version + 1,
                        "updated_at": fill.recorded_at.isoformat(),
                        "last_actor": fill.actor,
                        "last_reason": fill.reason,
                    }
                )
                validate_manual_trade_transition(
                    current,
                    updated,
                    allow_terminal_fill_update=(
                        current.state is ManualOrderState.CANCELLED
                        or fill.fill_kind is FillKind.CORRECTION
                    ),
                )
                _update_trade(connection, updated, current.version)
                _insert_trade_event(connection, updated, f"{idempotency_key}:trade")
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    record=updated,
                    fill=fill,
                )
                connection.commit()
                return updated, fill
            except Exception:
                connection.rollback()
                raise

    def transition_trade(
        self,
        record: ManualTradeRecord,
        *,
        expected_version: int,
        idempotency_key: str,
        command_hash: str,
    ) -> ManualTradeRecord:
        with self._connect() as connection:
            _acquire_trade_scopes(connection, record.manual_trade_id)
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(command, command_hash, record.manual_trade_id)
                    result = _load_trade(
                        connection,
                        record.manual_trade_id,
                        int(command["result_version"]),
                    )
                    connection.commit()
                    return result
                current = _load_trade(connection, record.manual_trade_id)
                self._validate_loaded_trade(connection, current)
                if current.version != expected_version:
                    raise ExecutionVersionConflictError("manual trade CAS conflict")
                validate_manual_trade_transition(current, record)
                _update_trade(connection, record, expected_version)
                _insert_trade_event(connection, record, idempotency_key)
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    record=record,
                    fill=None,
                )
                connection.commit()
                return record
            except Exception:
                connection.rollback()
                raise

    def get_trade(self, trade_id: ManualTradeId) -> ManualTradeRecord:
        with self._connect() as connection:
            return _load_trade(connection, trade_id)

    def get_trade_for_idempotency_key(self, idempotency_key: str) -> ManualTradeRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT manual_trade_id FROM execution_commands
                WHERE idempotency_key = %s AND fill_id IS NULL
                """,
                (idempotency_key,),
            ).fetchone()
            if row is None:
                return None
            return _load_trade(connection, ManualTradeId(str(row["manual_trade_id"])))

    def fills_for_trade(self, trade_id: ManualTradeId) -> tuple[Fill, ...]:
        with self._connect() as connection:
            return _fills_for_trade(connection, trade_id)

    def proposal_effective_filled_quantity(self, proposal_id: ArtifactId) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(filled_quantity), 0) AS quantity
                FROM manual_trade_records
                WHERE authority_route = 'STRATEGY'
                  AND strategy_proposal_id = %s
                """,
                (str(proposal_id),),
            ).fetchone()
            return 0 if row is None else int(row["quantity"])

    def proposal_has_execution_history(self, proposal_id: ArtifactId) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM manual_trade_records
                    WHERE authority_route = 'STRATEGY'
                      AND strategy_proposal_id = %s
                ) AS present
                """,
                (str(proposal_id),),
            ).fetchone()
            return row is not None and bool(row["present"])

    def inspect_strategy_execution(
        self,
        *,
        account_id: str,
        proposal_id: ArtifactId,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            proposal_rows = connection.execute(
                """
                SELECT aggregate_json
                FROM manual_trade_records
                WHERE authority_route = 'STRATEGY'
                  AND account_id = %s
                  AND strategy_proposal_id = %s
                ORDER BY manual_trade_id
                """,
                (account_id, str(proposal_id)),
            ).fetchall()
            trades = tuple(ManualTradeRecord.from_canonical_dict(_object_payload(row["aggregate_json"])) for row in proposal_rows)
            if not trades:
                raise KeyError(f"{account_id}:{proposal_id}")
            authorization = trades[0].strategy_execution_authorization
            assert authorization is not None
            authorized = authorization.recommended_quantity
            filled = sum(item.filled_quantity for item in trades)
            reserved = sum(
                max(0, item.intended_quantity - item.filled_quantity) for item in trades if item.state in _ACTIVE_RESERVATION_STATES
            )
            released = sum(
                max(0, item.intended_quantity - item.filled_quantity)
                for item in trades
                if item.state in {ManualOrderState.CANCELLED, ManualOrderState.REJECTED}
            )
            account_rows = connection.execute(
                """
                SELECT aggregate_json
                FROM manual_trade_records
                WHERE authority_route = 'STRATEGY' AND account_id = %s
                ORDER BY manual_trade_id
                """,
                (account_id,),
            ).fetchall()
            account_trades = tuple(ManualTradeRecord.from_canonical_dict(_object_payload(row["aggregate_json"])) for row in account_rows)
            account_reserved_cash = sum(
                Decimal(max(0, item.intended_quantity - item.filled_quantity)) * item.strategy_execution_authorization.reference_price
                for item in account_trades
                if item.side is TradeSide.BUY
                and item.state in _ACTIVE_RESERVATION_STATES
                and item.strategy_execution_authorization is not None
            )
            observation_row = connection.execute(
                """
                SELECT as_of_time
                FROM manual_account_observation
                WHERE observation_id = %s
                """,
                (str(authorization.account_observation_reference.artifact_id),),
            ).fetchone()
            if observation_row is None:
                raise ValueError("Strategy Account Observation projection is missing")
            position_rows = connection.execute(
                """
                SELECT symbol, total_quantity, observed_market_value
                FROM manual_position_observation
                WHERE observation_id = %s
                """,
                (str(authorization.account_observation_reference.artifact_id),),
            ).fetchall()
            physical_by_symbol = {
                str(item["symbol"]): Decimal(str(item["observed_market_value"]))
                for item in position_rows
            }
            observation_marks = {
                str(item["symbol"]): (
                    Decimal("0")
                    if int(item["total_quantity"]) == 0
                    else Decimal(str(item["observed_market_value"]))
                    / Decimal(int(item["total_quantity"]))
                )
                for item in position_rows
            }
            reserved_by_symbol: dict[str, Decimal] = {}
            for item in account_trades:
                item_authorization = item.strategy_execution_authorization
                if item.side is not TradeSide.BUY or item.state not in _ACTIVE_RESERVATION_STATES or item_authorization is None:
                    continue
                reserved_by_symbol[item.symbol] = reserved_by_symbol.get(item.symbol, Decimal("0")) + (
                    Decimal(max(0, item.intended_quantity - item.filled_quantity)) * item_authorization.reference_price
                )
            latest_account_marks = {
                item.symbol: item.strategy_execution_authorization.reference_price
                for item in account_trades
                if item.strategy_execution_authorization is not None
            }
            unobserved_by_symbol = _marked_unobserved_fill_notional_by_symbol(
                connection,
                account_id,
                observation_as_of=observation_row["as_of_time"],
                mark_prices={
                    **latest_account_marks,
                    **observation_marks,
                    authorization.symbol: authorization.reference_price,
                },
            )
            projected_gross_notional = (
                sum(physical_by_symbol.values(), Decimal("0"))
                + sum(reserved_by_symbol.values(), Decimal("0"))
                + sum(unobserved_by_symbol.values(), Decimal("0"))
            )
            projected_symbol_notional = (
                physical_by_symbol.get(authorization.symbol, Decimal("0"))
                + reserved_by_symbol.get(authorization.symbol, Decimal("0"))
                + unobserved_by_symbol.get(authorization.symbol, Decimal("0"))
            )
            unobserved_fill_cash = _unobserved_buy_fill_cash(
                connection,
                account_id,
                observation_as_of=observation_row["as_of_time"],
            )
            strategy_trades = tuple(
                item
                for item in account_trades
                if item.strategy_execution_authorization is not None
                and item.strategy_execution_authorization.strategy_version_reference == authorization.strategy_version_reference
            )
            latest_strategy_marks = {
                item.symbol: item.strategy_execution_authorization.reference_price
                for item in strategy_trades
                if item.strategy_execution_authorization is not None
            }
            sleeve_quantities = _strategy_sleeve_quantities(
                connection,
                account_id=account_id,
            )
            strategy_filled_notional = _marked_strategy_sleeve_notional(
                sleeve_quantities=sleeve_quantities,
                strategy_version_id=str(
                    authorization.strategy_version_reference.artifact_id
                ),
                target_symbol=authorization.symbol,
                target_price=authorization.reference_price,
                observation_marks=observation_marks,
                latest_strategy_marks=latest_strategy_marks,
            )
            strategy_reserved_notional = sum(
                (
                    Decimal(max(0, item.intended_quantity - item.filled_quantity)) * item.strategy_execution_authorization.reference_price
                    for item in strategy_trades
                    if item.side is TradeSide.BUY
                    and item.state in _ACTIVE_RESERVATION_STATES
                    and item.strategy_execution_authorization is not None
                ),
                Decimal("0"),
            )
            return {
                "account_id": account_id,
                "proposal_id": str(proposal_id),
                "authorized_quantity": authorized,
                "reserved_quantity": reserved,
                "effective_filled_quantity": filled,
                "released_quantity": released,
                "remaining_quantity": max(0, authorized - filled - reserved),
                "active_intents": [
                    {
                        "manual_trade_id": str(item.manual_trade_id),
                        "state": item.state.value,
                        "intended_quantity": item.intended_quantity,
                        "filled_quantity": item.filled_quantity,
                    }
                    for item in trades
                    if item.state in _ACTIVE_RESERVATION_STATES
                ],
                "account_reserved_cash": str(account_reserved_cash),
                "account_available_cash": str(authorization.available_cash),
                "account_unobserved_fill_cash": str(unobserved_fill_cash),
                "account_remaining_cash": str(authorization.available_cash - account_reserved_cash - unobserved_fill_cash),
                "projected_post_trade_exposure": {
                    "gross_weight": str(projected_gross_notional / authorization.account_nav),
                    "symbol_weight": str(projected_symbol_notional / authorization.account_nav),
                    "strategy_weight": str(
                        (strategy_filled_notional + strategy_reserved_notional)
                        / authorization.account_nav
                    ),
                },
                "portfolio_reference": authorization.portfolio_decision_reference.to_canonical_dict(),
                "account_observation_reference": authorization.account_observation_reference.to_canonical_dict(),
                "account_reconciliation_reference": (
                    None
                    if authorization.account_reconciliation_reference is None
                    else authorization.account_reconciliation_reference.to_canonical_dict()
                ),
                "price_owner_reference": authorization.price_reference.to_canonical_dict(),
                "price_source_reference": (
                    None if authorization.price_source_reference is None else authorization.price_source_reference.to_canonical_dict()
                ),
                "price": str(authorization.reference_price),
                "price_observed_at": (None if authorization.price_observed_at is None else authorization.price_observed_at.isoformat()),
                "price_available_at": (None if authorization.price_available_at is None else authorization.price_available_at.isoformat()),
                "decision_time": authorization.decision_time.isoformat(),
                "trading_calendar_reference": authorization.trading_calendar_reference.to_canonical_dict(),
            }

    def all_fills(self, account_id: str, symbol: str) -> tuple[Fill, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT fill_json FROM manual_fills
                WHERE account_id = %s AND symbol = %s ORDER BY recorded_at, fill_id
                """,
                (account_id, symbol),
            ).fetchall()
            return tuple(Fill.from_canonical_dict(_object_json(str(item["fill_json"]))) for item in rows)

    def _validate_loaded_trade(self, connection: PostgresConnection, record: ManualTradeRecord) -> None:
        """Subclass hook for route-specific immutable binding validation."""


_ACTIVE_RESERVATION_STATES = frozenset(
    {
        ManualOrderState.RECORDED,
        ManualOrderState.PARTIALLY_FILLED,
        ManualOrderState.UNKNOWN,
        ManualOrderState.RECONCILIATION_REQUIRED,
    }
)


def _acquire_strategy_scopes(
    connection: PostgresConnection,
    record: ManualTradeRecord,
) -> None:
    """Serialize Strategy execution in the global account -> proposal order."""

    authorization = record.strategy_execution_authorization
    if authorization is None:
        return
    acquire_scope_lock(
        connection,
        namespace="strategy-execution-account",
        identity=authorization.account_id,
    )
    acquire_scope_lock(
        connection,
        namespace="strategy-execution-proposal",
        identity=authorization.proposal_reference.artifact_id,
    )


def _acquire_trade_scopes(
    connection: PostgresConnection,
    trade_id: ManualTradeId,
) -> None:
    """Lock immutable Strategy scopes before the mutable trade aggregate."""

    row = connection.execute(
        """
        SELECT authority_route, account_id, strategy_proposal_id
        FROM manual_trade_records
        WHERE manual_trade_id = %s
        """,
        (str(trade_id),),
    ).fetchone()
    if row is not None and str(row["authority_route"]) == "STRATEGY":
        acquire_scope_lock(
            connection,
            namespace="strategy-execution-account",
            identity=str(row["account_id"]),
        )
        acquire_scope_lock(
            connection,
            namespace="strategy-execution-proposal",
            identity=str(row["strategy_proposal_id"]),
        )
    acquire_scope_lock(
        connection,
        namespace="manual-trade",
        identity=trade_id,
    )


def _validate_authority(
    record: ManualTradeRecord,
    risk: RiskDecision,
    portfolio: PortfolioDecision,
    target: TargetPosition,
) -> None:
    if risk.state is not RiskDecisionState.APPROVED:
        raise ValueError("ManualTradeRecord requires approved RiskDecision")
    if risk.portfolio_decision_id != portfolio.decision_id:
        raise ValueError("RiskDecision and PortfolioDecision mismatch")
    expected_risk = IndependentRiskService().assess(
        portfolio,
        actor=risk.actor,
        reason=risk.reason,
        started_at=risk.started_at,
        completed_at=risk.completed_at,
    )
    if expected_risk != risk:
        raise ValueError("ManualTradeRecord requires independently valid RiskDecision")
    if target not in portfolio.target_positions:
        raise ValueError("ManualTradeRecord TargetPosition is not in PortfolioDecision")
    expected_side = TradeSide.BUY if target.trade_quantity > 0 else TradeSide.SELL
    if target.trade_quantity == 0:
        raise ValueError("zero TargetPosition delta cannot create ManualTradeRecord")
    if (
        record.risk_decision_id != risk.risk_decision_id
        or record.risk_decision_hash != canonical_hash(risk.to_canonical_dict())
        or record.portfolio_decision_id != portfolio.decision_id
        or record.target_position_hash != canonical_hash(target.to_canonical_dict())
        or record.symbol != target.symbol
        or record.side is not expected_side
        or record.intended_quantity != abs(target.trade_quantity)
    ):
        raise ValueError("ManualTradeRecord authority binding mismatch")


def _validate_strategy_authority(
    connection: PostgresConnection,
    record: ManualTradeRecord,
) -> None:
    authorization = record.strategy_execution_authorization
    if authorization is None:
        raise ValueError("Strategy ManualTradeRecord authorization is missing")
    expected_kinds = (
        ("portfolio", authorization.portfolio_decision_reference, "CROSS_STRATEGY_PORTFOLIO"),
        ("version", authorization.strategy_version_reference, "STRATEGY_VERSION"),
        ("proposal", authorization.proposal_reference, "STRATEGY_PROPOSAL"),
        ("account", authorization.account_observation_reference, "MANUAL_ACCOUNT_OBSERVATION"),
        (
            "reconciliation",
            authorization.account_reconciliation_reference,
            "ACCOUNT_RECONCILIATION",
        ),
        ("calendar", authorization.trading_calendar_reference, "TRADING_CALENDAR"),
        ("price", authorization.price_reference, "CANONICAL_MARKET_BAR"),
    )
    for label, reference, expected_kind in expected_kinds:
        if reference is None:
            raise ValueError(f"Strategy {label} authority is missing")
        if reference.reference_kind != expected_kind:
            raise ValueError(f"Strategy {label} authority kind mismatch")
    row = connection.execute(
        """
        SELECT d.decision_hash, l.accepted_weight,
               p.proposal_hash, p.strategy_version_id,
               p.strategy_version_hash, p.symbol, p.action,
               v.version_hash, c.decision_time, c.payload_json
        FROM cross_strategy_portfolio_decision AS d
        JOIN cross_strategy_portfolio_line AS l
          ON l.decision_id = d.decision_id
        JOIN strategy_proposal AS p
          ON p.proposal_id = l.proposal_id
         AND p.proposal_hash = l.proposal_hash
        JOIN strategy_version AS v
          ON v.version_id = p.strategy_version_id
         AND v.version_hash = p.strategy_version_hash
        JOIN strategy_run AS r ON r.run_id = p.run_id
        JOIN multi_strategy_cycle AS c ON c.cycle_id = r.cycle_id
        WHERE d.decision_id = %s AND l.proposal_id = %s
        FOR SHARE OF d, l, p, v
        """,
        (
            str(authorization.portfolio_decision_reference.artifact_id),
            str(authorization.proposal_reference.artifact_id),
        ),
    ).fetchone()
    if row is None:
        raise ValueError("Strategy execution requires an accepted Portfolio line")
    if (
        str(row["decision_hash"]) != authorization.portfolio_decision_reference.content_hash
        or Decimal(str(row["accepted_weight"])) == 0
        or Decimal(str(row["accepted_weight"])) != authorization.accepted_weight
        or str(row["proposal_hash"]) != authorization.proposal_reference.content_hash
        or str(row["strategy_version_id"]) != str(authorization.strategy_version_reference.artifact_id)
        or str(row["strategy_version_hash"]) != authorization.strategy_version_reference.content_hash
        or str(row["version_hash"]) != authorization.strategy_version_reference.content_hash
        or str(row["symbol"]) != authorization.symbol
        or str(row["action"]) != authorization.action
        or row["decision_time"] != authorization.decision_time
    ):
        raise ValueError("Strategy Portfolio/Proposal authorization mismatch")
    observation = connection.execute(
        """
        SELECT content_hash, account_id, as_of_time, total_equity, available_cash
        FROM manual_account_observation
        WHERE observation_id = %s
        FOR SHARE
        """,
        (str(authorization.account_observation_reference.artifact_id),),
    ).fetchone()
    if observation is None or (
        str(observation["content_hash"]) != authorization.account_observation_reference.content_hash
        or str(observation["account_id"]) != authorization.account_id
        or observation["as_of_time"] != authorization.decision_time
        or Decimal(str(observation["total_equity"])) != authorization.account_nav
        or Decimal(str(observation["available_cash"])) != authorization.available_cash
    ):
        raise ValueError("Strategy Account Observation authorization mismatch")
    latest_observation = connection.execute(
        """
        SELECT observation_id
        FROM manual_account_observation
        WHERE account_id = %s AND as_of_time <= %s
        ORDER BY as_of_time DESC, revision DESC
        LIMIT 1
        FOR SHARE
        """,
        (authorization.account_id, authorization.decision_time),
    ).fetchone()
    if latest_observation is None or str(latest_observation["observation_id"]) != str(
        authorization.account_observation_reference.artifact_id
    ):
        raise ValueError("DATA_INSUFFICIENT: Account Observation is not latest eligible")
    reconciliation_reference = authorization.account_reconciliation_reference
    assert reconciliation_reference is not None
    reconciliation = connection.execute(
        """
        SELECT content_hash, account_id, as_of_time, manual_observation_id,
               fill_ledger_complete, status, trading_date, revision
        FROM account_reconciliation
        WHERE reconciliation_id = %s
        FOR SHARE
        """,
        (str(reconciliation_reference.artifact_id),),
    ).fetchone()
    if reconciliation is None or (
        str(reconciliation["content_hash"]) != reconciliation_reference.content_hash
        or str(reconciliation["account_id"]) != authorization.account_id
        or reconciliation["as_of_time"] != authorization.decision_time
        or str(reconciliation["manual_observation_id"]) != str(authorization.account_observation_reference.artifact_id)
        or not bool(reconciliation["fill_ledger_complete"])
        or str(reconciliation["status"]) != "RECONCILED"
    ):
        raise ValueError("RECONCILIATION_REQUIRED: Account state is incomplete")
    latest_reconciliation = connection.execute(
        """
        SELECT reconciliation_id
        FROM account_reconciliation
        WHERE account_id = %s AND trading_date = %s AND as_of_time <= %s
        ORDER BY as_of_time DESC, revision DESC
        LIMIT 1
        FOR SHARE
        """,
        (
            authorization.account_id,
            reconciliation["trading_date"],
            authorization.decision_time,
        ),
    ).fetchone()
    if latest_reconciliation is None or str(latest_reconciliation["reconciliation_id"]) != str(reconciliation_reference.artifact_id):
        raise ValueError("RECONCILIATION_REQUIRED: reconciliation is not latest eligible")
    _validate_strategy_price_owner(row["payload_json"], authorization)
    position = connection.execute(
        """
        SELECT total_quantity, available_quantity
        FROM manual_position_observation
        WHERE observation_id = %s AND symbol = %s
        FOR SHARE
        """,
        (
            str(authorization.account_observation_reference.artifact_id),
            authorization.symbol,
        ),
    ).fetchone()
    physical_quantity = 0 if position is None else int(position["total_quantity"])
    physical_available = 0 if position is None else int(position["available_quantity"])
    if authorization.current_quantity > physical_quantity or authorization.available_quantity > physical_available:
        raise ValueError("Strategy quantity exceeds Physical Position authority")
    _validate_strategy_aggregate_authority(
        connection,
        record,
        observation_as_of=observation["as_of_time"],
    )
    calendar_row = connection.execute(
        """
        SELECT calendar_hash, payload_json
        FROM pit_trading_calendar_canonical_snapshot
        WHERE calendar_id = %s
        FOR SHARE
        """,
        (str(authorization.trading_calendar_reference.artifact_id),),
    ).fetchone()
    if calendar_row is None or str(calendar_row["calendar_hash"]) != (authorization.trading_calendar_reference.content_hash):
        raise ValueError("Strategy Trading Calendar authorization mismatch")
    calendar_payload = calendar_row["payload_json"]
    if not isinstance(calendar_payload, dict):
        raise ValueError("Strategy Trading Calendar payload is invalid")
    calendar = TradingCalendarArtifact.from_canonical_dict(calendar_payload)
    decision_date = authorization.decision_time.astimezone(ZoneInfo(calendar.timezone_name)).date()
    if not calendar.contains(decision_date):
        raise ValueError("Strategy decision is outside the authorized Trading Calendar")
    if not (Decimal(str(record.expected_price_lower)) <= authorization.reference_price <= Decimal(str(record.expected_price_upper))):
        raise ValueError("Strategy reference price is outside the Manual Intent range")


def _validate_strategy_aggregate_authority(
    connection: PostgresConnection,
    record: ManualTradeRecord,
    *,
    observation_as_of: datetime,
) -> None:
    """Rebuild Proposal and account reservations under their transaction locks."""

    authorization = record.strategy_execution_authorization
    if authorization is None:
        raise ValueError("Strategy execution authorization is missing")
    rows = connection.execute(
        """
        SELECT aggregate_json
        FROM manual_trade_records
        WHERE authority_route = 'STRATEGY' AND account_id = %s
        ORDER BY manual_trade_id
        """,
        (authorization.account_id,),
    ).fetchall()
    trades = tuple(ManualTradeRecord.from_canonical_dict(_object_payload(row["aggregate_json"])) for row in rows)
    proposal_rows = connection.execute(
        """
        SELECT aggregate_json
        FROM manual_trade_records
        WHERE authority_route = 'STRATEGY'
          AND strategy_proposal_id = %s
        ORDER BY manual_trade_id
        """,
        (str(authorization.proposal_reference.artifact_id),),
    ).fetchall()
    proposal_trades = tuple(
        ManualTradeRecord.from_canonical_dict(
            _object_payload(row["aggregate_json"])
        )
        for row in proposal_rows
    )
    if proposal_trades:
        proposal_authorized = proposal_trades[0].strategy_execution_authorization
        assert proposal_authorized is not None
        if any(
            item.strategy_execution_authorization is None
            or item.account_id != authorization.account_id
            or item.strategy_execution_authorization.recommended_quantity != proposal_authorized.recommended_quantity
            or item.strategy_execution_authorization.reference_price != proposal_authorized.reference_price
            or item.strategy_execution_authorization.account_observation_reference != proposal_authorized.account_observation_reference
            for item in proposal_trades
        ):
            raise ValueError("Proposal execution authority is not reconstructible")
        if (
            authorization.recommended_quantity != proposal_authorized.recommended_quantity
            or authorization.reference_price != proposal_authorized.reference_price
            or authorization.account_observation_reference != proposal_authorized.account_observation_reference
        ):
            raise ValueError("Proposal execution authority cannot be re-sized")
        authorized_quantity = proposal_authorized.recommended_quantity
    else:
        if authorization.replacement_authority:
            raise ValueError(
                "Proposal replacement authority requires prior execution history"
            )
        authorized_quantity = authorization.recommended_quantity
    filled_quantity = sum(item.filled_quantity for item in proposal_trades)
    reserved_quantity = sum(
        max(0, item.intended_quantity - item.filled_quantity) for item in proposal_trades if item.state in _ACTIVE_RESERVATION_STATES
    )
    remaining_quantity = max(
        0,
        authorized_quantity - filled_quantity - reserved_quantity,
    )
    if record.intended_quantity > remaining_quantity:
        raise ValueError(
            "Proposal remaining authority is insufficient: "
            f"authorized={authorized_quantity}, filled={filled_quantity}, "
            f"reserved={reserved_quantity}, remaining={remaining_quantity}"
        )

    if record.side is TradeSide.BUY:
        active_reserved_cash = sum(
            Decimal(max(0, item.intended_quantity - item.filled_quantity)) * item.strategy_execution_authorization.reference_price
            for item in trades
            if item.side is TradeSide.BUY and item.state in _ACTIVE_RESERVATION_STATES and item.strategy_execution_authorization is not None
        )
        unobserved_fill_cash = _unobserved_buy_fill_cash(
            connection,
            authorization.account_id,
            observation_as_of=observation_as_of,
        )
        requested_cash = Decimal(record.intended_quantity) * authorization.reference_price
        remaining_cash = authorization.available_cash - active_reserved_cash - unobserved_fill_cash
        if requested_cash > remaining_cash:
            raise ValueError(
                "Account available cash authority is insufficient: "
                f"available={authorization.available_cash}, "
                f"reserved={active_reserved_cash}, "
                f"unobserved_fills={unobserved_fill_cash}, "
                f"remaining={remaining_cash}"
            )
        _validate_projected_post_trade_exposure(
            connection,
            record,
            trades=trades,
            observation_as_of=observation_as_of,
        )
    else:
        physical = connection.execute(
            """
            SELECT available_quantity
            FROM manual_position_observation
            WHERE observation_id = %s AND symbol = %s
            """,
            (
                str(authorization.account_observation_reference.artifact_id),
                authorization.symbol,
            ),
        ).fetchone()
        available_sell_quantity = 0 if physical is None else int(physical["available_quantity"])
        active_sell_reservation = sum(
            max(0, item.intended_quantity - item.filled_quantity)
            for item in trades
            if item.side is TradeSide.SELL and item.symbol == authorization.symbol and item.state in _ACTIVE_RESERVATION_STATES
        )
        unobserved_sell_fills = _unobserved_effective_fill_quantity(
            connection,
            account_id=authorization.account_id,
            symbol=authorization.symbol,
            side=TradeSide.SELL,
            observation_as_of=observation_as_of,
        )
        remaining_sell_quantity = available_sell_quantity - active_sell_reservation - unobserved_sell_fills
        if record.intended_quantity > remaining_sell_quantity:
            raise ValueError(
                "Account available sell quantity authority is insufficient: "
                f"available={available_sell_quantity}, "
                f"reserved={active_sell_reservation}, "
                f"unobserved_fills={unobserved_sell_fills}, "
                f"remaining={remaining_sell_quantity}"
            )


def _validate_strategy_price_owner(
    cycle_payload_value: object,
    authorization: StrategyExecutionAuthorization,
) -> None:
    cycle_payload = _object_payload(cycle_payload_value)
    runtime_input = cycle_payload.get("runtime_input")
    if not isinstance(runtime_input, dict):
        raise ValueError("Strategy cycle Runtime input is invalid")
    prices = runtime_input.get("decision_prices")
    if not isinstance(prices, list):
        raise ValueError("DATA_INSUFFICIENT: Strategy cycle has no Price owner")
    matching = tuple(item for item in prices if isinstance(item, dict) and item.get("symbol") == authorization.symbol)
    if len(matching) != 1:
        raise ValueError("Strategy Price owner symbol mismatch")
    price = StrategyDecisionPrice.from_canonical_dict(matching[0])
    source_reference = authorization.price_source_reference
    if source_reference is None:
        raise ValueError("Strategy Price Dataset lineage is missing")
    if (
        price.price_owner_reference != authorization.price_reference
        or price.source_dataset_reference != source_reference
        or price.symbol != authorization.symbol
        or price.price != authorization.reference_price
        or price.observed_at != authorization.price_observed_at
        or price.available_at != authorization.price_available_at
    ):
        raise ValueError("Strategy Price owner binding mismatch")
    if price.observed_at > authorization.decision_time:
        raise ValueError("Strategy Price owner is from the future")
    if price.available_at > authorization.decision_time:
        raise ValueError("Strategy Price owner was unavailable at decision time")
    if price.freshness_expires_at < authorization.decision_time:
        raise ValueError("Strategy Price owner is stale")


def _unobserved_buy_fill_cash(
    connection: PostgresConnection,
    account_id: str,
    *,
    observation_as_of: datetime,
) -> Decimal:
    revisions = _effective_fill_revisions(
        connection,
        account_id=account_id,
        side=TradeSide.BUY,
        observation_as_of=observation_as_of,
    )
    return sum(
        (
            _fill_cash(current) - _fill_cash(at_observation)
            for current, at_observation in revisions
        ),
        Decimal("0"),
    )


def _unobserved_effective_fill_quantity(
    connection: PostgresConnection,
    *,
    account_id: str,
    symbol: str,
    side: TradeSide,
    observation_as_of: datetime,
) -> int:
    revisions = _effective_fill_revisions(
        connection,
        account_id=account_id,
        side=side,
        observation_as_of=observation_as_of,
        symbol=symbol,
    )
    return sum(
        current.quantity - (0 if at_observation is None else at_observation.quantity)
        for current, at_observation in revisions
    )


def _validate_projected_post_trade_exposure(
    connection: PostgresConnection,
    record: ManualTradeRecord,
    *,
    trades: tuple[ManualTradeRecord, ...],
    observation_as_of: datetime,
) -> None:
    authorization = record.strategy_execution_authorization
    assert authorization is not None
    portfolio_row = connection.execute(
        """
        SELECT payload_json
        FROM cross_strategy_portfolio_decision
        WHERE decision_id = %s
        """,
        (str(authorization.portfolio_decision_reference.artifact_id),),
    ).fetchone()
    if portfolio_row is None:
        raise ValueError("Strategy Portfolio policy is missing")
    portfolio_payload = _object_payload(portfolio_row["payload_json"])
    policy = portfolio_payload.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("Strategy Portfolio policy payload is invalid")
    maximum_gross = Decimal(str(policy["maximum_gross_weight"]))
    maximum_symbol = Decimal(str(policy["maximum_symbol_weight"]))
    positions = connection.execute(
        """
        SELECT symbol, total_quantity, observed_market_value
        FROM manual_position_observation
        WHERE observation_id = %s
        """,
        (str(authorization.account_observation_reference.artifact_id),),
    ).fetchall()
    physical_by_symbol = {str(item["symbol"]): Decimal(str(item["observed_market_value"])) for item in positions}
    observation_marks = {
        str(item["symbol"]): (
            Decimal("0")
            if int(item["total_quantity"]) == 0
            else Decimal(str(item["observed_market_value"]))
            / Decimal(int(item["total_quantity"]))
        )
        for item in positions
    }
    reserved_by_symbol: dict[str, Decimal] = {}
    for item in trades:
        item_authorization = item.strategy_execution_authorization
        if item.side is not TradeSide.BUY or item.state not in _ACTIVE_RESERVATION_STATES or item_authorization is None:
            continue
        reserved_by_symbol[item.symbol] = reserved_by_symbol.get(item.symbol, Decimal("0")) + (
            Decimal(max(0, item.intended_quantity - item.filled_quantity)) * item_authorization.reference_price
        )
    latest_account_marks = {
        item.symbol: item.strategy_execution_authorization.reference_price
        for item in trades
        if item.strategy_execution_authorization is not None
    }
    unobserved_by_symbol = _marked_unobserved_fill_notional_by_symbol(
        connection,
        authorization.account_id,
        observation_as_of=observation_as_of,
        mark_prices={
            **latest_account_marks,
            **observation_marks,
            authorization.symbol: authorization.reference_price,
        },
    )
    proposed = Decimal(record.intended_quantity) * authorization.reference_price
    symbol_notional = (
        physical_by_symbol.get(record.symbol, Decimal("0"))
        + reserved_by_symbol.get(record.symbol, Decimal("0"))
        + unobserved_by_symbol.get(record.symbol, Decimal("0"))
        + proposed
    )
    gross_notional = (
        sum(physical_by_symbol.values(), Decimal("0"))
        + sum(reserved_by_symbol.values(), Decimal("0"))
        + sum(unobserved_by_symbol.values(), Decimal("0"))
        + proposed
    )
    if gross_notional / authorization.account_nav > maximum_gross:
        raise ValueError("Projected post-trade gross exposure exceeds Portfolio policy")
    if symbol_notional / authorization.account_nav > maximum_symbol:
        raise ValueError("Projected post-trade symbol exposure exceeds Portfolio policy")
    contract_row = connection.execute(
        """
        SELECT c.payload_json
        FROM strategy_version AS v
        JOIN strategy_contract AS c
          ON c.contract_id = v.contract_id
         AND c.contract_hash = v.contract_hash
        WHERE v.version_id = %s AND v.version_hash = %s
        """,
        (
            str(authorization.strategy_version_reference.artifact_id),
            authorization.strategy_version_reference.content_hash,
        ),
    ).fetchone()
    if contract_row is None:
        raise ValueError("Strategy Contract budget owner is missing")
    contract_payload = _object_payload(contract_row["payload_json"])
    strategy_budget = Decimal(str(contract_payload["strategy_budget"]))
    strategy_trades = tuple(
        item
        for item in trades
        if item.strategy_execution_authorization is not None
        and item.strategy_execution_authorization.strategy_version_reference
        == authorization.strategy_version_reference
    )
    sleeve_quantities = _strategy_sleeve_quantities(
        connection,
        account_id=authorization.account_id,
    )
    latest_strategy_marks = {
        item.symbol: item.strategy_execution_authorization.reference_price
        for item in strategy_trades
        if item.strategy_execution_authorization is not None
    }
    filled_strategy_notional = _marked_strategy_sleeve_notional(
        sleeve_quantities=sleeve_quantities,
        strategy_version_id=str(
            authorization.strategy_version_reference.artifact_id
        ),
        target_symbol=authorization.symbol,
        target_price=authorization.reference_price,
        observation_marks=observation_marks,
        latest_strategy_marks=latest_strategy_marks,
    )
    active_strategy_buy_notional = sum(
        (
            Decimal(max(0, item.intended_quantity - item.filled_quantity)) * item.strategy_execution_authorization.reference_price
            for item in strategy_trades
            if item.side is TradeSide.BUY and item.state in _ACTIVE_RESERVATION_STATES and item.strategy_execution_authorization is not None
        ),
        Decimal("0"),
    )
    projected_strategy_notional = (
        filled_strategy_notional + active_strategy_buy_notional + proposed
    )
    if projected_strategy_notional / authorization.account_nav > strategy_budget:
        raise ValueError("Projected post-trade Strategy exposure exceeds Strategy Contract")


def _marked_unobserved_fill_notional_by_symbol(
    connection: PostgresConnection,
    account_id: str,
    *,
    observation_as_of: datetime,
    mark_prices: dict[str, Decimal],
) -> dict[str, Decimal]:
    quantities: dict[str, int] = {}
    for side, sign in (
        (TradeSide.BUY, 1),
        (TradeSide.SELL, -1),
    ):
        revisions = _effective_fill_revisions(
            connection,
            account_id=account_id,
            side=side,
            observation_as_of=observation_as_of,
        )
        for current, at_observation in revisions:
            delta = sign * (
                current.quantity
                - (0 if at_observation is None else at_observation.quantity)
            )
            quantities[current.symbol] = quantities.get(current.symbol, 0) + delta
    result: dict[str, Decimal] = {}
    for symbol, quantity in quantities.items():
        mark = mark_prices.get(symbol)
        if mark is None or mark <= 0:
            raise ValueError(
                "DATA_INSUFFICIENT: unobserved Fill has no owner-resolved mark"
            )
        result[symbol] = Decimal(quantity) * mark
    return result


def _strategy_sleeve_quantities(
    connection: PostgresConnection,
    *,
    account_id: str,
) -> dict[tuple[str, str], int]:
    """Reload allocated effective Fills and fail closed on allocation lag."""

    batch_rows = connection.execute(
        """
        SELECT payload_json
        FROM strategy_fill_allocation_batch
        WHERE account_id = %s
        ORDER BY created_at, batch_id
        """,
        (account_id,),
    ).fetchall()
    batches = tuple(
        FillAllocationBatch.from_canonical_dict(
            _object_payload(item["payload_json"])
        )
        for item in batch_rows
    )
    fill_rows = connection.execute(
        """
        SELECT f.fill_json
        FROM manual_fills AS f
        JOIN manual_trade_records AS t
          ON t.manual_trade_id = f.manual_trade_id
        WHERE f.account_id = %s AND t.authority_route = 'STRATEGY'
        ORDER BY f.recorded_at, f.fill_id
        """,
        (account_id,),
    ).fetchall()
    fills = tuple(
        Fill.from_canonical_dict(_object_payload(item["fill_json"]))
        for item in fill_rows
    )
    executions = {
        item.fill_id: item for item in fills if item.fill_kind is FillKind.EXECUTION
    }
    corrections = {
        item.correction_of_fill_id: item
        for item in fills
        if item.fill_kind is FillKind.CORRECTION
    }
    effective_fills = {
        (
            str(current.fill_id),
            canonical_hash(current.to_canonical_dict()),
        )
        for fill_id, original in executions.items()
        for current in (corrections.get(fill_id, original),)
    }
    effective_batches = effective_fill_allocation_batches(batches)
    allocated_fills = {
        (str(item.source_fill_id), item.source_fill_hash)
        for item in effective_batches
    }
    if effective_fills != allocated_fills:
        raise ValueError(
            "RECONCILIATION_REQUIRED: effective Strategy Fill allocation is incomplete"
        )
    return {
        (
            str(item.strategy_version_reference.artifact_id),
            item.symbol,
        ): item.quantity
        for item in project_strategy_sleeves(batches)
        if item.quantity > 0
    }


def _marked_strategy_sleeve_notional(
    *,
    sleeve_quantities: dict[tuple[str, str], int],
    strategy_version_id: str,
    target_symbol: str,
    target_price: Decimal,
    observation_marks: dict[str, Decimal],
    latest_strategy_marks: dict[str, Decimal],
) -> Decimal:
    notional = Decimal("0")
    for (version_id, symbol), quantity in sleeve_quantities.items():
        if version_id != strategy_version_id:
            continue
        mark = (
            target_price
            if symbol == target_symbol
            else observation_marks.get(symbol, latest_strategy_marks.get(symbol))
        )
        if mark is None or mark <= 0:
            raise ValueError(
                "DATA_INSUFFICIENT: Strategy sleeve has no owner-resolved mark"
            )
        notional += Decimal(quantity) * mark
    return notional


def _effective_fill_revisions(
    connection: PostgresConnection,
    *,
    account_id: str,
    side: TradeSide,
    observation_as_of: datetime,
    symbol: str | None = None,
) -> tuple[tuple[Fill, Fill | None], ...]:
    """Return current and observation-time effective Fill for each execution fact."""

    rows = connection.execute(
        """
        SELECT f.fill_json
        FROM manual_fills AS f
        JOIN manual_trade_records AS t
          ON t.manual_trade_id = f.manual_trade_id
        WHERE f.account_id = %s
          AND t.authority_route = 'STRATEGY'
          AND t.side = %s
          AND (%s::text IS NULL OR f.symbol = %s)
        ORDER BY f.manual_trade_id, f.recorded_at, f.fill_id
        """,
        (account_id, side.value, symbol, symbol),
    ).fetchall()
    fills = tuple(Fill.from_canonical_dict(_object_payload(row["fill_json"])) for row in rows)
    executions = {item.fill_id: item for item in fills if item.fill_kind is FillKind.EXECUTION}
    corrections = {item.correction_of_fill_id: item for item in fills if item.fill_kind is FillKind.CORRECTION}
    result: list[tuple[Fill, Fill | None]] = []
    for fill_id, fill in executions.items():
        correction = corrections.get(fill_id)
        current = fill if correction is None else correction
        if fill.recorded_at > observation_as_of:
            at_observation = None
        elif correction is not None and correction.recorded_at <= observation_as_of:
            at_observation = correction
        else:
            at_observation = fill
        if current != at_observation:
            result.append((current, at_observation))
    return tuple(result)


def _fill_notional(fill: Fill | None) -> Decimal:
    if fill is None:
        return Decimal("0")
    return Decimal(fill.quantity) * Decimal(str(fill.price))


def _fill_cash(fill: Fill | None) -> Decimal:
    if fill is None:
        return Decimal("0")
    return _fill_notional(fill) + Decimal(str(fill.fees))


def _trade_projection_values(record: ManualTradeRecord) -> tuple[object, ...]:
    authorization = record.strategy_execution_authorization
    route = record.authority_route.value if record.authority_route is not None else ManualTradeAuthorityRoute.INCREASING.value
    return (
        str(record.manual_trade_id),
        str(record.risk_decision_id) if record.risk_decision_id is not None else None,
        record.account_id,
        record.symbol,
        record.side.value,
        record.state.value,
        _json(record.to_canonical_dict()),
        route,
        str(authorization.authorization_id) if authorization is not None else None,
        authorization.authorization_hash if authorization is not None else None,
        (str(authorization.portfolio_decision_reference.artifact_id) if authorization is not None else None),
        (authorization.portfolio_decision_reference.content_hash if authorization is not None else None),
        (str(authorization.proposal_reference.artifact_id) if authorization is not None else None),
        authorization.proposal_reference.content_hash if authorization is not None else None,
        (str(authorization.strategy_version_reference.artifact_id) if authorization is not None else None),
        (authorization.strategy_version_reference.content_hash if authorization is not None else None),
        (str(authorization.account_observation_reference.artifact_id) if authorization is not None else None),
        (authorization.account_observation_reference.content_hash if authorization is not None else None),
        (str(authorization.trading_calendar_reference.artifact_id) if authorization is not None else None),
        (authorization.trading_calendar_reference.content_hash if authorization is not None else None),
        (
            "OWNER_RESOLVED_V2"
            if authorization is not None and authorization.schema_version == "strategy-execution-authorization/v2"
            else ("CALLER_PRICE_V1" if authorization is not None else None)
        ),
        (
            str(authorization.account_reconciliation_reference.artifact_id)
            if authorization is not None and authorization.account_reconciliation_reference is not None
            else None
        ),
        (
            authorization.account_reconciliation_reference.content_hash
            if authorization is not None and authorization.account_reconciliation_reference is not None
            else None
        ),
        (
            str(authorization.price_reference.artifact_id)
            if authorization is not None and authorization.schema_version == "strategy-execution-authorization/v2"
            else None
        ),
        (
            authorization.price_reference.content_hash
            if authorization is not None and authorization.schema_version == "strategy-execution-authorization/v2"
            else None
        ),
        (
            str(authorization.price_source_reference.artifact_id)
            if authorization is not None and authorization.price_source_reference is not None
            else None
        ),
        (
            authorization.price_source_reference.content_hash
            if authorization is not None and authorization.price_source_reference is not None
            else None
        ),
        authorization.price_observed_at if authorization is not None else None,
        authorization.price_available_at if authorization is not None else None,
        (
            authorization.recommended_quantity
            if authorization is not None and authorization.schema_version == "strategy-execution-authorization/v2"
            else None
        ),
    )


def _effective_quantity(fills: tuple[Fill, ...]) -> int:
    executions = {item.fill_id: item for item in fills if item.fill_kind is FillKind.EXECUTION}
    corrections = {item.correction_of_fill_id: item for item in fills if item.fill_kind is FillKind.CORRECTION}
    return sum(corrections.get(fill_id, fill).quantity for fill_id, fill in executions.items())


def _load_trade(
    connection: PostgresConnection,
    trade_id: ManualTradeId,
    version: int | None = None,
) -> ManualTradeRecord:
    row = connection.execute(
        "SELECT * FROM manual_trade_records WHERE manual_trade_id = %s",
        (str(trade_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown ManualTradeRecord: {trade_id}")
    current_version = int(row["version"])
    requested = current_version if version is None else version
    events = connection.execute(
        """
        SELECT aggregate_json FROM manual_trade_events
        WHERE manual_trade_id = %s AND sequence <= %s ORDER BY sequence
        """,
        (str(trade_id), requested),
    ).fetchall()
    if requested < 0 or requested > current_version or len(events) != requested + 1:
        raise ValueError("ManualTradeRecord history is not contiguous")
    history = tuple(ManualTradeRecord.from_canonical_dict(_object_json(str(item["aggregate_json"]))) for item in events)
    for before, after in zip(history, history[1:]):
        validate_manual_trade_transition(
            before,
            after,
            allow_terminal_fill_update=True,
        )
    result = history[-1]
    if requested == current_version:
        stored = ManualTradeRecord.from_canonical_dict(_object_json(str(row["aggregate_json"])))
        projected_route = result.authority_route.value if result.authority_route is not None else "INCREASING"
        route_projection_valid = True
        if "authority_route" in row.keys():
            route_projection_valid = (
                row["authority_route"] == projected_route
                and row["risk_decision_id"] == (str(result.risk_decision_id) if result.risk_decision_id is not None else None)
                and row["risk_reducing_decision_id"]
                == (str(result.risk_reducing_decision_id) if result.risk_reducing_decision_id is not None else None)
                and row["risk_reduction_confirmation_id"]
                == (str(result.risk_reduction_confirmation_id) if result.risk_reduction_confirmation_id is not None else None)
            )
        strategy_projection_valid = True
        if "strategy_authorization_id" in row.keys():
            authorization = result.strategy_execution_authorization
            strategy_projection_valid = (
                row["strategy_authorization_id"] == (str(authorization.authorization_id) if authorization is not None else None)
                and row["strategy_authorization_hash"] == (authorization.authorization_hash if authorization is not None else None)
                and row["strategy_portfolio_decision_id"]
                == (str(authorization.portfolio_decision_reference.artifact_id) if authorization is not None else None)
                and row["strategy_portfolio_decision_hash"]
                == (authorization.portfolio_decision_reference.content_hash if authorization is not None else None)
                and row["strategy_proposal_id"]
                == (str(authorization.proposal_reference.artifact_id) if authorization is not None else None)
                and row["strategy_proposal_hash"] == (authorization.proposal_reference.content_hash if authorization is not None else None)
                and row["strategy_version_id"]
                == (str(authorization.strategy_version_reference.artifact_id) if authorization is not None else None)
                and row["strategy_version_hash"]
                == (authorization.strategy_version_reference.content_hash if authorization is not None else None)
                and row["strategy_account_observation_id"]
                == (str(authorization.account_observation_reference.artifact_id) if authorization is not None else None)
                and row["strategy_account_observation_hash"]
                == (authorization.account_observation_reference.content_hash if authorization is not None else None)
                and row["strategy_calendar_id"]
                == (str(authorization.trading_calendar_reference.artifact_id) if authorization is not None else None)
                and row["strategy_calendar_hash"]
                == (authorization.trading_calendar_reference.content_hash if authorization is not None else None)
            )
            if "strategy_execution_authority_version" in row.keys():
                owner_resolved = authorization is not None and authorization.schema_version == "strategy-execution-authorization/v2"
                reconciliation = None if authorization is None else authorization.account_reconciliation_reference
                price_source = None if authorization is None else authorization.price_source_reference
                strategy_projection_valid = strategy_projection_valid and (
                    row["strategy_execution_authority_version"]
                    == ("OWNER_RESOLVED_V2" if owner_resolved else ("CALLER_PRICE_V1" if authorization is not None else None))
                    and row["strategy_reconciliation_id"] == (str(reconciliation.artifact_id) if reconciliation is not None else None)
                    and row["strategy_reconciliation_hash"] == (reconciliation.content_hash if reconciliation is not None else None)
                    and row["strategy_price_owner_id"]
                    == (str(authorization.price_reference.artifact_id) if owner_resolved and authorization is not None else None)
                    and row["strategy_price_owner_hash"]
                    == (authorization.price_reference.content_hash if owner_resolved and authorization is not None else None)
                    and row["strategy_price_source_id"] == (str(price_source.artifact_id) if price_source is not None else None)
                    and row["strategy_price_source_hash"] == (price_source.content_hash if price_source is not None else None)
                    and row["strategy_price_observed_at"] == (authorization.price_observed_at if authorization is not None else None)
                    and row["strategy_price_available_at"] == (authorization.price_available_at if authorization is not None else None)
                    and row["strategy_authorized_quantity"]
                    == (authorization.recommended_quantity if owner_resolved and authorization is not None else None)
                )
        if (
            stored != result
            or row["manual_trade_id"] != str(result.manual_trade_id)
            or row["account_id"] != result.account_id
            or row["symbol"] != result.symbol
            or row["side"] != result.side.value
            or row["state"] != result.state.value
            or int(row["filled_quantity"]) != result.filled_quantity
            or int(row["version"]) != result.version
            or not route_projection_valid
            or not strategy_projection_valid
        ):
            raise ValueError("ManualTradeRecord projection is not reconstructible")
    return result


def _load_fill(connection: PostgresConnection, fill_id: FillId) -> Fill:
    row = connection.execute("SELECT fill_json FROM manual_fills WHERE fill_id = %s", (str(fill_id),)).fetchone()
    if row is None:
        raise KeyError(f"unknown Fill: {fill_id}")
    return Fill.from_canonical_dict(_object_json(str(row["fill_json"])))


def _fills_for_trade(connection: PostgresConnection, trade_id: ManualTradeId) -> tuple[Fill, ...]:
    rows = connection.execute(
        """
        SELECT fill_json FROM manual_fills
        WHERE manual_trade_id = %s ORDER BY recorded_at, fill_id
        """,
        (str(trade_id),),
    ).fetchall()
    return tuple(Fill.from_canonical_dict(_object_json(str(item["fill_json"]))) for item in rows)


def _update_trade(connection: PostgresConnection, record: ManualTradeRecord, expected_version: int) -> None:
    updated = connection.execute(
        """
        UPDATE manual_trade_records
        SET state = %s, filled_quantity = %s, aggregate_json = %s, version = %s
        WHERE manual_trade_id = %s AND version = %s
        """,
        (
            record.state.value,
            record.filled_quantity,
            _json(record.to_canonical_dict()),
            record.version,
            str(record.manual_trade_id),
            expected_version,
        ),
    )
    if updated.rowcount != 1:
        raise ExecutionVersionConflictError("manual trade compare-and-swap failed")


def _insert_trade_event(connection: PostgresConnection, record: ManualTradeRecord, idempotency_key: str) -> None:
    connection.execute(
        """
        INSERT INTO manual_trade_events(
            manual_trade_id, sequence, state, aggregate_json,
            idempotency_key, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            str(record.manual_trade_id),
            record.version,
            record.state.value,
            _json(record.to_canonical_dict()),
            idempotency_key,
            record.updated_at.isoformat(),
        ),
    )


def _command(connection: PostgresConnection, key: str) -> dict[str, Any] | None:
    return connection.execute("SELECT * FROM execution_commands WHERE idempotency_key = %s", (key,)).fetchone()


def _validate_command(row: dict[str, Any], command_hash: str, trade_id: ManualTradeId) -> None:
    if row["command_hash"] != command_hash or row["manual_trade_id"] != str(trade_id):
        raise ValueError("idempotency key reused for different execution command")


def _insert_command(
    connection: PostgresConnection,
    *,
    idempotency_key: str,
    command_hash: str,
    record: ManualTradeRecord,
    fill: Fill | None,
) -> None:
    connection.execute(
        """
        INSERT INTO execution_commands(
            idempotency_key, command_hash, manual_trade_id,
            fill_id, result_version, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            idempotency_key,
            command_hash,
            str(record.manual_trade_id),
            str(fill.fill_id) if fill is not None else None,
            record.version,
            datetime.now(UTC).isoformat(),
        ),
    )


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _object_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("manual execution JSON must be an object")
    return payload


def _object_payload(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return _object_json(value)
    raise ValueError("PostgreSQL authority payload must be an object")


def load_manual_trade_projection(
    connection: PostgresConnection,
    trade_id: ManualTradeId,
    version: int | None = None,
) -> ManualTradeRecord:
    """Public in-transaction ManualTrade replay for composed repositories."""

    return _load_trade(connection, trade_id, version)


def insert_manual_trade_event(
    connection: PostgresConnection,
    record: ManualTradeRecord,
    idempotency_key: str,
) -> None:
    """Append one ManualTrade event inside a caller-owned transaction."""

    _insert_trade_event(connection, record, idempotency_key)


def serialize_manual_execution_json(payload: dict[str, Any]) -> str:
    """Serialize canonical manual-execution persistence JSON."""

    return _json(payload)


def restore_manual_execution_json(value: str) -> dict[str, Any]:
    """Restore object-shaped manual-execution persistence JSON."""

    return _object_json(value)


__all__ = [
    "ExecutionVersionConflictError",
    "PostgresManualExecutionRepository",
    "insert_manual_trade_event",
    "load_manual_trade_projection",
    "restore_manual_execution_json",
    "serialize_manual_execution_json",
]
