from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
from threading import Barrier
from zoneinfo import ZoneInfo

import psycopg
import pytest

from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
    RuntimeTickReceipt,
)
from market_regime_alpha.application.continuous_research.multi_strategy import (
    MultiStrategyContinuousAdapter,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousRunState,
    ContinuousSessionPhase,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.decision_system.contracts import (
    FillDerivedPositionReference,
    ManualAccountObservation,
    ManualPositionObservation,
    ReconciliationTolerance,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.reconciliation import (
    reconcile_account,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import (
    PostgresStrategyShadowRepository,
)
from market_regime_alpha.application.trading_lifecycle.manual_execution import (
    ManualExecutionApplicationService,
)
from market_regime_alpha.application.trading_lifecycle.strategy_execution import (
    StrategyExecutionApplicationService,
)
from market_regime_alpha.cli.decision_system import main as decision_system_main
from market_regime_alpha.core.identity import ArtifactId, DatasetId, ManualTradeId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_authority import PITArtifactReference
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.data.postgres_trading_calendar import (
    PostgresPITTradingCalendarSnapshotRepository,
)
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    Fill,
    ManualOrderState,
    ManualTradeRecord,
)
from market_regime_alpha.execution.postgres_manual_repository import (
    ExecutionVersionConflictError,
)
from market_regime_alpha.execution.postgres_repository import (
    PostgresManualExecutionRepository,
)
from market_regime_alpha.market_data import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    FormalPitStatus,
    MarketDataDatasetArtifact,
    PriceAdjustmentPolicy,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.position.authority import PositionState
from market_regime_alpha.strategies.contracts import (
    CanonicalStrategyAction,
    MultiStrategyCycle,
    StrategyFamily,
    StrategyProposal,
)
from market_regime_alpha.strategies.defaults import (
    canonical_exploratory_strategy_registry,
)
from market_regime_alpha.strategies.portfolio import (
    CrossStrategyPortfolioDecision,
    CrossStrategyPortfolioPolicy,
)
from market_regime_alpha.strategies.postgres_repository import (
    PostgresMultiStrategyRepository,
)
from market_regime_alpha.strategies.runtime import MultiStrategyRuntime
from tests.persistence.postgres.pit_fixture import (
    FixturePITArtifactAuthorityResolver,
    MutableClock,
    fixture_provider_policy,
)
from tests.persistence.postgres.conftest import TEST_DATABASE_URL_ENV
from tests.persistence.postgres.test_continuous_research_journal import (
    NOW as JOURNAL_NOW,
    _command as journal_command,
    _tick as journal_tick,
)
from tests.strategies.test_multi_strategy_runtime import _candidate_set


ACCOUNT = "account-a"
SYMBOL = "000001.SZ"
HASH = canonical_hash({"stateful": "runtime-v2"})
TZ = ZoneInfo("Asia/Shanghai")
SESSION_TIMES = tuple(datetime(2026, 8, day, 14, 55, tzinfo=TZ).astimezone(UTC) for day in (14, 17, 18, 19, 20, 21, 24))


def _seed_calendar(
    factory: PostgresConnectionFactory,
) -> RuntimeArtifactReference:
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("stateful-calendar-dataset"),
        market="XSHG",
        calendar_version="stateful-calendar-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                trade_date=value.astimezone(TZ).date(),
                session_close=value.astimezone(TZ).replace(hour=15, minute=0),
            )
            for value in SESSION_TIMES
        ),
    )
    PostgresPITAuthority(
        factory,
        clock=MutableClock(SESSION_TIMES[0] - timedelta(minutes=5)),
        artifact_resolver=FixturePITArtifactAuthorityResolver(),
        provider_policy=fixture_provider_policy(),
    ).resolve_artifact(
        PITArtifactReference("TRADING_CALENDAR", calendar.artifact_id, calendar.content_hash),
        actor="stateful-runtime-test",
        reason="resolve exact multi-session calendar",
        idempotency_key="stateful-runtime-calendar-owner",
    )
    PostgresPITTradingCalendarSnapshotRepository(factory).record(calendar)
    return RuntimeArtifactReference("TRADING_CALENDAR", calendar.artifact_id, calendar.content_hash)


def _adapter(
    factory: PostgresConnectionFactory,
    *,
    portfolio_policy: CrossStrategyPortfolioPolicy | None = None,
) -> MultiStrategyContinuousAdapter:
    return MultiStrategyContinuousAdapter(
        repository=PostgresMultiStrategyRepository(
            factory,
            apply_migrations=False,
        ),
        portfolio_policy=(
            CrossStrategyPortfolioPolicy(
                maximum_gross_weight=Decimal("0.50"),
                maximum_symbol_weight=Decimal("0.20"),
            )
            if portfolio_policy is None
            else portfolio_policy
        ),
        strategy_shadow_repository=PostgresStrategyShadowRepository(
            factory,
            apply_migrations=False,
        ),
        account_id=ACCOUNT,
    )


