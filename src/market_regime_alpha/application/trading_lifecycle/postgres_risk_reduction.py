"""Application-layer native PostgreSQL H4.5 authority unit of work."""

from __future__ import annotations

from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalCompositionStatus,
)
from market_regime_alpha.application.operational_research.composite_artifact import (
    VerifiedCompositeOperationalManifest,
)
from market_regime_alpha.application.operational_research.postgres_composite_repository import (
    PostgresCompositeOperationalRepository,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    ManualTradeId,
    PositionSnapshotId,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.decision.opportunity import (
    OpportunityState,
    TradingOpportunity,
)
from market_regime_alpha.decision.postgres_repository import (
    PostgresDecisionLifecycleRepository,
)
from market_regime_alpha.decision.thesis import ThesisState, TradingThesis
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
    ManualOrderState,
    ManualTradeAuthorityRoute,
    ManualTradeRecord,
    TradeSide,
)
from market_regime_alpha.execution.position_book import (
    PositionBook,
    PositionBookState,
)
from market_regime_alpha.execution.risk_reduction import (
    OperationalExitDirectiveV2,
    RiskReductionConfirmationAttempt,
    RiskReductionConfirmationCommand,
    RiskReductionConfirmationResult,
    RiskReductionConfirmationState,
)
from market_regime_alpha.execution.postgres_manual_repository import (
    insert_manual_trade_event as _insert_trade_event,
    load_manual_trade_projection as _load_trade,
    restore_manual_execution_json as _object_json,
    serialize_manual_execution_json as _json,
)
from market_regime_alpha.execution.postgres_traceability import (
    PostgresTraceableManualExecutionRepository,
)
from market_regime_alpha.portfolio.risk_routes import (
    RiskChangeKind,
    RiskReducingDecision,
    RiskReducingDecisionState,
    RiskReducingExecutionGate,
    VerifiedRiskReducingDecisionBundle,
)
from market_regime_alpha.portfolio.postgres_risk_routes import (
    PostgresRiskRouteRepository,
)
from market_regime_alpha.position.assessment import ExitAssessment
from market_regime_alpha.position.authority import (
    PositionProjector,
    PositionSnapshot,
    SymbolTradingSessionStatus,
)
from market_regime_alpha.position.postgres_thesis_health import (
    PostgresThesisHealthRepository,
)
from market_regime_alpha.position.thesis_health import (
    VerifiedThesisHealthBundle,
)
from market_regime_alpha.application.trading_lifecycle.risk_reduction_lineage import (
    build_operational_exit_directive_v2,
    validate_h5_h6_operational_lineage,
)
from market_regime_alpha.application.trading_lifecycle.risk_reduction_confirmation import (
    RiskReductionConfirmationIdempotencyConflict,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.native_repository import (
    PostgresConnection,
    acquire_scope_lock,
    aware_datetime,
)


class PostgresRiskReductionManualIntentRepository(
    PostgresTraceableManualExecutionRepository
):
    """Native PostgreSQL lifecycle unit of work for atomic H4.5 confirmation."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        super().__init__(factory)
        self._risk_routes = PostgresRiskRouteRepository(factory)
        self._thesis_health = PostgresThesisHealthRepository(factory)
        self._decisions = PostgresDecisionLifecycleRepository(factory)
        self._composite = PostgresCompositeOperationalRepository(factory)

    def get_manual_trade(self, trade_id: ManualTradeId) -> ManualTradeRecord:
        """Reload one observed manual intent without creating execution state."""

        if not isinstance(trade_id, ManualTradeId):
            raise TypeError("trade_id must be a ManualTradeId")
        with self._connect() as connection:
            return _load_trade(connection, trade_id)

    def save_operational_exit_directive(
        self,
        directive: OperationalExitDirectiveV2,
        *,
        exit_assessment: ExitAssessment,
        risk_reducing_decision_id: ArtifactId,
    ) -> OperationalExitDirectiveV2:
        with self._connect() as connection:
            try:
                acquire_scope_lock(
                    connection,
                    namespace="operational-exit-directive",
                    identity=str(directive.directive_id),
                )
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
                    WHERE directive_id = %s OR content_hash = %s
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
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                            directive.created_at,
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

    def get_confirmed_risk_reduction(
        self, risk_reducing_decision_id: ArtifactId
    ) -> RiskReductionConfirmationResult | None:
        """Read the unique durable H4.5 confirmation for one H4 decision.

        This query is the observation seam used by resumable orchestration.  It
        deliberately does not run the confirmation service and therefore can
        neither create a ManualTrade nor mutate Fill authority.
        """

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT attempt_id
                FROM risk_reduction_confirmation_attempts
                WHERE risk_reducing_decision_id = %s
                  AND state = 'CONFIRMED_INTENT'
                ORDER BY created_at, attempt_id
                """,
                (str(risk_reducing_decision_id),),
            ).fetchall()
            if not rows:
                return None
            if len(rows) != 1:
                raise ValueError(
                    "risk-reducing decision has ambiguous confirmed intent"
                )
            attempt, current_position = _load_attempt(
                connection, ArtifactId(str(rows[0]["attempt_id"]))
            )
            if (
                attempt.state
                is not RiskReductionConfirmationState.CONFIRMED_INTENT
                or attempt.risk_reducing_decision_id
                != risk_reducing_decision_id
                or attempt.manual_trade_id is None
            ):
                raise ValueError("confirmed H4.5 projection is inconsistent")
            trade = _load_trade(connection, attempt.manual_trade_id)
            self._validate_loaded_trade(connection, trade)
            if (
                trade.manual_trade_id != attempt.manual_trade_id
                or trade.risk_reducing_decision_id
                != attempt.risk_reducing_decision_id
                or trade.risk_reducing_decision_hash
                != attempt.risk_reducing_decision_hash
                or trade.risk_reduction_confirmation_id != attempt.attempt_id
                or trade.risk_reduction_confirmation_hash
                != attempt.content_hash
            ):
                raise ValueError("confirmed H4.5 ManualTrade lineage is inconsistent")
            return RiskReductionConfirmationResult(
                attempt=attempt,
                current_position=current_position,
                manual_trade=trade,
                outcome="MANUAL_INTENT_CREATED",
            )

    def get_fill_derived_position(
        self,
        risk_reducing_decision_id: ArtifactId,
        *,
        position_snapshot_id: PositionSnapshotId | None = None,
    ) -> PositionSnapshot | None:
        """Load a current or historical Fill-derived Position projection.

        The confirmed H4.5 attempt stores the exact TradingCalendar and symbol
        session evidence used by the manual intent.  Historical snapshots are
        replayed from every append-only Fill prefix, so a settled lifecycle
        reference remains loadable after later Fill records are appended.
        """

        result = self.get_confirmed_risk_reduction(risk_reducing_decision_id)
        if result is None:
            return None
        trade = result.manual_trade
        if trade is None or trade.position_book_id is None:
            raise ValueError("confirmed H4.5 result has no PositionBook binding")
        reducing_fills = self.fills_for_trade(trade.manual_trade_id)
        if not reducing_fills:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT trading_calendar_json, symbol_trading_status_json
                FROM risk_reduction_confirmation_attempts
                WHERE attempt_id = %s AND state = 'CONFIRMED_INTENT'
                """,
                (str(result.attempt.attempt_id),),
            ).fetchone()
            if row is None:
                raise ValueError("confirmed H4.5 Reader evidence is missing")
        calendar = TradingCalendarArtifact.from_canonical_dict(
            _object_json(str(row["trading_calendar_json"]))
        )
        status_payload = _object_json(str(row["symbol_trading_status_json"]))
        status_items = status_payload.get("items")
        if not isinstance(status_items, list) or any(
            not isinstance(item, dict) for item in status_items
        ):
            raise ValueError("stored H4.5 symbol status evidence is invalid")
        statuses = tuple(
            SymbolTradingSessionStatus.from_canonical_dict(item)
            for item in status_items
        )
        book = self.get_position_book(trade.position_book_id)
        trades = self.trades_for_book(book.position_book_id)
        fills = self.fills_for_book(book.position_book_id)
        prefixes = (
            (fills,)
            if position_snapshot_id is None
            else tuple(fills[:index] for index in range(1, len(fills) + 1))
        )
        reducing_fill_ids = {item.fill_id for item in reducing_fills}
        for prefix in prefixes:
            if not reducing_fill_ids.intersection(
                item.fill_id for item in prefix
            ):
                continue
            position_as_of = max(
                result.attempt.confirmed_at,
                *(item.recorded_at for item in prefix),
            )
            position = PositionProjector().project_book_t_plus_one(
                book=book,
                trades=trades,
                fills=prefix,
                calendar=calendar,
                symbol_session_statuses=statuses,
                as_of=position_as_of,
            )
            if (
                position_snapshot_id is None
                or position.snapshot_id == position_snapshot_id
            ):
                return position
        raise KeyError(f"unknown Fill-derived PositionSnapshot: {position_snapshot_id}")

    def confirm_risk_reduction(
        self, command: RiskReductionConfirmationCommand
    ) -> RiskReductionConfirmationResult:
        with self._connect() as connection:
            try:
                acquire_scope_lock(
                    connection,
                    namespace="risk-reduction-confirmation",
                    identity=str(command.risk_reducing_decision_id),
                )
                replay = _resolve_confirmation_command(connection, command)
                if replay is not None:
                    connection.commit()
                    return replay

                directive_row = connection.execute(
                    """
                    SELECT * FROM operational_exit_directives
                    WHERE directive_id = %s
                    """,
                    (str(command.exit_directive_id),),
                ).fetchone()
                directive_id_resolved = directive_row is not None
                if directive_row is None:
                    risk_bundle = (
                        self._risk_routes.get_verified_reducing_decision_bundle(
                            command.risk_reducing_decision_id
                        )
                    )
                    fallback_rows = connection.execute(
                        """
                        SELECT * FROM operational_exit_directives
                        WHERE risk_reducing_decision_id = %s
                        ORDER BY created_at, directive_id
                        """,
                        (str(risk_bundle.decision.decision_id),),
                    ).fetchall()
                    if len(fallback_rows) != 1:
                        raise KeyError(
                            "unknown or ambiguous OperationalExitDirectiveV2: "
                            f"{command.exit_directive_id}"
                        )
                    directive_row = fallback_rows[0]
                else:
                    risk_bundle = (
                        self._risk_routes.get_verified_reducing_decision_bundle(
                            ArtifactId(
                                str(directive_row["risk_reducing_decision_id"])
                            )
                        )
                    )
                directive = _directive_from_row(directive_row)
                decision = risk_bundle.decision
                decision_reference_matches = (
                    decision.decision_id == command.risk_reducing_decision_id
                    and decision.content_hash
                    == command.risk_reducing_decision_hash
                )
                directive_reference_matches = (
                    directive_id_resolved
                    and directive.content_hash == command.exit_directive_hash
                    and directive_row["risk_reducing_decision_id"]
                    == str(decision.decision_id)
                )
                decision_is_latest_same_scope = _is_latest_same_scope_decision(
                    connection,
                    decision,
                )

                book = self.get_position_book(decision.position_book_id)
                trades = self.trades_for_book(book.position_book_id)
                fills = self.fills_for_book(book.position_book_id)
                source_position = risk_bundle.position
                current_fill_ids = tuple(
                    item.fill_id
                    for item in sorted(
                        fills,
                        key=lambda item: (item.recorded_at, str(item.fill_id)),
                    )
                )
                current_status_ids = tuple(
                    sorted(
                        {
                            item.status_id
                            for item in command.symbol_trading_statuses
                            if item.availability_time <= command.confirmed_at
                        },
                        key=str,
                    )
                )
                position_authority_changed = (
                    current_fill_ids != source_position.source_fill_ids
                    or current_status_ids
                    != source_position.source_trading_status_ids
                    or command.trading_calendar.artifact_id
                    != source_position.calendar_artifact_id
                    or command.trading_calendar.content_hash
                    != source_position.calendar_content_hash
                )
                position_as_of = (
                    command.confirmed_at
                    if position_authority_changed
                    else source_position.as_of
                )
                current_position = PositionProjector().project_book_t_plus_one(
                    book=book,
                    trades=trades,
                    fills=fills,
                    calendar=command.trading_calendar,
                    symbol_session_statuses=command.symbol_trading_statuses,
                    as_of=position_as_of,
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
                    decision_reference_matches=decision_reference_matches,
                    directive_reference_matches=directive_reference_matches,
                    decision_is_latest_same_scope=(
                        decision_is_latest_same_scope
                    ),
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
                    WHERE risk_reducing_decision_id = %s
                      AND state = 'CONFIRMED_INTENT'
                    """,
                    (str(decision.decision_id),),
                ).fetchone()
                if confirmed is not None:
                    result = _persist_failed_confirmation(
                        connection,
                        command=command,
                        directive=directive,
                        risk_bundle=risk_bundle,
                        current_position=current_position,
                        state=(
                            RiskReductionConfirmationState.BLOCKED_ON_RECHECK
                        ),
                        reason_codes=(
                            "RISK_REDUCING_DECISION_ALREADY_CONFIRMED",
                        ),
                    )
                    connection.commit()
                    return result
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
        risk_bundle: VerifiedRiskReducingDecisionBundle,
        current_position: PositionSnapshot,
        book: PositionBook,
        thesis: TradingThesis,
        opportunity: TradingOpportunity,
        health_bundle: VerifiedThesisHealthBundle,
        composite: VerifiedCompositeOperationalManifest,
        decision_reference_matches: bool,
        directive_reference_matches: bool,
        decision_is_latest_same_scope: bool,
    ) -> tuple[RiskReductionConfirmationState, tuple[str, ...]] | None:
        decision = risk_bundle.decision
        source = risk_bundle.position
        health = health_bundle.observation
        manifest = composite.manifest
        if not decision_reference_matches:
            return (
                RiskReductionConfirmationState.DATA_INSUFFICIENT,
                ("RISK_REDUCING_DECISION_HASH_MISMATCH",),
            )
        if not directive_reference_matches:
            return (
                RiskReductionConfirmationState.DATA_INSUFFICIENT,
                ("OPERATIONAL_EXIT_DIRECTIVE_REFERENCE_MISMATCH",),
            )
        if not decision_is_latest_same_scope:
            return (
                RiskReductionConfirmationState.BLOCKED_ON_RECHECK,
                ("RISK_REDUCING_DECISION_SUPERSEDED",),
            )
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
        position_age = (command.confirmed_at - source.as_of).total_seconds()
        if position_age < 0.0:
            return (
                RiskReductionConfirmationState.DATA_INSUFFICIENT,
                ("CONFIRMATION_PRECEDES_SOURCE_POSITION",),
            )
        if position_age > command.confirmation_policy.maximum_position_age_seconds:
            return (
                RiskReductionConfirmationState.EXPIRED,
                ("SOURCE_POSITION_EXPIRED",),
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
    connection: PostgresConnection,
    *,
    command: RiskReductionConfirmationCommand,
    directive: OperationalExitDirectiveV2,
    risk_bundle: VerifiedRiskReducingDecisionBundle,
    current_position: PositionSnapshot,
    book: PositionBook,
    opportunity: TradingOpportunity,
    thesis: TradingThesis,
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
        ) VALUES (%s, 'REDUCING', NULL, %s, %s, %s, %s, 'SELL', %s, 0, %s, 0)
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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            command.confirmed_at,
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
    connection: PostgresConnection,
    *,
    command: RiskReductionConfirmationCommand,
    directive: OperationalExitDirectiveV2,
    risk_bundle: VerifiedRiskReducingDecisionBundle,
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
    risk_bundle: VerifiedRiskReducingDecisionBundle,
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
    connection: PostgresConnection,
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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            command.confirmed_at,
        ),
    )


