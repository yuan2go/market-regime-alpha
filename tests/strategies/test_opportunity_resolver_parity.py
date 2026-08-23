from __future__ import annotations

from types import SimpleNamespace
from decimal import Decimal

from market_regime_alpha.application.continuous_research.multi_strategy import (
    PostgresContinuousStrategyOpportunityResolver,
)
from market_regime_alpha.application.historical_research.multi_strategy import (
    PostgresHistoricalStrategyOpportunityResolver,
)
from market_regime_alpha.strategies.defaults import (
    canonical_exploratory_strategy_registry,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.strategies.opportunity import (
    PreStrategyMarketFact,
    PreStrategyRiskFacts,
)
from tests.strategies.test_multi_strategy_runtime import NOW, _candidate_set


class _Authority:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object, object]] = []
        self.risk_states: list[object] = []

    def record_risk_state(self, state: object, *, created_at: object) -> object:
        self.risk_states.append(state)
        return state

    def record_opportunity(self, opportunity: object, *, created_at: object) -> object:
        return opportunity

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


class _RiskFacts:
    def __init__(self, facts: PreStrategyRiskFacts) -> None:
        self.facts = facts

    def resolve(self, **_: object) -> PreStrategyRiskFacts:
        return self.facts


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def test_continuous_and_historical_use_the_same_risk_producer_semantics() -> None:
    authority = _Authority()
    candidates = _candidate_set()
    registry = canonical_exploratory_strategy_registry()
    risk_reference = _reference("DECISION_RISK_CONFIGURATION", "risk")
    facts = PreStrategyRiskFacts(
        account_scope="research-account",
        account_state_reference=_reference(
            "MANUAL_ACCOUNT_OBSERVATION", "account"
        ),
        reconciliation_reference=_reference(
            "ACCOUNT_RECONCILIATION", "reconciliation"
        ),
        market_state_reference=_reference("DYNAMIC_STOCK_POOL", "pool"),
        risk_limit_reference=risk_reference,
        decision_time=NOW,
        available_at=NOW,
        total_equity=Decimal("1000"),
        available_cash=Decimal("500"),
        positions=(),
        market_facts=tuple(
            PreStrategyMarketFact(
                symbol,
                True,
                Decimal("0.90"),
                False,
                False,
            )
            for symbol in ("000001.SZ", "000002.SZ")
        ),
        maximum_single_symbol_weight=Decimal("0.20"),
        minimum_liquidity=Decimal("0.50"),
        daily_loss_limit=None,
    )
    resolver = _RiskFacts(facts)
    continuous = PostgresContinuousStrategyOpportunityResolver(
        authority,
        risk_fact_resolver=resolver,
        account_scope="research-account",
        risk_limit_reference=risk_reference,
    )
    historical = PostgresHistoricalStrategyOpportunityResolver(
        authority,
        risk_fact_resolver=resolver,
        account_scope="research-account",
        risk_limit_reference=risk_reference,
    )

    continuous.resolve(
        request=SimpleNamespace(as_of_time=NOW),
        candidates=candidates,
        registry=registry,
    )
    historical.resolve(
        request=SimpleNamespace(decision_time=NOW, materialized_at=NOW),
        candidates=candidates,
        registry=registry,
    )

    assert authority.risk_states[0] == authority.risk_states[1]