def _request(
    day: int,
    calendar: RuntimeArtifactReference,
) -> ChildExecutionRequest:
    decision_time = SESSION_TIMES[day]
    return ChildExecutionRequest(
        trading_date=decision_time.astimezone(TZ).date(),
        as_of_time=decision_time,
        run_id=ArtifactId(f"stateful-continuous-run-{day}"),
        tick_id=ArtifactId(f"stateful-continuous-tick-{day}"),
        tick_sequence=1,
        claim_id=f"stateful-claim-{day}",
        fencing_token=1,
        tick_version=1,
        lease_acquired_at=decision_time - timedelta(minutes=1),
        lease_expires_at=decision_time + timedelta(minutes=5),
        heartbeat_at=decision_time - timedelta(seconds=30),
        provider_attempt_id=1,
        source_manifest_id=ArtifactId(f"stateful-source-{day}"),
        source_manifest_hash=HASH,
        evidence_commit_id=ArtifactId(f"stateful-evidence-{day}"),
        evidence_commit_hash=HASH,
        decision_id=ArtifactId(f"stateful-decision-{day}"),
        decision_hash=HASH,
        input_references=tuple(
            sorted(
                (
                    RuntimeArtifactReference(
                        "RESEARCH_SUMMARY",
                        ArtifactId(f"stateful-summary-{day}"),
                        HASH,
                    ),
                    calendar,
                ),
                key=lambda item: (
                    item.reference_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        ),
        configuration_references=(
            RuntimeArtifactReference(
                "CONFIGURATION",
                ArtifactId("stateful-configuration"),
                HASH,
            ),
        ),
        authority_mode=RuntimeAuthorityMode.SHADOW,
        run_hash=canonical_hash({"run": day}),
        tick_hash=canonical_hash({"tick": day}),
    )


def _upstream(day: int) -> ChildExecutionResult:
    return ChildExecutionResult(
        child_kind=ContinuousChildKind.DECISION_SYSTEM,
        child_run_id=ArtifactId(f"stateful-summary-run-{day}"),
        child_receipt_id=ArtifactId(f"stateful-summary-receipt-{day}"),
        child_receipt_hash=HASH,
        child_artifact_id=ArtifactId(f"stateful-summary-{day}"),
        child_artifact_hash=HASH,
        input_references=(
            RuntimeArtifactReference(
                "SUMMARY_INPUT",
                ArtifactId(f"stateful-summary-input-{day}"),
                HASH,
            ),
        ),
        configuration_references=(
            RuntimeArtifactReference(
                "SUMMARY_CONFIGURATION",
                ArtifactId("stateful-summary-configuration"),
                HASH,
            ),
        ),
    )


def _execute_day(
    factory: PostgresConnectionFactory,
    day: int,
    calendar: RuntimeArtifactReference,
    *,
    decision_price_bars: tuple[CanonicalMarketBar, ...] | None = None,
    portfolio_policy: CrossStrategyPortfolioPolicy | None = None,
) -> tuple[MultiStrategyCycle, CrossStrategyPortfolioDecision]:
    default_bar = _decision_price_bar(
        day=day,
        symbol=SYMBOL,
        observed_at=SESSION_TIMES[day],
        available_at=SESSION_TIMES[day],
    )
    price_bars = (
        (default_bar,) if decision_price_bars is None else decision_price_bars
    )
    price_dataset = MarketDataDatasetArtifact.create(
        decision_time=SESSION_TIMES[day],
        created_at=max(
            SESSION_TIMES[day],
            *(item.available_at for item in price_bars),
        ),
        bars=price_bars,
        expected_symbols=tuple(sorted({item.symbol for item in price_bars})),
        expected_timeframes=(Timeframe.MINUTE_1,),
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="stateful-price-raw-v1",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=(
            (
                ArtifactId(f"stateful-price-manifest-{day}"),
                canonical_hash({"stateful_price_manifest": day}),
            ),
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("ENGINEERING_FIXTURE_ONLY",),
    )
    result = _adapter(factory, portfolio_policy=portfolio_policy).execute(
        request=_request(day, calendar),
        candidate_set=_candidate_set(),
        dataset_reference=RuntimeArtifactReference(
            "DATASET",
            ArtifactId("stateful-dataset"),
            HASH,
        ),
        upstream=_upstream(day),
        decision_price_dataset=price_dataset,
    )
    repository = PostgresMultiStrategyRepository(factory, apply_migrations=False)
    if result.child_artifact_id is None:
        raise AssertionError("Strategy child did not persist Portfolio decision")
    return (
        repository.get_cycle(result.child_run_id),
        repository.get_portfolio(result.child_artifact_id),
    )


def _decision_price_bar(
    *,
    day: int,
    symbol: str,
    observed_at: datetime,
    available_at: datetime,
    price: Decimal = Decimal("10.00"),
) -> CanonicalMarketBar:
    return CanonicalMarketBar.create(
        symbol=symbol,
        exchange=Exchange(symbol.rsplit(".", 1)[1]),
        asset_type=AssetType.A_SHARE,
        timeframe=Timeframe.MINUTE_1,
        market_date=observed_at.astimezone(TZ).date(),
        event_start=observed_at - timedelta(minutes=1),
        event_end=observed_at,
        available_at=available_at,
        open=price,
        high=price,
        low=price,
        close=price,
        previous_close=price,
        volume=Decimal("10000"),
        volume_unit=VolumeUnit.SHARES,
        amount=price * Decimal("10000"),
        turnover_rate=None,
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_factor=Decimal("1"),
        trading_status=TradingStatus.TRADING,
        price_limit_state=PriceLimitState.NORMAL,
        source_artifact_id=ArtifactId(f"stateful-price-source-{day}-{symbol}"),
        source_content_hash=canonical_hash(
            {
                "stateful_price_source": day,
                "symbol": symbol,
                "observed_at": observed_at.isoformat(),
            }
        ),
    )


def _proposal(
    cycle: MultiStrategyCycle,
    *,
    family: StrategyFamily,
    action: CanonicalStrategyAction,
) -> StrategyProposal:
    registry = canonical_exploratory_strategy_registry()
    run = next(item for item in cycle.runs if registry.family_for(item) is family)
    return next(item for item in run.proposals if item.symbol == SYMBOL and item.action is action)


def _observe(
    factory: PostgresConnectionFactory,
    *,
    day: int,
    quantity: int,
    price: str,
    available_cash: str = "50000",
    total_equity: str = "100000",
    as_of_time: datetime | None = None,
    fill_ledger_complete: bool = True,
) -> ManualAccountObservation:
    observed_at = SESSION_TIMES[day] if as_of_time is None else as_of_time
    positions = (
        ()
        if quantity == 0
        else (
            ManualPositionObservation(
                symbol=SYMBOL,
                total_quantity=quantity,
                available_quantity=quantity,
                frozen_quantity=0,
                average_cost=Decimal("10"),
                observed_market_value=Decimal(quantity) * Decimal(price),
            ),
        )
    )
    observation = ManualAccountObservation.create(
        account_id=ACCOUNT,
        trading_date=observed_at.astimezone(TZ).date(),
        as_of_time=observed_at,
        total_equity=Decimal(total_equity),
        available_cash=Decimal(available_cash),
        frozen_cash=Decimal("0"),
        source="MANUAL_ACCOUNT_AUTHORITY",
        actor="stateful-operator",
        reason="stateful mark",
        notes="",
        idempotency_key=f"stateful-observation-{day}",
        revision=1,
        previous_observation_id=None,
        positions=positions,
        created_at=observed_at,
    )
    repository = PostgresDecisionSystemRepository(factory, clock=lambda: JOURNAL_NOW)
    persisted = repository.record_manual_observation(observation)
    journal = PostgresContinuousResearchJournal(factory, clock=lambda: JOURNAL_NOW)
    command = journal_command(
        code_revision="stateful-reconciliation",
        idempotency_key="stateful-reconciliation-runtime",
    )
    journal.create_or_get(command)
    tick = journal.admit_tick(
        journal_tick(command, minute=42 + day),
        session_phase=ContinuousSessionPhase.DECISION_WINDOW,
    )
    claim = journal.claim_tick(
        run_id=command.run_id,
        tick_id=tick.command.tick_id,
    )
    tolerance = ReconciliationTolerance.create(
        equity_tolerance=Decimal("0.01"),
        cash_tolerance=Decimal("0.01"),
        average_cost_tolerance=Decimal("0.000001"),
    )
    repository.record_reconciliation_tolerance(tolerance, claim=claim)
    fill_positions = (
        ()
        if quantity == 0
        else (
            FillDerivedPositionReference(
                snapshot_id=ArtifactId(f"stateful-position-snapshot-{day}"),
                snapshot_hash=canonical_hash({"stateful_position_snapshot": day, "quantity": quantity}),
                account_id=ACCOUNT,
                symbol=SYMBOL,
                as_of_time=observed_at,
                total_quantity=quantity,
                available_quantity=quantity,
                frozen_quantity=0,
                average_cost=Decimal("10"),
                source_fill_ids=(f"stateful-position-fill-{day}",),
                complete=fill_ledger_complete,
            ),
        )
    )
    report = reconcile_account(
        observation=persisted,
        positions=fill_positions,
        fill_ledger_head=canonical_hash({"stateful_fill_ledger": day, "quantity": quantity}),
        fill_ledger_complete=fill_ledger_complete,
        tolerance=tolerance,
        authoritative_total_equity=persisted.total_equity,
        authoritative_available_cash=persisted.available_cash,
        authoritative_frozen_cash=persisted.frozen_cash,
        as_of_time=observed_at,
        revision=1,
        previous_reconciliation_id=None,
        idempotency_key=f"stateful-reconciliation-{day}",
        created_at=observed_at,
    )
    persisted_report = repository.save_reconciliation(report, claim=claim)
    journal.complete_tick(
        claim=claim,
        receipt=RuntimeTickReceipt.create(
            claim=claim,
            input_references=(),
            output_references=(
                RuntimeArtifactReference(
                    "ACCOUNT_RECONCILIATION",
                    persisted_report.reconciliation_id,
                    persisted_report.content_hash,
                ),
            ),
            reason_codes=("STATEFUL_ACCOUNT_RECONCILED",),
            created_at=JOURNAL_NOW,
        ),
        run_state=ContinuousRunState.DECISION_WINDOW_OPEN,
    )
    return persisted


def _action(
    cycle: MultiStrategyCycle,
    family: StrategyFamily,
) -> CanonicalStrategyAction:
    registry = canonical_exploratory_strategy_registry()
    run = next(item for item in cycle.runs if registry.family_for(item) is family)
    return next(item.action for item in run.gate_attributions if item.symbol == SYMBOL)


def _intent(
    service: StrategyExecutionApplicationService,
    *,
    day: int,
    portfolio: CrossStrategyPortfolioDecision,
    proposal: StrategyProposal,
    calendar: RuntimeArtifactReference,
    quantity: int | None,
    key: str,
) -> ManualTradeRecord:
    return service.create_intent(
        portfolio_decision_id=portfolio.decision_id,
        proposal_id=proposal.proposal_id,
        trading_calendar_reference=calendar,
        lot_size=100,
        actor="stateful-operator",
        reason="accept canonical Strategy Proposal",
        created_at=SESSION_TIMES[day] + timedelta(seconds=1),
        idempotency_key=f"stateful-intent-{key}",
        operator_quantity=quantity,
        override_reason=(
            None
            if proposal.action is CanonicalStrategyAction.EXIT or quantity is None
            else "controlled engineering scenario below recommendation"
        ),
    )


def _partial_fills(
    service: StrategyExecutionApplicationService,
    *,
    trade: ManualTradeRecord,
    day: int,
    quantities: tuple[int, ...],
    price: float,
    key: str,
    expected_prior: int = 0,
) -> tuple[Fill, ...]:
    trade_id = trade.manual_trade_id
    fills: list[Fill] = []
    for index, quantity in enumerate(quantities, start=1):
        updated, fill, batches, _ = service.record_fill(
            trade_id,
            external_fill_id=f"stateful-external-{key}-{index}",
            quantity=quantity,
            price=price,
            fees=float(Decimal("0.01") * quantity),
            occurred_at=SESSION_TIMES[day] + timedelta(minutes=index),
            recorded_at=SESSION_TIMES[day] + timedelta(minutes=index, seconds=1),
            actor="stateful-operator",
            reason="observed partial Fill",
            idempotency_key=f"stateful-fill-{key}-{index}",
        )
        assert len(batches) == expected_prior + index
        assert service.reconcile_fill_allocations(trade_id) == batches
        fills.append(fill)
    assert updated.state is ManualOrderState.FILLED
    return tuple(fills)


def test_postgres_canonical_partial_fill_correction_recovery_and_replay(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    strategy_repository = PostgresMultiStrategyRepository(postgres_factory)
    strategy_repository.register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    execution = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )

    _observe(postgres_factory, day=0, quantity=0, price="0")
    day0, portfolio0 = _execute_day(postgres_factory, 0, calendar)
    assert _action(day0, StrategyFamily.OVERNIGHT) is CanonicalStrategyAction.ENTER
    assert _action(day0, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.ENTER
    overnight_entry = _intent(
        execution,
        day=0,
        portfolio=portfolio0,
        proposal=_proposal(
            day0,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.ENTER,
        ),
        calendar=calendar,
        quantity=100,
        key="overnight-entry",
    )
    swing_entry_proposal = _proposal(
        day0,
        family=StrategyFamily.SWING_STATE,
        action=CanonicalStrategyAction.ENTER,
    )
    swing_entry = _intent(
        execution,
        day=0,
        portfolio=portfolio0,
        proposal=swing_entry_proposal,
        calendar=calendar,
        quantity=100,
        key="swing-entry",
    )
    _partial_fills(
        execution,
        trade=overnight_entry,
        day=0,
        quantities=(30, 40, 30),
        price=10.0,
        key="overnight-entry",
    )
    retried_entry = _intent(
        execution,
        day=0,
        portfolio=portfolio0,
        proposal=_proposal(
            day0,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.ENTER,
        ),
        calendar=calendar,
        quantity=100,
        key="overnight-entry",
    )
    assert retried_entry.manual_trade_id == overnight_entry.manual_trade_id
    assert retried_entry.state is ManualOrderState.FILLED
    assert retried_entry.filled_quantity == 100
    _partial_fills(
        execution,
        trade=swing_entry,
        day=0,
        quantities=(30, 40, 30),
        price=10.0,
        key="swing-entry",
    )

    _observe(postgres_factory, day=1, quantity=200, price="10.00")
    day1, portfolio1 = _execute_day(postgres_factory, 1, calendar)
    assert _action(day1, StrategyFamily.OVERNIGHT) is CanonicalStrategyAction.EXIT
    assert _action(day1, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.HOLD
    assert {item.sessions_held for item in day1.runtime_input.positions} == {1}
    overnight_exit = _intent(
        execution,
        day=1,
        portfolio=portfolio1,
        proposal=_proposal(
            day1,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.EXIT,
        ),
        calendar=calendar,
        quantity=100,
        key="overnight-exit",
    )
    _partial_fills(
        execution,
        trade=overnight_exit,
        day=1,
        quantities=(20, 30, 50),
        price=10.0,
        key="overnight-exit",
    )

    _observe(postgres_factory, day=2, quantity=100, price="10.40")
    day2, portfolio2 = _execute_day(postgres_factory, 2, calendar)
    assert _action(day2, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.ADD
    swing_state = next(
        item
        for item in day2.runtime_input.positions
        if item.strategy_version_id == swing_entry_proposal.strategy_version_reference.artifact_id
    )
    assert swing_state.sessions_held == 2
    assert swing_state.peak_price == Decimal("10.40")
    swing_add = _intent(
        execution,
        day=2,
        portfolio=portfolio2,
        proposal=_proposal(
            day2,
            family=StrategyFamily.SWING_STATE,
            action=CanonicalStrategyAction.ADD,
        ),
        calendar=calendar,
        quantity=100,
        key="swing-add",
    )
    _partial_fills(
        execution,
        trade=swing_add,
        day=2,
        quantities=(30, 70),
        price=10.4,
        key="swing-add",
    )

    _observe(postgres_factory, day=3, quantity=200, price="10.50")
    day3, _ = _execute_day(postgres_factory, 3, calendar)
    assert _action(day3, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.HOLD
    assert next(item for item in day3.runtime_input.positions if item.symbol == SYMBOL).add_count == 1

    _observe(postgres_factory, day=4, quantity=200, price="9.90")
    day4, portfolio4 = _execute_day(postgres_factory, 4, calendar)
    assert _action(day4, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.REDUCE
    recovered_day4, recovered_portfolio4 = _execute_day(postgres_factory, 4, calendar)
    assert (recovered_day4, recovered_portfolio4) == (day4, portfolio4)
    swing_reduce = _intent(
        execution,
        day=4,
        portfolio=portfolio4,
        proposal=_proposal(
            day4,
            family=StrategyFamily.SWING_STATE,
            action=CanonicalStrategyAction.REDUCE,
        ),
        calendar=calendar,
        quantity=100,
        key="swing-reduce",
    )
    _partial_fills(
        execution,
        trade=swing_reduce,
        day=4,
        quantities=(20, 80),
        price=9.9,
        key="swing-reduce",
    )

    _observe(postgres_factory, day=5, quantity=100, price="9.00")
    day5, portfolio5 = _execute_day(postgres_factory, 5, calendar)
    assert _action(day5, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.EXIT
    final_state = next(item for item in day5.runtime_input.positions if item.symbol == SYMBOL)
    assert final_state.sessions_held == 5
    assert final_state.add_count == 1
    assert final_state.reduce_count == 1
    assert final_state.peak_price == Decimal("10.50")
    swing_exit_proposal = _proposal(
        day5,
        family=StrategyFamily.SWING_STATE,
        action=CanonicalStrategyAction.EXIT,
    )
    swing_exit = _intent(
        execution,
        day=5,
        portfolio=portfolio5,
        proposal=swing_exit_proposal,
        calendar=calendar,
        quantity=100,
        key="swing-exit",
    )

    # Fill persisted -> crash.  A fresh bridge reconstructs the missing
    # allocation from the immutable V4 ManualTrade authorization.
    raw_manual = ManualExecutionApplicationService(PostgresManualExecutionRepository(postgres_factory))
    _, crash_fill = raw_manual.record_fill(
        swing_exit.manual_trade_id,
        external_fill_id="stateful-external-swing-exit-1",
        quantity=20,
        price=9.0,
        fees=2.0,
        occurred_at=SESSION_TIMES[5] + timedelta(minutes=1),
        recorded_at=SESSION_TIMES[5] + timedelta(minutes=1, seconds=1),
        actor="stateful-operator",
        reason="persist before simulated crash",
        idempotency_key="stateful-fill-swing-exit-1",
    )
    _, preallocation_correction = raw_manual.record_fill(
        swing_exit.manual_trade_id,
        external_fill_id="stateful-external-swing-exit-1-correction",
        quantity=20,
        price=9.05,
        fees=1.5,
        occurred_at=crash_fill.occurred_at,
        recorded_at=SESSION_TIMES[5] + timedelta(minutes=1, seconds=2),
        actor="stateful-operator",
        reason="correct Fill before Strategy allocation",
        idempotency_key="stateful-fill-swing-exit-1-correction",
        correction_of_fill_id=crash_fill.fill_id,
    )
    assert preallocation_correction.correction_of_fill_id == crash_fill.fill_id
    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute(
            """
            SELECT count(*) FROM strategy_fill_allocation_batch
            WHERE source_fill_id IN (%s, %s)
            """,
            (str(crash_fill.fill_id), str(preallocation_correction.fill_id)),
        ).fetchone() == (0,)
    restarted_execution = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    assert len(restarted_execution.reconcile_fill_allocations(swing_exit.manual_trade_id)) == 2
    remaining_exit_fills = _partial_fills(
        restarted_execution,
        trade=swing_exit,
        day=5,
        quantities=(30, 50),
        price=9.0,
        key="swing-exit-recovered",
        expected_prior=2,
    )

    physical = raw_manual.rebuild_position(
        account_id=ACCOUNT,
        symbol=SYMBOL,
        as_of=SESSION_TIMES[5] + timedelta(minutes=4),
    )
    assert physical.state is PositionState.CLOSED
    assert physical.total_quantity == 0

    _observe(postgres_factory, day=6, quantity=0, price="0")
    day6, _ = _execute_day(postgres_factory, 6, calendar)
    assert day6.runtime_input.positions == ()
    shadow = PostgresStrategyShadowRepository(
        postgres_factory,
        apply_migrations=False,
    )
    initial_outcomes = shadow.settle_multi_strategy_outcomes(
        account_id=ACCOUNT,
        decision_time=SESSION_TIMES[6],
    )
    assert len(initial_outcomes) == 2
    swing_initial = next(
        item
        for item in initial_outcomes
        if item.strategy_version_reference.artifact_id == swing_exit_proposal.strategy_version_reference.artifact_id
    )
    assert swing_initial.revision == 1
    assert swing_initial.supersedes_outcome_reference is None

    corrected_target = remaining_exit_fills[-1]
    correction_barrier = Barrier(2)

    def correct_exit_fill() -> tuple[
        ManualTradeRecord,
        Fill,
        tuple[object, ...],
        tuple[object, ...],
    ]:
        correction_barrier.wait()
        return restarted_execution.record_fill(
            swing_exit.manual_trade_id,
            external_fill_id="stateful-external-swing-exit-correction",
            quantity=corrected_target.quantity,
            price=9.1,
            fees=4.0,
            occurred_at=corrected_target.occurred_at,
            recorded_at=SESSION_TIMES[6] + timedelta(minutes=1),
            actor="stateful-operator",
            reason="correct observed exit economics",
            idempotency_key="stateful-fill-swing-exit-correction",
            correction_of_fill_id=corrected_target.fill_id,
        )

    def settle_while_correcting() -> tuple[object, ...]:
        correction_barrier.wait()
        return shadow.settle_multi_strategy_outcomes(
            account_id=ACCOUNT,
            decision_time=SESSION_TIMES[6] + timedelta(minutes=2),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        correction_future = executor.submit(correct_exit_fill)
        settlement_future = executor.submit(settle_while_correcting)
    _, correction, _, _ = correction_future.result()
    try:
        settlement_future.result()
    except ValueError as exc:
        assert "RECONCILIATION_REQUIRED" in str(exc)
    corrected_outcomes = shadow.settle_multi_strategy_outcomes(
        account_id=ACCOUNT,
        decision_time=SESSION_TIMES[6] + timedelta(minutes=2),
    )
    assert correction.correction_of_fill_id == corrected_target.fill_id
    swing_corrected = next(
        item
        for item in corrected_outcomes
        if item.strategy_version_reference.artifact_id == swing_exit_proposal.strategy_version_reference.artifact_id
    )
    assert swing_corrected.revision == 2
    assert swing_corrected.supersedes_outcome_reference == RuntimeArtifactReference(
        "STRATEGY_REALIZED_OUTCOME",
        swing_initial.outcome_id,
        swing_initial.outcome_hash,
    )
    assert swing_corrected.net_pnl != swing_initial.net_pnl
    assert shadow.get_multi_strategy_outcome(swing_initial.outcome_id) == swing_initial

    current = shadow.settle_multi_strategy_outcomes(
        account_id=ACCOUNT,
        decision_time=SESSION_TIMES[6] + timedelta(minutes=2),
    )
    assert len(current) == 2
    assert swing_corrected in current
    with ThreadPoolExecutor(max_workers=4) as executor:
        concurrent = tuple(
            executor.map(
                lambda _: PostgresStrategyShadowRepository(
                    postgres_factory,
                    apply_migrations=False,
                ).settle_multi_strategy_outcomes(
                    account_id=ACCOUNT,
                    decision_time=SESSION_TIMES[6] + timedelta(minutes=2),
                ),
                range(4),
            )
        )
    assert concurrent == (current,) * 4
    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM strategy_realized_outcome WHERE account_id = %s",
            (ACCOUNT,),
        ).fetchone() == (3,)
        assert connection.execute(
            """
            SELECT count(*) FROM strategy_realized_outcome AS current
            WHERE account_id = %s
              AND NOT EXISTS (
                  SELECT 1 FROM strategy_realized_outcome AS successor
                  WHERE successor.supersedes_outcome_id = current.outcome_id
              )
            """,
            (ACCOUNT,),
        ).fetchone() == (2,)
    with (
        postgres_factory.connection() as connection,
        pytest.raises(psycopg.errors.RaiseException, match="append-only"),
    ):
        connection.execute(
            "UPDATE strategy_realized_outcome SET net_pnl = 0 WHERE account_id = %s",
            (ACCOUNT,),
        )

    replayed = MultiStrategyRuntime(canonical_exploratory_strategy_registry()).execute(day5.runtime_input)
    assert replayed == day5
    assert strategy_repository.get_cycle(day5.cycle_id) == day5


def test_strategy_execution_bridge_rejects_wrong_account(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(postgres_factory, day=0, quantity=0, price="0")
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    proposal = _proposal(
        cycle,
        family=StrategyFamily.OVERNIGHT,
        action=CanonicalStrategyAction.ENTER,
    )
    wrong_account = StrategyExecutionApplicationService(
        postgres_factory,
        account_id="account-b",
    )
    with pytest.raises(ValueError, match="DATA_INSUFFICIENT"):
        _intent(
            wrong_account,
            day=0,
            portfolio=portfolio,
            proposal=proposal,
            calendar=calendar,
            quantity=100,
            key="wrong-account",
        )
    correct = _intent(
        StrategyExecutionApplicationService(
            postgres_factory,
            account_id=ACCOUNT,
        ),
        day=0,
        portfolio=portfolio,
        proposal=proposal,
        calendar=calendar,
        quantity=100,
        key="account-bound-intent",
    )
    with pytest.raises(ValueError, match="different intent"):
        _intent(
            wrong_account,
            day=0,
            portfolio=portfolio,
            proposal=proposal,
            calendar=calendar,
            quantity=100,
            key="account-bound-intent",
        )
    with pytest.raises(ValueError, match="does not match Strategy execution authority"):
        wrong_account.record_fill(
            correct.manual_trade_id,
            external_fill_id="wrong-account-fill",
            quantity=100,
            price=10.0,
            fees=1.0,
            occurred_at=SESSION_TIMES[0] + timedelta(minutes=1),
            recorded_at=SESSION_TIMES[0] + timedelta(minutes=1, seconds=1),
            actor="stateful-operator",
            reason="must fail before Fill persistence",
            idempotency_key="wrong-account-fill",
        )
    assert PostgresManualExecutionRepository(postgres_factory).fills_for_trade(correct.manual_trade_id) == ()


def test_same_proposal_different_commands_cannot_reuse_execution_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(postgres_factory, day=0, quantity=0, price="0")
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    proposal = _proposal(
        cycle,
        family=StrategyFamily.OVERNIGHT,
        action=CanonicalStrategyAction.ENTER,
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    first = _intent(
        service,
        day=0,
        portfolio=portfolio,
        proposal=proposal,
        calendar=calendar,
        quantity=None,
        key="proposal-authority-a",
    )
    assert first.state is ManualOrderState.RECORDED

    with pytest.raises(ValueError, match="Proposal remaining authority"):
        service.create_intent(
            portfolio_decision_id=portfolio.decision_id,
            proposal_id=proposal.proposal_id,
            trading_calendar_reference=calendar,
            lot_size=100,
            actor="stateful-operator",
            reason="accept canonical Strategy Proposal",
            created_at=SESSION_TIMES[0] + timedelta(seconds=2),
            idempotency_key="stateful-intent-proposal-authority-b",
            operator_quantity=100,
            override_reason="controlled engineering scenario below recommendation",
        )


def test_partial_fill_cancel_correction_and_replacement_use_remaining_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(postgres_factory, day=0, quantity=0, price="0")
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    proposal = _proposal(
        cycle,
        family=StrategyFamily.OVERNIGHT,
        action=CanonicalStrategyAction.ENTER,
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    first = _intent(
        service,
        day=0,
        portfolio=portfolio,
        proposal=proposal,
        calendar=calendar,
        quantity=None,
        key="replacement-a",
    )
    authorization = first.strategy_execution_authorization
    assert authorization is not None
    assert authorization.reference_price == Decimal("10.00")
    partial, execution_fill, _, _ = service.record_fill(
        first.manual_trade_id,
        external_fill_id="replacement-fill-a",
        quantity=100,
        price=10.0,
        fees=1.0,
        occurred_at=SESSION_TIMES[0] + timedelta(minutes=1),
        recorded_at=SESSION_TIMES[0] + timedelta(minutes=1, seconds=1),
        actor="stateful-operator",
        reason="partial observed Fill",
        idempotency_key="replacement-fill-a",
    )
    cancelled = service.mark_intent_state(
        first.manual_trade_id,
        expected_version=partial.version,
        state=ManualOrderState.CANCELLED,
        actor="stateful-operator",
        reason="release unfilled reservation",
        changed_at=SESSION_TIMES[0] + timedelta(minutes=2),
        idempotency_key="replacement-cancel-a",
    )
    corrected, correction, _, _ = service.record_fill(
        first.manual_trade_id,
        external_fill_id="replacement-fill-a-correction",
        quantity=200,
        price=10.0,
        fees=1.5,
        occurred_at=execution_fill.occurred_at,
        recorded_at=SESSION_TIMES[0] + timedelta(minutes=2, seconds=1),
        actor="stateful-operator",
        reason="broker corrected effective Fill quantity",
        idempotency_key="replacement-fill-a-correction",
        correction_of_fill_id=execution_fill.fill_id,
    )
    assert cancelled.state is ManualOrderState.CANCELLED
    assert corrected.state is ManualOrderState.CANCELLED
    assert correction.correction_of_fill_id == execution_fill.fill_id
    inspection = service.inspect_proposal_execution(proposal.proposal_id)
    assert inspection["effective_filled_quantity"] == 200
    assert inspection["reserved_quantity"] == 0
    assert inspection["released_quantity"] == (authorization.recommended_quantity - 200)
    remaining = int(inspection["remaining_quantity"])
    replacement = _intent(
        service,
        day=0,
        portfolio=portfolio,
        proposal=proposal,
        calendar=calendar,
        quantity=remaining,
        key="replacement-b",
    )
    assert replacement.intended_quantity == remaining
    with pytest.raises(ValueError, match="Proposal remaining authority"):
        _intent(
            service,
            day=0,
            portfolio=portfolio,
            proposal=proposal,
            calendar=calendar,
            quantity=100,
            key="replacement-c",
        )


def test_partial_exit_cancel_replacement_consumes_only_remaining_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    _observe(postgres_factory, day=0, quantity=0, price="0")
    day0, portfolio0 = _execute_day(postgres_factory, 0, calendar)
    entry = _intent(
        service,
        day=0,
        portfolio=portfolio0,
        proposal=_proposal(
            day0,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.ENTER,
        ),
        calendar=calendar,
        quantity=200,
        key="exit-replacement-entry",
    )
    _partial_fills(
        service,
        trade=entry,
        day=0,
        quantities=(200,),
        price=10.0,
        key="exit-replacement-entry",
    )

    _observe(postgres_factory, day=1, quantity=200, price="10.00")
    day1, portfolio1 = _execute_day(postgres_factory, 1, calendar)
    exit_proposal = _proposal(
        day1,
        family=StrategyFamily.OVERNIGHT,
        action=CanonicalStrategyAction.EXIT,
    )
    first_exit = _intent(
        service,
        day=1,
        portfolio=portfolio1,
        proposal=exit_proposal,
        calendar=calendar,
        quantity=200,
        key="exit-replacement-a",
    )
    partial, _, _, _ = service.record_fill(
        first_exit.manual_trade_id,
        external_fill_id="exit-replacement-fill-a",
        quantity=100,
        price=10.0,
        fees=1.0,
        occurred_at=SESSION_TIMES[1] + timedelta(minutes=1),
        recorded_at=SESSION_TIMES[1] + timedelta(minutes=1, seconds=1),
        actor="stateful-operator",
        reason="partial EXIT Fill",
        idempotency_key="exit-replacement-fill-a",
    )
    service.mark_intent_state(
        first_exit.manual_trade_id,
        expected_version=partial.version,
        state=ManualOrderState.CANCELLED,
        actor="stateful-operator",
        reason="replace unfilled EXIT remainder",
        changed_at=SESSION_TIMES[1] + timedelta(minutes=2),
        idempotency_key="exit-replacement-cancel-a",
    )
    replacement = service.create_intent(
        portfolio_decision_id=portfolio1.decision_id,
        proposal_id=exit_proposal.proposal_id,
        trading_calendar_reference=calendar,
        lot_size=100,
        actor="stateful-operator",
        reason="replace remaining EXIT authority",
        created_at=SESSION_TIMES[1] + timedelta(minutes=2, seconds=1),
        idempotency_key="exit-replacement-b",
        operator_quantity=100,
        override_reason="replacement consumes only unfilled EXIT authority",
    )
    assert replacement.intended_quantity == 100
    inspection = service.inspect_proposal_execution(exit_proposal.proposal_id)
    assert inspection["effective_filled_quantity"] == 100
    assert inspection["reserved_quantity"] == 100
    assert inspection["remaining_quantity"] == 0


def test_account_cash_reservation_rejects_reuse_and_release_restores_budget(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(
        postgres_factory,
        day=0,
        quantity=0,
        price="0",
        available_cash="5000",
    )
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    overnight = _proposal(
        cycle,
        family=StrategyFamily.OVERNIGHT,
        action=CanonicalStrategyAction.ENTER,
    )
    swing = _proposal(
        cycle,
        family=StrategyFamily.SWING_STATE,
        action=CanonicalStrategyAction.ENTER,
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    first = _intent(
        service,
        day=0,
        portfolio=portfolio,
        proposal=overnight,
        calendar=calendar,
        quantity=None,
        key="cash-a",
    )
    with pytest.raises(ValueError, match="Account available cash authority"):
        _intent(
            service,
            day=0,
            portfolio=portfolio,
            proposal=swing,
            calendar=calendar,
            quantity=None,
            key="cash-b-blocked",
        )
    service.mark_intent_state(
        first.manual_trade_id,
        expected_version=first.version,
        state=ManualOrderState.CANCELLED,
        actor="stateful-operator",
        reason="release account cash reservation",
        changed_at=SESSION_TIMES[0] + timedelta(minutes=1),
        idempotency_key="cash-a-cancel",
    )
    second = _intent(
        service,
        day=0,
        portfolio=portfolio,
        proposal=swing,
        calendar=calendar,
        quantity=None,
        key="cash-b-released",
    )
    assert second.state is ManualOrderState.RECORDED


def test_same_symbol_reservations_across_strategies_share_symbol_budget(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(
        postgres_factory,
        day=0,
        quantity=200,
        price="10.00",
        available_cash="50000",
    )
    cycle, portfolio = _execute_day(
        postgres_factory,
        0,
        calendar,
        portfolio_policy=CrossStrategyPortfolioPolicy(
            maximum_gross_weight=Decimal("0.50"),
            maximum_symbol_weight=Decimal("0.10"),
        ),
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    first = _intent(
        service,
        day=0,
        portfolio=portfolio,
        proposal=_proposal(
            cycle,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.ENTER,
        ),
        calendar=calendar,
        quantity=None,
        key="cross-strategy-symbol-a",
    )
    assert first.intended_quantity > 0
    with pytest.raises(
        ValueError,
        match="Projected post-trade symbol exposure",
    ):
        _intent(
            service,
            day=0,
            portfolio=portfolio,
            proposal=_proposal(
                cycle,
                family=StrategyFamily.SWING_STATE,
                action=CanonicalStrategyAction.ENTER,
            ),
            calendar=calendar,
            quantity=None,
            key="cross-strategy-symbol-b",
        )


def test_concurrent_account_cash_reservation_serializes_across_proposals(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(
        postgres_factory,
        day=0,
        quantity=0,
        price="0",
        available_cash="5000",
    )
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    proposals = (
        _proposal(
            cycle,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.ENTER,
        ),
        _proposal(
            cycle,
            family=StrategyFamily.SWING_STATE,
            action=CanonicalStrategyAction.ENTER,
        ),
    )

    def create(index: int) -> ManualTradeRecord:
        return _intent(
            StrategyExecutionApplicationService(
                postgres_factory,
                account_id=ACCOUNT,
            ),
            day=0,
            portfolio=portfolio,
            proposal=proposals[index],
            calendar=calendar,
            quantity=None,
            key=f"cash-race-{index}",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(executor.submit(create, index) for index in range(2))
    successes: list[ManualTradeRecord] = []
    failures: list[BaseException] = []
    for future in futures:
        try:
            successes.append(future.result())
        except BaseException as exc:
            failures.append(exc)
    assert len(successes) == 1
    assert len(failures) == 1
    assert "Account available cash authority" in str(failures[0])


def test_concurrent_same_proposal_intents_share_one_remaining_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(postgres_factory, day=0, quantity=0, price="0")
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    proposal = _proposal(
        cycle,
        family=StrategyFamily.OVERNIGHT,
        action=CanonicalStrategyAction.ENTER,
    )

    def create(index: int) -> ManualTradeRecord:
        return _intent(
            StrategyExecutionApplicationService(
                postgres_factory,
                account_id=ACCOUNT,
            ),
            day=0,
            portfolio=portfolio,
            proposal=proposal,
            calendar=calendar,
            quantity=None,
            key=f"proposal-race-{index}",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(executor.submit(create, index) for index in range(2))
    results: list[ManualTradeRecord] = []
    errors: list[BaseException] = []
    for future in futures:
        try:
            results.append(future.result())
        except BaseException as exc:
            errors.append(exc)
    assert len(results) == 1
    assert len(errors) == 1
    assert "Proposal remaining authority" in str(errors[0])


def test_fill_cancel_race_preserves_fill_and_reconstructs_remaining_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(postgres_factory, day=0, quantity=0, price="0")
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    proposal = _proposal(
        cycle,
        family=StrategyFamily.OVERNIGHT,
        action=CanonicalStrategyAction.ENTER,
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    intent = _intent(
        service,
        day=0,
        portfolio=portfolio,
        proposal=proposal,
        calendar=calendar,
        quantity=None,
        key="fill-cancel-race",
    )
    barrier = Barrier(2)

    def record_fill() -> ManualTradeRecord:
        barrier.wait()
        updated, _, _, _ = StrategyExecutionApplicationService(
            postgres_factory,
            account_id=ACCOUNT,
        ).record_fill(
            intent.manual_trade_id,
            external_fill_id="fill-cancel-race-fill",
            quantity=100,
            price=10.0,
            fees=1.0,
            occurred_at=SESSION_TIMES[0] + timedelta(minutes=1),
            recorded_at=SESSION_TIMES[0] + timedelta(minutes=1, seconds=1),
            actor="stateful-operator",
            reason="Fill observed while cancellation was in flight",
            idempotency_key="fill-cancel-race-fill",
        )
        return updated

    def cancel() -> ManualTradeRecord:
        barrier.wait()
        return StrategyExecutionApplicationService(
            postgres_factory,
            account_id=ACCOUNT,
        ).mark_intent_state(
            intent.manual_trade_id,
            expected_version=intent.version,
            state=ManualOrderState.CANCELLED,
            actor="stateful-operator",
            reason="cancel unfilled remainder",
            changed_at=SESSION_TIMES[0] + timedelta(minutes=1),
            idempotency_key="fill-cancel-race-cancel",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        fill_future = executor.submit(record_fill)
        cancel_future = executor.submit(cancel)
    fill_future.result()
    try:
        cancel_future.result()
    except ExecutionVersionConflictError:
        pass
    except ValueError as exc:
        assert str(exc) == "stale ManualTradeRecord version"

    execution = PostgresManualExecutionRepository(postgres_factory)
    current = execution.get_trade(intent.manual_trade_id)
    assert current.filled_quantity == 100
    if current.state is not ManualOrderState.CANCELLED:
        current = service.mark_intent_state(
            intent.manual_trade_id,
            expected_version=current.version,
            state=ManualOrderState.CANCELLED,
            actor="stateful-operator",
            reason="retry cancellation after serialized Fill",
            changed_at=SESSION_TIMES[0] + timedelta(minutes=2),
            idempotency_key="fill-cancel-race-cancel-retry",
        )
    assert current.state is ManualOrderState.CANCELLED
    inspection = service.inspect_proposal_execution(proposal.proposal_id)
    assert inspection["effective_filled_quantity"] == 100
    assert inspection["reserved_quantity"] == 0
    assert inspection["remaining_quantity"] == (
        inspection["authorized_quantity"] - 100
    )


def test_fill_correction_and_position_resolution_share_account_boundary(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    _observe(postgres_factory, day=0, quantity=0, price="0")
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    proposal = _proposal(
        cycle,
        family=StrategyFamily.SWING_STATE,
        action=CanonicalStrategyAction.ENTER,
    )
    intent = _intent(
        service,
        day=0,
        portfolio=portfolio,
        proposal=proposal,
        calendar=calendar,
        quantity=200,
        key="position-correction-entry",
    )
    _, execution_fill, _, _ = service.record_fill(
        intent.manual_trade_id,
        external_fill_id="position-correction-execution",
        quantity=100,
        price=10.0,
        fees=1.0,
        occurred_at=SESSION_TIMES[0] + timedelta(minutes=1),
        recorded_at=SESSION_TIMES[0] + timedelta(minutes=1, seconds=1),
        actor="stateful-operator",
        reason="partial Fill before correction race",
        idempotency_key="position-correction-execution",
    )
    _observe(postgres_factory, day=1, quantity=200, price="10.00")
    barrier = Barrier(2)

    def correct_fill() -> None:
        barrier.wait()
        StrategyExecutionApplicationService(
            postgres_factory,
            account_id=ACCOUNT,
        ).record_fill(
            intent.manual_trade_id,
            external_fill_id="position-correction-head",
            quantity=200,
            price=10.0,
            fees=2.0,
            occurred_at=execution_fill.occurred_at,
            recorded_at=SESSION_TIMES[1] + timedelta(minutes=1),
            actor="stateful-operator",
            reason="correct effective position quantity",
            idempotency_key="position-correction-head",
            correction_of_fill_id=execution_fill.fill_id,
        )

    def resolve_position() -> tuple[object, ...]:
        barrier.wait()
        return PostgresStrategyShadowRepository(
            postgres_factory,
            apply_migrations=False,
        ).resolve_multi_strategy_positions(
            account_id=ACCOUNT,
            decision_time=SESSION_TIMES[1] + timedelta(minutes=2),
            trading_calendar_reference=calendar,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        correction_future = executor.submit(correct_fill)
        position_future = executor.submit(resolve_position)
    correction_future.result()
    try:
        position_future.result()
    except ValueError as exc:
        assert "RECONCILIATION_REQUIRED" in str(exc)
    current = PostgresStrategyShadowRepository(
        postgres_factory,
        apply_migrations=False,
    ).resolve_multi_strategy_positions(
        account_id=ACCOUNT,
        decision_time=SESSION_TIMES[1] + timedelta(minutes=2),
        trading_calendar_reference=calendar,
    )
    matched = next(
        item
        for item in current
        if item.strategy_version_id
        == proposal.strategy_version_reference.artifact_id
        and item.symbol == SYMBOL
    )
    assert matched.quantity == 200


def test_existing_physical_exposure_blocks_new_buy(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(
        postgres_factory,
        day=0,
        quantity=5000,
        price="10.00",
    )
    cycle0, portfolio0 = _execute_day(postgres_factory, 0, calendar)
    enter = _proposal(
        cycle0,
        family=StrategyFamily.OVERNIGHT,
        action=CanonicalStrategyAction.ENTER,
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    with pytest.raises(ValueError, match="Projected post-trade gross exposure"):
        _intent(
            service,
            day=0,
            portfolio=portfolio0,
            proposal=enter,
            calendar=calendar,
            quantity=100,
            key="exposure-blocked-enter",
        )


def test_strategy_budget_marks_allocated_sleeve_at_current_owner_price(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    _observe(
        postgres_factory,
        day=0,
        quantity=0,
        price="0",
        available_cash="500000",
        total_equity="1000000",
    )
    day0, portfolio0 = _execute_day(postgres_factory, 0, calendar)
    swing_entry = _intent(
        service,
        day=0,
        portfolio=portfolio0,
        proposal=_proposal(
            day0,
            family=StrategyFamily.SWING_STATE,
            action=CanonicalStrategyAction.ENTER,
        ),
        calendar=calendar,
        quantity=None,
        key="current-sleeve-mark-entry",
    )
    _partial_fills(
        service,
        trade=swing_entry,
        day=0,
        quantities=(swing_entry.intended_quantity,),
        price=10.0,
        key="current-sleeve-mark-entry",
    )
    _observe(
        postgres_factory,
        day=1,
        quantity=swing_entry.intended_quantity,
        price="10.00",
        available_cash="500000",
        total_equity="1000000",
    )
    day1, _ = _execute_day(postgres_factory, 1, calendar)
    assert _action(day1, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.HOLD

    current_price = Decimal("250000") / Decimal(swing_entry.intended_quantity)
    _observe(
        postgres_factory,
        day=2,
        quantity=swing_entry.intended_quantity,
        price=str(current_price),
        available_cash="500000",
        total_equity="1000000",
    )
    current_bar = _decision_price_bar(
        day=2,
        symbol=SYMBOL,
        observed_at=SESSION_TIMES[2],
        available_at=SESSION_TIMES[2],
        price=current_price,
    )
    day2, portfolio2 = _execute_day(
        postgres_factory,
        2,
        calendar,
        decision_price_bars=(current_bar,),
        portfolio_policy=CrossStrategyPortfolioPolicy(
            maximum_gross_weight=Decimal("1.00"),
            maximum_symbol_weight=Decimal("1.00"),
        ),
    )
    assert _action(day2, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.ADD
    with pytest.raises(
        ValueError,
        match="Projected post-trade Strategy exposure",
    ):
        _intent(
            service,
            day=2,
            portfolio=portfolio2,
            proposal=_proposal(
                day2,
                family=StrategyFamily.SWING_STATE,
                action=CanonicalStrategyAction.ADD,
            ),
            calendar=calendar,
            quantity=100,
            key="current-sleeve-mark-add",
        )


def test_unobserved_sell_uses_owner_mark_quantity_delta_for_exposure(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    _observe(postgres_factory, day=0, quantity=0, price="0")
    day0, portfolio0 = _execute_day(postgres_factory, 0, calendar)
    entry = _intent(
        service,
        day=0,
        portfolio=portfolio0,
        proposal=_proposal(
            day0,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.ENTER,
        ),
        calendar=calendar,
        quantity=100,
        key="sell-mark-entry",
    )
    _partial_fills(
        service,
        trade=entry,
        day=0,
        quantities=(100,),
        price=10.0,
        key="sell-mark-entry",
    )

    _observe(postgres_factory, day=1, quantity=100, price="10.00")
    second_symbol = "000002.SZ"
    day1_bars = (
        _decision_price_bar(
            day=1,
            symbol=SYMBOL,
            observed_at=SESSION_TIMES[1],
            available_at=SESSION_TIMES[1],
        ),
        _decision_price_bar(
            day=1,
            symbol=second_symbol,
            observed_at=SESSION_TIMES[1],
            available_at=SESSION_TIMES[1],
        ),
    )
    day1, portfolio1 = _execute_day(
        postgres_factory,
        1,
        calendar,
        decision_price_bars=day1_bars,
        portfolio_policy=CrossStrategyPortfolioPolicy(
            maximum_gross_weight=Decimal("0.08"),
            maximum_symbol_weight=Decimal("0.08"),
        ),
    )
    exit_intent = _intent(
        service,
        day=1,
        portfolio=portfolio1,
        proposal=_proposal(
            day1,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.EXIT,
        ),
        calendar=calendar,
        quantity=100,
        key="sell-mark-exit",
    )
    service.record_fill(
        exit_intent.manual_trade_id,
        external_fill_id="sell-mark-exit-fill",
        quantity=50,
        price=20.0,
        fees=0.0,
        occurred_at=SESSION_TIMES[1] + timedelta(minutes=1),
        recorded_at=SESSION_TIMES[1] + timedelta(minutes=1, seconds=1),
        actor="stateful-operator",
        reason="SELL Fill price differs from owner mark",
        idempotency_key="sell-mark-exit-fill",
    )
    accepted_line = next(
        item
        for item in portfolio1.lines
        if item.symbol == second_symbol
        and item.action is CanonicalStrategyAction.ENTER
        and item.accepted_weight > 0
    )
    buy_proposal = next(
        item
        for run in day1.runs
        for item in run.proposals
        if item.proposal_id == accepted_line.proposal_reference.artifact_id
    )
    with pytest.raises(
        ValueError,
        match="Projected post-trade gross exposure",
    ):
        service.create_intent(
            portfolio_decision_id=portfolio1.decision_id,
            proposal_id=buy_proposal.proposal_id,
            trading_calendar_reference=calendar,
            lot_size=100,
            actor="stateful-operator",
            reason="exercise owner-marked post-SELL exposure",
            created_at=SESSION_TIMES[1] + timedelta(minutes=2),
            idempotency_key="sell-mark-second-symbol-buy",
        )


def test_overlimit_account_allows_owner_resolved_risk_reducing_exit(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    service = StrategyExecutionApplicationService(
        postgres_factory,
        account_id=ACCOUNT,
    )
    _observe(postgres_factory, day=0, quantity=0, price="0")
    day0, portfolio0 = _execute_day(postgres_factory, 0, calendar)
    entry = _intent(
        service,
        day=0,
        portfolio=portfolio0,
        proposal=_proposal(
            day0,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.ENTER,
        ),
        calendar=calendar,
        quantity=100,
        key="overlimit-exit-entry",
    )
    _partial_fills(
        service,
        trade=entry,
        day=0,
        quantities=(100,),
        price=10.0,
        key="overlimit-exit-entry",
    )
    _observe(
        postgres_factory,
        day=1,
        quantity=100,
        price="600.00",
    )
    day1, portfolio1 = _execute_day(postgres_factory, 1, calendar)
    exit_intent = _intent(
        service,
        day=1,
        portfolio=portfolio1,
        proposal=_proposal(
            day1,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.EXIT,
        ),
        calendar=calendar,
        quantity=100,
        key="overlimit-risk-reducing-exit",
    )
    assert exit_intent.side.value == "SELL"


@pytest.mark.parametrize(
    ("symbol", "observed_delta", "available_delta", "message"),
    (
        ("000002.SZ", timedelta(0), timedelta(0), "Price owner is not exact"),
        (SYMBOL, timedelta(minutes=-5), timedelta(minutes=-5), "Price owner is not exact"),
        (SYMBOL, timedelta(minutes=1), timedelta(minutes=1), "after DecisionTime"),
    ),
)
def test_strategy_execution_rejects_wrong_symbol_stale_and_future_price_owner(
    postgres_factory: PostgresConnectionFactory,
    symbol: str,
    observed_delta: timedelta,
    available_delta: timedelta,
    message: str,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(postgres_factory, day=0, quantity=0, price="0")
    observed_at = SESSION_TIMES[0] + observed_delta
    available_at = SESSION_TIMES[0] + available_delta
    price_bar = _decision_price_bar(
        day=0,
        symbol=symbol,
        observed_at=observed_at,
        available_at=available_at,
    )
    if observed_at > SESSION_TIMES[0] or available_at > SESSION_TIMES[0]:
        with pytest.raises(ValueError, match=message):
            _execute_day(
                postgres_factory,
                0,
                calendar,
                decision_price_bars=(price_bar,),
            )
        return
    cycle, portfolio = _execute_day(
        postgres_factory,
        0,
        calendar,
        decision_price_bars=(price_bar,),
    )
    with pytest.raises(ValueError, match=message):
        _intent(
            StrategyExecutionApplicationService(
                postgres_factory,
                account_id=ACCOUNT,
            ),
            day=0,
            portfolio=portfolio,
            proposal=_proposal(
                cycle,
                family=StrategyFamily.OVERNIGHT,
                action=CanonicalStrategyAction.ENTER,
            ),
            calendar=calendar,
            quantity=100,
            key="wrong-price-owner",
        )


def test_strategy_execution_requires_fresh_latest_reconciled_account_owner(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(
        postgres_factory,
        day=0,
        quantity=0,
        price="0",
        as_of_time=SESSION_TIMES[0] - timedelta(minutes=5),
    )
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    proposal = _proposal(
        cycle,
        family=StrategyFamily.OVERNIGHT,
        action=CanonicalStrategyAction.ENTER,
    )
    with pytest.raises(ValueError, match="Account Observation is stale"):
        _intent(
            StrategyExecutionApplicationService(
                postgres_factory,
                account_id=ACCOUNT,
            ),
            day=0,
            portfolio=portfolio,
            proposal=proposal,
            calendar=calendar,
            quantity=100,
            key="stale-account-owner",
        )


def test_newer_unreconciled_account_revision_blocks_execution(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    first = _observe(postgres_factory, day=0, quantity=0, price="0")
    newer = ManualAccountObservation.create(
        account_id=ACCOUNT,
        trading_date=first.trading_date,
        as_of_time=first.as_of_time,
        total_equity=first.total_equity,
        available_cash=first.available_cash - Decimal("100"),
        frozen_cash=first.frozen_cash,
        source="MANUAL_ACCOUNT_AUTHORITY",
        actor="stateful-operator",
        reason="newer same-time account revision",
        notes="",
        idempotency_key="stateful-observation-newer-unreconciled",
        revision=2,
        previous_observation_id=first.observation_id,
        positions=(),
        created_at=first.created_at,
    )
    PostgresDecisionSystemRepository(postgres_factory).record_manual_observation(newer)
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    with pytest.raises(ValueError, match="RECONCILIATION_REQUIRED"):
        _intent(
            StrategyExecutionApplicationService(
                postgres_factory,
                account_id=ACCOUNT,
            ),
            day=0,
            portfolio=portfolio,
            proposal=_proposal(
                cycle,
                family=StrategyFamily.OVERNIGHT,
                action=CanonicalStrategyAction.ENTER,
            ),
            calendar=calendar,
            quantity=100,
            key="newer-unreconciled-account",
        )


def test_incomplete_account_reconciliation_fails_closed(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _seed_calendar(postgres_factory)
    PostgresMultiStrategyRepository(postgres_factory).register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    _observe(
        postgres_factory,
        day=0,
        quantity=0,
        price="0",
        fill_ledger_complete=False,
    )
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    with pytest.raises(ValueError, match="RECONCILIATION_REQUIRED"):
        _intent(
            StrategyExecutionApplicationService(
                postgres_factory,
                account_id=ACCOUNT,
            ),
            day=0,
            portfolio=portfolio,
            proposal=_proposal(
                cycle,
                family=StrategyFamily.OVERNIGHT,
                action=CanonicalStrategyAction.ENTER,
            ),
            calendar=calendar,
            quantity=100,
            key="incomplete-account-owner",
        )


def test_decision_system_cli_runs_and_recovers_strategy_execution(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calendar = _seed_calendar(postgres_factory)
    repository = PostgresMultiStrategyRepository(postgres_factory)
    repository.register(
        canonical_exploratory_strategy_registry(),
        created_at=SESSION_TIMES[0],
    )
    observation = _observe(postgres_factory, day=0, quantity=0, price="0")
    cycle, portfolio = _execute_day(postgres_factory, 0, calendar)
    proposal = _proposal(
        cycle,
        family=StrategyFamily.OVERNIGHT,
        action=CanonicalStrategyAction.ENTER,
    )
    database_arguments = (
        "--database-url",
        os.environ[TEST_DATABASE_URL_ENV],
        "--database-schema",
        postgres_factory.application_schema,
    )
    intent_input = tmp_path / "strategy-intent.json"
    intent_payload = {
        "portfolio_decision_id": str(portfolio.decision_id),
        "proposal_id": str(proposal.proposal_id),
        "account_id": observation.account_id,
        "trading_calendar_reference": calendar.to_canonical_dict(),
        "lot_size": 100,
        "actor": "stateful-operator",
        "reason": "accept canonical Strategy Proposal",
        "created_at": (SESSION_TIMES[0] + timedelta(seconds=1)).isoformat(),
        "idempotency_key": "cli-strategy-intent",
        "operator_quantity": 100,
        "override_reason": "controlled engineering scenario",
    }
    intent_input.write_text(
        json.dumps({**intent_payload, "reference_price": "1.00"}),
        encoding="utf-8",
    )
    assert (
        decision_system_main(
            (*database_arguments, "create-strategy-intent", "--input", str(intent_input))
        )
        == 2
    )
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["status"] == "FAILED"
    assert rejected["order_created"] is False

    intent_input.write_text(
        json.dumps(intent_payload),
        encoding="utf-8",
    )

    assert decision_system_main((*database_arguments, "create-strategy-intent", "--input", str(intent_input))) == 0
    intent_output = json.loads(capsys.readouterr().out)
    trade_id = ManualTradeId(intent_output["manual_trade"]["manual_trade_id"])
    assert intent_output["manual_intent_created"] is True
    assert intent_output["order_created"] is False
    assert intent_output["broker_called"] is False

    fill_input = tmp_path / "strategy-fill.json"
    fill_input.write_text(
        json.dumps(
            {
                "trade_id": str(trade_id),
                "external_fill_id": "cli-partial-fill-1",
                "quantity": 30,
                "price": "10.00",
                "fees": "0.30",
                "occurred_at": (SESSION_TIMES[0] + timedelta(minutes=1)).isoformat(),
                "recorded_at": (SESSION_TIMES[0] + timedelta(minutes=1, seconds=1)).isoformat(),
                "actor": "stateful-operator",
                "reason": "record observed partial Fill",
                "idempotency_key": "cli-partial-fill-1",
            }
        ),
        encoding="utf-8",
    )
    assert decision_system_main((*database_arguments, "record-strategy-fill", "--input", str(fill_input))) == 0
    fill_output = json.loads(capsys.readouterr().out)
    assert fill_output["status"] == ManualOrderState.PARTIALLY_FILLED.value
    assert fill_output["fill_created"] is True
    assert len(fill_output["allocation_batches"]) == 1

    raw_manual = ManualExecutionApplicationService(PostgresManualExecutionRepository(postgres_factory))
    raw_manual.record_fill(
        trade_id,
        external_fill_id="cli-partial-fill-2",
        quantity=70,
        price=10.0,
        fees=0.7,
        occurred_at=SESSION_TIMES[0] + timedelta(minutes=2),
        recorded_at=SESSION_TIMES[0] + timedelta(minutes=2, seconds=1),
        actor="stateful-operator",
        reason="persist Fill before simulated process failure",
        idempotency_key="cli-partial-fill-2",
    )
    assert (
        decision_system_main(
            (
                *database_arguments,
                "recover-strategy-execution",
            "--trade-id",
            str(trade_id),
                "--decision-time",
                (SESSION_TIMES[0] + timedelta(minutes=3)).isoformat(),
            )
        )
        == 0
    )
    recovered = json.loads(capsys.readouterr().out)
    assert recovered["status"] == "RECOVERED"
    assert recovered["manual_trade"]["state"] == ManualOrderState.FILLED.value
    assert len(recovered["allocation_batches"]) == 2
    assert (
        decision_system_main(
            (
                *database_arguments,
                "inspect-strategy-execution",
                "--account-id",
                ACCOUNT,
                "--proposal-id",
                str(proposal.proposal_id),
            )
        )
        == 0
    )
    inspected = json.loads(capsys.readouterr().out)["execution_authority"]
    assert inspected["effective_filled_quantity"] == 100
    assert inspected["reserved_quantity"] == 0
    assert inspected["price_owner_reference"]["reference_kind"] == ("CANONICAL_MARKET_BAR")
    assert inspected["account_reconciliation_reference"]["reference_kind"] == ("ACCOUNT_RECONCILIATION")
    physical = raw_manual.rebuild_position(
        account_id=ACCOUNT,
        symbol=SYMBOL,
        as_of=SESSION_TIMES[0] + timedelta(minutes=3),
    )
    assert physical.total_quantity == 100