def _insert_confirmation_command(
    connection: PostgresConnection,
    command: RiskReductionConfirmationCommand,
    attempt: RiskReductionConfirmationAttempt,
    trade: ManualTradeRecord | None,
) -> None:
    connection.execute(
        """
        INSERT INTO risk_reduction_confirmation_commands(
            idempotency_key, command_hash, risk_reducing_decision_id,
            attempt_id, manual_trade_id, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            command.idempotency_key,
            command.command_hash,
            str(attempt.risk_reducing_decision_id),
            str(attempt.attempt_id),
            str(trade.manual_trade_id) if trade is not None else None,
            command.confirmed_at,
        ),
    )


def _resolve_confirmation_command(
    connection: PostgresConnection,
    command: RiskReductionConfirmationCommand,
) -> RiskReductionConfirmationResult | None:
    row = connection.execute(
        """
        SELECT command_hash, attempt_id, manual_trade_id
        FROM risk_reduction_confirmation_commands
        WHERE idempotency_key = %s
        """,
        (command.idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if row["command_hash"] != command.command_hash:
        raise RiskReductionConfirmationIdempotencyConflict(
            "idempotency key reused for different H4.5 command"
        )
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


def _is_latest_same_scope_decision(
    connection: PostgresConnection,
    decision: RiskReducingDecision,
) -> bool:
    """Resolve same-book, same-Thesis, same-symbol supersession deterministically."""

    rows = connection.execute(
        """
        SELECT decision_id, position_book_id, thesis_id, decision_json,
               assessed_at AS created_at
        FROM risk_reducing_decisions
        WHERE position_book_id = %s AND thesis_id = %s
        ORDER BY created_at, decision_id
        """,
        (str(decision.position_book_id), str(decision.thesis_id)),
    ).fetchall()
    same_scope: list[RiskReducingDecision] = []
    for row in rows:
        candidate = RiskReducingDecision.from_canonical_dict(
            _object_json(str(row["decision_json"]))
        )
        if (
            row["decision_id"] != str(candidate.decision_id)
            or row["position_book_id"] != str(candidate.position_book_id)
            or row["thesis_id"] != str(candidate.thesis_id)
            or aware_datetime(row["created_at"], label="created_at")
            != candidate.assessed_at
        ):
            raise ValueError("risk-reducing decision scope projection is invalid")
        if candidate.symbol == decision.symbol:
            same_scope.append(candidate)
    if not any(item.decision_id == decision.decision_id for item in same_scope):
        raise ValueError("risk-reducing decision is missing from its durable scope")
    latest = max(
        same_scope,
        key=lambda item: (item.assessed_at, str(item.decision_id)),
    )
    return latest.decision_id == decision.decision_id


def _load_directive(
    connection: PostgresConnection, directive_id: ArtifactId
) -> OperationalExitDirectiveV2:
    row = connection.execute(
        "SELECT * FROM operational_exit_directives WHERE directive_id = %s",
        (str(directive_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown OperationalExitDirectiveV2: {directive_id}")
    return _directive_from_row(row)


def _directive_from_row(row: dict[str, object]) -> OperationalExitDirectiveV2:
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
        or aware_datetime(row["created_at"], label="created_at")
        != directive.created_at
        or assessment.assessment_id != directive.exit_assessment_id
        or canonical_hash(assessment.to_canonical_dict())
        != directive.exit_assessment_hash
    ):
        raise ValueError("OperationalExitDirectiveV2 projection is invalid")
    return directive


def _load_attempt(
    connection: PostgresConnection, attempt_id: ArtifactId
) -> tuple[RiskReductionConfirmationAttempt, PositionSnapshot]:
    row = connection.execute(
        "SELECT * FROM risk_reduction_confirmation_attempts WHERE attempt_id = %s",
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
        or aware_datetime(row["created_at"], label="created_at")
        != attempt.confirmed_at
        or position.snapshot_id != attempt.current_position_snapshot_id
        or canonical_hash(position.to_canonical_dict())
        != attempt.current_position_snapshot_hash
    ):
        raise ValueError("RiskReductionConfirmationAttempt projection is invalid")
    return attempt, position



__all__ = ["PostgresRiskReductionManualIntentRepository"]
