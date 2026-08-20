from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import json

import psycopg
import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import (
    FillId,
    ManualTradeId,
    StrategyId,
)
from market_regime_alpha.execution.manual import FILL_SCHEMA, Fill, FillKind, TradeSide
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import (
    PostgresMigrator,
    load_packaged_migrations,
)
from market_regime_alpha.strategies.path_outcomes import (
    PathPriceObservation,
    measure_strategy_path,
)
from market_regime_alpha.strategies.feedback import (
    StrategyFeedbackArtifact,
    StrategyFeedbackKind,
    StrategyFeedbackStatus,
)
from market_regime_alpha.strategies.feedback_service import (
    close_strategy_feedback_loop,
)
from market_regime_alpha.strategies.contracts import (
    StrategyContract,
    StrategyFamily,
    StrategyRegistry,
    StrategyVersion,
)
from market_regime_alpha.strategies.portfolio import (
    CrossStrategyPortfolioPolicy,
    build_cross_strategy_portfolio,
)
from market_regime_alpha.strategies.postgres_repository import (
    PostgresMultiStrategyRepository,
)
from market_regime_alpha.strategies.runtime import MultiStrategyRuntime
from market_regime_alpha.strategies.sleeves import allocate_observed_fill
from tests.strategies.test_multi_strategy_runtime import NOW, _reference, _registry, _runtime_input


def _cycle_and_portfolio():
    registry = _registry()
    cycle = MultiStrategyRuntime(registry).execute(_runtime_input(registry.active_versions))
    portfolio = build_cross_strategy_portfolio(
        cycle=cycle,
        policy=CrossStrategyPortfolioPolicy(
            maximum_gross_weight=Decimal("0.50"),
            maximum_symbol_weight=Decimal("0.20"),
        ),
    )
    return registry, cycle, portfolio


def _with_swing_challenger(registry: StrategyRegistry) -> StrategyRegistry:
    incumbent = next(item for item in registry.contracts if item.family is StrategyFamily.SWING_STATE)
    challenger = StrategyContract.create(
        strategy_id=StrategyId("swing-state-challenger"),
        family=incumbent.family,
        semantic_version="1.0.0-challenger",
        objective="Swing State challenger with a stricter entry threshold.",
        universe_reference=incumbent.universe_reference,
        target_references=incumbent.target_references,
        decision_times=incumbent.decision_times,
        horizon_sessions=incumbent.horizon_sessions,
        candidate_policy_version=incumbent.candidate_policy_version,
        action_policy_version=incumbent.action_policy_version,
        portfolio_weighting=incumbent.portfolio_weighting,
        top_k=incumbent.top_k,
        strategy_budget=incumbent.strategy_budget,
        cost_model_reference=incumbent.cost_model_reference,
        evaluation_protocol_reference=incumbent.evaluation_protocol_reference,
        code_reference=incumbent.code_reference,
        configuration_reference=_reference(
            "CONFIGURATION",
            "swing-state-challenger",
        ),
        parameters=tuple((name, "0.55" if name == "minimum_entry_score" else value) for name, value in incumbent.parameters),
        limitations=incumbent.limitations,
    )
    return StrategyRegistry.create(
        contracts=(*registry.contracts, challenger),
        versions=(*registry.versions, StrategyVersion.activate(challenger)),
    )


def _fill() -> Fill:
    return Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId("fill-multi-strategy-pg"),
        manual_trade_id=ManualTradeId("trade-multi-strategy-pg"),
        account_id="account-a",
        symbol="000001.SZ",
        side=TradeSide.BUY,
        quantity=100,
        price=10.0,
        fees=0.0,
        occurred_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=1, seconds=1),
        actor="human-trader-a",
        reason="postgres allocation proof",
        external_fill_id="external-multi-strategy-pg",
        fill_kind=FillKind.EXECUTION,
        correction_of_fill_id=None,
    )


