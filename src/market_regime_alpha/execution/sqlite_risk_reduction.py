"""Unified SQLite H4.5 authority and atomic manual-intent confirmation."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalCompositionStatus,
)
from market_regime_alpha.application.operational_research.sqlite_composite_repository import (
    SQLiteCompositeOperationalRepository,
)
from market_regime_alpha.core.identity import ArtifactId, ManualTradeId
from market_regime_alpha.decision.opportunity import OpportunityState
from market_regime_alpha.decision.sqlite_repository import (
    SQLiteDecisionLifecycleRepository,
)
from market_regime_alpha.decision.thesis import ThesisState
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
    ManualOrderState,
    ManualTradeAuthorityRoute,
    ManualTradeRecord,
    TradeSide,
)
from market_regime_alpha.execution.position_book import PositionBookState
from market_regime_alpha.execution.risk_reduction import (
    OperationalExitDirectiveV2,
    RiskReductionConfirmationAttempt,
    RiskReductionConfirmationCommand,
    RiskReductionConfirmationResult,
    RiskReductionConfirmationState,
    build_operational_exit_directive_v2,
    validate_h5_h6_operational_lineage,
)
from market_regime_alpha.execution.sqlite_repository import (
    _insert_trade_event,
    _json,
    _load_trade,
    _object_json,
)
from market_regime_alpha.execution.sqlite_traceability import (
    SQLiteTraceableManualExecutionRepository,
)
from market_regime_alpha.portfolio.risk_routes import (
    RiskChangeKind,
    RiskReducingDecisionState,
    RiskReducingExecutionGate,
)
from market_regime_alpha.portfolio.sqlite_risk_routes import (
    SQLiteRiskRouteRepository,
)
from market_regime_alpha.position.assessment import ExitAssessment
from market_regime_alpha.position.authority import (
    PositionProjector,
    PositionSnapshot,
)
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)


class SQLiteRiskReductionManualIntentRepository(
    SQLiteTraceableManualExecutionRepository
):
    """One lifecycle DB, one writer transaction, no Fill or broker side effect."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._risk_routes = SQLiteRiskRouteRepository(path)
        self._thesis_health = SQLiteThesisHealthRepository(path)
        self._decisions = SQLiteDecisionLifecycleRepository(path)
        self._composite = SQLiteCompositeOperationalRepository(path)
        with self._connect() as connection:
            _validate_h4_5_schema(connection)

    def save_operational_exit_directive(
        self,
        directive: OperationalExitDirectiveV2,
        *,
        exit_assessment: ExitAssessment,
        risk_reducing_decision_id: ArtifactId,
    ) -> OperationalExitDirectiveV2:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                risk_bundle = (
                    self._risk_routes.get_verified_reducing_decision_bundle(
                        risk_reducing_decision_id
                    )
                )
                health_bundle = (
                    self._thesis_health.get_verified_thesis_health_bundle(
                        directive.thesis_health_observation_id
                    )
                )
                composite = self._composite.get_manifest(
                    directive.composite_manifest_id
                )
                expected = build_operational_exit_directive_v2(
                    exit_assessment=exit_assessment,
                    risk_bundle=risk_bundle,
                    health_bundle=health_bundle,
                    composite=composite,
                    created_at=directive.created_at,
                )
                if expected != directive:
                    raise ValueError("OperationalExitDirectiveV2 authority mismatch")
                existing = connection.execute(
                    """
                    SELECT directive_json, exit_assessment_json,
                           risk_reducing_decision_id
                    FROM operational_exit_directives
                    WHERE directive_id = ? OR content_hash = ?
                    """,
                    (str(directive.directive_id), directive.content_hash),
                ).fetchone()
                assessment_json = _json(exit_assessment.to_canonical_dict())
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO operational_exit_directives(
                            directive_id, content_hash, exit_assessment_id,
                            risk_reducing_decision_id,
                            thesis_health_observation_id,
                            composite_manifest_id, directive_json,
                            exit_assessment_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(directive.directive_id),
                            directive.content_hash,
                            str(directive.exit_assessment_id),
                            str(risk_reducing_decision_id),
                            str(directive.thesis_health_observation_id),
                            str(directive.composite_manifest_id),
                            _json(directive.to_canonical_dict()),
                            assessment_json,
                            directive.created_at.isoformat(),
                        ),
                    )
                elif (
                    _object_json(str(existing["directive_json"]))
                    != directive.to_canonical_dict()
                    or str(existing["exit_assessment_json"]) != assessment_json
                    or existing["risk_reducing_decision_id"]
                    != str(risk_reducing_decision_id)
                ):
                    raise ValueError("OperationalExitDirectiveV2 identity conflict")
                stored = _load_directive(connection, directive.directive_id)
                connection.commit()
                return stored
            except Exception:
                connection.rollback()
                raise

    def get_operational_exit_directive(
        self, directive_id: ArtifactId
    ) -> OperationalExitDirectiveV2:
        with self._connect() as connection:
            return _load_directive(connection, directive_id)

    def get_confirmation_attempt(
        self, attempt_id: ArtifactId
    ) -> RiskReductionConfirmationAttempt:
        with self._connect() as connection:
            return _load_attempt(connection, attempt_id)[0]

    def confirm_risk_reduction(
        self, command: RiskReductionConfirmationCommand
    ) -> RiskReductionConfirmationResult:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay = _resolve_confirmation_command(connection, command)
                if replay is not None:
                    connection.commit()
                    return replay

                risk_bundle = (
                    self._risk_routes.get_verified_reducing_decision_bundle(
                        command.risk_reducing_decision_id
                    )
                )
                decision = risk_bundle.decision
                if decision.content_hash != command.risk_reducing_decision_hash:
                    raise ValueError("RiskReducingDecision hash mismatch")
                directive_row = connection.execute(
                    """
                    SELECT * FROM operational_exit_directives
                    WHERE directive_id = ?
                    """,
                    (str(command.exit_directive_id),),
                ).fetchone()
                if directive_row is None:
                    raise KeyError(
                        f"unknown OperationalExitDirectiveV2: {command.exit_directive_id}"
                    )
                directive = _directive_from_row(directive_row)
                if (
                    directive.content_hash != command.exit_directive_hash
                    or directive_row["risk_reducing_decision_id"]
                    != str(decision.decision_id)
                ):
                    raise ValueError("OperationalExitDirectiveV2 hash/scope mismatch")

                book = self.get_position_book(decision.position_book_id)
                trades = self.trades_for_book(book.position_book_id)
                fills = self.fills_for_book(book.position_book_id)
                current_position = PositionProjector().project_book_t_plus_one(
                    book=book,
                    trades=trades,
                    fills=fills,
                    calendar=command.trading_calendar,
                    symbol_session_statuses=command.symbol_trading_statuses,
                    as_of=command.confirmed_at,
                )
                thesis = self._decisions.get_thesis(decision.thesis_id)
                opportunity = self._decisions.get_opportunity(thesis.opportunity_id)
                health_bundle = (
                    self._thesis_health.get_verified_thesis_health_bundle(
                        command.thesis_health_observation_id
                    )
                )
                composite = self._composite.get_manifest(
                    command.composite_manifest_id
                )

                failure = self._confirmation_failure(
                    command=command,
                    directive=directive,
                    risk_bundle=risk_bundle,
                    current_position=current_position,
                    book=book,
                    thesis=thesis,
                    opportunity=opportunity,
                    health_bundle=health_bundle,
                    composite=composite,
                )
                if failure is not None:
                    state, reason_codes = failure
                    result = _persist_failed_confirmation(
                        connection,
                        command=command,
                        directive=directive,
                        risk_bundle=risk_bundle,
                        current_position=current_position,
                        state=state,
                        reason_codes=reason_codes,
                    )
                    connection.commit()
                    return result

                confirmed = connection.execute(
                    """
                    SELECT attempt_id FROM risk_reduction_confirmation_attempts
                    WHERE risk_reducing_decision_id = ?
                      AND state = 'CONFIRMED_INTENT'
                    """,
                    (str(decision.decision_id),),
                ).fetchone()
                if confirmed is not None:
                    raise ValueError(
                        "RiskReducingDecision already created a confirmed intent"
                    )
                result = _persist_confirmed_intent(
                    connection,
                    command=command,
                    directive=directive,
                    risk_bundle=risk_bundle,
                    current_position=current_position,
                    book=book,
                    opportunity=opportunity,
                    thesis=thesis,
                )
                assert result.manual_trade is not None
                stored_trade = _load_trade(
                    connection, result.manual_trade.manual_trade_id
                )
                self._validate_loaded_trade(connection, stored_trade)
                stored_attempt, stored_position = _load_attempt(
                    connection, result.attempt.attempt_id
                )
                if (
                    stored_trade != result.manual_trade
                    or stored_attempt != result.attempt
                    or stored_position != current_position
                ):
                    raise ValueError("H4.5 atomic projection replay mismatch")
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def _confirmation_failure(
        self,
        *,
        command: RiskReductionConfirmationCommand,
        directive: OperationalExitDirectiveV2,
        risk_bundle,
        current_position: PositionSnapshot,
        book,
        thesis,
        opportunity,
        health_bundle,
        composite,
    ) -> tuple[RiskReductionConfirmationState, tuple[str, ...]] | None:
        decision = risk_bundle.decision
        source = risk_bundle.position
        health = health_bundle.observation
        manifest = composite.manifest
        if decision.state is RiskReducingDecisionState.DATA_INSUFFICIENT:
            return (
                RiskReductionConfirmationState.DATA_INSUFFICIENT,
                ("H4_DECISION_DATA_INSUFFICIENT",),
            )
        if decision.state is not RiskReducingDecisionState.PERMITTED_FOR_MANUAL_CONFIRMATION:
            return (
                RiskReductionConfirmationState.BLOCKED_ON_RECHECK,
                ("H4_DECISION_NOT_PERMITTED",),
            )
        decision_age = (command.confirmed_at - decision.assessed_at).total_seconds()
        if decision_age < 0.0:
            return (
                RiskReductionConfirmationState.DATA_INSUFFICIENT,
                ("CONFIRMATION_PRECEDES_H4_DECISION",),
            )
        if decision_age > command.confirmation_policy.maximum_decision_age_seconds:
            return (
                RiskReductionConfirmationState.EXPIRED,
                ("RISK_REDUCING_DECISION_EXPIRED",),
            )
        if (
            decision.action is RiskChangeKind.REDUCE
            and decision.target_quantity == 0
        ):
            return (
                RiskReductionConfirmationState.ACTION_SEMANTICS_CONFLICT,
                (
                    "H4_V2_REDUCE_REQUIRES_POSITIVE_REMAINDER",
                    "REQUIRES_NEW_EXIT_DECISION",
                ),
            )
        if (
            book.state is not PositionBookState.OPEN
            or thesis.state is ThesisState.CLOSED
            or thesis.state not in {ThesisState.APPROVED, ThesisState.INVALIDATED}
        ):
            return (
                RiskReductionConfirmationState.BLOCKED_ON_RECHECK,
                ("POSITION_BOOK_OR_THESIS_CLOSED",),
            )
        if (
            opportunity.state is not OpportunityState.CONFIRMED_TO_THESIS
            or opportunity.opportunity_id != thesis.opportunity_id
            or thesis.thesis_id != decision.thesis_id
            or thesis.symbol != decision.symbol
            or book.thesis_id != thesis.thesis_id
            or book.opportunity_id != opportunity.opportunity_id
            or directive.action.value != decision.action.value
            or directive.position_book_id != decision.position_book_id
            or directive.thesis_id != decision.thesis_id
            or directive.opportunity_id != opportunity.opportunity_id
            or directive.symbol != decision.symbol
        ):
            return (
                RiskReductionConfirmationState.DATA_INSUFFICIENT,
                ("DECISION_LIFECYCLE_SCOPE_MISMATCH",),
            )
        if (
            health.content_hash != command.thesis_health_observation_hash
            or health.observation_id != command.thesis_health_observation_id
            or health.observation_id != directive.thesis_health_observation_id
            or health.content_hash != directive.thesis_health_observation_hash
            or health.thesis_id != thesis.thesis_id
            or health.thesis_version != thesis.version
            or health.opportunity_id != opportunity.opportunity_id
            or health.symbol != thesis.symbol
            or manifest.manifest_id != command.composite_manifest_id
            or manifest.content_hash != command.composite_manifest_hash
            or manifest.manifest_id != directive.composite_manifest_id
            or manifest.content_hash != directive.composite_manifest_hash
            or manifest.status is not CompositeOperationalCompositionStatus.VERIFIED
        ):
            return (
                RiskReductionConfirmationState.DATA_INSUFFICIENT,
                ("H5_H6_CURRENT_LINEAGE_MISMATCH",),
            )
        try:
            validate_h5_h6_operational_lineage(
                health_bundle=health_bundle,
                composite=composite,
            )
        except ValueError:
            return (
                RiskReductionConfirmationState.DATA_INSUFFICIENT,
                ("H5_H6_OPERATIONAL_LINEAGE_NOT_VERIFIED",),
            )
        current_hash = canonical_hash(current_position.to_canonical_dict())
        source_hash = canonical_hash(source.to_canonical_dict())
        if (
            source.snapshot_id != current_position.snapshot_id
            or source_hash != current_hash
            or source.version != current_position.version
            or source.total_quantity != current_position.total_quantity
            or source.available_quantity != current_position.available_quantity
            or source.position_book_id != current_position.position_book_id
            or source.thesis_id != current_position.thesis_id
            or source.opportunity_id != current_position.opportunity_id
            or source.symbol != current_position.symbol
            or decision.position_snapshot_hash != source_hash
        ):
            return (
                RiskReductionConfirmationState.POSITION_CHANGED,
                ("LATEST_FILL_DERIVED_POSITION_CHANGED",),
            )
        observation = command.execution_observation
        observation_age = (
            command.confirmed_at - observation.availability_time
        ).total_seconds()
        session_date = command.confirmed_at.astimezone(
            command.trading_calendar.sessions[0].session_close.tzinfo
        ).date()
        current_status = tuple(
            item
            for item in command.symbol_trading_statuses
            if item.session_date == session_date
        )
        if (
            observation_age < 0.0
            or observation_age
            > command.confirmation_policy.maximum_execution_observation_age_seconds
            or observation.symbol != decision.symbol
            or observation.session_date != session_date
            or len(current_status) != 1
        ):
            return (
                RiskReductionConfirmationState.DATA_INSUFFICIENT,
                ("FRESH_EXECUTION_OBSERVATION_NOT_ESTABLISHED",),
            )
        replay = RiskReducingExecutionGate().assess(
            action=decision.action,
            position=current_position,
            target_quantity=decision.target_quantity,
            order_quantity=decision.order_quantity,
            execution_observation=observation,
            configuration=risk_bundle.configuration,
            actor=command.actor,
            reason=command.reason,
            assessed_at=command.confirmed_at,
        )
        if replay.state is RiskReducingDecisionState.DATA_INSUFFICIENT:
            return (
                RiskReductionConfirmationState.DATA_INSUFFICIENT,
                tuple(sorted(set(replay.reason_codes))),
            )
        if replay.state is not RiskReducingDecisionState.PERMITTED_FOR_MANUAL_CONFIRMATION:
            return (
                RiskReductionConfirmationState.BLOCKED_ON_RECHECK,
                tuple(sorted(set(replay.reason_codes))),
            )
        reference = observation.reference_price
        deviation = command.confirmation_policy.maximum_reference_price_deviation
        if (
            not command.expected_price_lower <= reference <= command.expected_price_upper
            or abs(command.expected_price_lower - reference) / reference > deviation
            or abs(command.expected_price_upper - reference) / reference > deviation
        ):
            return (
                RiskReductionConfirmationState.BLOCKED_ON_RECHECK,
                ("EXPECTED_PRICE_RANGE_OUTSIDE_POLICY",),
            )
        return None


