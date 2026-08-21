from __future__ import annotations

from types import SimpleNamespace

from market_regime_alpha.application.continuous_research.multi_strategy import (
    PostgresContinuousStrategyOpportunityResolver,
)
from market_regime_alpha.application.historical_research.multi_strategy import (
    PostgresHistoricalStrategyOpportunityResolver,
)
from market_regime_alpha.strategies.defaults import (
    canonical_exploratory_strategy_registry,
)
from tests.strategies.test_multi_strategy_runtime import NOW, _candidate_set


class _Authority:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object, object]] = []

    def resolve(
        self,
        *,
        candidate_reference: object,
        decision_time: object,
        registry: object,
    ) -> tuple[()]:
        self.calls.append((candidate_reference, decision_time, registry))
        return ()


def test_continuous_and_historical_resolvers_bind_identical_business_inputs() -> None:
    authority = _Authority()
    continuous = PostgresContinuousStrategyOpportunityResolver(authority)
    historical = PostgresHistoricalStrategyOpportunityResolver(authority)
    candidates = _candidate_set()
    registry = canonical_exploratory_strategy_registry()

    assert continuous.resolve(
        request=SimpleNamespace(as_of_time=NOW),
        candidates=candidates,
        registry=registry,
    ) == ()
    assert historical.resolve(
        request=SimpleNamespace(decision_time=NOW),
        candidates=candidates,
        registry=registry,
    ) == ()

    assert authority.calls[0] == authority.calls[1]