def _seed_fill(factory: PostgresConnectionFactory, fill: Fill) -> None:
    with factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO manual_trade_records(
                manual_trade_id, risk_decision_id, account_id, symbol, side,
                state, filled_quantity, aggregate_json, version
            ) VALUES (%s, 'risk-multi-strategy-pg', %s, %s, %s,
                      'FILLED', %s, '{}', 1)
            """,
            (
                str(fill.manual_trade_id),
                fill.account_id,
                fill.symbol,
                fill.side.value,
                fill.quantity,
            ),
        )
        connection.execute(
            """
            INSERT INTO manual_fills(
                fill_id, external_fill_id, manual_trade_id, account_id,
                symbol, fill_kind, correction_of_fill_id, fill_json,
                recorded_at, idempotency_key
            ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
            """,
            (
                str(fill.fill_id),
                fill.external_fill_id,
                str(fill.manual_trade_id),
                fill.account_id,
                fill.symbol,
                fill.fill_kind.value,
                json.dumps(fill.to_canonical_dict(), sort_keys=True),
                fill.recorded_at,
                "allocate-multi-strategy-pg",
            ),
        )
        connection.commit()


def test_migration_085_upgrades_084_forward_only_and_installs_business_tables(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:84]).apply_all(postgres_factory)

    applied = PostgresMigrator(migrations=migrations[:85]).apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT tablename FROM pg_catalog.pg_tables
                WHERE schemaname = current_schema()
                  AND tablename IN (
                    'strategy_contract', 'strategy_version',
                    'multi_strategy_cycle', 'strategy_run',
                    'strategy_gate_attribution', 'strategy_proposal',
                    'cross_strategy_portfolio_decision',
                    'cross_strategy_portfolio_line',
                    'strategy_fill_allocation_batch',
                    'strategy_fill_allocation', 'strategy_path_outcome',
                    'strategy_feedback_artifact'
                  )
                """
            ).fetchall()
        }
    assert tuple((item.version, item.name) for item in applied) == ((85, "multi_strategy_business_closure"),)
    assert len(tables) == 12


def test_migration_086_upgrades_085_with_one_fill_derived_outcome_table(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:85]).apply_all(postgres_factory)

    applied = PostgresMigrator(migrations=migrations[:86]).apply_all(
        postgres_factory
    )

    with postgres_factory.connection(read_only=True) as connection:
        table = connection.execute(
            """
            SELECT tablename FROM pg_catalog.pg_tables
            WHERE schemaname = current_schema()
              AND tablename = 'strategy_realized_outcome'
            """
        ).fetchone()
    assert tuple((item.version, item.name) for item in applied) == (
        (86, "stateful_strategy_lifecycle"),
    )
    assert table == ("strategy_realized_outcome",)


def test_migration_087_upgrades_086_without_a_parallel_ledger(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:86]).apply_all(postgres_factory)

    applied = PostgresMigrator(migrations=migrations[:87]).apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        strategy_columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'manual_trade_records'
                  AND column_name LIKE 'strategy_%'
                """
            ).fetchall()
        }
        outcome_columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'strategy_realized_outcome'
                  AND column_name IN (
                    'revision', 'supersedes_outcome_id',
                    'supersedes_outcome_hash'
                  )
                """
            ).fetchall()
        }
    assert tuple((item.version, item.name) for item in applied) == (
        (87, "strategy_execution_integrity"),
    )
    assert "strategy_authorization_id" in strategy_columns
    assert outcome_columns == {
        "revision",
        "supersedes_outcome_id",
        "supersedes_outcome_hash",
    }


