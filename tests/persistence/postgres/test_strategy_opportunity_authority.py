from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import psycopg
import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.strategies.contracts import (
    StrategyOpportunityInput,
    StrategyRegistry,
    StrategyVersion,
    strategy_reference,
)
from market_regime_alpha.strategies.opportunity import (
    PreStrategyRiskState,
    PreStrategySymbolRiskDecision,
)
from market_regime_alpha.strategies.postgres_opportunity import (
    PostgresStrategyOpportunityAuthority,
    ResolvedStrategySource,
)
from market_regime_alpha.strategies.postgres_repository import (
    PostgresMultiStrategyRepository,
)
from tests.strategies.test_multi_strategy_runtime import (
    NOW,
    _candidate_set,
    _conditional_contract,
)


class _Sources:
    def __init__(self) -> None:
        self.values: dict[RuntimeArtifactReference, ResolvedStrategySource] = {}

    def add(
        self,
        reference: RuntimeArtifactReference,
        *,
        available_at: datetime = NOW,
        symbols: tuple[str, ...] = (),
        sources: tuple[RuntimeArtifactReference, ...] = (),
    ) -> None:
        self.values[reference] = ResolvedStrategySource(
            reference,
            available_at,
            tuple(sorted(symbols)),
            tuple(
                sorted(
                    sources,
                    key=lambda item: (
                        item.reference_kind,
                        str(item.artifact_id),
                        item.content_hash,
                    ),
                )
            ),
            {},
        )

    def reload(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        return self.values[reference]


def test_strategy_opportunity_is_pg_owned_idempotent_and_owner_resolved(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    candidate_set = _candidate_set()
    candidate = RuntimeArtifactReference(
        "CANDIDATE_SET",
        candidate_set.envelope.artifact_id,
        candidate_set.envelope.content_hash,
    )
    contract = _conditional_contract()
    version = StrategyVersion.activate(contract)
    registry = StrategyRegistry.create(
        contracts=(contract,),
        versions=(version,),
    )
    PostgresMultiStrategyRepository(postgres_factory).register(
        registry,
        created_at=NOW,
    )
    sources = _Sources()
    account = _reference("ACCOUNT_STATE", "account")
    positions = _reference("POSITION_BOOK", "positions")
    limits = _reference("RISK_LIMIT_SET", "limits")
    for reference in (candidate, account, positions, limits):
        sources.add(
            reference,
            symbols=("000001.SZ", "000002.SZ")
            if reference == candidate
            else (),
        )
    risk = PreStrategyRiskState.create(
        account_scope="research-account",
        candidate_reference=candidate,
        decision_time=NOW,
        available_at=NOW,
        account_state_reference=account,
        position_state_references=(positions,),
        liquidity_constraint_references=(),
        position_constraint_references=(),
        risk_limit_references=(limits,),
        trading_restriction_references=(),
        symbol_decisions=(
            PreStrategySymbolRiskDecision("000001.SZ", True, ()),
        ),
        limitations=("RESEARCH_ONLY",),
    )
    authority = PostgresStrategyOpportunityAuthority(
        postgres_factory,
        source_authority=sources,
        apply_migrations=False,
    )
    assert authority.record_risk_state(risk, created_at=NOW) == risk
    assert authority.record_risk_state(risk, created_at=NOW) == risk

    signal = _reference("SIGNAL_SNAPSHOT", "signal")
    context = _reference("CONTEXT_CONDITIONAL_EVALUATION", "context")
    model = _reference("MODEL_VERSION", "model")
    forecast = _reference("CONDITIONAL_FORECAST_RESULT", "forecast")
    strategy = strategy_reference(version)
    sources.add(strategy)
    sources.add(signal, symbols=("000001.SZ",), sources=(candidate,))
    sources.add(context)
    sources.add(model)
    sources.add(
        forecast,
        symbols=("000001.SZ",),
        sources=(signal, context, model),
    )
    opportunity = StrategyOpportunityInput.create(
        symbol="000001.SZ",
        strategy_version_reference=strategy,
        candidate_reference=candidate,
        decision_time=NOW,
        signal_reference=signal,
        forecast_reference=forecast,
        context_reference=context,
        risk_state_reference=risk.reference,
        model_reference=model,
        signal_active=True,
        risk_allows_action=True,
        risk_reason_codes=(),
        expected_return=Decimal("0.02"),
        prediction_uncertainty=Decimal("0.01"),
        calibration_status="NOT_CALIBRATED",
        available_at=NOW,
    )

    assert authority.record_opportunity(opportunity, created_at=NOW) == opportunity
    assert authority.record_opportunity(opportunity, created_at=NOW) == opportunity
    assert authority.resolve(
        candidate_reference=candidate,
        decision_time=NOW,
        registry=registry,
    ) == (opportunity,)

    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException
    ):
        connection.execute(
            "DELETE FROM strategy_opportunity WHERE opportunity_id = %s",
            (str(opportunity.opportunity_id),),
        )


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    from market_regime_alpha.core.identity import ArtifactId
    from market_regime_alpha.evidence.canonical import canonical_hash

    return RuntimeArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )
