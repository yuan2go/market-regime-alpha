from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import psycopg
import pytest
from psycopg.types.json import Jsonb

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_research.contracts import (
    HistoricalResearchCommand,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.application.decision_system.contracts import (
    ManualAccountObservation,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.reconciliation import (
    reconcile_account,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.strategies.postgres_pre_strategy_risk import (
    PostgresHistoricalPreStrategyRiskFactResolver,
    PostgresPreStrategyRiskFactResolver,
    _historical_market_facts,
)
from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from market_regime_alpha.strategies.contracts import (
    StrategyOpportunityInput,
    StrategyRegistry,
    StrategyVersion,
    strategy_reference,
)
from market_regime_alpha.strategies.opportunity import (
    PreStrategyMarketFact,
    PreStrategyRiskFacts,
    StrategyOpportunityMaterial,
    StrategyOpportunityProducer,
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
from tests.application.decision_system.support import (
    HASH_A,
    risk_configuration,
    tolerance,
)
from tests.application.state_system.test_repositories import (
    _active_claim,
    _pool,
)
from tests.persistence.postgres.test_continuous_research_journal import (
    MutableClock,
    NOW as JOURNAL_NOW,
)
from tests.application.historical_research.test_contracts import (
    _command as _historical_command,
)
from tests.universe.test_runtime_scope import _policy


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
    account = _reference("MANUAL_ACCOUNT_OBSERVATION", "account")
    reconciliation = _reference("ACCOUNT_RECONCILIATION", "reconciliation")
    pool = _reference("DYNAMIC_STOCK_POOL", "pool")
    limits = _reference("DECISION_RISK_CONFIGURATION", "limits")
    for reference in (candidate, account, reconciliation, pool, limits):
        sources.add(
            reference,
            symbols=("000001.SZ", "000002.SZ")
            if reference == candidate
            else (),
        )
    facts = PreStrategyRiskFacts(
        account_scope="research-account",
        account_state_reference=account,
        reconciliation_reference=reconciliation,
        market_state_reference=pool,
        risk_limit_reference=limits,
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
    authority = PostgresStrategyOpportunityAuthority(
        postgres_factory,
        source_authority=sources,
        apply_migrations=False,
    )
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
    risk, produced = StrategyOpportunityProducer(authority).produce(
        candidates=candidate_set,
        facts=facts,
        registry=registry,
        materials=(
            StrategyOpportunityMaterial(
                symbol="000001.SZ",
                strategy_version_reference=strategy,
                signal_reference=signal,
                forecast_reference=forecast,
                context_reference=context,
                model_reference=model,
                signal_active=True,
                expected_return=Decimal("0.02"),
                prediction_uncertainty=Decimal("0.01"),
                calibration_status="NOT_CALIBRATED",
                available_at=NOW,
            ),
        ),
        created_at=NOW,
    )
    assert authority.record_risk_state(risk, created_at=NOW) == risk
    assert len(produced) == 1
    opportunity = produced[0]
    assert opportunity == StrategyOpportunityInput.create(
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


def test_postgres_pre_strategy_risk_resolver_reloads_real_owner_facts(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(JOURNAL_NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    candidates = _candidate_set()
    pool = _pool(claim)
    state_repository = PostgresStateSystemRepository(
        postgres_factory,
        clock=clock,
        apply_migrations=False,
    )
    state_repository.append_pool(
        pool,
        claim=claim,
        expected_previous_pool_id=None,
    )
    receipt_hash = canonical_hash({"owner": "pre-strategy-risk-test"})
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO state_runtime_receipt(
                receipt_id, receipt_hash, run_id, tick_id, pool_id,
                status, receipt_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, 'COMPLETED', %s, %s)
            """,
            (
                "pre-strategy-state-receipt",
                receipt_hash,
                str(claim.run_id),
                str(claim.tick_id),
                str(pool.pool_id),
                "{}",
                JOURNAL_NOW,
            ),
        )
        connection.execute(
            """
            INSERT INTO state_research_stage_authority(
                run_id, tick_id, state_receipt_id, stage,
                artifact_id, artifact_hash, available_at, created_at
            ) VALUES (%s, %s, %s, 'DYNAMIC_POOL', %s, %s, %s, %s)
            """,
            (
                str(claim.run_id),
                str(claim.tick_id),
                "pre-strategy-state-receipt",
                str(pool.pool_id),
                pool.pool_hash,
                pool.available_at,
                JOURNAL_NOW,
            ),
        )
        connection.execute(
            """
            INSERT INTO state_runtime_candidate_artifact(
                run_id, tick_id, candidate_id, candidate_hash,
                stage_artifact_id, stage_artifact_hash, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(claim.run_id),
                str(claim.tick_id),
                str(candidates.envelope.artifact_id),
                candidates.envelope.content_hash,
                "pre-strategy-candidate-stage",
                canonical_hash({"stage": "candidate"}),
                Jsonb(candidates.to_canonical_dict()),
                JOURNAL_NOW,
            ),
        )

    account = ManualAccountObservation.create(
        account_id="pre-strategy-account",
        trading_date=JOURNAL_NOW.date(),
        as_of_time=JOURNAL_NOW,
        total_equity=Decimal("100000"),
        available_cash=Decimal("80000"),
        frozen_cash=Decimal("0"),
        source="MANUAL_ACCOUNT_AUTHORITY",
        actor="operator",
        reason="pre-Strategy Risk owner test",
        notes="",
        idempotency_key="pre-strategy-account-observation",
        revision=1,
        previous_observation_id=None,
        positions=(),
        created_at=JOURNAL_NOW,
    )
    decision = PostgresDecisionSystemRepository(
        postgres_factory,
        clock=lambda: JOURNAL_NOW,
    )
    decision.record_manual_observation(account)
    selected_tolerance = tolerance()
    decision.record_reconciliation_tolerance(selected_tolerance, claim=claim)
    reconciliation = reconcile_account(
        observation=account,
        positions=(),
        fill_ledger_head=HASH_A,
        fill_ledger_complete=True,
        tolerance=selected_tolerance,
        authoritative_total_equity=account.total_equity,
        authoritative_available_cash=account.available_cash,
        authoritative_frozen_cash=account.frozen_cash,
        as_of_time=JOURNAL_NOW,
        revision=1,
        previous_reconciliation_id=None,
        idempotency_key="pre-strategy-reconciliation",
        created_at=JOURNAL_NOW,
    )
    decision.save_reconciliation(reconciliation, claim=claim)
    limits = risk_configuration()
    decision.record_risk_configuration(limits, claim=claim)
    limit_reference = RuntimeArtifactReference(
        "DECISION_RISK_CONFIGURATION",
        limits.configuration_id,
        limits.configuration_hash,
    )

    facts = PostgresPreStrategyRiskFactResolver(postgres_factory).resolve(
        candidates=candidates,
        account_scope=account.account_id,
        decision_time=JOURNAL_NOW,
        risk_limit_reference=limit_reference,
    )

    assert facts.account_state_reference.artifact_id == account.observation_id
    assert facts.reconciliation_reference.artifact_id == reconciliation.reconciliation_id
    assert facts.market_state_reference.artifact_id == pool.pool_id
    assert facts.risk_limit_reference == limit_reference
    assert facts.total_equity == Decimal("100000")


def test_postgres_historical_pre_strategy_resolver_reloads_frozen_session_owners(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command_values = _historical_command().semantic_values()
    command = HistoricalResearchCommand.create(
        **{
            **command_values,
            "idempotency_key": "historical-risk-owner-session",
            "start_date": NOW.date(),
            "end_date": NOW.date(),
            "trading_sessions": (NOW.date(),),
            "created_at": NOW,
        }
    )
    PostgresRuntimeScopeRepository(postgres_factory).register_policy(_policy())
    run = PostgresHistoricalResearchJournal(
        postgres_factory,
        clock=lambda: NOW,
    ).create_or_get(command)
    session = run.sessions[0]
    decision_time = session.request.decision_time
    source = ValidationArtifactReference(
        "HISTORICAL_SOURCE",
        ArtifactId("historical-risk-source"),
        canonical_hash({"historical": "risk-source"}),
    )
    candidates = _candidate_set()
    pool = HistoricalSessionComponent.create(
        run_id=command.run_id,
        session_id=session.request.session_id,
        trading_date=NOW.date(),
        component_kind=HistoricalComponentKind.DYNAMIC_POOL,
        source_max_event_time=decision_time,
        materialized_at=decision_time,
        source_references=(source,),
        payload={
            "universal_integrity": [
                {
                    "symbol": item.symbol,
                    "eligible": True,
                    "checks": {
                        "suspension_known": True,
                        "not_suspended": True,
                    },
                }
                for item in candidates.records
            ]
        },
    )
    candidate_component = HistoricalSessionComponent.create(
        run_id=command.run_id,
        session_id=session.request.session_id,
        trading_date=NOW.date(),
        component_kind=HistoricalComponentKind.CANDIDATE,
        source_max_event_time=decision_time,
        materialized_at=decision_time,
        source_references=(pool.reference,),
        payload=candidates.to_canonical_dict(),
    )
    PostgresHistoricalMaterializationRepository(postgres_factory).put_many(
        ((pool, 1), (candidate_component, 2))
    )

    clock = MutableClock(JOURNAL_NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    account = ManualAccountObservation.create(
        account_id="historical-risk-account",
        trading_date=NOW.date(),
        as_of_time=decision_time,
        total_equity=Decimal("100000"),
        available_cash=Decimal("80000"),
        frozen_cash=Decimal("0"),
        source="MANUAL_ACCOUNT_AUTHORITY",
        actor="operator",
        reason="Historical pre-Strategy Risk owner test",
        notes="",
        idempotency_key="historical-risk-account-observation",
        revision=1,
        previous_observation_id=None,
        positions=(),
        created_at=decision_time,
    )
    decision = PostgresDecisionSystemRepository(
        postgres_factory,
        clock=lambda: JOURNAL_NOW,
    )
    decision.record_manual_observation(account)
    selected_tolerance = tolerance()
    decision.record_reconciliation_tolerance(selected_tolerance, claim=claim)
    reconciliation = reconcile_account(
        observation=account,
        positions=(),
        fill_ledger_head=HASH_A,
        fill_ledger_complete=True,
        tolerance=selected_tolerance,
        authoritative_total_equity=account.total_equity,
        authoritative_available_cash=account.available_cash,
        authoritative_frozen_cash=account.frozen_cash,
        as_of_time=decision_time,
        revision=1,
        previous_reconciliation_id=None,
        idempotency_key="historical-risk-reconciliation",
        created_at=decision_time,
    )
    decision.save_reconciliation(reconciliation, claim=claim)
    limits = risk_configuration()
    decision.record_risk_configuration(limits, claim=claim)
    account_reference = RuntimeArtifactReference(
        "MANUAL_ACCOUNT_OBSERVATION",
        account.observation_id,
        account.content_hash,
    )
    reconciliation_reference = RuntimeArtifactReference(
        "ACCOUNT_RECONCILIATION",
        reconciliation.reconciliation_id,
        reconciliation.content_hash,
    )
    limit_reference = RuntimeArtifactReference(
        "DECISION_RISK_CONFIGURATION",
        limits.configuration_id,
        limits.configuration_hash,
    )

    facts = PostgresHistoricalPreStrategyRiskFactResolver(
        postgres_factory,
        account_scope=account.account_id,
        account_state_references=(account_reference,),
        reconciliation_references=(reconciliation_reference,),
    ).resolve(
        candidates=candidates,
        account_scope=account.account_id,
        decision_time=decision_time,
        risk_limit_reference=limit_reference,
    )

    assert facts.account_state_reference == account_reference
    assert facts.reconciliation_reference == reconciliation_reference
    assert facts.market_state_reference.reference_kind == "HISTORICAL_DYNAMIC_POOL"
    assert facts.risk_limit_reference == limit_reference
    assert all(item.liquidity is None for item in facts.market_facts)


def test_historical_pool_rejects_non_boolean_suspension_facts() -> None:
    with pytest.raises(ValueError, match="suspension fact is malformed"):
        _historical_market_facts(
            {
                "universal_integrity": [
                    {
                        "symbol": "000001.SZ",
                        "eligible": True,
                        "checks": {
                            "suspension_known": True,
                            "not_suspended": "false",
                        },
                    }
                ]
            }
        )


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    from market_regime_alpha.core.identity import ArtifactId
    from market_regime_alpha.evidence.canonical import canonical_hash

    return RuntimeArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )
