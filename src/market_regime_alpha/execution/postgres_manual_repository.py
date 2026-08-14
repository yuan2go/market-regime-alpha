"""PostgreSQL-native manual execution ledger with append-only Fill enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from typing import Any, Callable
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import FillId, ManualTradeId
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
            authority_validator=lambda connection: _validate_strategy_authority(
                connection, record
            ),
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
            acquire_scope_lock(
                connection,
                namespace="manual-trade",
                identity=record.manual_trade_id,
            )
            try:
                if authority_validator is not None:
                    authority_validator(connection)
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
                existing = connection.execute(
                    "SELECT aggregate_json FROM manual_trade_records WHERE manual_trade_id = %s",
                    (str(record.manual_trade_id),),
                ).fetchone()
                if existing is not None:
                    current = ManualTradeRecord.from_canonical_dict(
                        _object_json(str(existing["aggregate_json"]))
                    )
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
                            strategy_calendar_id, strategy_calendar_hash
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, 0, %s, 0,
                            %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s
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
            acquire_scope_lock(
                connection,
                namespace="manual-trade",
                identity=fill.manual_trade_id,
            )
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
                if current.state in {ManualOrderState.CANCELLED, ManualOrderState.REJECTED}:
                    raise ValueError("terminal cancelled/rejected trade cannot accept Fill")
                if current.state is ManualOrderState.FILLED and fill.fill_kind is FillKind.EXECUTION:
                    raise ValueError("filled trade accepts correction records only")
                existing_fill = connection.execute(
                    "SELECT fill_json FROM manual_fills WHERE fill_id = %s OR external_fill_id = %s",
                    (str(fill.fill_id), fill.external_fill_id),
                ).fetchone()
                if existing_fill is not None:
                    stored = Fill.from_canonical_dict(
                        _object_json(str(existing_fill["fill_json"]))
                    )
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
                    if any(
                        item.correction_of_fill_id == fill.correction_of_fill_id
                        for item in existing_fills
                    ):
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
                        (
                            str(fill.correction_of_fill_id)
                            if fill.correction_of_fill_id is not None
                            else None
                        ),
                        _json(fill.to_canonical_dict()),
                        fill.recorded_at.isoformat(),
                        idempotency_key,
                    ),
                )
                all_fills = (*existing_fills, fill)
                effective_quantity = _effective_quantity(all_fills)
                if effective_quantity < current.intended_quantity:
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
                validate_manual_trade_transition(current, updated)
                _update_trade(connection, updated, current.version)
                _insert_trade_event(
                    connection, updated, f"{idempotency_key}:trade"
                )
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

    def get_trade_for_idempotency_key(
        self, idempotency_key: str
    ) -> ManualTradeRecord | None:
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

    def all_fills(self, account_id: str, symbol: str) -> tuple[Fill, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT fill_json FROM manual_fills
                WHERE account_id = %s AND symbol = %s ORDER BY recorded_at, fill_id
                """,
                (account_id, symbol),
            ).fetchall()
            return tuple(
                Fill.from_canonical_dict(_object_json(str(item["fill_json"])))
                for item in rows
            )

    def _validate_loaded_trade(
        self, connection: PostgresConnection, record: ManualTradeRecord
    ) -> None:
        """Subclass hook for route-specific immutable binding validation."""


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
        ("calendar", authorization.trading_calendar_reference, "TRADING_CALENDAR"),
    )
    for label, reference, expected_kind in expected_kinds:
        if reference.reference_kind != expected_kind:
            raise ValueError(f"Strategy {label} authority kind mismatch")
    row = connection.execute(
        """
        SELECT d.decision_hash, l.accepted_weight,
               p.proposal_hash, p.strategy_version_id,
               p.strategy_version_hash, p.symbol, p.action,
               v.version_hash, c.decision_time
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
        str(row["decision_hash"])
        != authorization.portfolio_decision_reference.content_hash
        or Decimal(str(row["accepted_weight"])) == 0
        or Decimal(str(row["accepted_weight"])) != authorization.accepted_weight
        or str(row["proposal_hash"])
        != authorization.proposal_reference.content_hash
        or str(row["strategy_version_id"])
        != str(authorization.strategy_version_reference.artifact_id)
        or str(row["strategy_version_hash"])
        != authorization.strategy_version_reference.content_hash
        or str(row["version_hash"])
        != authorization.strategy_version_reference.content_hash
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
        str(observation["content_hash"])
        != authorization.account_observation_reference.content_hash
        or str(observation["account_id"]) != authorization.account_id
        or observation["as_of_time"] > authorization.decision_time
        or Decimal(str(observation["total_equity"])) != authorization.account_nav
        or Decimal(str(observation["available_cash"]))
        != authorization.available_cash
    ):
        raise ValueError("Strategy Account Observation authorization mismatch")
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
    physical_available = (
        0 if position is None else int(position["available_quantity"])
    )
    if (
        authorization.current_quantity > physical_quantity
        or authorization.available_quantity > physical_available
    ):
        raise ValueError("Strategy quantity exceeds Physical Position authority")
    calendar_row = connection.execute(
        """
        SELECT calendar_hash, payload_json
        FROM pit_trading_calendar_canonical_snapshot
        WHERE calendar_id = %s
        FOR SHARE
        """,
        (str(authorization.trading_calendar_reference.artifact_id),),
    ).fetchone()
    if calendar_row is None or str(calendar_row["calendar_hash"]) != (
        authorization.trading_calendar_reference.content_hash
    ):
        raise ValueError("Strategy Trading Calendar authorization mismatch")
    calendar_payload = calendar_row["payload_json"]
    if not isinstance(calendar_payload, dict):
        raise ValueError("Strategy Trading Calendar payload is invalid")
    calendar = TradingCalendarArtifact.from_canonical_dict(calendar_payload)
    decision_date = authorization.decision_time.astimezone(
        ZoneInfo(calendar.timezone_name)
    ).date()
    if not calendar.contains(decision_date):
        raise ValueError("Strategy decision is outside the authorized Trading Calendar")
    if not (
        Decimal(str(record.expected_price_lower))
        <= authorization.reference_price
        <= Decimal(str(record.expected_price_upper))
    ):
        raise ValueError("Strategy reference price is outside the Manual Intent range")


def _trade_projection_values(record: ManualTradeRecord) -> tuple[object, ...]:
    authorization = record.strategy_execution_authorization
    route = (
        record.authority_route.value
        if record.authority_route is not None
        else ManualTradeAuthorityRoute.INCREASING.value
    )
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
        (
            str(authorization.portfolio_decision_reference.artifact_id)
            if authorization is not None
            else None
        ),
        (
            authorization.portfolio_decision_reference.content_hash
            if authorization is not None
            else None
        ),
        (
            str(authorization.proposal_reference.artifact_id)
            if authorization is not None
            else None
        ),
        authorization.proposal_reference.content_hash if authorization is not None else None,
        (
            str(authorization.strategy_version_reference.artifact_id)
            if authorization is not None
            else None
        ),
        (
            authorization.strategy_version_reference.content_hash
            if authorization is not None
            else None
        ),
        (
            str(authorization.account_observation_reference.artifact_id)
            if authorization is not None
            else None
        ),
        (
            authorization.account_observation_reference.content_hash
            if authorization is not None
            else None
        ),
        (
            str(authorization.trading_calendar_reference.artifact_id)
            if authorization is not None
            else None
        ),
        (
            authorization.trading_calendar_reference.content_hash
            if authorization is not None
            else None
        ),
    )


def _effective_quantity(fills: tuple[Fill, ...]) -> int:
    executions = {item.fill_id: item for item in fills if item.fill_kind is FillKind.EXECUTION}
    corrections = {
        item.correction_of_fill_id: item
        for item in fills
        if item.fill_kind is FillKind.CORRECTION
    }
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
    history = tuple(
        ManualTradeRecord.from_canonical_dict(_object_json(str(item["aggregate_json"])))
        for item in events
    )
    for before, after in zip(history, history[1:]):
        validate_manual_trade_transition(before, after)
    result = history[-1]
    if requested == current_version:
        stored = ManualTradeRecord.from_canonical_dict(
            _object_json(str(row["aggregate_json"]))
        )
        projected_route = (
            result.authority_route.value
            if result.authority_route is not None
            else "INCREASING"
        )
        route_projection_valid = True
        if "authority_route" in row.keys():
            route_projection_valid = (
                row["authority_route"] == projected_route
                and row["risk_decision_id"]
                == (
                    str(result.risk_decision_id)
                    if result.risk_decision_id is not None
                    else None
                )
                and row["risk_reducing_decision_id"]
                == (
                    str(result.risk_reducing_decision_id)
                    if result.risk_reducing_decision_id is not None
                    else None
                )
                and row["risk_reduction_confirmation_id"]
                == (
                    str(result.risk_reduction_confirmation_id)
                    if result.risk_reduction_confirmation_id is not None
                    else None
                )
            )
        strategy_projection_valid = True
        if "strategy_authorization_id" in row.keys():
            authorization = result.strategy_execution_authorization
            strategy_projection_valid = (
                row["strategy_authorization_id"]
                == (
                    str(authorization.authorization_id)
                    if authorization is not None
                    else None
                )
                and row["strategy_authorization_hash"]
                == (
                    authorization.authorization_hash
                    if authorization is not None
                    else None
                )
                and row["strategy_portfolio_decision_id"]
                == (
                    str(authorization.portfolio_decision_reference.artifact_id)
                    if authorization is not None
                    else None
                )
                and row["strategy_portfolio_decision_hash"]
                == (
                    authorization.portfolio_decision_reference.content_hash
                    if authorization is not None
                    else None
                )
                and row["strategy_proposal_id"]
                == (
                    str(authorization.proposal_reference.artifact_id)
                    if authorization is not None
                    else None
                )
                and row["strategy_proposal_hash"]
                == (
                    authorization.proposal_reference.content_hash
                    if authorization is not None
                    else None
                )
                and row["strategy_version_id"]
                == (
                    str(authorization.strategy_version_reference.artifact_id)
                    if authorization is not None
                    else None
                )
                and row["strategy_version_hash"]
                == (
                    authorization.strategy_version_reference.content_hash
                    if authorization is not None
                    else None
                )
                and row["strategy_account_observation_id"]
                == (
                    str(authorization.account_observation_reference.artifact_id)
                    if authorization is not None
                    else None
                )
                and row["strategy_account_observation_hash"]
                == (
                    authorization.account_observation_reference.content_hash
                    if authorization is not None
                    else None
                )
                and row["strategy_calendar_id"]
                == (
                    str(authorization.trading_calendar_reference.artifact_id)
                    if authorization is not None
                    else None
                )
                and row["strategy_calendar_hash"]
                == (
                    authorization.trading_calendar_reference.content_hash
                    if authorization is not None
                    else None
                )
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
    row = connection.execute(
        "SELECT fill_json FROM manual_fills WHERE fill_id = %s", (str(fill_id),)
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown Fill: {fill_id}")
    return Fill.from_canonical_dict(_object_json(str(row["fill_json"])))


def _fills_for_trade(
    connection: PostgresConnection, trade_id: ManualTradeId
) -> tuple[Fill, ...]:
    rows = connection.execute(
        """
        SELECT fill_json FROM manual_fills
        WHERE manual_trade_id = %s ORDER BY recorded_at, fill_id
        """,
        (str(trade_id),),
    ).fetchall()
    return tuple(
        Fill.from_canonical_dict(_object_json(str(item["fill_json"])))
        for item in rows
    )


def _update_trade(
    connection: PostgresConnection, record: ManualTradeRecord, expected_version: int
) -> None:
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


def _insert_trade_event(
    connection: PostgresConnection, record: ManualTradeRecord, idempotency_key: str
) -> None:
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
    return connection.execute(
        "SELECT * FROM execution_commands WHERE idempotency_key = %s", (key,)
    ).fetchone()


def _validate_command(
    row: dict[str, Any], command_hash: str, trade_id: ManualTradeId
) -> None:
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
