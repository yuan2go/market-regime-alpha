"""Adapter from the sole Continuous control plane into shared Strategy semantics."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from market_regime_alpha.application.continuous_research.composition import (
    _with_upstream_result,
)
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.strategies.contracts import (
    StrategyPositionState,
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
from market_regime_alpha.strategies.sleeves import project_strategy_sleeves


class MultiStrategyContinuousAdapter:
    """Executes Strategy and Portfolio work as one bounded Continuous child."""

    def __init__(
        self,
        *,
        repository: PostgresMultiStrategyRepository,
        portfolio_policy: CrossStrategyPortfolioPolicy,
        account_id: str | None = None,
    ) -> None:
        self._repository = repository
        self._portfolio_policy = portfolio_policy
        self._account_id = account_id

    def execute(
        self,
        *,
        request: ChildExecutionRequest,
        candidate_set: CandidateSet,
        dataset_reference: RuntimeArtifactReference,
        upstream: ChildExecutionResult,
    ) -> ChildExecutionResult:
        registry = self._repository.load_registry()
        strategy_request = _with_upstream_result(
            replace(
                request,
                input_references=upstream.input_references,
                configuration_references=upstream.configuration_references,
            ),
            upstream,
        )
        run_hash = request.run_hash or canonical_hash({"continuous_run_id": str(request.run_id)})
        tick_hash = request.tick_hash or canonical_hash(
            {
                "continuous_tick_id": str(request.tick_id),
                "tick_sequence": request.tick_sequence,
                "fencing_token": request.fencing_token,
            }
        )
        runtime_input = StrategyRuntimeInput(
            origin=StrategyRunOrigin.CONTINUOUS,
            authority_mode=request.authority_mode,
            parent_run_reference=RuntimeArtifactReference("CONTINUOUS_RESEARCH_RUN", request.run_id, run_hash),
            parent_tick_reference=RuntimeArtifactReference("CONTINUOUS_RUNTIME_TICK", request.tick_id, tick_hash),
            candidate_set=candidate_set,
            dataset_reference=dataset_reference,
            decision_time=request.as_of_time,
            positions=self._positions(),
            code_reference=_reference_set(
                "STRATEGY_CODE_SET",
                (
                    RuntimeArtifactReference(
                        "CONTINUOUS_RUN_CODE_IDENTITY",
                        request.run_id,
                        run_hash,
                    ),
                    *(contract.code_reference for contract in registry.contracts),
                ),
            ),
            configuration_reference=_reference_set(
                "STRATEGY_CONFIGURATION_SET",
                tuple(
                    sorted(
                        {
                            *request.configuration_references,
                            *(contract.configuration_reference for contract in registry.contracts),
                        },
                        key=lambda item: (
                            item.reference_kind,
                            str(item.artifact_id),
                            item.content_hash,
                        ),
                    )
                ),
            ),
        )
        cycle = self._repository.save_cycle(MultiStrategyRuntime(registry).execute(runtime_input))
        portfolio = self._repository.save_portfolio(
            build_cross_strategy_portfolio(
                cycle=cycle,
                policy=self._portfolio_policy,
            ),
            created_at=request.as_of_time,
        )
        return ChildExecutionResult(
            child_kind=ContinuousChildKind.STRATEGY_RUNTIME,
            child_run_id=cycle.cycle_id,
            child_receipt_id=cycle.cycle_id,
            child_receipt_hash=cycle.cycle_hash,
            child_artifact_id=portfolio.decision_id,
            child_artifact_hash=portfolio.decision_hash,
            input_references=strategy_request.input_references,
            configuration_references=strategy_request.configuration_references,
        )

    def _positions(self) -> tuple[StrategyPositionState, ...]:
        if self._account_id is None:
            return ()
        sleeves = project_strategy_sleeves(self._repository.list_fill_allocations(account_id=self._account_id))
        return tuple(
            StrategyPositionState(
                strategy_version_id=item.strategy_version_reference.artifact_id,
                symbol=item.symbol,
                quantity=Decimal(item.quantity),
                average_cost=item.average_cost,
                current_price=None,
                peak_price=item.average_cost,
                sessions_held=0,
            )
            for item in sleeves
            if item.quantity > 0 and item.average_cost is not None
        )


def _reference_set(
    reference_kind: str,
    references: tuple[RuntimeArtifactReference, ...],
) -> RuntimeArtifactReference:
    payload = [item.to_canonical_dict() for item in references]
    digest = canonical_hash({"reference_kind": reference_kind, "references": payload})
    return RuntimeArtifactReference(
        reference_kind,
        ArtifactId(f"{reference_kind.lower().replace('_', '-')}:{digest[7:]}"),
        digest,
    )


__all__ = ["MultiStrategyContinuousAdapter"]
