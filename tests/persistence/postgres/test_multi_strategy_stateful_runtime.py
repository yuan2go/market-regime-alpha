from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, timedelta
from decimal import Decimal

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
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
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
from market_regime_alpha.strategies.portfolio import CrossStrategyPortfolioPolicy
from market_regime_alpha.strategies.postgres_repository import (
    PostgresMultiStrategyRepository,
)
from market_regime_alpha.strategies.runtime import MultiStrategyRuntime
from market_regime_alpha.strategies.sleeves import allocate_observed_fill
from tests.execution.test_manual_position_authority import _trade
from tests.strategies.test_multi_strategy_runtime import NOW, _candidate_set


ACCOUNT = "account-a"
SYMBOL = "000001.SZ"
HASH = canonical_hash({"stateful": "runtime"})
BASE = NOW.astimezone(UTC)


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


def _request(day: int) -> ChildExecutionRequest:
    decision_time = BASE + timedelta(days=day)
    return ChildExecutionRequest(
        trading_date=decision_time.date(),
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
        input_references=(
            RuntimeArtifactReference(
                "RESEARCH_SUMMARY",
                ArtifactId(f"stateful-summary-{day}"),
                HASH,
            ),
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
) -> tuple[MultiStrategyCycle, object]:
    request = _request(day)
    result = _adapter(factory).execute(
        request=request,
        candidate_set=_candidate_set(),
        dataset_reference=RuntimeArtifactReference(
            "DATASET",
            ArtifactId("stateful-dataset"),
            HASH,
        ),
        upstream=_upstream(day),
    )
    repository = PostgresMultiStrategyRepository(factory, apply_migrations=False)
    return (
        repository.get_cycle(result.child_run_id),
        repository.get_portfolio(result.child_artifact_id),  # type: ignore[arg-type]
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


def _record_fill(
    factory: PostgresConnectionFactory,
    *,
    day: int,
    current: int,
    target: int,
    price: float,
    proposal: StrategyProposal,
    key: str,
) -> None:
    service = ManualExecutionApplicationService(
        PostgresManualExecutionRepository(factory)
    )
    trade = _trade(
        service,
        current=current,
        available=current,
        target=target,
        key=f"stateful-trade-{key}",
    )
    _, fill = service.record_fill(
        trade.manual_trade_id,
        external_fill_id=f"stateful-external-{key}",
        quantity=abs(target - current),
        price=price,
        fees=0.0,
        occurred_at=BASE + timedelta(days=day, minutes=1),
        recorded_at=BASE + timedelta(days=day, minutes=2),
        actor="stateful-operator",
        reason="stateful runtime observed Fill",
        idempotency_key=f"stateful-fill-{key}",
    )
    batch = allocate_observed_fill(
        fill=fill,
        allocations=(
            (
                proposal.strategy_version_reference,
                RuntimeArtifactReference(
                    "STRATEGY_PROPOSAL",
                    proposal.proposal_id,
                    proposal.proposal_hash,
                ),
                fill.quantity,
            ),
        ),
    )
    repository = PostgresMultiStrategyRepository(
        factory,
        apply_migrations=False,
    )
    stored = repository.save_fill_allocation(batch)
    assert repository.save_fill_allocation(batch) == stored


def _record_combined_entry(
    factory: PostgresConnectionFactory,
    *,
    cycle: MultiStrategyCycle,
) -> None:
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
    service = ManualExecutionApplicationService(
        PostgresManualExecutionRepository(factory)
    )
    trade = _trade(
        service,
        current=0,
        available=0,
        target=200,
        key="stateful-trade-combined-entry",
    )
    _, fill = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="stateful-external-combined-entry",
        quantity=200,
        price=10.0,
        fees=0.0,
        occurred_at=BASE + timedelta(minutes=1),
        recorded_at=BASE + timedelta(minutes=2),
        actor="stateful-operator",
        reason="stateful combined observed Fill",
        idempotency_key="stateful-fill-combined-entry",
    )
    batch = allocate_observed_fill(
        fill=fill,
        allocations=tuple(
            (
                proposal.strategy_version_reference,
                RuntimeArtifactReference(
                    "STRATEGY_PROPOSAL",
                    proposal.proposal_id,
                    proposal.proposal_hash,
                ),
                100,
            )
            for proposal in (overnight, swing)
        ),
    )
    repository = PostgresMultiStrategyRepository(
        factory,
        apply_migrations=False,
    )
    stored = repository.save_fill_allocation(batch)
    assert repository.save_fill_allocation(batch) == stored


def _observe(
    factory: PostgresConnectionFactory,
    *,
    day: int,
    quantity: int,
    price: str,
) -> None:
    observed_at = BASE + timedelta(days=day)
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
        trading_date=observed_at.date(),
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
    PostgresDecisionSystemRepository(
        factory,
    ).record_manual_observation(observation)


def _action(
    cycle: MultiStrategyCycle,
    family: StrategyFamily,
) -> CanonicalStrategyAction:
    registry = canonical_exploratory_strategy_registry()
    run = next(item for item in cycle.runs if registry.family_for(item) is family)
    return next(item.action for item in run.gate_attributions if item.symbol == SYMBOL)


def test_postgres_composed_multi_session_lifecycle_recovery_and_replay(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    strategy_repository = PostgresMultiStrategyRepository(postgres_factory)
    strategy_repository.register(
        canonical_exploratory_strategy_registry(),
        created_at=BASE,
    )

    day0, _ = _execute_day(postgres_factory, 0)
    assert _action(day0, StrategyFamily.OVERNIGHT) is CanonicalStrategyAction.ENTER
    assert _action(day0, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.ENTER
    _record_combined_entry(postgres_factory, cycle=day0)

    _observe(postgres_factory, day=1, quantity=200, price="10.00")
    day1, _ = _execute_day(postgres_factory, 1)
    assert _action(day1, StrategyFamily.OVERNIGHT) is CanonicalStrategyAction.EXIT
    assert _action(day1, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.HOLD
    assert {item.sessions_held for item in day1.runtime_input.positions} == {1}
    _record_fill(
        postgres_factory,
        day=1,
        current=200,
        target=100,
        price=10.0,
        proposal=_proposal(
            day1,
            family=StrategyFamily.OVERNIGHT,
            action=CanonicalStrategyAction.EXIT,
        ),
        key="overnight-exit",
    )

    _observe(postgres_factory, day=2, quantity=100, price="10.40")
    day2, _ = _execute_day(postgres_factory, 2)
    assert _action(day2, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.ADD
    swing_state = next(
        item
        for item in day2.runtime_input.positions
        if item.strategy_version_id
        == _proposal(
            day2,
            family=StrategyFamily.SWING_STATE,
            action=CanonicalStrategyAction.ADD,
        ).strategy_version_reference.artifact_id
    )
    assert swing_state.sessions_held == 2
    assert swing_state.peak_price == Decimal("10.40")
    _record_fill(
        postgres_factory,
        day=2,
        current=100,
        target=150,
        price=10.4,
        proposal=_proposal(
            day2,
            family=StrategyFamily.SWING_STATE,
            action=CanonicalStrategyAction.ADD,
        ),
        key="swing-add",
    )

    _observe(postgres_factory, day=3, quantity=150, price="10.50")
    day3, _ = _execute_day(postgres_factory, 3)
    assert _action(day3, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.HOLD
    swing_state = next(
        item for item in day3.runtime_input.positions if item.symbol == SYMBOL
    )
    assert swing_state.add_count == 1
    assert swing_state.sessions_held == 3

    _observe(postgres_factory, day=4, quantity=150, price="9.90")
    day4, _ = _execute_day(postgres_factory, 4)
    assert _action(day4, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.REDUCE
    # Proposal-persisted crash: a fresh composition deterministically resumes
    # the exact same Tick without duplicating cycle or proposal facts.
    recovered_day4, _ = _execute_day(postgres_factory, 4)
    assert recovered_day4 == day4
    reduce_proposal = _proposal(
        day4,
        family=StrategyFamily.SWING_STATE,
        action=CanonicalStrategyAction.REDUCE,
    )
    _record_fill(
        postgres_factory,
        day=4,
        current=150,
        target=130,
        price=9.9,
        proposal=reduce_proposal,
        key="swing-reduce",
    )

    _observe(postgres_factory, day=5, quantity=130, price="9.00")
    day5, _ = _execute_day(postgres_factory, 5)
    assert _action(day5, StrategyFamily.SWING_STATE) is CanonicalStrategyAction.EXIT
    final_state = next(
        item for item in day5.runtime_input.positions if item.symbol == SYMBOL
    )
    assert final_state.add_count == 1
    assert final_state.reduce_count == 1
    assert final_state.sessions_held == 5
    assert final_state.peak_price == Decimal("10.50")
    # Position-state snapshot persisted -> crash: the canonical child reloads
    # the identical owner-resolved state and Proposal identities after restart.
    recovered_day5, _ = _execute_day(postgres_factory, 5)
    assert recovered_day5 == day5
    exit_proposal = _proposal(
        day5,
        family=StrategyFamily.SWING_STATE,
        action=CanonicalStrategyAction.EXIT,
    )
    # Fill-persisted crash: observed Fill survives independently; allocation is
    # then retried through its immutable Strategy ledger after repository restart.
    _record_fill(
        postgres_factory,
        day=5,
        current=130,
        target=0,
        price=9.0,
        proposal=exit_proposal,
        key="swing-exit",
    )
    physical = ManualExecutionApplicationService(
        PostgresManualExecutionRepository(postgres_factory)
    ).rebuild_position(
        account_id=ACCOUNT,
        symbol=SYMBOL,
        as_of=BASE + timedelta(days=5, minutes=3),
    )
    assert physical.state is PositionState.CLOSED
    assert physical.total_quantity == 0

    _observe(postgres_factory, day=6, quantity=0, price="0")
    day6, _ = _execute_day(postgres_factory, 6)
    assert day6.runtime_input.positions == ()
    shadow = PostgresStrategyShadowRepository(
        postgres_factory,
        apply_migrations=False,
    )
    outcomes = shadow.settle_multi_strategy_outcomes(
        account_id=ACCOUNT,
        decision_time=BASE + timedelta(days=6),
    )
    assert len(outcomes) == 2
    swing_outcome = next(
        item
        for item in outcomes
        if item.strategy_version_reference.artifact_id
        == exit_proposal.strategy_version_reference.artifact_id
    )
    assert swing_outcome.entry_proposal_reference.artifact_id == _proposal(
        day0,
        family=StrategyFamily.SWING_STATE,
        action=CanonicalStrategyAction.ENTER,
    ).proposal_id
    assert swing_outcome.exit_proposal_reference.artifact_id == exit_proposal.proposal_id
    assert len(swing_outcome.source_fill_references) == 4
    assert len(swing_outcome.source_allocation_references) == 4
    assert shadow.settle_multi_strategy_outcomes(
        account_id=ACCOUNT,
        decision_time=BASE + timedelta(days=6),
    ) == outcomes
    with ThreadPoolExecutor(max_workers=4) as executor:
        concurrent = tuple(
            executor.map(
                lambda _: PostgresStrategyShadowRepository(
                    postgres_factory,
                    apply_migrations=False,
                ).settle_multi_strategy_outcomes(
                    account_id=ACCOUNT,
                    decision_time=BASE + timedelta(days=6),
                ),
                range(4),
            )
        )
    assert concurrent == (outcomes,) * 4
    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM strategy_realized_outcome WHERE account_id = %s",
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

    # Frozen input replay uses the same public policy kernel and exactly matches
    # every action/hash in the persisted cycle.
    replayed = MultiStrategyRuntime(
        canonical_exploratory_strategy_registry()
    ).execute(day5.runtime_input)
    assert replayed == day5
    assert strategy_repository.get_cycle(day5.cycle_id) == day5