def test_migration_088_extends_manual_trade_without_reservation_ledger(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:87]).apply_all(postgres_factory)

    applied = PostgresMigrator(migrations=migrations[:88]).apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'manual_trade_records'
                  AND column_name IN (
                    'strategy_execution_authority_version',
                    'strategy_reconciliation_id',
                    'strategy_price_owner_id',
                    'strategy_price_source_id',
                    'strategy_authorized_quantity'
                  )
                """
            ).fetchall()
        }
        reservation_tables = connection.execute(
            """
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name LIKE '%execution%reservation%'
            """
        ).fetchone()
    assert tuple((item.version, item.name) for item in applied) == ((88, "portfolio_execution_authority"),)
    assert columns == {
        "strategy_execution_authority_version",
        "strategy_reconciliation_id",
        "strategy_price_owner_id",
        "strategy_price_source_id",
        "strategy_authorized_quantity",
    }
    assert reservation_tables == (0,)


def test_registry_cycle_portfolio_and_replay_are_transactional_and_idempotent(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    registry, cycle, portfolio = _cycle_and_portfolio()
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(registry, created_at=NOW)

    with ThreadPoolExecutor(max_workers=4) as executor:
        stored = tuple(executor.map(lambda _: repository.save_cycle(cycle), range(4)))
    assert stored == (cycle,) * 4
    assert repository.save_portfolio(portfolio, created_at=NOW) == portfolio

    restarted = PostgresMultiStrategyRepository(postgres_factory, apply_migrations=False)
    assert restarted.load_registry() == registry
    assert restarted.get_cycle(cycle.cycle_id) == cycle
    assert restarted.get_portfolio(portfolio.decision_id) == portfolio

    with postgres_factory.connection() as connection:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            connection.execute("UPDATE strategy_proposal SET desired_weight = 0 WHERE true")


def test_legacy_unbound_fill_is_rejected_while_path_outcome_lineage_reloads(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    registry, cycle, portfolio = _cycle_and_portfolio()
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(registry, created_at=NOW)
    repository.save_cycle(cycle)
    repository.save_portfolio(portfolio, created_at=NOW)
    fill = _fill()
    _seed_fill(postgres_factory, fill)
    entry_lines = tuple(item for item in portfolio.lines if item.symbol == "000001.SZ")
    batch = allocate_observed_fill(
        fill=fill,
        allocations=(
            (
                entry_lines[0].strategy_version_reference,
                entry_lines[0].proposal_reference,
                60,
            ),
            (
                entry_lines[1].strategy_version_reference,
                entry_lines[1].proposal_reference,
                40,
            ),
        ),
    )
    run = next(item for item in cycle.runs if registry.family_for(item) is StrategyFamily.SWING_STATE)
    run_version = next(
        item
        for item in registry.versions
        if item.version_id == run.strategy_version_reference.artifact_id
    )
    outcome = measure_strategy_path(
        strategy_version_reference=run.strategy_version_reference,
        strategy_run_reference=RuntimeArtifactReference("STRATEGY_RUN", run.run_id, run.run_hash),
        dataset_reference=cycle.runtime_input.dataset_reference,
        target_reference=registry.contract_for(run_version).target_references[0],
        symbol="000001.SZ",
        decision_time=NOW,
        reference_price=Decimal("10"),
        target_return=Decimal("0.02"),
        stop_return=Decimal("0.02"),
        continuation_return=Decimal("0.01"),
        failure_return=Decimal("-0.01"),
        observations=(
            PathPriceObservation(
                observed_at=NOW + timedelta(days=3),
                session_offset=3,
                high=Decimal("10.30"),
                low=Decimal("9.90"),
                close=Decimal("10.20"),
            ),
        ),
        exit_time=None,
        exit_price=None,
        measured_at=NOW + timedelta(days=4),
    )

    with pytest.raises(ValueError, match="Strategy-authorized"):
        repository.save_fill_allocation(batch)
    assert repository.save_path_outcome(outcome) == outcome
    challenger_registry = _with_swing_challenger(registry)
    repository.register(challenger_registry, created_at=NOW)
    challenger_input = replace(
        _runtime_input(challenger_registry.active_versions),
        parent_tick_reference=_reference("CONTINUOUS_TICK", "challenger-tick"),
    )
    challenger_cycle = repository.save_cycle(MultiStrategyRuntime(challenger_registry).execute(challenger_input))
    challenger_version = next(
        item
        for item in challenger_registry.versions
        if challenger_registry.contract_for(item).strategy_id == StrategyId("swing-state-challenger")
    )
    challenger_run = next(
        item for item in challenger_cycle.runs if item.strategy_version_reference.artifact_id == challenger_version.version_id
    )
    challenger_outcome = measure_strategy_path(
        strategy_version_reference=challenger_run.strategy_version_reference,
        strategy_run_reference=RuntimeArtifactReference(
            "STRATEGY_RUN",
            challenger_run.run_id,
            challenger_run.run_hash,
        ),
        dataset_reference=challenger_cycle.runtime_input.dataset_reference,
        target_reference=(
            challenger_registry.contract_for(challenger_version).target_references[0]
        ),
        symbol="000001.SZ",
        decision_time=NOW,
        reference_price=Decimal("10"),
        target_return=Decimal("0.02"),
        stop_return=Decimal("0.02"),
        continuation_return=Decimal("0.01"),
        failure_return=Decimal("-0.01"),
        observations=(
            PathPriceObservation(
                observed_at=NOW + timedelta(days=3),
                session_offset=3,
                high=Decimal("10.25"),
                low=Decimal("9.95"),
                close=Decimal("10.15"),
            ),
        ),
        exit_time=None,
        exit_price=None,
        measured_at=NOW + timedelta(days=4),
    )
    repository.save_path_outcome(challenger_outcome)
    feedback = close_strategy_feedback_loop(
        repository=repository,
        incumbent_version_reference=run.strategy_version_reference,
        challenger_version_reference=challenger_run.strategy_version_reference,
        formal_pit=False,
        formal_oos=False,
        calibrated=False,
        net_economics_established=False,
        prospective_evidence=False,
        created_at=NOW + timedelta(days=5),
    )
    assert repository.list_fill_allocations(account_id="account-a") == ()
    assert repository.get_path_outcome(outcome.outcome_id) == outcome
    assert repository.list_feedback(
        strategy_version_id=run.strategy_version_reference.artifact_id,
        artifact_kind=StrategyFeedbackKind.ATTRIBUTION,
    ) == (feedback[0],)
    assert {
        item.artifact_id
        for item in repository.list_feedback(
            strategy_version_id=challenger_run.strategy_version_reference.artifact_id,
        )
    } == {item.artifact_id for item in feedback[1:]}
    unrelated_run = next(item for item in cycle.runs if registry.family_for(item) is StrategyFamily.OVERNIGHT)
    assert (
        repository.list_feedback(
            strategy_version_id=unrelated_run.strategy_version_reference.artifact_id,
        )
        == ()
    )


def test_fill_allocation_rejects_forged_or_unpersisted_physical_fill(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    registry, cycle, portfolio = _cycle_and_portfolio()
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(registry, created_at=NOW)
    repository.save_cycle(cycle)
    repository.save_portfolio(portfolio, created_at=NOW)
    line = next(item for item in portfolio.lines if item.symbol == "000001.SZ")
    batch = allocate_observed_fill(
        fill=_fill(),
        allocations=((line.strategy_version_reference, line.proposal_reference, 100),),
    )

    with pytest.raises(ValueError, match="observed Fill"):
        repository.save_fill_allocation(batch)


def test_path_outcome_rejects_cross_strategy_run_version_lineage(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    registry, cycle, _ = _cycle_and_portfolio()
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(registry, created_at=NOW)
    repository.save_cycle(cycle)
    swing_run = next(
        item
        for item in cycle.runs
        if registry.family_for(item) is StrategyFamily.SWING_STATE
    )
    overnight_run = next(
        item
        for item in cycle.runs
        if registry.family_for(item) is StrategyFamily.OVERNIGHT
    )
    swing_contract = registry.contract_for(
        next(
            item
            for item in registry.versions
            if item.version_id
            == swing_run.strategy_version_reference.artifact_id
        )
    )
    mismatched = measure_strategy_path(
        strategy_version_reference=overnight_run.strategy_version_reference,
        strategy_run_reference=RuntimeArtifactReference(
            "STRATEGY_RUN",
            swing_run.run_id,
            swing_run.run_hash,
        ),
        dataset_reference=cycle.runtime_input.dataset_reference,
        target_reference=swing_contract.target_references[0],
        symbol="000001.SZ",
        decision_time=NOW,
        reference_price=Decimal("10"),
        target_return=Decimal("0.02"),
        stop_return=Decimal("0.02"),
        continuation_return=Decimal("0.01"),
        failure_return=Decimal("-0.01"),
        observations=(
            PathPriceObservation(
                observed_at=NOW + timedelta(days=3),
                session_offset=3,
                high=Decimal("10.30"),
                low=Decimal("9.90"),
                close=Decimal("10.20"),
            ),
        ),
        exit_time=None,
        exit_price=None,
        measured_at=NOW + timedelta(days=4),
    )

    with pytest.raises(ValueError, match="Run/Version lineage"):
        repository.save_path_outcome(mismatched)


def test_fill_allocation_rejects_proposal_from_another_strategy_version(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    registry, cycle, portfolio = _cycle_and_portfolio()
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(registry, created_at=NOW)
    repository.save_cycle(cycle)
    repository.save_portfolio(portfolio, created_at=NOW)
    fill = _fill()
    _seed_fill(postgres_factory, fill)
    first, second = tuple(
        item for item in portfolio.lines if item.symbol == "000001.SZ"
    )
    cross_bound = allocate_observed_fill(
        fill=fill,
        allocations=(
            (
                first.strategy_version_reference,
                second.proposal_reference,
                60,
            ),
            (
                second.strategy_version_reference,
                first.proposal_reference,
                40,
            ),
        ),
    )

    with pytest.raises(ValueError, match="Proposal/Version lineage"):
        repository.save_fill_allocation(cross_bound)


def test_fill_allocation_rejects_side_that_disagrees_with_strategy_action(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    registry, cycle, portfolio = _cycle_and_portfolio()
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(registry, created_at=NOW)
    repository.save_cycle(cycle)
    repository.save_portfolio(portfolio, created_at=NOW)
    entry_line = next(
        item
        for item in portfolio.lines
        if item.symbol == "000001.SZ" and item.action.value == "ENTER"
    )
    sell = replace(
        _fill(),
        fill_id=FillId("fill-multi-strategy-invalid-side"),
        external_fill_id="external-multi-strategy-invalid-side",
        side=TradeSide.SELL,
    )
    _seed_fill(postgres_factory, sell)
    batch = allocate_observed_fill(
        fill=sell,
        allocations=((entry_line.strategy_version_reference, entry_line.proposal_reference, 100),),
    )

    with pytest.raises(ValueError, match="Fill side does not match Strategy action"):
        repository.save_fill_allocation(batch)


def test_feedback_service_rejects_caller_asserted_positive_qualification(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    registry, cycle, _ = _cycle_and_portfolio()
    challenger_registry = _with_swing_challenger(registry)
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(challenger_registry, created_at=NOW)
    incumbent = next(
        item
        for item in cycle.runs
        if registry.family_for(item) is StrategyFamily.SWING_STATE
    )
    challenger = next(
        item
        for item in challenger_registry.versions
        if challenger_registry.contract_for(item).strategy_id
        == StrategyId("swing-state-challenger")
    )

    with pytest.raises(ValueError, match="owner-resolved"):
        close_strategy_feedback_loop(
            repository=repository,
            incumbent_version_reference=incumbent.strategy_version_reference,
            challenger_version_reference=RuntimeArtifactReference(
                "STRATEGY_VERSION",
                challenger.version_id,
                challenger.version_hash,
            ),
            formal_pit=True,
            formal_oos=True,
            calibrated=True,
            net_economics_established=True,
            prospective_evidence=True,
            created_at=NOW + timedelta(days=3),
        )


def test_feedback_repository_rejects_cross_strategy_or_positive_caller_lineage(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    registry = _registry()
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(registry, created_at=NOW)
    first, second = registry.active_versions
    first_reference = RuntimeArtifactReference(
        "STRATEGY_VERSION",
        first.version_id,
        first.version_hash,
    )
    second_reference = RuntimeArtifactReference(
        "STRATEGY_VERSION",
        second.version_id,
        second.version_hash,
    )
    contaminated = StrategyFeedbackArtifact.create(
        artifact_kind=StrategyFeedbackKind.ATTRIBUTION,
        strategy_version_reference=first_reference,
        source_references=(second_reference,),
        status=StrategyFeedbackStatus.NOT_ESTIMABLE,
        metrics=(("outcome_count", "0"),),
        findings=("PATH_OUTCOME_NOT_AVAILABLE",),
        created_at=NOW + timedelta(days=1),
    )
    caller_positive = StrategyFeedbackArtifact.create(
        artifact_kind=StrategyFeedbackKind.QUALIFICATION_DECISION,
        strategy_version_reference=first_reference,
        source_references=(first_reference,),
        status=StrategyFeedbackStatus.NOT_QUALIFIED,
        metrics=(("formal_pit", "true"),),
        findings=("PRODUCTION_AUTHORIZED_FALSE",),
        created_at=NOW + timedelta(days=1),
    )

    with pytest.raises(ValueError, match="exact Strategy Version"):
        repository.save_feedback(contaminated)
    with pytest.raises(ValueError, match="owner-resolved"):
        repository.save_feedback(caller_positive)
