"""Owner-resolved Strategy state projected from existing PostgreSQL facts.

The projection is deliberately stateless: observed Fill allocations remain the
Strategy sleeve ledger, manual account observations own marks, and each
Multi-Strategy cycle freezes the resulting state for replay.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from typing import Iterable, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.decision_system.contracts import (
    ManualAccountObservation,
    ManualPositionObservation,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.execution.manual import TradeSide
from market_regime_alpha.strategies.contracts import (
    CanonicalStrategyAction,
    StrategyPositionState,
)
from market_regime_alpha.strategies.sleeves import (
    FillAllocationBatch,
    effective_fill_allocation_batches,
    project_strategy_sleeves,
)


_STATE_DECIMAL_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)
_BUY_ACTIONS = frozenset(
    {CanonicalStrategyAction.ENTER, CanonicalStrategyAction.ADD}
)
_SELL_ACTIONS = frozenset(
    {CanonicalStrategyAction.REDUCE, CanonicalStrategyAction.EXIT}
)


def project_strategy_position_states(
    *,
    account_id: str,
    decision_time: datetime,
    batches: tuple[FillAllocationBatch, ...],
    proposal_actions: Mapping[ArtifactId, CanonicalStrategyAction],
    observations: tuple[ManualAccountObservation, ...],
) -> tuple[StrategyPositionState, ...]:
    """Rebuild open Strategy states without caller-supplied lifecycle values."""

    available_batches = tuple(
        batch
        for batch in batches
        if batch.recorded_at <= decision_time
    )
    if any(batch.account_id != account_id for batch in available_batches):
        raise ValueError("Strategy position projection crossed account scope")
    effective = effective_fill_allocation_batches(available_batches)
    _verify_fill_actions(effective, proposal_actions)
    latest_observations = _latest_available_observations(
        account_id=account_id,
        decision_time=decision_time,
        observations=observations,
    )
    with localcontext(_STATE_DECIMAL_CONTEXT):
        sleeves = project_strategy_sleeves(effective)
        states = tuple(
            _state_for_sleeve(
                account_id=account_id,
                decision_time=decision_time,
                sleeve_version_id=sleeve.strategy_version_reference.artifact_id,
                sleeve_version_hash=sleeve.strategy_version_reference.content_hash,
                symbol=sleeve.symbol,
                quantity=Decimal(sleeve.quantity),
                average_cost=sleeve.average_cost,
                effective=effective,
                proposal_actions=proposal_actions,
                observations=latest_observations,
            )
            for sleeve in sleeves
            if sleeve.quantity > 0 and sleeve.average_cost is not None
        )
    return tuple(sorted(states, key=lambda item: (str(item.strategy_version_id), item.symbol)))


def _verify_fill_actions(
    batches: tuple[FillAllocationBatch, ...],
    proposal_actions: Mapping[ArtifactId, CanonicalStrategyAction],
) -> None:
    for batch in batches:
        for allocation in batch.allocations:
            try:
                action = proposal_actions[allocation.proposal_reference.artifact_id]
            except KeyError as error:
                raise ValueError("Fill allocation requires owner-resolved Strategy action") from error
            expected = _BUY_ACTIONS if batch.side is TradeSide.BUY else _SELL_ACTIONS
            if action not in expected:
                raise ValueError("Fill side does not match Strategy action")


def _latest_available_observations(
    *,
    account_id: str,
    decision_time: datetime,
    observations: tuple[ManualAccountObservation, ...],
) -> tuple[ManualAccountObservation, ...]:
    by_date: dict[object, ManualAccountObservation] = {}
    for observation in observations:
        if observation.account_id != account_id:
            raise ValueError("Strategy price observation crossed account scope")
        if observation.as_of_time > decision_time:
            continue
        current = by_date.get(observation.trading_date)
        if current is None or observation.revision > current.revision:
            by_date[observation.trading_date] = observation
    return tuple(
        sorted(
            by_date.values(),
            key=lambda item: (item.trading_date, item.as_of_time, item.revision),
        )
    )


def _state_for_sleeve(
    *,
    account_id: str,
    decision_time: datetime,
    sleeve_version_id: ArtifactId,
    sleeve_version_hash: str,
    symbol: str,
    quantity: Decimal,
    average_cost: Decimal | None,
    effective: tuple[FillAllocationBatch, ...],
    proposal_actions: Mapping[ArtifactId, CanonicalStrategyAction],
    observations: tuple[ManualAccountObservation, ...],
) -> StrategyPositionState:
    if average_cost is None:
        raise ValueError("open Strategy sleeve requires average cost")
    scoped = tuple(
        (batch, allocation, proposal_actions[allocation.proposal_reference.artifact_id])
        for batch in effective
        for allocation in batch.allocations
        if allocation.strategy_version_reference.artifact_id == sleeve_version_id
        and batch.symbol == symbol
    )
    entries = tuple(
        batch.recorded_at
        for batch, _, action in scoped
        if action is CanonicalStrategyAction.ENTER
    )
    if not entries:
        raise ValueError("open Strategy sleeve has no ENTER Fill lineage")
    entry_time = min(entries)
    marks = tuple(
        (observation, position)
        for observation in observations
        if observation.as_of_time > entry_time
        for position in observation.positions
        if position.symbol == symbol
    )
    for _, position in marks:
        if Decimal(position.total_quantity) < quantity:
            raise ValueError("Physical Position is below allocated Strategy sleeves")
    prices = tuple(_observed_price(position) for _, position in marks)
    current_price = None if not prices else prices[-1]
    peak_price = max((average_cost, *prices))
    allocation_references = _references(
        RuntimeArtifactReference(
            "STRATEGY_FILL_ALLOCATION",
            allocation.allocation_id,
            allocation.allocation_hash,
        )
        for _, allocation, _ in scoped
    )
    fill_references = _references(
        allocation.fill_reference for _, allocation, _ in scoped
    )
    observation_references = _references(
        RuntimeArtifactReference(
            "MANUAL_ACCOUNT_OBSERVATION",
            observation.observation_id,
            observation.content_hash,
        )
        for observation, _ in marks
    )
    return StrategyPositionState.owner_resolved(
        strategy_version_id=sleeve_version_id,
        strategy_version_hash=sleeve_version_hash,
        account_id=account_id,
        symbol=symbol,
        quantity=quantity,
        average_cost=average_cost,
        current_price=current_price,
        peak_price=peak_price,
        sessions_held=len({observation.trading_date for observation, _ in marks}),
        add_count=sum(
            action is CanonicalStrategyAction.ADD for _, _, action in scoped
        ),
        reduce_count=sum(
            action is CanonicalStrategyAction.REDUCE for _, _, action in scoped
        ),
        source_allocation_references=allocation_references,
        source_fill_references=fill_references,
        price_observation_references=observation_references,
    )


def _observed_price(position: ManualPositionObservation) -> Decimal:
    if position.total_quantity <= 0:
        raise ValueError("open Strategy sleeve requires non-zero Physical Position mark")
    return position.observed_market_value / Decimal(position.total_quantity)


def _references(
    values: Iterable[RuntimeArtifactReference],
) -> tuple[RuntimeArtifactReference, ...]:
    references = tuple(values)
    return tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


__all__ = ["project_strategy_position_states"]
