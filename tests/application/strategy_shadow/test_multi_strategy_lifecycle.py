from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from market_regime_alpha.application.decision_system.contracts import (
    ManualAccountObservation,
    ManualPositionObservation,
)
from market_regime_alpha.application.strategy_shadow.multi_strategy_lifecycle import (
    project_strategy_position_states,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, FillId, ManualTradeId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import FILL_SCHEMA, Fill, FillKind, TradeSide
from market_regime_alpha.strategies.contracts import CanonicalStrategyAction
from market_regime_alpha.strategies.sleeves import allocate_observed_fill


START = datetime(2026, 1, 5, 7, 0, tzinfo=UTC)
ACCOUNT = "stateful-account"
SYMBOL = "000001.SZ"
VERSION = RuntimeArtifactReference(
    "STRATEGY_VERSION",
    ArtifactId("strategy-version-swing-stateful"),
    canonical_hash({"version": "swing-stateful"}),
)


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def _fill(
    name: str,
    *,
    side: TradeSide,
    quantity: int,
    price: float,
    day: int,
) -> Fill:
    return Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId(f"fill-{name}"),
        manual_trade_id=ManualTradeId(f"manual-trade-{name}"),
        account_id=ACCOUNT,
        symbol=SYMBOL,
        side=side,
        quantity=quantity,
        price=price,
        fees=0.0,
        occurred_at=START + timedelta(days=day, minutes=1),
        recorded_at=START + timedelta(days=day, minutes=2),
        actor="operator",
        reason="stateful lifecycle proof",
        external_fill_id=f"external-{name}",
        fill_kind=FillKind.EXECUTION,
        correction_of_fill_id=None,
    )


def _observation(day: int, *, quantity: int, price: str) -> ManualAccountObservation:
    observed_at = START + timedelta(days=day, hours=2)
    return ManualAccountObservation.create(
        account_id=ACCOUNT,
        trading_date=date(2026, 1, 5) + timedelta(days=day),
        as_of_time=observed_at,
        total_equity=Decimal("100000"),
        available_cash=Decimal("50000"),
        frozen_cash=Decimal("0"),
        source="MANUAL_ACCOUNT_AUTHORITY",
        actor="operator",
        reason="owner-resolved mark",
        notes="",
        idempotency_key=f"observation-{day}",
        revision=1,
        previous_observation_id=None,
        positions=(
            ManualPositionObservation(
                symbol=SYMBOL,
                total_quantity=quantity,
                available_quantity=quantity,
                frozen_quantity=0,
                average_cost=Decimal("10"),
                observed_market_value=Decimal(quantity) * Decimal(price),
            ),
        ),
        created_at=observed_at,
    )


def test_owner_projection_preserves_price_age_counters_and_fill_lineage() -> None:
    entry = _reference("STRATEGY_PROPOSAL", "proposal-enter")
    add = _reference("STRATEGY_PROPOSAL", "proposal-add")
    reduce = _reference("STRATEGY_PROPOSAL", "proposal-reduce")
    batches = (
        allocate_observed_fill(
            fill=_fill("enter", side=TradeSide.BUY, quantity=100, price=10.0, day=0),
            allocations=((VERSION, entry, 100),),
        ),
        allocate_observed_fill(
            fill=_fill("add", side=TradeSide.BUY, quantity=50, price=11.0, day=1),
            allocations=((VERSION, add, 50),),
        ),
        allocate_observed_fill(
            fill=_fill("reduce", side=TradeSide.SELL, quantity=20, price=10.5, day=2),
            allocations=((VERSION, reduce, 20),),
        ),
    )

    states = project_strategy_position_states(
        account_id=ACCOUNT,
        decision_time=START + timedelta(days=3),
        batches=batches,
        proposal_actions={
            entry.artifact_id: CanonicalStrategyAction.ENTER,
            add.artifact_id: CanonicalStrategyAction.ADD,
            reduce.artifact_id: CanonicalStrategyAction.REDUCE,
        },
        observations=(
            _observation(1, quantity=150, price="11.20"),
            _observation(2, quantity=130, price="10.50"),
        ),
    )

    assert len(states) == 1
    state = states[0]
    assert state.account_id == ACCOUNT
    assert state.quantity == Decimal("130")
    assert state.average_cost == Decimal("10.33333333333333333333333333")
    assert state.current_price == Decimal("10.50")
    assert state.peak_price == Decimal("11.20")
    assert state.sessions_held == 2
    assert state.add_count == 1
    assert state.reduce_count == 1
    assert state.strategy_version_hash == VERSION.content_hash
    assert len(state.source_allocation_references) == 3
    assert len(state.source_fill_references) == 3
    assert len(state.price_observation_references) == 2
    assert state.state_reference is not None
    assert state.state_reference.content_hash == canonical_hash(state.identity_payload())


def test_projection_uses_only_facts_available_at_decision_time() -> None:
    entry = _reference("STRATEGY_PROPOSAL", "proposal-enter")
    future_add = _reference("STRATEGY_PROPOSAL", "proposal-future-add")
    batches = (
        allocate_observed_fill(
            fill=_fill("enter", side=TradeSide.BUY, quantity=100, price=10.0, day=0),
            allocations=((VERSION, entry, 100),),
        ),
        allocate_observed_fill(
            fill=_fill("future-add", side=TradeSide.BUY, quantity=50, price=20.0, day=3),
            allocations=((VERSION, future_add, 50),),
        ),
    )

    states = project_strategy_position_states(
        account_id=ACCOUNT,
        decision_time=START + timedelta(days=2),
        batches=batches,
        proposal_actions={
            entry.artifact_id: CanonicalStrategyAction.ENTER,
            future_add.artifact_id: CanonicalStrategyAction.ADD,
        },
        observations=(
            _observation(1, quantity=100, price="10.50"),
            _observation(3, quantity=150, price="20.00"),
        ),
    )

    assert states[0].quantity == Decimal("100")
    assert states[0].current_price == Decimal("10.50")
    assert states[0].peak_price == Decimal("10.50")
    assert states[0].sessions_held == 1
    assert states[0].add_count == 0


def test_fill_side_must_match_strategy_action() -> None:
    proposal = _reference("STRATEGY_PROPOSAL", "proposal-invalid-sell")
    batch = allocate_observed_fill(
        fill=_fill("invalid-sell", side=TradeSide.SELL, quantity=10, price=10.0, day=0),
        allocations=((VERSION, proposal, 10),),
    )

    try:
        project_strategy_position_states(
            account_id=ACCOUNT,
            decision_time=START + timedelta(days=1),
            batches=(batch,),
            proposal_actions={proposal.artifact_id: CanonicalStrategyAction.ENTER},
            observations=(),
        )
    except ValueError as error:
        assert "Fill side does not match Strategy action" in str(error)
    else:
        raise AssertionError("invalid Fill/action lineage was accepted")
