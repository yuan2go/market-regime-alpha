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
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.strategies.contracts import (
    StrategyRunOrigin,
    StrategyRuntimeInput,
)
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
