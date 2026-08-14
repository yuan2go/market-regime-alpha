"""Adapter from the sole Continuous control plane into shared Strategy semantics."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

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
from market_regime_alpha.application.strategy_shadow.postgres_repository import (
    PostgresStrategyShadowRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data.contracts import Timeframe
from market_regime_alpha.market_data.dataset import MarketDataDatasetArtifact
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.strategies.contracts import (
    StrategyPositionState,
    StrategyDecisionPrice,
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


class MultiStrategyContinuousAdapter:
    """Executes Strategy and Portfolio work as one bounded Continuous child."""

    def __init__(
        self,
        *,
        repository: PostgresMultiStrategyRepository,
        portfolio_policy: CrossStrategyPortfolioPolicy,
        strategy_shadow_repository: PostgresStrategyShadowRepository | None = None,
        account_id: str | None = None,
    ) -> None:
        self._repository = repository
        self._portfolio_policy = portfolio_policy
        self._strategy_shadow_repository = strategy_shadow_repository
        self._account_id = account_id
        if (account_id is None) != (strategy_shadow_repository is None):
            raise ValueError(
                "stateful Strategy Runtime requires both account and Shadow owner"
            )

    def execute(
        self,
        *,
        request: ChildExecutionRequest,
        candidate_set: CandidateSet,
        dataset_reference: RuntimeArtifactReference,
        upstream: ChildExecutionResult,
        decision_price_dataset: MarketDataDatasetArtifact | None = None,
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
            positions=self._positions(request=request),
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
            decision_prices=(
                ()
                if decision_price_dataset is None
                else freeze_strategy_decision_prices(
                    dataset=decision_price_dataset,
                    symbols=tuple(item.symbol for item in candidate_set.records),
                    decision_time=request.as_of_time,
                )
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

    def _positions(
        self, *, request: ChildExecutionRequest
    ) -> tuple[StrategyPositionState, ...]:
        if self._account_id is None or self._strategy_shadow_repository is None:
            return ()
        calendar_references = tuple(
            item
            for item in request.input_references
            if item.reference_kind == "TRADING_CALENDAR"
        )
        if len(calendar_references) != 1:
            raise ValueError(
                "stateful Strategy Runtime requires one exact Trading Calendar owner"
            )
        self._strategy_shadow_repository.settle_multi_strategy_outcomes(
            account_id=self._account_id,
            decision_time=request.as_of_time,
        )
        return self._strategy_shadow_repository.resolve_multi_strategy_positions(
            account_id=self._account_id,
            decision_time=request.as_of_time,
            trading_calendar_reference=calendar_references[0],
        )


def freeze_strategy_decision_prices(
    *,
    dataset: MarketDataDatasetArtifact,
    symbols: tuple[str, ...],
    decision_time: datetime,
) -> tuple[StrategyDecisionPrice, ...]:
    """Project exact latest eligible minute bars; the Dataset remains owner."""

    prices: list[StrategyDecisionPrice] = []
    dataset_reference = RuntimeArtifactReference(
        "MARKET_DATA_DATASET",
        ArtifactId(str(dataset.dataset_id)),
        dataset.content_hash,
    )
    for symbol in sorted(set(symbols)):
        eligible = tuple(
            item
            for item in dataset.iter_bars()
            if item.symbol == symbol
            and item.timeframe is Timeframe.MINUTE_1
            if item.event_end <= decision_time and item.available_at <= decision_time
        )
        if not eligible:
            continue
        bar = max(eligible, key=lambda item: (item.event_end, str(item.bar_id)))
        duration = bar.timeframe.duration
        if duration is None or bar.event_end + duration < decision_time:
            continue
        prices.append(
            StrategyDecisionPrice(
                price_owner_reference=RuntimeArtifactReference(
                    "CANONICAL_MARKET_BAR",
                    bar.bar_id,
                    bar.content_hash,
                ),
                source_dataset_reference=dataset_reference,
                source_dataset_owner=dataset,
                price_owner=bar,
                symbol=bar.symbol,
                price=bar.close,
                observed_at=bar.event_end,
                available_at=bar.available_at,
                freshness_expires_at=bar.event_end + duration,
            )
        )
    return tuple(prices)


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


__all__ = ["MultiStrategyContinuousAdapter", "freeze_strategy_decision_prices"]
