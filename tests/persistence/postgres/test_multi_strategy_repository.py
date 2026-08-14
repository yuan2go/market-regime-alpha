from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import json

import psycopg
import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import FillId, ManualTradeId
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

    applied = PostgresMigrator().apply_all(postgres_factory)

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


def test_fill_allocation_and_path_outcome_reload_with_exact_strategy_lineage(
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
    run = cycle.runs[0]
    outcome = measure_strategy_path(
        strategy_version_reference=run.strategy_version_reference,
        strategy_run_reference=RuntimeArtifactReference("STRATEGY_RUN", run.run_id, run.run_hash),
        dataset_reference=cycle.runtime_input.dataset_reference,
        target_reference=_reference("TARGET_DEFINITION", "overnight-path"),
        symbol="000001.SZ",
        decision_time=NOW,
        reference_price=Decimal("10"),
        target_return=Decimal("0.02"),
        stop_return=Decimal("0.02"),
        continuation_return=Decimal("0.01"),
        failure_return=Decimal("-0.01"),
        observations=(
            PathPriceObservation(
                observed_at=NOW + timedelta(days=1),
                session_offset=1,
                high=Decimal("10.30"),
                low=Decimal("9.90"),
                close=Decimal("10.20"),
            ),
        ),
        exit_time=None,
        exit_price=None,
        measured_at=NOW + timedelta(days=2),
    )

    assert repository.save_fill_allocation(batch) == batch
    assert repository.save_path_outcome(outcome) == outcome
    assert repository.list_fill_allocations(account_id="account-a") == (batch,)
    assert repository.get_path_outcome(outcome.outcome_id) == outcome


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
