from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
import pytest

from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.multi_strategy import (
    MultiStrategyContinuousAdapter,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
)
from market_regime_alpha.application.decision_system.contracts import (
    ManualAccountObservation,
    ManualPositionObservation,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
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
from market_regime_alpha.execution.postgres_repository import (
    PostgresManualExecutionRepository,
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
from tests.strategies.test_multi_strategy_runtime import _candidate_set


ACCOUNT = "account-a"
SYMBOL = "000001.SZ"
HASH = canonical_hash({"stateful": "runtime-v2"})
TZ = ZoneInfo("Asia/Shanghai")
SESSION_TIMES = tuple(
    datetime(2026, 8, day, 14, 55, tzinfo=TZ).astimezone(UTC)
    for day in (14, 17, 18, 19, 20, 21, 24)
)


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
        PITArtifactReference(
            "TRADING_CALENDAR", calendar.artifact_id, calendar.content_hash
        ),
        actor="stateful-runtime-test",
        reason="resolve exact multi-session calendar",
        idempotency_key="stateful-runtime-calendar-owner",
    )
    PostgresPITTradingCalendarSnapshotRepository(factory).record(calendar)
    return RuntimeArtifactReference(
        "TRADING_CALENDAR", calendar.artifact_id, calendar.content_hash
    )


def _adapter(
    factory: PostgresConnectionFactory,
) -> MultiStrategyContinuousAdapter:
    return MultiStrategyContinuousAdapter(
        repository=PostgresMultiStrategyRepository(
            factory,
            apply_migrations=False,
        ),
        portfolio_policy=CrossStrategyPortfolioPolicy(
            maximum_gross_weight=Decimal("0.50"),
            maximum_symbol_weight=Decimal("0.20"),
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
) -> tuple[MultiStrategyCycle, CrossStrategyPortfolioDecision]:
    result = _adapter(factory).execute(
        request=_request(day, calendar),
        candidate_set=_candidate_set(),
        dataset_reference=RuntimeArtifactReference(
            "DATASET",
            ArtifactId("stateful-dataset"),
            HASH,
        ),
        upstream=_upstream(day),
    )
    repository = PostgresMultiStrategyRepository(factory, apply_migrations=False)
    if result.child_artifact_id is None:
        raise AssertionError("Strategy child did not persist Portfolio decision")
    return (
        repository.get_cycle(result.child_run_id),
        repository.get_portfolio(result.child_artifact_id),
    )


def _proposal(
    cycle: MultiStrategyCycle,
    *,
    family: StrategyFamily,
    action: CanonicalStrategyAction,
) -> StrategyProposal:
    registry = canonical_exploratory_strategy_registry()
    run = next(item for item in cycle.runs if registry.family_for(item) is family)
    return next(
        item
        for item in run.proposals
        if item.symbol == SYMBOL and item.action is action
    )


def _observe(
    factory: PostgresConnectionFactory,
    *,
    day: int,
    quantity: int,
    price: str,
) -> ManualAccountObservation:
    observed_at = SESSION_TIMES[day]
    position = ManualPositionObservation(
        symbol=SYMBOL,
        total_quantity=quantity,
        available_quantity=quantity,
        frozen_quantity=0,
        average_cost=None if quantity == 0 else Decimal("10"),
        observed_market_value=Decimal(quantity) * Decimal(price),
    )
    observation = ManualAccountObservation.create(
        account_id=ACCOUNT,
        trading_date=observed_at.astimezone(TZ).date(),
        as_of_time=observed_at,
        total_equity=Decimal("100000"),
        available_cash=Decimal("50000"),
        frozen_cash=Decimal("0"),
        source="MANUAL_ACCOUNT_AUTHORITY",
        actor="stateful-operator",
        reason="stateful mark",
        notes="",
        idempotency_key=f"stateful-observation-{day}",
        revision=1,
        previous_observation_id=None,
        positions=(position,),
        created_at=observed_at,
    )
    return PostgresDecisionSystemRepository(factory).record_manual_observation(
        observation
    )


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
    observation: ManualAccountObservation,
    calendar: RuntimeArtifactReference,
    price: str,
    quantity: int,
    key: str,
) -> ManualTradeRecord:
    return service.create_intent(
        portfolio_decision_id=portfolio.decision_id,
        proposal_id=proposal.proposal_id,
        account_observation_id=observation.observation_id,
        trading_calendar_reference=calendar,
        reference_price=Decimal(price),
        lot_size=100,
        actor="stateful-operator",
        reason="accept canonical Strategy Proposal",
        created_at=SESSION_TIMES[day] + timedelta(seconds=1),
        idempotency_key=f"stateful-intent-{key}",
        operator_quantity=quantity,
        override_reason=(
            None
            if proposal.action is CanonicalStrategyAction.EXIT
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

    day0_observation = _observe(
        postgres_factory, day=0, quantity=0, price="0"
    )
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
        observation=day0_observation,
        calendar=calendar,
        price="10.00",
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
        observation=day0_observation,
        calendar=calendar,
        price="10.00",
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
        observation=day0_observation,
        calendar=calendar,
        price="10.00",
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

    day1_observation = _observe(
        postgres_factory, day=1, quantity=200, price="10.00"
    )
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
        observation=day1_observation,
        calendar=calendar,
        price="10.00",
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

    day2_observation = _observe(
        postgres_factory, day=2, quantity=100, price="10.40"
    )
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
        observation=day2_observation,
        calendar=calendar,
        price="10.40",
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

    day4_observation = _observe(
        postgres_factory, day=4, quantity=200, price="9.90"
    )
    day4, portfolio4 = _execute_day(postgres_factory, 4, calendar)
    assert _action(day4, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.REDUCE
    recovered_day4, recovered_portfolio4 = _execute_day(
        postgres_factory, 4, calendar
    )
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
        observation=day4_observation,
        calendar=calendar,
        price="9.90",
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

    day5_observation = _observe(
        postgres_factory, day=5, quantity=100, price="9.00"
    )
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
        observation=day5_observation,
        calendar=calendar,
        price="9.00",
        quantity=100,
        key="swing-exit",
    )

    # Fill persisted -> crash.  A fresh bridge reconstructs the missing
    # allocation from the immutable V4 ManualTrade authorization.
    raw_manual = ManualExecutionApplicationService(
        PostgresManualExecutionRepository(postgres_factory)
    )
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
    assert len(
        restarted_execution.reconcile_fill_allocations(
            swing_exit.manual_trade_id
        )
    ) == 2
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
        if item.strategy_version_reference.artifact_id
        == swing_exit_proposal.strategy_version_reference.artifact_id
    )
    assert swing_initial.revision == 1
    assert swing_initial.supersedes_outcome_reference is None

    corrected_target = remaining_exit_fills[-1]
    _, correction, _, corrected_outcomes = restarted_execution.record_fill(
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
    assert correction.correction_of_fill_id == corrected_target.fill_id
    swing_corrected = next(
        item
        for item in corrected_outcomes
        if item.strategy_version_reference.artifact_id
        == swing_exit_proposal.strategy_version_reference.artifact_id
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

    replayed = MultiStrategyRuntime(
        canonical_exploratory_strategy_registry()
    ).execute(day5.runtime_input)
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
    observation = _observe(postgres_factory, day=0, quantity=0, price="0")
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
    with pytest.raises(ValueError, match="does not match execution account"):
        _intent(
            wrong_account,
            day=0,
            portfolio=portfolio,
            proposal=proposal,
            observation=observation,
            calendar=calendar,
            price="10.00",
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
        observation=observation,
        calendar=calendar,
        price="10.00",
        quantity=100,
        key="account-bound-intent",
    )
    with pytest.raises(ValueError, match="different intent"):
        _intent(
            wrong_account,
            day=0,
            portfolio=portfolio,
            proposal=proposal,
            observation=observation,
            calendar=calendar,
            price="10.00",
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
    assert PostgresManualExecutionRepository(postgres_factory).fills_for_trade(
        correct.manual_trade_id
    ) == ()


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
    intent_input.write_text(
        json.dumps(
            {
                "portfolio_decision_id": str(portfolio.decision_id),
                "proposal_id": str(proposal.proposal_id),
                "account_observation_id": str(observation.observation_id),
                "trading_calendar_reference": calendar.to_canonical_dict(),
                "reference_price": "10.00",
                "lot_size": 100,
                "actor": "stateful-operator",
                "reason": "accept canonical Strategy Proposal",
                "created_at": (SESSION_TIMES[0] + timedelta(seconds=1)).isoformat(),
                "idempotency_key": "cli-strategy-intent",
                "operator_quantity": 100,
                "override_reason": "controlled engineering scenario",
            }
        ),
        encoding="utf-8",
    )

    assert decision_system_main(
        (*database_arguments, "create-strategy-intent", "--input", str(intent_input))
    ) == 0
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
                "recorded_at": (
                    SESSION_TIMES[0] + timedelta(minutes=1, seconds=1)
                ).isoformat(),
                "actor": "stateful-operator",
                "reason": "record observed partial Fill",
                "idempotency_key": "cli-partial-fill-1",
            }
        ),
        encoding="utf-8",
    )
    assert decision_system_main(
        (*database_arguments, "record-strategy-fill", "--input", str(fill_input))
    ) == 0
    fill_output = json.loads(capsys.readouterr().out)
    assert fill_output["status"] == ManualOrderState.PARTIALLY_FILLED.value
    assert fill_output["fill_created"] is True
    assert len(fill_output["allocation_batches"]) == 1

    raw_manual = ManualExecutionApplicationService(
        PostgresManualExecutionRepository(postgres_factory)
    )
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
    assert decision_system_main(
        (
            *database_arguments,
            "recover-strategy-execution",
            "--trade-id",
            str(trade_id),
            "--decision-time",
            (SESSION_TIMES[0] + timedelta(minutes=3)).isoformat(),
        )
    ) == 0
    recovered = json.loads(capsys.readouterr().out)
    assert recovered["status"] == "RECOVERED"
    assert recovered["manual_trade"]["state"] == ManualOrderState.FILLED.value
    assert len(recovered["allocation_batches"]) == 2
    physical = raw_manual.rebuild_position(
        account_id=ACCOUNT,
        symbol=SYMBOL,
        as_of=SESSION_TIMES[0] + timedelta(minutes=3),
    )
    assert physical.total_quantity == 100
