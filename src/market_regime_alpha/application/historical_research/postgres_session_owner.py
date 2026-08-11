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
from market_regime_alpha.application.shadow_research.postgres_repository import (
    PostgresShadowResearchRepository,
)
from market_regime_alpha.application.strategy_shadow.postgres_performance import (
    PostgresPortfolioPerformanceRepository,
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
        decision = None
        for row in rows:
            try:
                continuous = self._continuous.get_run(
                    ArtifactId(str(row[1]))
                ).command
            except ContinuousResearchNotFound as error:
                raise HistoricalResearchConflict(
                    "Historical Shadow Decision parent run is missing"
                ) from error
            if _continuous_command_matches(continuous, request, scope):
                decision = self._decisions.get_decision(ArtifactId(str(row[0])))
                break
        if decision is None:
            return _blocked(
                request,
                inputs,
                "HISTORICAL_DECISION_OWNER_INCOMPATIBLE",
            )
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
        sessions = tuple(
            item
            for item in self._strategy.list_sessions(trading_date=request.trading_date)
            if item.research_shadow_reference.artifact_id == decision.artifact_id
            and item.updated_at <= request.materialized_at
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
        rows = self._rows(
            """
            SELECT state_id FROM strategy_shadow_portfolio_day
            WHERE trading_date = %s AND recorded_at <= %s
            ORDER BY portfolio_id, state_id
            """,
            (request.trading_date, request.materialized_at),
        )
        states = tuple(
            self._portfolio.get_state(ArtifactId(str(row[0]))) for row in rows
        )
        if not states:
            return _blocked(request, inputs, "HISTORICAL_PORTFOLIO_OWNER_MISSING")
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
        rows = self._rows(
            """
            SELECT settlement_id FROM targeted_shadow_outcome
            WHERE shadow_decision_id = %s AND created_at <= %s
            ORDER BY target_protocol_id, settlement_id
            """,
            (str(decision.artifact_id), request.materialized_at),
        )
        outcomes = tuple(
            self._outcomes.get(ArtifactId(str(row[0]))) for row in rows
        )
        if not outcomes:
            return _blocked(request, inputs, "HISTORICAL_OUTCOME_OWNER_MISSING")
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
        state_ids = tuple(
            sorted(
                str(item.artifact_id)
                for item in inputs
                if item.artifact_kind == "SHADOW_PORTFOLIO_DAY_STATE"
            )
        )
        rows = (
            self._rows(
                """
                SELECT DISTINCT report.report_id
                FROM shadow_performance_report AS report
                JOIN shadow_performance_state_binding AS binding
                  ON binding.report_id = report.report_id
                WHERE report.end_date = %s AND report.generated_at <= %s
                  AND binding.state_id = ANY(%s::text[])
                ORDER BY report.report_id
                """,
                (request.trading_date, request.materialized_at, list(state_ids)),
            )
            if state_ids
            else ()
        )
        reports = tuple(
            self._performance.get(ArtifactId(str(row[0]))) for row in rows
        )
        if not reports:
            return _blocked(request, inputs, "HISTORICAL_PERFORMANCE_OWNER_MISSING")
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

    def _rows(self, query: str, parameters: tuple[Any, ...]) -> tuple[Any, ...]:
        with self._factory.connection(read_only=True) as connection:
            return tuple(connection.execute(query, parameters).fetchall())


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

    return (
        command.trading_date == request.trading_date
        and command.requested_symbols == scope.requested_symbols
        and command.trading_calendar_id == request.trading_calendar_id
        and command.trading_calendar_hash == request.trading_calendar_hash
        and command.policy_id == request.decision_policy_id
        and command.policy_hash == request.decision_policy_hash
        and command.code_revision == request.code_revision
    )


__all__ = ["PostgresHistoricalSessionOwner"]
