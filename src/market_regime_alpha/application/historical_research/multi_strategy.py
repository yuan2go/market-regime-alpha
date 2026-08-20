"""Historical adapter for the same multi-Strategy policy kernel used by Continuous."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_corpus.golden_loop import (
    GoldenLoopScoringContract,
    evaluate_golden_loop_session,
)
from market_regime_alpha.application.historical_corpus.alpha_discovery import (
    ALPHA_DISCOVERY_CONTRACT_KIND,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
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
from market_regime_alpha.application.research_validation.historical_economics import (
    HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET_KIND,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.strategies.contracts import (
    StrategyRunOrigin,
    StrategyRuntimeInput,
)
from market_regime_alpha.strategies.feedback import attribute_path_outcomes
from market_regime_alpha.strategies.portfolio import (
    CrossStrategyPortfolioPolicy,
    build_cross_strategy_portfolio,
)
from market_regime_alpha.strategies.postgres_repository import (
    PostgresMultiStrategyRepository,
)
from market_regime_alpha.strategies.runtime import MultiStrategyRuntime


class HistoricalStageDelegate(Protocol):
    def compute_stage(
        self,
        *,
        request: ResearchDecisionSessionRequest,
        stage: ResearchSessionStage,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation: ...


@dataclass(slots=True)
class MultiStrategyHistoricalAdapter:
    """Decorate existing historical owners; never create another scheduler."""

    delegate: HistoricalStageDelegate
    component_repository: PostgresHistoricalMaterializationRepository
    strategy_repository: PostgresMultiStrategyRepository
    parent_run_reference: RuntimeArtifactReference
    portfolio_policy: CrossStrategyPortfolioPolicy

    def compute_stage(
        self,
        *,
        request: ResearchDecisionSessionRequest,
        stage: ResearchSessionStage,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        delegated = self.delegate.compute_stage(
            request=request,
            stage=stage,
            input_references=input_references,
        )
        if delegated.status is not SessionStageStatus.COMPLETE:
            return delegated
        if stage is ResearchSessionStage.STRATEGY:
            return self._strategy_stage(request, input_references, delegated)
        if stage is ResearchSessionStage.PORTFOLIO:
            return self._portfolio_stage(request, delegated)
        if stage is ResearchSessionStage.PERFORMANCE:
            return self._performance_stage(request, input_references, delegated)
        return delegated

    def _strategy_stage(
        self,
        request: ResearchDecisionSessionRequest,
        inputs: tuple[ValidationArtifactReference, ...],
        delegated: SessionStageComputation,
    ) -> SessionStageComputation:
        candidate_reference = _single(inputs, "HISTORICAL_CANDIDATE")
        candidate_component = self.component_repository.get(candidate_reference)
        candidates = CandidateSet.from_canonical_dict(dict(candidate_component.payload))
        dataset = _single_configuration(request, "NORMALIZED_DATASET")
        registry = self.strategy_repository.load_registry()
        runtime_input = StrategyRuntimeInput(
            origin=StrategyRunOrigin.HISTORICAL,
            authority_mode=RuntimeAuthorityMode.RESEARCH,
            parent_run_reference=self.parent_run_reference,
            parent_tick_reference=RuntimeArtifactReference(
                "RESEARCH_DECISION_SESSION",
                request.session_id,
                request.session_hash,
            ),
            candidate_set=candidates,
            dataset_reference=_runtime_reference(dataset),
            decision_time=request.decision_time,
            positions=(),
            code_reference=_aggregate_reference(
                "HISTORICAL_STRATEGY_CODE_SET",
                (
                    RuntimeArtifactReference(
                        "HISTORICAL_CODE_REVISION",
                        ArtifactId(f"historical-code:{canonical_hash({'code_revision': request.code_revision})[7:]}"),
                        canonical_hash({"code_revision": request.code_revision}),
                    ),
                    *(item.code_reference for item in registry.contracts),
                ),
            ),
            configuration_reference=_aggregate_reference(
                "HISTORICAL_STRATEGY_CONFIGURATION_SET",
                tuple(_runtime_reference(item) for item in request.configuration_references),
            ),
        )
        cycle = self.strategy_repository.save_cycle(MultiStrategyRuntime(registry).execute(runtime_input))
        return _extend(
            delegated,
            ValidationArtifactReference(
                "MULTI_STRATEGY_CYCLE",
                cycle.cycle_id,
                cycle.cycle_hash,
            ),
            "MULTI_STRATEGY_SHARED_SEMANTICS",
        )

    def _portfolio_stage(
        self,
        request: ResearchDecisionSessionRequest,
        delegated: SessionStageComputation,
    ) -> SessionStageComputation:
        cycle_reference = _single(
            delegated.input_references,
            "MULTI_STRATEGY_CYCLE",
        )
        cycle = self.strategy_repository.get_cycle(cycle_reference.artifact_id)
        portfolio = self.strategy_repository.save_portfolio(
            build_cross_strategy_portfolio(
                cycle=cycle,
                policy=self.portfolio_policy,
            ),
            created_at=request.materialized_at,
        )
        return _extend(
            delegated,
            ValidationArtifactReference(
                "CROSS_STRATEGY_PORTFOLIO",
                portfolio.decision_id,
                portfolio.decision_hash,
            ),
            "CROSS_STRATEGY_PORTFOLIO_SHARED_SEMANTICS",
        )

    def _performance_stage(
        self,
        request: ResearchDecisionSessionRequest,
        inputs: tuple[ValidationArtifactReference, ...],
        delegated: SessionStageComputation,
    ) -> SessionStageComputation:
        contract = GoldenLoopScoringContract.create_v2()
        if contract.reference not in request.configuration_references:
            return delegated
        discovery_references = tuple(
            item
            for item in request.configuration_references
            if item.artifact_kind == ALPHA_DISCOVERY_CONTRACT_KIND
        )
        if len(discovery_references) > 1:
            raise ValueError("Historical command binds multiple Alpha Discovery contracts")
        source_run_references = tuple(
            item
            for item in request.configuration_references
            if item.artifact_kind == "HISTORICAL_RESEARCH_SOURCE_RUN"
        )
        if len(source_run_references) > 1:
            raise ValueError("Historical command binds multiple source runs")
        available = _validation_references(
            (*inputs, *delegated.output_references)
        )
        panel = self.component_repository.get(
            _single(available, "HISTORICAL_RESEARCH_PANEL")
        )
        outcome = self.component_repository.get(
            _single(available, "HISTORICAL_OUTCOME")
        )
        cycle_reference = _single(available, "MULTI_STRATEGY_CYCLE")
        cycle = self.strategy_repository.get_cycle(cycle_reference.artifact_id)
        if _validation_reference(cycle_reference) != ValidationArtifactReference(
            "MULTI_STRATEGY_CYCLE",
            cycle.cycle_id,
            cycle.cycle_hash,
        ):
            raise ValueError("Historical Multi-Strategy Cycle owner hash mismatch")
        portfolio_reference = _single(available, "CROSS_STRATEGY_PORTFOLIO")
        portfolio = self.strategy_repository.get_portfolio(
            portfolio_reference.artifact_id
        )
        if _validation_reference(portfolio_reference) != ValidationArtifactReference(
            "CROSS_STRATEGY_PORTFOLIO",
            portfolio.decision_id,
            portfolio.decision_hash,
        ):
            raise ValueError("Historical Cross-Strategy Portfolio owner hash mismatch")
        if portfolio.cycle_reference != _runtime_reference(cycle_reference):
            raise ValueError("Historical Portfolio does not source the canonical Cycle")
        attributions = tuple(
            self.strategy_repository.save_feedback(
                attribute_path_outcomes(
                    strategy_version_reference=run.strategy_version_reference,
                    outcomes=(),
                    created_at=request.materialized_at,
                )
            )
            for run in cycle.runs
        )
        evaluation = evaluate_golden_loop_session(
            panel=panel,
            outcome=outcome,
            experiment_reference=request.experiment_definition_reference,
            cycle_reference=cycle_reference,
            portfolio_reference=portfolio_reference,
            portfolio_status=portfolio.status.value,
            portfolio_line_count=len(portfolio.lines),
            attribution_references=tuple(
                ValidationArtifactReference(
                    item.reference.reference_kind,
                    item.reference.artifact_id,
                    item.reference.content_hash,
                )
                for item in attributions
            ),
            additional_source_references=(
                _single(
                    request.configuration_references,
                    HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET_KIND,
                ),
                *discovery_references,
                *source_run_references,
            ),
            scoring_contract=contract,
            enable_alpha_discovery=bool(discovery_references),
        )
        component = HistoricalSessionComponent.create(
            run_id=panel.run_id,
            session_id=request.session_id,
            trading_date=request.trading_date,
            component_kind=HistoricalComponentKind.RESEARCH_EVALUATION,
            source_max_event_time=max(
                panel.source_max_event_time,
                outcome.source_max_event_time,
            ),
            materialized_at=request.materialized_at,
            source_references=evaluation.source_references,
            payload=evaluation.to_canonical_dict(),
            limitations=(
                "HISTORICAL_SHADOW_SIMULATION_NOT_OBSERVED_FILL",
                "NO_PHYSICAL_POSITION_AUTHORITY",
            ),
        )
        stored = self.component_repository.put(
            component=component,
            ordinal=tuple(HistoricalComponentKind).index(
                HistoricalComponentKind.RESEARCH_EVALUATION
            )
            + 1,
        )
        return _extend(
            delegated,
            stored.reference,
            "GOLDEN_LOOP_V2_CANONICAL_EVALUATION_MATERIALIZED",
        )


def _extend(
    computation: SessionStageComputation,
    output: ValidationArtifactReference,
    reason: str,
) -> SessionStageComputation:
    return SessionStageComputation(
        status=computation.status,
        output_references=_validation_references((*computation.output_references, output)),
        input_references=computation.input_references,
        completed_at=computation.completed_at,
        reason_codes=tuple(sorted({*computation.reason_codes, reason})),
    )


def _single(
    references: tuple[ValidationArtifactReference, ...],
    kind: str,
) -> ValidationArtifactReference:
    selected = tuple(item for item in references if item.artifact_kind == kind)
    if len(selected) != 1:
        raise ValueError(f"Historical {kind} reference must be unique")
    return selected[0]


def _single_configuration(
    request: ResearchDecisionSessionRequest,
    kind: str,
) -> ValidationArtifactReference:
    return _single(request.configuration_references, kind)


def _runtime_reference(
    reference: ValidationArtifactReference,
) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        reference.artifact_kind,
        reference.artifact_id,
        reference.content_hash,
    )


def _validation_reference(
    reference: ValidationArtifactReference,
) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        reference.artifact_kind,
        reference.artifact_id,
        reference.content_hash,
    )


def _aggregate_reference(
    kind: str,
    references: tuple[RuntimeArtifactReference, ...],
) -> RuntimeArtifactReference:
    ordered = tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )
    digest = canonical_hash({"reference_kind": kind, "references": [item.to_canonical_dict() for item in ordered]})
    return RuntimeArtifactReference(
        kind,
        ArtifactId(f"{kind.lower().replace('_', '-')}:{digest[7:]}"),
        digest,
    )


def _validation_references(
    references: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    values = {(item.artifact_kind, str(item.artifact_id), item.content_hash): item for item in references}
    return tuple(values[key] for key in sorted(values))


__all__ = ["MultiStrategyHistoricalAdapter"]
