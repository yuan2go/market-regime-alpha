from __future__ import annotations

from datetime import timedelta

import pytest

from market_regime_alpha.application.operational_research.postgres_composite_repository import (
    PostgresCompositeOperationalRepository,
)
from market_regime_alpha.application.trading_lifecycle import (
    CompleteAccountPortfolioRiskApplicationService,
    DecisionLifecycleService,
    ManualExecutionApplicationService,
    PortfolioRiskApplicationService,
    TraceableManualExecutionApplicationService,
)
from market_regime_alpha.decision import OpportunityState, ThesisState
from market_regime_alpha.decision.postgres_repository import (
    PostgresDecisionLifecycleRepository,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution import ManualOrderState
from market_regime_alpha.execution.postgres_repository import (
    PostgresManualExecutionRepository,
    PostgresTraceableManualExecutionRepository,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform import ModelLifecycleStatus
from market_regime_alpha.platform.durable_governance import (
    PersistentExperimentGovernance,
    PersistentModelRegistry,
)
from market_regime_alpha.platform.postgres_governance import (
    PostgresExperimentGovernanceRepository,
    PostgresModelRegistryRepository,
)
from market_regime_alpha.portfolio import (
    PortfolioOutputMode,
    RiskDecisionState,
)
from market_regime_alpha.portfolio.postgres_repository import (
    PostgresCompleteAccountPortfolioRiskRepository,
    PostgresPortfolioDecisionRepository,
    PostgresRiskRouteRepository,
)
from market_regime_alpha.position import PositionState, ThesisHealthObservationBuilder
from market_regime_alpha.position.postgres_thesis_health import (
    PostgresThesisHealthRepository,
)
from market_regime_alpha.position.thesis_health import thesis_health_command_hash
from tests.application.operational_research.test_postgres_composite_repository import (
    _publication,
)
from tests.daily_decision.conftest import (
    DailyDecisionFixture,
    daily_decision_fixture,
)
from tests.decision.test_lifecycle import (
    CREATED,
    _conditions,
    _create,
    _evidence,
)
from tests.execution.test_manual_position_authority import (
    NOW as EXECUTION_NOW,
    _trade,
)
from tests.execution.test_traceable_execution_chain import (
    NOW as TRACE_NOW,
    _authority as _trace_authority,
    _create_trade as _create_traceable_trade,
)
from tests.platform.test_governance_persistence import CHANGED_AT, _protocol
from tests.platform.test_platform_kernel import _model_definition
from tests.portfolio.risk_route_test_support import make_decision
from tests.portfolio.test_risk_authority import (
    NOW as PORTFOLIO_NOW,
    _account,
    _allocation,
    _budget,
    _position,
    _thesis,
)
from tests.portfolio.test_complete_account_risk import (
    NOW as COMPLETE_ACCOUNT_NOW,
    _risk_configuration,
    _thesis as _complete_account_thesis,
)
from market_regime_alpha.portfolio import (
    AccountPortfolioCompleteness,
    AccountReconciliationState,
    AuthoritativeAccountPortfolioSnapshot,
    ThesisAllocationRequest,
)
from tests.position.test_thesis_health_builder import _bundle
from tests.position.thesis_health_fixtures import make_h5_fixture


def test_postgres_governance_preserves_restart_idempotency_and_budgets(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    registry = PersistentModelRegistry(
        PostgresModelRegistryRepository(postgres_factory)
    )
    definition = _model_definition()
    registered = registry.register(definition, idempotency_key="pg-model-register")
    transitioned = registry.transition(
        definition.model_id,
        expected_version=registered.version,
        idempotency_key="pg-model-transition",
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=CHANGED_AT,
        reason="PostgreSQL parity",
    )
    restored = PersistentModelRegistry(
        PostgresModelRegistryRepository(postgres_factory)
    ).get(definition.model_id)
    assert restored == transitioned
    assert registry.register(
        definition, idempotency_key="pg-model-register"
    ) == registered

    experiments = PersistentExperimentGovernance(
        PostgresExperimentGovernanceRepository(postgres_factory)
    )
    protocol = _protocol(accesses=1)
    governed = experiments.register(protocol, idempotency_key="pg-exp-register")
    accessed = experiments.record_validation_access(
        protocol.experiment_id,
        expected_version=governed.version,
        idempotency_key="pg-exp-access",
    )
    restarted = PersistentExperimentGovernance(
        PostgresExperimentGovernanceRepository(postgres_factory)
    )
    assert restarted.get(protocol.experiment_id) == accessed
    with pytest.raises(ValueError, match="budget exhausted"):
        restarted.record_validation_access(
            protocol.experiment_id,
            expected_version=accessed.version,
            idempotency_key="pg-exp-over-budget",
        )


def test_postgres_decision_lifecycle_is_atomic_idempotent_and_restorable(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresDecisionLifecycleRepository(postgres_factory)
    service = DecisionLifecycleService(repository)
    opportunity, candidate, signal, forecast = _create(service)
    kwargs = {
        "expected_version": 0,
        "supporting_evidence": _evidence(candidate, signal, forecast),
        "invalidation_conditions": _conditions(),
        "time_invalidation": CREATED + timedelta(days=5),
        "actor": "approver-a",
        "reason": "approved for PostgreSQL parity",
        "confirmed_at": CREATED + timedelta(minutes=5),
        "idempotency_key": "pg-confirm-opportunity",
    }
    thesis = service.confirm_opportunity(opportunity.opportunity_id, **kwargs)
    assert service.confirm_opportunity(opportunity.opportunity_id, **kwargs) == thesis

    restored = PostgresDecisionLifecycleRepository(postgres_factory)
    assert restored.get_opportunity(opportunity.opportunity_id).state is (
        OpportunityState.CONFIRMED_TO_THESIS
    )
    assert restored.get_thesis(thesis.thesis_id) == thesis
    assert thesis.state is ThesisState.APPROVED


def test_postgres_portfolio_risk_is_durable_and_manual_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresPortfolioDecisionRepository(postgres_factory)
    service = PortfolioRiskApplicationService(repository)
    thesis = _thesis(1, "000001.SZ")
    portfolio, risk = service.run(
        theses=(thesis,),
        allocations=(_allocation(thesis),),
        current_positions=(_position(thesis.symbol),),
        account_snapshot=_account(),
        risk_budget=_budget(),
        mode=PortfolioOutputMode.MANUAL_CONFIRMATION,
        actor="risk-operator-a",
        reason="PostgreSQL parity",
        portfolio_created_at=PORTFOLIO_NOW,
        risk_started_at=PORTFOLIO_NOW,
        risk_completed_at=PORTFOLIO_NOW + timedelta(seconds=1),
        idempotency_key="pg-portfolio-risk",
    )
    restored = PostgresPortfolioDecisionRepository(postgres_factory)
    assert risk.state is RiskDecisionState.APPROVED
    assert risk.approved_for_manual_intent
    assert restored.get_portfolio(portfolio.decision_id) == portfolio
    assert restored.get_risk(risk.risk_decision_id) == risk


def test_postgres_manual_execution_rebuilds_only_from_recorded_fills(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresManualExecutionRepository(postgres_factory)
    service = ManualExecutionApplicationService(repository)
    trade = _trade(service, key="pg-create-manual-trade")
    partial, first = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="pg-external-fill-1",
        quantity=40,
        price=10.0,
        fees=1.0,
        occurred_at=EXECUTION_NOW + timedelta(minutes=1),
        recorded_at=EXECUTION_NOW + timedelta(minutes=1, seconds=1),
        actor="human-trader-a",
        reason="PostgreSQL first partial fill",
        idempotency_key="pg-fill-command-1",
    )
    duplicate, duplicate_fill = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="pg-external-fill-1",
        quantity=40,
        price=10.0,
        fees=1.0,
        occurred_at=EXECUTION_NOW + timedelta(minutes=1),
        recorded_at=EXECUTION_NOW + timedelta(minutes=1, seconds=1),
        actor="human-trader-a",
        reason="PostgreSQL first partial fill",
        idempotency_key="pg-fill-command-1",
    )
    assert partial.state is ManualOrderState.PARTIALLY_FILLED
    assert (duplicate, duplicate_fill) == (partial, first)

    filled, _ = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="pg-external-fill-2",
        quantity=60,
        price=10.1,
        fees=1.0,
        occurred_at=EXECUTION_NOW + timedelta(minutes=2),
        recorded_at=EXECUTION_NOW + timedelta(minutes=2, seconds=1),
        actor="human-trader-a",
        reason="PostgreSQL final partial fill",
        idempotency_key="pg-fill-command-2",
    )
    assert filled.state is ManualOrderState.FILLED
    snapshot = ManualExecutionApplicationService(
        PostgresManualExecutionRepository(postgres_factory)
    ).rebuild_position(
        account_id="account-a",
        symbol="000001.SZ",
        as_of=EXECUTION_NOW + timedelta(minutes=3),
    )
    assert snapshot.state is PositionState.OPEN
    assert snapshot.total_quantity == 100


def test_postgres_complete_account_risk_and_traceable_execution_restart(
    tmp_path,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    complete_repository = PostgresCompleteAccountPortfolioRiskRepository(
        postgres_factory
    )
    complete_service = CompleteAccountPortfolioRiskApplicationService(
        complete_repository
    )
    thesis = _complete_account_thesis("000001.SZ")
    account = AuthoritativeAccountPortfolioSnapshot.create(
        account_id="account-pg",
        as_of=COMPLETE_ACCOUNT_NOW - timedelta(seconds=1),
        source_reference="PostgreSQL complete-account parity",
        net_asset_value=100_000.0,
        available_cash=100_000.0,
        all_positions=(),
        completeness=AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
        reconciliation_state=AccountReconciliationState.RECONCILED,
        version=1,
    )
    allocation = ThesisAllocationRequest(
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        theme_id="theme-pg",
        target_quantity=100,
        reference_price=10.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=1.0,
    )
    portfolio, risk = complete_service.run(
        theses=(thesis,),
        allocations=(allocation,),
        account_snapshot=account,
        configuration=_risk_configuration(),
        mode=PortfolioOutputMode.MANUAL_CONFIRMATION,
        actor="risk-operator-pg",
        reason="PostgreSQL complete-account parity",
        portfolio_created_at=COMPLETE_ACCOUNT_NOW,
        risk_started_at=COMPLETE_ACCOUNT_NOW,
        risk_completed_at=COMPLETE_ACCOUNT_NOW + timedelta(seconds=1),
        idempotency_key="pg-complete-account-risk",
    )
    restarted_complete = PostgresCompleteAccountPortfolioRiskRepository(
        postgres_factory
    )
    assert (
        restarted_complete.get_account_snapshot(str(account.snapshot_id)) == account
    )
    assert (
        restarted_complete.get_complete_account_portfolio(portfolio.decision_id)
        == portfolio
    )
    assert (
        restarted_complete.get_complete_account_risk(risk.risk_decision_id) == risk
    )

    trace_repository = PostgresTraceableManualExecutionRepository(postgres_factory)
    trace_service = TraceableManualExecutionApplicationService(trace_repository)
    authority = _trace_authority(tmp_path, index=11)
    book, trade = _create_traceable_trade(
        trace_service, authority, "pg-create-traceable-trade"
    )
    _, fill = trace_service.record_fill(
        trade.manual_trade_id,
        external_fill_id="pg-traceable-fill",
        quantity=100,
        price=10.0,
        fees=1.0,
        occurred_at=TRACE_NOW + timedelta(minutes=1),
        recorded_at=TRACE_NOW + timedelta(minutes=1, seconds=1),
        actor="manual-operator",
        reason="PostgreSQL traceable fill",
        idempotency_key="pg-traceable-fill-command",
    )
    snapshot = TraceableManualExecutionApplicationService(
        PostgresTraceableManualExecutionRepository(postgres_factory)
    ).rebuild_position(book.position_book_id, as_of=TRACE_NOW + timedelta(minutes=2))
    assert snapshot.source_manual_trade_ids == (trade.manual_trade_id,)
    assert snapshot.source_fill_ids == (fill.fill_id,)


def test_postgres_h4_and_h5_repositories_preserve_verified_bundles(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    risk_repository = PostgresRiskRouteRepository(postgres_factory)
    position, observation, configuration, decision = make_decision()
    risk_hash = canonical_hash(
        {"command": "PG_RISK_REDUCTION", "decision": decision.to_canonical_dict()}
    )
    assert risk_repository.save_reducing_decision(
        decision,
        position=position,
        execution_observation=observation,
        configuration=configuration,
        idempotency_key="pg-risk-reduction",
        command_hash=risk_hash,
    ) == decision
    assert PostgresRiskRouteRepository(
        postgres_factory
    ).get_verified_reducing_decision_bundle(decision.decision_id).decision == decision

    health_repository = PostgresThesisHealthRepository(postgres_factory)
    bundle = _bundle(make_h5_fixture())
    health = ThesisHealthObservationBuilder().build(bundle)
    command_hash = thesis_health_command_hash(bundle)
    assert health_repository.save_observation(
        health,
        input_bundle=bundle,
        idempotency_key="pg-thesis-health",
        command_hash=command_hash,
    ) == health
    verified = PostgresThesisHealthRepository(
        postgres_factory
    ).get_verified_thesis_health_bundle(health.observation_id)
    assert verified.observation == health
    assert verified.input_bundle == bundle


def test_postgres_h6_manifest_is_idempotent_and_restorable(
    tmp_path,
    daily_decision_fixture: DailyDecisionFixture,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    daily_path, supplemental_path, verified, command_hash = _publication(
        tmp_path, daily_decision_fixture
    )
    repository = PostgresCompositeOperationalRepository(postgres_factory)
    first = repository.save_manifest(
        verified,
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        idempotency_key="pg-h6-command",
        command_hash=command_hash,
    )
    second = repository.save_manifest(
        verified,
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        idempotency_key="pg-h6-command",
        command_hash=command_hash,
    )
    restarted = PostgresCompositeOperationalRepository(postgres_factory)
    assert first == second == verified
    assert restarted.get_manifest(verified.manifest.manifest_id) == verified
    assert restarted.get_source_package_paths(verified.manifest.manifest_id) == (
        daily_path.resolve(),
        supplemental_path.resolve(),
    )


__all__ = ["daily_decision_fixture"]
