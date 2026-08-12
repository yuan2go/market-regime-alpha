"""Historical session adapter that reloads existing PostgreSQL fact owners."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    ContinuousResearchNotFound,
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalResearchConflict,
)
from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_session.contracts import (
    ResearchDecisionSessionRequest,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchSessionStage,
    SessionStageComputation,
    SessionStageStatus,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    FormalProtocolConflict,
    load_formal_protocol_owner,
)
from market_regime_alpha.application.shadow_research.postgres_repository import (
    PostgresShadowResearchRepository,
)
from market_regime_alpha.application.strategy_shadow.postgres_performance import (
    PostgresPortfolioPerformanceRepository,
)
from market_regime_alpha.application.strategy_shadow.observation_builder import (
    ObservationKind,
)
from market_regime_alpha.application.strategy_shadow.postgres_observations import (
    PostgresShadowObservationRepository,
)
from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import (
    PostgresStrategyShadowRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from market_regime_alpha.universe.runtime_scope import RuntimeScopeReceipt


StageHandler = Callable[
    [ResearchDecisionSessionRequest, tuple[ValidationArtifactReference, ...]],
    SessionStageComputation,
]


class PostgresHistoricalSessionOwner:
    """Map each shared stage to immutable facts already owned by PostgreSQL."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        self._scope = PostgresRuntimeScopeRepository(
            factory,
            apply_migrations=apply_migrations,
        )
        self._continuous = PostgresContinuousResearchJournal(
            factory,
            apply_migrations=False,
        )
        self._decisions = PostgresShadowResearchRepository(
            factory,
            apply_migrations=False,
        )
        self._strategy = PostgresStrategyShadowRepository(
            factory,
            apply_migrations=False,
        )
        self._portfolio = PostgresShadowPortfolioRepository(
            factory,
            apply_migrations=False,
        )
        self._outcomes = PostgresTargetOutcomeRepository(
            factory,
            apply_migrations=False,
        )
        self._performance = PostgresPortfolioPerformanceRepository(
            factory,
            apply_migrations=False,
        )
        self._observations = PostgresShadowObservationRepository(
            factory,
            apply_migrations=False,
        )

    def compute_stage(
        self,
        *,
        request: ResearchDecisionSessionRequest,
        stage: ResearchSessionStage,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        handlers: dict[ResearchSessionStage, StageHandler] = {
            ResearchSessionStage.SCOPE: self._scope_stage,
            ResearchSessionStage.DECISION: self._decision_stage,
            ResearchSessionStage.STRATEGY: self._strategy_stage,
            ResearchSessionStage.PORTFOLIO: self._portfolio_stage,
            ResearchSessionStage.OUTCOME: self._outcome_stage,
            ResearchSessionStage.PERFORMANCE: self._performance_stage,
        }
        return handlers[stage](request, input_references)

    def _scope_stage(
        self,
        request: ResearchDecisionSessionRequest,
        inputs: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        try:
            receipt = self._scope.resolve(
                policy_id=request.runtime_scope_policy_id,
                as_of=request.decision_time,
                known_at=request.materialized_at,
            )
        except KeyError:
            return _blocked(request, inputs, "HISTORICAL_RUNTIME_SCOPE_MISSING")
        if receipt.policy_hash != request.runtime_scope_policy_hash:
            raise HistoricalResearchConflict("Historical Runtime Scope Policy drift")
        return _complete(
            inputs,
            (
                ValidationArtifactReference(
                    "RUNTIME_SCOPE", receipt.scope_id, receipt.scope_hash
                ),
            ),
            receipt.built_at,
            "HISTORICAL_RUNTIME_SCOPE_RELOADED",
        )

    def _decision_stage(
        self,
        request: ResearchDecisionSessionRequest,
        inputs: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        scope_reference = _single(inputs, "RUNTIME_SCOPE")
        scope = self._scope.get(scope_reference.artifact_id)
        if scope.scope_hash != scope_reference.content_hash:
            raise HistoricalResearchConflict("Historical Runtime Scope hash drift")
        rows = self._rows(
            """
            SELECT decision.decision_id, decision.run_id
            FROM shadow_research_decision AS decision
            JOIN shadow_research_session AS session
              ON session.session_id = decision.session_id
            WHERE session.trading_date = %s
              AND decision.decision_time <= %s
              AND decision.created_at <= %s
            ORDER BY decision.decision_time DESC, decision.decision_id
            """,
            (request.trading_date, request.decision_time, request.materialized_at),
        )
        if not rows:
            return _blocked(request, inputs, "HISTORICAL_DECISION_OWNER_MISSING")
        matching_decisions = []
        for row in rows:
            try:
                continuous = self._continuous.get_run(
                    ArtifactId(str(row[1]))
                ).command
            except ContinuousResearchNotFound as error:
                raise HistoricalResearchConflict(
                    "Historical Shadow Decision parent run is missing"
                ) from error
            if _continuous_command_matches(
                continuous, request, scope
            ) and self._formal_experiment_matches(request):
                matching_decisions.append(
                    self._decisions.get_decision(ArtifactId(str(row[0])))
                )
        if not matching_decisions:
            return _blocked(
                request,
                inputs,
                "HISTORICAL_DECISION_OWNER_INCOMPATIBLE",
            )
        if len(matching_decisions) != 1:
            raise HistoricalResearchConflict(
                "Historical Decision owner is ambiguous for exact session inputs"
            )
        decision = matching_decisions[0]
        return _complete(
            inputs,
            (
                ValidationArtifactReference(
                    "SHADOW_DECISION", decision.decision_id, decision.decision_hash
                ),
            ),
            decision.decision_frozen_at,
            "HISTORICAL_DECISION_OWNER_RELOADED",
        )

    def _strategy_stage(
        self,
        request: ResearchDecisionSessionRequest,
        inputs: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        decision = _single(inputs, "SHADOW_DECISION")
        configured_policy = _required_configuration(
            request, "STRATEGY_SHADOW_POLICY"
        )
        rows = self._rows(
            """
            SELECT DISTINCT session.session_id
            FROM strategy_shadow_session AS session
            JOIN strategy_shadow_session_lineage_binding AS decision_binding
              ON decision_binding.session_id = session.session_id
             AND decision_binding.artifact_kind = 'SHADOW_DECISION'
             AND decision_binding.artifact_id = %s
             AND decision_binding.content_hash = %s
            WHERE session.trading_date = %s
              AND session.lineage_status = 'EXACT_V1'
              AND session.updated_at <= %s
              AND (
                    EXISTS (
                        SELECT 1
                        FROM strategy_shadow_session_lineage_binding AS policy_binding
                        WHERE policy_binding.session_id = session.session_id
                          AND policy_binding.artifact_kind = %s
                          AND policy_binding.artifact_id = %s
                          AND policy_binding.content_hash = %s
                    )
              )
            ORDER BY session.session_id
            """,
            (
                str(decision.artifact_id),
                decision.content_hash,
                request.trading_date,
                request.materialized_at,
                "STRATEGY_SHADOW_POLICY",
                str(configured_policy.artifact_id),
                configured_policy.content_hash,
            ),
        )
        sessions = tuple(
            self._strategy.get(ArtifactId(str(row[0]))) for row in rows
        )
        if not sessions:
            return _blocked(request, inputs, "HISTORICAL_STRATEGY_OWNER_MISSING")
        return _complete(
            inputs,
            tuple(
                ValidationArtifactReference(
                    "STRATEGY_SHADOW_SESSION", item.session_id, item.session_hash
                )
                for item in sessions
            ),
            max(item.updated_at for item in sessions),
            "HISTORICAL_STRATEGY_OWNER_RELOADED",
        )

    def _portfolio_stage(
        self,
        request: ResearchDecisionSessionRequest,
        inputs: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        strategy_references = tuple(
            item
            for item in inputs
            if item.artifact_kind == "STRATEGY_SHADOW_SESSION"
        )
        if not strategy_references:
            raise HistoricalResearchConflict(
                "Historical Portfolio predecessor Strategy is missing"
            )
        configured_policy = _required_configuration(
            request, "SHADOW_PORTFOLIO_POLICY"
        )
        strategy_by_id = {
            str(item.artifact_id): item for item in strategy_references
        }
        rows = self._rows(
            """
            SELECT state.state_id, portfolio.portfolio_id,
                   portfolio.portfolio_hash, portfolio.strategy_session_id,
                   portfolio.strategy_session_hash, portfolio.policy_id,
                   portfolio.policy_hash
            FROM strategy_shadow_portfolio AS portfolio
            JOIN strategy_shadow_portfolio_day AS state
              ON state.portfolio_id = portfolio.portfolio_id
            WHERE portfolio.lineage_status = 'EXACT_V1'
              AND portfolio.strategy_session_id = ANY(%s::text[])
              AND state.recorded_at <= %s
              AND (
                    portfolio.policy_id = %s
                    AND portfolio.policy_hash = %s
              )
            ORDER BY portfolio.portfolio_id, state.trading_date, state.state_id
            """,
            (
                list(strategy_by_id),
                request.materialized_at,
                str(configured_policy.artifact_id),
                configured_policy.content_hash,
            ),
        )
        states = []
        portfolio_ids_by_strategy: dict[str, set[str]] = {
            strategy_id: set() for strategy_id in strategy_by_id
        }
        for row in rows:
            strategy_reference = strategy_by_id.get(str(row[3]))
            if strategy_reference is None or (
                str(row[4]) != strategy_reference.content_hash
            ):
                raise HistoricalResearchConflict(
                    "Historical Portfolio Strategy identity drift"
                )
            policy_reference = ValidationArtifactReference(
                "SHADOW_PORTFOLIO_POLICY",
                ArtifactId(str(row[5])),
                str(row[6]),
            )
            if policy_reference != configured_policy:
                raise HistoricalResearchConflict(
                    "Historical Portfolio Policy identity drift"
                )
            _policy, portfolio = self._portfolio.get_portfolio(
                ArtifactId(str(row[1]))
            )
            if (
                portfolio.portfolio_hash != str(row[2])
                or portfolio.strategy_reference != strategy_reference
            ):
                raise HistoricalResearchConflict(
                    "Historical Portfolio owner identity drift"
                )
            state = self._portfolio.get_state(ArtifactId(str(row[0])))
            receipt = self._portfolio_receipt(
                request=request,
                state=state,
                decision_reference=_single(inputs, "SHADOW_DECISION"),
            )
            if not {
                portfolio.research_reference,
                portfolio.candidate_reference,
            }.issubset(set(receipt.source_references)):
                raise HistoricalResearchConflict(
                    "Historical Portfolio source lineage drift"
                )
            states.append(state)
            portfolio_ids_by_strategy[str(row[3])].add(str(portfolio.portfolio_id))
        if not states:
            return _blocked(request, inputs, "HISTORICAL_PORTFOLIO_OWNER_MISSING")
        if any(
            len(portfolio_ids) != 1
            for portfolio_ids in portfolio_ids_by_strategy.values()
        ):
            raise HistoricalResearchConflict(
                "Historical Portfolio owner is not unique for exact Strategy and Policy"
            )
        return _complete(
            inputs,
            tuple(
                ValidationArtifactReference(
                    "SHADOW_PORTFOLIO_DAY_STATE", item.state_id, item.state_hash
                )
                for item in states
            ),
            max(item.recorded_at for item in states),
            "HISTORICAL_PORTFOLIO_OWNER_RELOADED",
        )

    def _outcome_stage(
        self,
        request: ResearchDecisionSessionRequest,
        inputs: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        decision = _single(inputs, "SHADOW_DECISION")
        outcome_references: set[ValidationArtifactReference] = set()
        for state_reference in (
            item
            for item in inputs
            if item.artifact_kind == "SHADOW_PORTFOLIO_DAY_STATE"
        ):
            state = self._portfolio.get_state(state_reference.artifact_id)
            if state.state_hash != state_reference.content_hash:
                raise HistoricalResearchConflict(
                    "Historical Portfolio State owner hash drift"
                )
            receipt = self._portfolio_receipt(
                request=request,
                state=state,
                decision_reference=decision,
            )
            outcome_references.update(
                item
                for item in receipt.source_references
                if item.artifact_kind == "TARGETED_SHADOW_OUTCOME"
            )
        outcomes = tuple(
            self._outcomes.get(item.artifact_id)
            for item in sorted(
                outcome_references,
                key=lambda item: (str(item.artifact_id), item.content_hash),
            )
        )
        if not outcomes:
            return _blocked(request, inputs, "HISTORICAL_OUTCOME_OWNER_MISSING")
        if any(
            item.target_protocol_reference != request.target_protocol_reference
            or not _same_reference(item.shadow_decision, decision)
            or item.created_at > request.materialized_at
            or ValidationArtifactReference(
                "TARGETED_SHADOW_OUTCOME",
                item.settlement_id,
                item.settlement_hash,
            ) not in outcome_references
            for item in outcomes
        ):
            raise HistoricalResearchConflict(
                "Historical Outcome Target Protocol drift"
            )
        return _complete(
            inputs,
            tuple(
                ValidationArtifactReference(
                    "TARGETED_SHADOW_OUTCOME",
                    item.settlement_id,
                    item.settlement_hash,
                )
                for item in outcomes
            ),
            max(item.created_at for item in outcomes),
            "HISTORICAL_OUTCOME_OWNER_RELOADED",
        )

    def _performance_stage(
        self,
        request: ResearchDecisionSessionRequest,
        inputs: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        state_references = tuple(
            item
            for item in inputs
            if item.artifact_kind == "SHADOW_PORTFOLIO_DAY_STATE"
        )
        states = tuple(
            self._portfolio.get_state(item.artifact_id)
            for item in state_references
        )
        state_by_id = {
            str(reference.artifact_id): (reference, state)
            for reference, state in zip(state_references, states, strict=True)
        }
        expected_states_by_portfolio: dict[
            str, set[ValidationArtifactReference]
        ] = {}
        for reference, state in zip(state_references, states, strict=True):
            expected_states_by_portfolio.setdefault(
                str(state.portfolio_reference.artifact_id),
                set(),
            ).add(reference)
        configured_policy = _required_configuration(
            request, "SHADOW_PERFORMANCE_POLICY"
        )
        rows = self._rows(
            """
            SELECT DISTINCT report.report_id
            FROM shadow_performance_report AS report
            JOIN shadow_performance_state_binding AS binding
              ON binding.report_id = report.report_id
            JOIN strategy_shadow_portfolio_day AS state
              ON state.state_id = binding.state_id
            WHERE binding.state_id = ANY(%s::text[])
              AND binding.state_hash = state.state_hash
              AND report.end_date = state.trading_date
              AND report.generated_at <= %s
              AND (
                    report.policy_id = %s AND report.policy_hash = %s
              )
            ORDER BY report.report_id
            """,
            (
                list(state_by_id),
                request.materialized_at,
                str(configured_policy.artifact_id),
                configured_policy.content_hash,
            ),
        ) if state_by_id else ()
        reports = []
        covered: set[str] = set()
        for row in rows:
            report = self._performance.get(ArtifactId(str(row[0])))
            matching = {
                str(reference.artifact_id)
                for reference in report.input_state_references
                if str(reference.artifact_id) in state_by_id
                and reference == state_by_id[str(reference.artifact_id)][0]
            }
            if not matching:
                raise HistoricalResearchConflict(
                    "Historical Performance State identity drift"
                )
            portfolio_id = str(report.portfolio_reference.artifact_id)
            portfolio_ids = {
                str(state_by_id[state_id][1].portfolio_reference.artifact_id)
                for state_id in matching
            }
            if portfolio_ids != {portfolio_id}:
                raise HistoricalResearchConflict(
                    "Historical Performance Portfolio lineage drift"
                )
            if set(report.input_state_references) != expected_states_by_portfolio.get(
                portfolio_id,
                set(),
            ):
                raise HistoricalResearchConflict(
                    "Historical Performance exact State set drift"
                )
            reports.append(report)
            covered.update(matching)
        if covered != set(state_by_id):
            reports = []
        if not reports:
            return _blocked(request, inputs, "HISTORICAL_PERFORMANCE_OWNER_MISSING")
        if len(reports) != len(
            {item.portfolio_reference for item in reports}
        ):
            raise HistoricalResearchConflict(
                "Historical Performance owner is ambiguous for exact Policy"
            )
        return _complete(
            inputs,
            tuple(
                ValidationArtifactReference(
                    "SHADOW_PERFORMANCE_REPORT", item.report_id, item.report_hash
                )
                for item in reports
            ),
            max(item.generated_at for item in reports),
            "HISTORICAL_PERFORMANCE_OWNER_RELOADED",
        )

    def _portfolio_receipt(
        self,
        *,
        request: ResearchDecisionSessionRequest,
        state: Any,
        decision_reference: ValidationArtifactReference,
    ) -> Any:
        receipt_references = tuple(
            item
            for item in state.source_references
            if item.artifact_kind == "SHADOW_OBSERVATION_RECEIPT"
        )
        if len(receipt_references) != 1:
            raise HistoricalResearchConflict(
                "Historical Portfolio Observation receipt is not unique"
            )
        reference = receipt_references[0]
        receipt = self._observations.get(reference.artifact_id)
        if (
            receipt.receipt_hash != reference.content_hash
            or receipt.kind is not ObservationKind.PORTFOLIO
            or receipt.research_trading_date != request.trading_date
            or receipt.trading_date != state.trading_date
            or decision_reference not in receipt.source_references
        ):
            raise HistoricalResearchConflict(
                "Historical Portfolio Observation lineage drift"
            )
        return receipt

    def _rows(self, query: str, parameters: tuple[Any, ...]) -> tuple[Any, ...]:
        with self._factory.connection(read_only=True) as connection:
            return tuple(connection.execute(query, parameters).fetchall())

    def _formal_experiment_matches(
        self,
        request: ResearchDecisionSessionRequest,
    ) -> bool:
        references = tuple(
            item
            for item in request.configuration_references
            if item.artifact_kind == "FORMAL_RESEARCH_PROTOCOL"
        )
        if len(references) != 1:
            return False
        reference = references[0]
        try:
            with self._factory.connection(read_only=True) as connection:
                protocol = load_formal_protocol_owner(
                    connection,
                    reference.artifact_id,
                    allow_legacy_replay=True,
                )
        except (KeyError, FormalProtocolConflict):
            return False
        experiment = protocol.experiment_definition
        return (
            protocol.protocol_hash == reference.content_hash
            and protocol.outcome_target_protocol_reference
            == request.target_protocol_reference
            and experiment is not None
            and experiment.definition_id
            == request.experiment_definition_reference.artifact_id
            and experiment.definition_hash
            == request.experiment_definition_reference.content_hash
        )


def _complete(
    inputs: tuple[ValidationArtifactReference, ...],
    outputs: tuple[ValidationArtifactReference, ...],
    completed_at: datetime,
    reason: str,
) -> SessionStageComputation:
    return SessionStageComputation(
        status=SessionStageStatus.COMPLETE,
        input_references=_references(inputs),
        output_references=_references(outputs),
        completed_at=completed_at,
        reason_codes=(reason,),
    )


def _blocked(
    request: ResearchDecisionSessionRequest,
    inputs: tuple[ValidationArtifactReference, ...],
    reason: str,
) -> SessionStageComputation:
    return SessionStageComputation(
        status=SessionStageStatus.BLOCKED,
        input_references=_references(inputs),
        output_references=(),
        completed_at=request.materialized_at,
        reason_codes=(reason,),
    )


def _single(
    inputs: tuple[ValidationArtifactReference, ...], artifact_kind: str
) -> ValidationArtifactReference:
    matches = tuple(item for item in inputs if item.artifact_kind == artifact_kind)
    if len(matches) != 1:
        raise HistoricalResearchConflict(
            f"Historical {artifact_kind} predecessor is not unique"
        )
    return matches[0]


def _optional_configuration(
    request: ResearchDecisionSessionRequest,
    artifact_kind: str,
) -> ValidationArtifactReference | None:
    matches = tuple(
        item
        for item in request.configuration_references
        if item.artifact_kind == artifact_kind
    )
    if len(matches) > 1:
        raise HistoricalResearchConflict(
            f"Historical {artifact_kind} configuration is ambiguous"
        )
    return None if not matches else matches[0]


def _required_configuration(
    request: ResearchDecisionSessionRequest,
    artifact_kind: str,
) -> ValidationArtifactReference:
    reference = _optional_configuration(request, artifact_kind)
    if reference is None:
        raise HistoricalResearchConflict(
            f"Historical {artifact_kind} exact configuration is required"
        )
    return reference


def _same_reference(left: Any, right: Any) -> bool:
    return (
        getattr(left, "artifact_kind", getattr(left, "reference_kind", None))
        == getattr(right, "artifact_kind", getattr(right, "reference_kind", None))
        and left.artifact_id == right.artifact_id
        and left.content_hash == right.content_hash
    )


def _references(
    values: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    return tuple(
        sorted(
            set(values),
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def _continuous_command_matches(
    command: ContinuousResearchCommand,
    request: ResearchDecisionSessionRequest,
    scope: RuntimeScopeReceipt,
) -> bool:
    """Require a decision parent frozen to the exact historical session inputs."""

    configuration_identities = {
        (str(item.artifact_id), item.content_hash)
        for item in request.configuration_references
    }
    return (
        command.trading_date == request.trading_date
        and command.requested_symbols == scope.requested_symbols
        and command.trading_calendar_id == request.trading_calendar_id
        and command.trading_calendar_hash == request.trading_calendar_hash
        and command.policy_id == request.decision_policy_id
        and command.policy_hash == request.decision_policy_hash
        and command.code_revision == request.code_revision
        and (
            str(command.provider_configuration_id),
            command.provider_configuration_hash,
        ) in configuration_identities
        and (
            str(command.research_configuration_id),
            command.research_configuration_hash,
        ) in configuration_identities
    )


__all__ = ["PostgresHistoricalSessionOwner"]