def _persist_confirmed_intent(
    connection: sqlite3.Connection,
    *,
    command: RiskReductionConfirmationCommand,
    directive: OperationalExitDirectiveV2,
    risk_bundle,
    current_position: PositionSnapshot,
    book,
    opportunity,
    thesis,
) -> RiskReductionConfirmationResult:
    decision = risk_bundle.decision
    manual_trade_id = ManualTradeId(
        f"manual-trade-reducing-{command.command_hash.split(':', 1)[1][:24]}"
    )
    attempt = _attempt(
        command=command,
        directive=directive,
        risk_bundle=risk_bundle,
        current_position=current_position,
        state=RiskReductionConfirmationState.CONFIRMED_INTENT,
        manual_trade_id=manual_trade_id,
        reason_codes=(
            "MANUAL_INTENT_CREATED",
            "NO_BROKER_ORDER_CREATED",
            "NO_FILL_CREATED",
            "OPERATOR_AUTHENTICATION_NOT_ESTABLISHED",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
    )
    trade = ManualTradeRecord(
        schema_version=ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
        manual_trade_id=manual_trade_id,
        risk_decision_id=None,
        risk_decision_hash=None,
        portfolio_decision_id=None,
        target_position_hash=None,
        account_id=book.account_id,
        symbol=decision.symbol,
        side=TradeSide.SELL,
        intended_quantity=decision.order_quantity,
        expected_price_lower=command.expected_price_lower,
        expected_price_upper=command.expected_price_upper,
        state=ManualOrderState.RECORDED,
        filled_quantity=0,
        version=0,
        actor=command.actor,
        reason=command.reason,
        created_at=command.confirmed_at,
        updated_at=command.confirmed_at,
        last_actor=command.actor,
        last_reason=command.reason,
        position_book_id=book.position_book_id,
        thesis_id=thesis.thesis_id,
        opportunity_id=opportunity.opportunity_id,
        authority_route=ManualTradeAuthorityRoute.REDUCING,
        risk_reducing_decision_id=decision.decision_id,
        risk_reducing_decision_hash=decision.content_hash,
        risk_reduction_confirmation_id=attempt.attempt_id,
        risk_reduction_confirmation_hash=attempt.content_hash,
        source_position_snapshot_id=decision.position_snapshot_id,
        source_position_snapshot_hash=decision.position_snapshot_hash,
        source_position_snapshot_version=decision.position_snapshot_version,
        target_quantity=decision.target_quantity,
        order_quantity=decision.order_quantity,
    )
    connection.execute(
        """
        INSERT INTO manual_trade_records(
            manual_trade_id, authority_route, risk_decision_id,
            risk_reducing_decision_id, risk_reduction_confirmation_id,
            account_id, symbol, side, state, filled_quantity,
            aggregate_json, version
        ) VALUES (?, 'REDUCING', NULL, ?, ?, ?, ?, 'SELL', ?, 0, ?, 0)
        """,
        (
            str(trade.manual_trade_id),
            str(decision.decision_id),
            str(attempt.attempt_id),
            trade.account_id,
            trade.symbol,
            trade.state.value,
            _json(trade.to_canonical_dict()),
        ),
    )
    _insert_trade_event(connection, trade, f"{command.idempotency_key}:trade")
    _insert_attempt(connection, command, attempt, current_position)
    connection.execute(
        """
        INSERT INTO risk_reducing_manual_trade_bindings(
            manual_trade_id, position_book_id, opportunity_id, thesis_id,
            symbol, risk_reducing_decision_id,
            risk_reducing_decision_hash, confirmation_attempt_id,
            confirmation_attempt_hash, source_position_snapshot_id,
            source_position_snapshot_hash, source_position_snapshot_version,
            target_quantity, order_quantity, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(trade.manual_trade_id),
            str(book.position_book_id),
            str(opportunity.opportunity_id),
            str(thesis.thesis_id),
            trade.symbol,
            str(decision.decision_id),
            decision.content_hash,
            str(attempt.attempt_id),
            attempt.content_hash,
            str(decision.position_snapshot_id),
            decision.position_snapshot_hash,
            decision.position_snapshot_version,
            decision.target_quantity,
            decision.order_quantity,
            command.confirmed_at.isoformat(),
        ),
    )
    _insert_confirmation_command(connection, command, attempt, trade)
    return RiskReductionConfirmationResult(
        attempt=attempt,
        current_position=current_position,
        manual_trade=trade,
        outcome="MANUAL_INTENT_CREATED",
    )


def _persist_failed_confirmation(
    connection: sqlite3.Connection,
    *,
    command: RiskReductionConfirmationCommand,
    directive: OperationalExitDirectiveV2,
    risk_bundle,
    current_position: PositionSnapshot,
    state: RiskReductionConfirmationState,
    reason_codes: tuple[str, ...],
) -> RiskReductionConfirmationResult:
    attempt = _attempt(
        command=command,
        directive=directive,
        risk_bundle=risk_bundle,
        current_position=current_position,
        state=state,
        manual_trade_id=None,
        reason_codes=reason_codes,
    )
    _insert_attempt(connection, command, attempt, current_position)
    _insert_confirmation_command(connection, command, attempt, None)
    return RiskReductionConfirmationResult(
        attempt=attempt,
        current_position=current_position,
        manual_trade=None,
        outcome=state.value,
    )


def _attempt(
    *,
    command: RiskReductionConfirmationCommand,
    directive: OperationalExitDirectiveV2,
    risk_bundle,
    current_position: PositionSnapshot,
    state: RiskReductionConfirmationState,
    manual_trade_id: ManualTradeId | None,
    reason_codes: tuple[str, ...],
) -> RiskReductionConfirmationAttempt:
    decision = risk_bundle.decision
    return RiskReductionConfirmationAttempt.create(
        state=state,
        risk_reducing_decision_id=decision.decision_id,
        risk_reducing_decision_hash=decision.content_hash,
        exit_directive_id=directive.directive_id,
        exit_directive_hash=directive.content_hash,
        source_position_snapshot_id=decision.position_snapshot_id,
        source_position_snapshot_hash=decision.position_snapshot_hash,
        current_position_snapshot_id=current_position.snapshot_id,
        current_position_snapshot_hash=canonical_hash(
            current_position.to_canonical_dict()
        ),
        thesis_health_observation_id=command.thesis_health_observation_id,
        thesis_health_observation_hash=command.thesis_health_observation_hash,
        composite_manifest_id=command.composite_manifest_id,
        composite_manifest_hash=command.composite_manifest_hash,
        recheck_observation_id=command.execution_observation.observation_id,
        recheck_observation_hash=command.execution_observation.content_hash,
        configuration_id=risk_bundle.configuration.configuration_id,
        configuration_hash=risk_bundle.configuration.configuration_hash,
        confirmation_policy_id=command.confirmation_policy.policy_id,
        confirmation_policy_hash=command.confirmation_policy.policy_hash,
        manual_trade_id=manual_trade_id,
        actor=command.actor,
        reason=command.reason,
        confirmed_at=command.confirmed_at,
        reason_codes=tuple(sorted(set(reason_codes))),
    )


def _insert_attempt(
    connection: sqlite3.Connection,
    command: RiskReductionConfirmationCommand,
    attempt: RiskReductionConfirmationAttempt,
    current_position: PositionSnapshot,
) -> None:
    connection.execute(
        """
        INSERT INTO risk_reduction_confirmation_attempts(
            attempt_id, content_hash, state, risk_reducing_decision_id,
            exit_directive_id, manual_trade_id, attempt_json, policy_json,
            recheck_observation_json, current_position_json,
            trading_calendar_json, symbol_trading_status_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(attempt.attempt_id),
            attempt.content_hash,
            attempt.state.value,
            str(attempt.risk_reducing_decision_id),
            str(attempt.exit_directive_id),
            (
                str(attempt.manual_trade_id)
                if attempt.manual_trade_id is not None
                else None
            ),
            _json(attempt.to_canonical_dict()),
            _json(command.confirmation_policy.to_canonical_dict()),
            _json(command.execution_observation.to_canonical_dict()),
            _json(current_position.to_canonical_dict()),
            _json(command.trading_calendar.to_canonical_dict()),
            _json(
                {
                    "items": [
                        item.to_canonical_dict()
                        for item in command.symbol_trading_statuses
                    ]
                }
            ),
            command.confirmed_at.isoformat(),
        ),
    )


def _insert_confirmation_command(
    connection: sqlite3.Connection,
    command: RiskReductionConfirmationCommand,
    attempt: RiskReductionConfirmationAttempt,
    trade: ManualTradeRecord | None,
) -> None:
    connection.execute(
        """
        INSERT INTO risk_reduction_confirmation_commands(
            idempotency_key, command_hash, risk_reducing_decision_id,
            attempt_id, manual_trade_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            command.idempotency_key,
            command.command_hash,
            str(attempt.risk_reducing_decision_id),
            str(attempt.attempt_id),
            str(trade.manual_trade_id) if trade is not None else None,
            command.confirmed_at.isoformat(),
        ),
    )


def _resolve_confirmation_command(
    connection: sqlite3.Connection,
    command: RiskReductionConfirmationCommand,
) -> RiskReductionConfirmationResult | None:
    row = connection.execute(
        """
        SELECT command_hash, attempt_id, manual_trade_id
        FROM risk_reduction_confirmation_commands
        WHERE idempotency_key = ?
        """,
        (command.idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if row["command_hash"] != command.command_hash:
        raise ValueError("idempotency key reused for different H4.5 command")
    attempt, current_position = _load_attempt(
        connection, ArtifactId(str(row["attempt_id"]))
    )
    trade = (
        _load_trade(connection, ManualTradeId(str(row["manual_trade_id"])))
        if row["manual_trade_id"] is not None
        else None
    )
    return RiskReductionConfirmationResult(
        attempt=attempt,
        current_position=current_position,
        manual_trade=trade,
        outcome=(
            "MANUAL_INTENT_CREATED"
            if trade is not None
            else attempt.state.value
        ),
    )


def _load_directive(
    connection: sqlite3.Connection, directive_id: ArtifactId
) -> OperationalExitDirectiveV2:
    row = connection.execute(
        "SELECT * FROM operational_exit_directives WHERE directive_id = ?",
        (str(directive_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown OperationalExitDirectiveV2: {directive_id}")
    return _directive_from_row(row)


def _directive_from_row(row: sqlite3.Row) -> OperationalExitDirectiveV2:
    directive = OperationalExitDirectiveV2.from_canonical_dict(
        _object_json(str(row["directive_json"]))
    )
    assessment = ExitAssessment.from_canonical_dict(
        _object_json(str(row["exit_assessment_json"]))
    )
    if (
        row["directive_id"] != str(directive.directive_id)
        or row["content_hash"] != directive.content_hash
        or row["exit_assessment_id"] != str(directive.exit_assessment_id)
        or row["thesis_health_observation_id"]
        != str(directive.thesis_health_observation_id)
        or row["composite_manifest_id"]
        != str(directive.composite_manifest_id)
        or row["created_at"] != directive.created_at.isoformat()
        or assessment.assessment_id != directive.exit_assessment_id
        or canonical_hash(assessment.to_canonical_dict())
        != directive.exit_assessment_hash
    ):
        raise ValueError("OperationalExitDirectiveV2 projection is invalid")
    return directive


def _load_attempt(
    connection: sqlite3.Connection, attempt_id: ArtifactId
) -> tuple[RiskReductionConfirmationAttempt, PositionSnapshot]:
    row = connection.execute(
        "SELECT * FROM risk_reduction_confirmation_attempts WHERE attempt_id = ?",
        (str(attempt_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown RiskReductionConfirmationAttempt: {attempt_id}")
    attempt = RiskReductionConfirmationAttempt.from_canonical_dict(
        _object_json(str(row["attempt_json"]))
    )
    position = PositionSnapshot.from_canonical_dict(
        _object_json(str(row["current_position_json"]))
    )
    if (
        row["attempt_id"] != str(attempt.attempt_id)
        or row["content_hash"] != attempt.content_hash
        or row["state"] != attempt.state.value
        or row["risk_reducing_decision_id"]
        != str(attempt.risk_reducing_decision_id)
        or row["exit_directive_id"] != str(attempt.exit_directive_id)
        or row["manual_trade_id"]
        != (
            str(attempt.manual_trade_id)
            if attempt.manual_trade_id is not None
            else None
        )
        or row["created_at"] != attempt.confirmed_at.isoformat()
        or position.snapshot_id != attempt.current_position_snapshot_id
        or canonical_hash(position.to_canonical_dict())
        != attempt.current_position_snapshot_hash
    ):
        raise ValueError("RiskReductionConfirmationAttempt projection is invalid")
    return attempt, position


_H4_5_COLUMNS = {
    "manual_trade_records": (
        "manual_trade_id",
        "authority_route",
        "risk_decision_id",
        "risk_reducing_decision_id",
        "risk_reduction_confirmation_id",
        "account_id",
        "symbol",
        "side",
        "state",
        "filled_quantity",
        "aggregate_json",
        "version",
    ),
    "operational_exit_directives": (
        "directive_id",
        "content_hash",
        "exit_assessment_id",
        "risk_reducing_decision_id",
        "thesis_health_observation_id",
        "composite_manifest_id",
        "directive_json",
        "exit_assessment_json",
        "created_at",
    ),
    "risk_reduction_confirmation_attempts": (
        "attempt_id",
        "content_hash",
        "state",
        "risk_reducing_decision_id",
        "exit_directive_id",
        "manual_trade_id",
        "attempt_json",
        "policy_json",
        "recheck_observation_json",
        "current_position_json",
        "trading_calendar_json",
        "symbol_trading_status_json",
        "created_at",
    ),
    "risk_reduction_confirmation_commands": (
        "idempotency_key",
        "command_hash",
        "risk_reducing_decision_id",
        "attempt_id",
        "manual_trade_id",
        "created_at",
    ),
    "risk_reducing_manual_trade_bindings": (
        "manual_trade_id",
        "position_book_id",
        "opportunity_id",
        "thesis_id",
        "symbol",
        "risk_reducing_decision_id",
        "risk_reducing_decision_hash",
        "confirmation_attempt_id",
        "confirmation_attempt_hash",
        "source_position_snapshot_id",
        "source_position_snapshot_hash",
        "source_position_snapshot_version",
        "target_quantity",
        "order_quantity",
        "created_at",
    ),
}

_H4_5_APPEND_ONLY_TRIGGERS = {
    "operational_exit_directives_no_update": (
        "operational_exit_directives",
        "update",
        "operational exit directives are append-only",
    ),
    "operational_exit_directives_no_delete": (
        "operational_exit_directives",
        "delete",
        "operational exit directives are append-only",
    ),
    "risk_reduction_confirmation_attempts_no_update": (
        "risk_reduction_confirmation_attempts",
        "update",
        "risk reduction confirmation attempts are append-only",
    ),
    "risk_reduction_confirmation_attempts_no_delete": (
        "risk_reduction_confirmation_attempts",
        "delete",
        "risk reduction confirmation attempts are append-only",
    ),
    "risk_reduction_confirmation_commands_no_update": (
        "risk_reduction_confirmation_commands",
        "update",
        "risk reduction confirmation commands are append-only",
    ),
    "risk_reduction_confirmation_commands_no_delete": (
        "risk_reduction_confirmation_commands",
        "delete",
        "risk reduction confirmation commands are append-only",
    ),
    "risk_reducing_manual_trade_bindings_no_update": (
        "risk_reducing_manual_trade_bindings",
        "update",
        "risk reducing manual trade bindings are append-only",
    ),
    "risk_reducing_manual_trade_bindings_no_delete": (
        "risk_reducing_manual_trade_bindings",
        "delete",
        "risk reducing manual trade bindings are append-only",
    ),
}

_H4_5_ROUTE_GUARDS = {
    "traceable_manual_trade_binding_route_guard": (
        "traceable_manual_trade_bindings",
        "'increasing'",
        "risk_reducing_manual_trade_bindings",
    ),
    "risk_reducing_manual_trade_binding_route_guard": (
        "risk_reducing_manual_trade_bindings",
        "'reducing'",
        "traceable_manual_trade_bindings",
    ),
}


def _validate_h4_5_schema(connection: sqlite3.Connection) -> None:
    if connection.execute(
        "SELECT 1 FROM pdl_schema_migrations WHERE version = 10"
    ).fetchone() is None:
        raise ValueError("H4.5 migration 010 is not applied")
    for table, expected_columns in _H4_5_COLUMNS.items():
        columns = tuple(
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info('{table}')")
        )
        if columns != expected_columns:
            raise ValueError(f"H4.5 table schema mismatch: {table}")
    manual_sql = _table_sql(connection, "manual_trade_records")
    if any(
        token not in manual_sql
        for token in (
            "authority_route='increasing'",
            "risk_decision_idisnotnull",
            "risk_reducing_decision_idisnull",
            "authority_route='reducing'",
            "risk_decision_idisnull",
            "risk_reducing_decision_idisnotnull",
            "risk_reduction_confirmation_idisnotnull",
        )
    ):
        raise ValueError("H4.5 manual trade route CHECK is missing")
    index = connection.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'index'
          AND name = 'one_confirmed_intent_per_reducing_decision'
        """
    ).fetchone()
    if index is None or "wherestate='confirmed_intent'" not in _compact_sql(
        str(index["sql"])
    ):
        raise ValueError("H4.5 confirmed-intent uniqueness is missing")
    triggers = {
        str(row["name"]): _compact_sql(str(row["sql"]))
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    for name, (table, operation, message) in _H4_5_APPEND_ONLY_TRIGGERS.items():
        actual = triggers.get(name, "")
        required = (
            f"before{operation}on{table}",
            f"raise(abort,'{message.replace(' ', '')}')",
        )
        if any(token not in actual for token in required):
            raise ValueError(f"H4.5 append-only trigger mismatch: {name}")
    for name, (table, route, opposite_table) in _H4_5_ROUTE_GUARDS.items():
        actual = triggers.get(name, "")
        if any(
            token not in actual
            for token in (
                f"beforeinserton{table}",
                "selectauthority_routefrommanual_trade_records",
                f"!={route}",
                f"from{opposite_table}",
                "raise(abort,'manualtradeauthorityroutebindingconflict')",
            )
        ):
            raise ValueError(f"H4.5 route guard mismatch: {name}")
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise ValueError("H4.5 database contains foreign-key violations")


def _table_sql(connection: sqlite3.Connection, table: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if row is None:
        raise ValueError(f"H4.5 table schema mismatch: {table}")
    return _compact_sql(str(row["sql"]))


def _compact_sql(value: str) -> str:
    return "".join(value.lower().split()).replace('"', "").replace("`", "")
