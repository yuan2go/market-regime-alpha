from __future__ import annotations

from types import SimpleNamespace
from decimal import Decimal
from typing import Any

import pytest

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
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.strategies.opportunity import (
    PreStrategyMarketFact,
    PreStrategyRiskFacts,
    StrategyOpportunityMaterial,
)
from market_regime_alpha.strategies.postgres_opportunity_material import (
    PostgresConditionalForecastOwnerResolver,
    PostgresStrategyOpportunityMaterialResolver,
)
from market_regime_alpha.strategies.contracts import (
    StrategyRegistry,
    StrategyVersion,
    strategy_reference,
)
from tests.strategies.test_multi_strategy_runtime import (
    NOW,
    _candidate_set,
    _conditional_contract,
)


class _Authority:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object, object]] = []
        self.risk_states: list[object] = []
        self.opportunities: list[object] = []

    def record_risk_state(self, state: object, *, created_at: object) -> object:
        self.risk_states.append(state)
        return state

    def record_opportunity(self, opportunity: object, *, created_at: object) -> object:
        self.opportunities.append(opportunity)
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


def test_resolvers_do_not_consume_caller_only_preexisting_opportunities() -> None:
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

    assert authority.calls == []


class _RiskFacts:
    def __init__(self, facts: PreStrategyRiskFacts) -> None:
        self.facts = facts

    def resolve(self, **_: object) -> PreStrategyRiskFacts:
        return self.facts


class _Materials:
    def __init__(self, values: tuple[StrategyOpportunityMaterial, ...]) -> None:
        self.values = values

    def resolve(self, **_: object) -> tuple[StrategyOpportunityMaterial, ...]:
        return self.values


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
        maximum_theme_weight=Decimal("0.20"),
        theme_exposures=(),
        theme_exposure_complete=True,
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


def test_continuous_resolver_records_materialized_opportunity_before_reload() -> None:
    authority = _Authority()
    candidates = _candidate_set()
    contract = _conditional_contract()
    version = StrategyVersion.activate(contract)
    registry = StrategyRegistry.create(
        contracts=(contract,),
        versions=(version,),
    )
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
        market_facts=(
            PreStrategyMarketFact(
                "000001.SZ", True, Decimal("0.90"), False, False
            ),
            PreStrategyMarketFact(
                "000002.SZ", True, Decimal("0.90"), False, False
            ),
        ),
        maximum_single_symbol_weight=Decimal("0.20"),
        maximum_theme_weight=Decimal("0.20"),
        theme_exposures=(),
        theme_exposure_complete=True,
        minimum_liquidity=Decimal("0.50"),
        daily_loss_limit=None,
    )
    material = StrategyOpportunityMaterial(
        symbol="000001.SZ",
        strategy_version_reference=strategy_reference(version),
        signal_reference=_reference("SIGNAL_SNAPSHOT", "signal"),
        forecast_reference=_reference(
            "CONDITIONAL_FORECAST_RESULT", "forecast"
        ),
        context_reference=_reference(
            "CONTEXT_CONDITIONAL_EVALUATION", "context"
        ),
        model_reference=_reference("RESEARCH_MODEL_ARTIFACT", "model"),
        signal_active=True,
        expected_return=Decimal("0.02"),
        prediction_uncertainty=Decimal("0.01"),
        calibration_status="NOT_CALIBRATED",
        available_at=NOW,
    )
    resolver = PostgresContinuousStrategyOpportunityResolver(
        authority,
        risk_fact_resolver=_RiskFacts(facts),
        account_scope="research-account",
        risk_limit_reference=risk_reference,
        material_resolver=_Materials((material,)),
    )

    resolver.resolve(
        request=SimpleNamespace(as_of_time=NOW),
        candidates=candidates,
        registry=registry,
    )

    assert len(authority.risk_states) == 1
    assert len(authority.opportunities) == 1


def test_conditional_owner_query_binds_exact_context_reference() -> None:
    captured: dict[str, Any] = {}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: str, parameters: tuple[str, ...]):
            captured["query"] = query
            captured["parameters"] = parameters
            return self

        def fetchall(self):
            return []

    class Factory:
        def connection(self, *, read_only: bool = False):
            assert read_only
            return Connection()

    resolver: Any = object.__new__(PostgresConditionalForecastOwnerResolver)
    resolver._factory = Factory()
    resolver._evidence = object()
    path = ValidationArtifactReference(
        "PATH_FORECAST", ArtifactId("path"), "sha256:" + "1" * 64
    )
    experiment = ValidationArtifactReference(
        "RESEARCH_EXPERIMENT_DEFINITION",
        ArtifactId("experiment"),
        "sha256:" + "2" * 64,
    )
    context = ValidationArtifactReference(
        "HISTORICAL_CONTEXT_CONDITIONAL_EVIDENCE",
        ArtifactId("context"),
        "sha256:" + "3" * 64,
    )

    with pytest.raises(ValueError, match="missing or ambiguous"):
        resolver.resolve(
            path_reference=path,
            experiment_reference=experiment,
            context_evidence_reference=context,
        )

    assert "context.artifact_id" in captured["query"]
    assert captured["parameters"][-3:] == (
        context.artifact_kind,
        str(context.artifact_id),
        context.content_hash,
    )


def test_material_resolver_never_selects_an_implicit_evidence_root() -> None:
    resolver: Any = object.__new__(PostgresStrategyOpportunityMaterialResolver)
    resolver._root = None
    contract = _conditional_contract()
    registry = StrategyRegistry.create(
        contracts=(contract,),
        versions=(StrategyVersion.activate(contract),),
    )

    with pytest.raises(ValueError, match="explicit Candidate Evidence root"):
        resolver.resolve(
            candidates=_candidate_set(),
            decision_time=NOW,
            registry=registry,
            path_forecasts=(),
        )
