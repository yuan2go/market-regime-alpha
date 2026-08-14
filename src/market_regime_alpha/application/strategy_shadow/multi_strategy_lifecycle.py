"""Owner-resolved Strategy state projected from existing PostgreSQL facts.

The projection is deliberately stateless: observed Fill allocations remain the
Strategy sleeve ledger, manual account observations own marks, and each
Multi-Strategy cycle freezes the resulting state for replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.decision_system.contracts import (
    ManualAccountObservation,
    ManualPositionObservation,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.execution.manual import TradeSide
from market_regime_alpha.strategies.contracts import (
    CanonicalStrategyAction,
    PriceFreshnessStatus,
    StrategyPositionState,
)
from market_regime_alpha.strategies.sleeves import (
    FillAllocation,
    FillAllocationBatch,
    effective_fill_allocation_batches,
    project_strategy_sleeves,
)


_STATE_DECIMAL_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)
_TRADING_TIME_ZONE = ZoneInfo("Asia/Shanghai")
_BUY_ACTIONS = frozenset(
    {CanonicalStrategyAction.ENTER, CanonicalStrategyAction.ADD}
)
_SELL_ACTIONS = frozenset(
    {CanonicalStrategyAction.REDUCE, CanonicalStrategyAction.EXIT}
)


@dataclass(slots=True)
class _StrategyLot:
    quantity: int
    trade_date: date


@dataclass(frozen=True, slots=True)
class FillDerivedStrategyOutcome:
    outcome_id: ArtifactId
    outcome_hash: str
    account_id: str
    strategy_version_reference: RuntimeArtifactReference
    entry_proposal_reference: RuntimeArtifactReference
    exit_proposal_reference: RuntimeArtifactReference
    pre_exit_state_reference: RuntimeArtifactReference
    symbol: str
    opened_at: datetime
    closed_at: datetime
    invested_notional: Decimal
    gross_pnl: Decimal
    total_cost: Decimal
    net_pnl: Decimal
    net_return: Decimal
    source_allocation_references: tuple[RuntimeArtifactReference, ...]
    source_fill_references: tuple[RuntimeArtifactReference, ...]
    settled_at: datetime
    limitations: tuple[str, ...]
    revision: int = 1
    supersedes_outcome_reference: RuntimeArtifactReference | None = None
    schema_version: str = "fill-derived-strategy-outcome/v2"

    def __post_init__(self) -> None:
        require_sha256("outcome_hash", self.outcome_hash)
        require_text("account_id", self.account_id)
        require_text("symbol", self.symbol)
        if self.schema_version not in {
            "fill-derived-strategy-outcome/v1",
            "fill-derived-strategy-outcome/v2",
        }:
            raise ValueError("unsupported Fill-derived Strategy Outcome schema")
        if self.revision < 1 or (self.revision == 1) != (
            self.supersedes_outcome_reference is None
        ):
            raise ValueError("Strategy Outcome revision lineage is invalid")
        if self.schema_version == "fill-derived-strategy-outcome/v1" and (
            self.revision != 1 or self.supersedes_outcome_reference is not None
        ):
            raise ValueError("V1 Strategy Outcome cannot carry revision lineage")
        canonical_datetime(self.opened_at)
        canonical_datetime(self.closed_at)
        canonical_datetime(self.settled_at)
        if not self.opened_at < self.closed_at <= self.settled_at:
            raise ValueError("Strategy Outcome time ordering is invalid")
        if self.invested_notional <= 0 or self.total_cost < 0:
            raise ValueError("Strategy Outcome economics are invalid")
        if self.net_pnl != self.gross_pnl - self.total_cost:
            raise ValueError("Strategy Outcome PnL reconciliation failed")
        with localcontext(_STATE_DECIMAL_CONTEXT):
            if self.net_return != self.net_pnl / self.invested_notional:
                raise ValueError("Strategy Outcome return reconciliation failed")
        if not self.source_allocation_references or not self.source_fill_references:
            raise ValueError("Strategy Outcome requires Fill allocation lineage")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Strategy Outcome limitations must be sorted and unique")
        digest = canonical_hash(self.identity_payload())
        if (
            digest != self.outcome_hash
            or str(self.outcome_id) != f"strategy-realized-outcome:{digest[7:]}"
        ):
            raise ValueError("Strategy Outcome identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> FillDerivedStrategyOutcome:
        normalized = dict(values)
        normalized["source_allocation_references"] = _references(
            normalized["source_allocation_references"]
        )
        normalized["source_fill_references"] = _references(
            normalized["source_fill_references"]
        )
        normalized["limitations"] = tuple(sorted(set(normalized["limitations"])))
        normalized.setdefault("revision", 1)
        normalized.setdefault("supersedes_outcome_reference", None)
        normalized.setdefault("schema_version", "fill-derived-strategy-outcome/v2")
        digest = canonical_hash(_strategy_outcome_payload(**normalized))
        return cls(
            outcome_id=ArtifactId(f"strategy-realized-outcome:{digest[7:]}"),
            outcome_hash=digest,
            **normalized,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _strategy_outcome_payload(
            account_id=self.account_id,
            strategy_version_reference=self.strategy_version_reference,
            entry_proposal_reference=self.entry_proposal_reference,
            exit_proposal_reference=self.exit_proposal_reference,
            pre_exit_state_reference=self.pre_exit_state_reference,
            symbol=self.symbol,
            opened_at=self.opened_at,
            closed_at=self.closed_at,
            invested_notional=self.invested_notional,
            gross_pnl=self.gross_pnl,
            total_cost=self.total_cost,
            net_pnl=self.net_pnl,
            net_return=self.net_return,
            source_allocation_references=self.source_allocation_references,
            source_fill_references=self.source_fill_references,
            settled_at=self.settled_at,
            limitations=self.limitations,
            revision=self.revision,
            supersedes_outcome_reference=self.supersedes_outcome_reference,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": str(self.outcome_id),
            "outcome_hash": self.outcome_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> FillDerivedStrategyOutcome:
        return cls(
            outcome_id=ArtifactId(str(payload["outcome_id"])),
            outcome_hash=str(payload["outcome_hash"]),
            account_id=str(payload["account_id"]),
            strategy_version_reference=_reference(payload["strategy_version_reference"]),
            entry_proposal_reference=_reference(payload["entry_proposal_reference"]),
            exit_proposal_reference=_reference(payload["exit_proposal_reference"]),
            pre_exit_state_reference=_reference(payload["pre_exit_state_reference"]),
            symbol=str(payload["symbol"]),
            opened_at=datetime.fromisoformat(str(payload["opened_at"])),
            closed_at=datetime.fromisoformat(str(payload["closed_at"])),
            invested_notional=Decimal(str(payload["invested_notional"])),
            gross_pnl=Decimal(str(payload["gross_pnl"])),
            total_cost=Decimal(str(payload["total_cost"])),
            net_pnl=Decimal(str(payload["net_pnl"])),
            net_return=Decimal(str(payload["net_return"])),
            source_allocation_references=tuple(
                _reference(item) for item in _sequence(payload["source_allocation_references"])
            ),
            source_fill_references=tuple(
                _reference(item) for item in _sequence(payload["source_fill_references"])
            ),
            settled_at=datetime.fromisoformat(str(payload["settled_at"])),
            limitations=tuple(str(item) for item in _sequence(payload["limitations"])),
            revision=int(payload.get("revision", 1)),
            supersedes_outcome_reference=(
                None
                if payload.get("supersedes_outcome_reference") is None
                else _reference(payload["supersedes_outcome_reference"])
            ),
            schema_version=str(payload["schema_version"]),
        )


def project_strategy_position_states(
    *,
    account_id: str,
    decision_time: datetime,
    trading_calendar: TradingCalendarArtifact,
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
        sleeves = project_strategy_sleeves(available_batches)
        states = tuple(
            _state_for_sleeve(
                account_id=account_id,
                decision_time=decision_time,
                trading_calendar=trading_calendar,
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


def settle_fill_derived_strategy_outcomes(
    *,
    account_id: str,
    decision_time: datetime,
    batches: tuple[FillAllocationBatch, ...],
    proposal_actions: Mapping[ArtifactId, CanonicalStrategyAction],
    pre_exit_states: Mapping[ArtifactId, StrategyPositionState],
) -> tuple[FillDerivedStrategyOutcome, ...]:
    """Settle each fully closed ENTER..EXIT lifecycle from observed cash flows."""

    available = tuple(batch for batch in batches if batch.recorded_at <= decision_time)
    if any(batch.account_id != account_id for batch in available):
        raise ValueError("Strategy Outcome crossed account scope")
    effective = effective_fill_allocation_batches(available)
    _verify_fill_actions(effective, proposal_actions)
    scoped: dict[
        tuple[str, str, str],
        list[tuple[FillAllocationBatch, FillAllocation, CanonicalStrategyAction]],
    ] = {}
    for batch in effective:
        for allocation in batch.allocations:
            key = (
                str(allocation.strategy_version_reference.artifact_id),
                allocation.strategy_version_reference.content_hash,
                batch.symbol,
            )
            scoped.setdefault(key, []).append(
                (
                    batch,
                    allocation,
                    proposal_actions[allocation.proposal_reference.artifact_id],
                )
            )
    outcomes: list[FillDerivedStrategyOutcome] = []
    with localcontext(_STATE_DECIMAL_CONTEXT):
        for facts in scoped.values():
            active: list[
                tuple[FillAllocationBatch, FillAllocation, CanonicalStrategyAction]
            ] = []
            quantity = 0
            for batch, allocation, action in facts:
                allocated_quantity = allocation.allocated_quantity
                if action is CanonicalStrategyAction.ENTER:
                    if quantity == 0:
                        active = []
                    elif any(
                        prior_action is CanonicalStrategyAction.ENTER
                        and prior_allocation.proposal_reference
                        != allocation.proposal_reference
                        for _, prior_allocation, prior_action in active
                    ):
                        raise ValueError(
                            "ENTER Fill cannot replace an open Strategy sleeve"
                        )
                elif not active:
                    raise ValueError("Strategy lifecycle action has no ENTER Fill")
                if batch.side is TradeSide.BUY:
                    quantity += allocated_quantity
                else:
                    if allocated_quantity > quantity:
                        raise ValueError("Strategy SELL Fill exceeds open sleeve")
                    quantity -= allocated_quantity
                active.append((batch, allocation, action))
                if action is CanonicalStrategyAction.REDUCE and quantity == 0:
                    raise ValueError("REDUCE Fill cannot close Strategy sleeve")
                if action is not CanonicalStrategyAction.EXIT or quantity != 0:
                    continue
                pre_exit = pre_exit_states.get(
                    allocation.proposal_reference.artifact_id
                )
                if (
                    pre_exit is None
                    or pre_exit.state_reference is None
                    or pre_exit.account_id != account_id
                    or pre_exit.strategy_version_id
                    != allocation.strategy_version_reference.artifact_id
                    or pre_exit.symbol != batch.symbol
                ):
                    raise ValueError("Strategy Outcome requires owner-resolved pre-exit state")
                outcomes.append(
                    _settled_outcome(
                        account_id=account_id,
                        facts=tuple(active),
                        pre_exit=pre_exit,
                    )
                )
                active = []
                quantity = 0
    return tuple(sorted(outcomes, key=lambda item: str(item.outcome_id)))


def _settled_outcome(
    *,
    account_id: str,
    facts: tuple[
        tuple[FillAllocationBatch, FillAllocation, CanonicalStrategyAction], ...
    ],
    pre_exit: StrategyPositionState,
) -> FillDerivedStrategyOutcome:
    entry_batch, entry_allocation, entry_action = facts[0]
    exit_batch, exit_allocation, exit_action = facts[-1]
    if (
        entry_action is not CanonicalStrategyAction.ENTER
        or exit_action is not CanonicalStrategyAction.EXIT
        or pre_exit.state_reference is None
    ):
        raise ValueError("Strategy Outcome lifecycle endpoints are invalid")
    buys = sum(
        (
            batch.price * Decimal(allocation.allocated_quantity)
            for batch, allocation, _ in facts
            if batch.side is TradeSide.BUY
        ),
        Decimal("0"),
    )
    sells = sum(
        (
            batch.price * Decimal(allocation.allocated_quantity)
            for batch, allocation, _ in facts
            if batch.side is TradeSide.SELL
        ),
        Decimal("0"),
    )
    costs = sum(
        (
            batch.fees
            * Decimal(allocation.allocated_quantity)
            / Decimal(batch.quantity)
            for batch, allocation, _ in facts
        ),
        Decimal("0"),
    )
    gross_pnl = sells - buys
    net_pnl = gross_pnl - costs
    return FillDerivedStrategyOutcome.create(
        account_id=account_id,
        strategy_version_reference=entry_allocation.strategy_version_reference,
        entry_proposal_reference=entry_allocation.proposal_reference,
        exit_proposal_reference=exit_allocation.proposal_reference,
        pre_exit_state_reference=pre_exit.state_reference,
        symbol=entry_batch.symbol,
        opened_at=entry_batch.occurred_at,
        closed_at=exit_batch.occurred_at,
        invested_notional=buys,
        gross_pnl=gross_pnl,
        total_cost=costs,
        net_pnl=net_pnl,
        net_return=net_pnl / buys,
        source_allocation_references=tuple(
            RuntimeArtifactReference(
                "STRATEGY_FILL_ALLOCATION",
                allocation.allocation_id,
                allocation.allocation_hash,
            )
            for _, allocation, _ in facts
        ),
        source_fill_references=tuple(
            allocation.fill_reference for _, allocation, _ in facts
        ),
        settled_at=exit_batch.recorded_at,
        limitations=(
            "ALPHA_NOT_ESTABLISHED",
            "ENGINEERING_CORRECTNESS_ONLY",
            "MARKET_PATH_OUTCOME_SEPARATE",
            "PRODUCTION_AUTHORIZED_FALSE",
        ),
    )


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
    trading_calendar: TradingCalendarArtifact,
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
    history = tuple(
        (batch, allocation, proposal_actions[allocation.proposal_reference.artifact_id])
        for batch in effective
        for allocation in batch.allocations
        if allocation.strategy_version_reference.artifact_id == sleeve_version_id
        and batch.symbol == symbol
    )
    scoped = _current_open_lifecycle(history)
    entries = tuple(
        batch.occurred_at
        for batch, _, action in scoped
        if action is CanonicalStrategyAction.ENTER
    )
    if not entries:
        raise ValueError("open Strategy sleeve has no ENTER Fill lineage")
    entry_time = min(entries)
    entry_trading_date = entry_time.astimezone(_TRADING_TIME_ZONE).date()
    if not trading_calendar.contains(entry_trading_date):
        raise ValueError("ENTER Fill occurrence is outside the canonical Trading Calendar")
    decision_local_date = decision_time.astimezone(_TRADING_TIME_ZONE).date()
    session_dates = tuple(
        item for item in trading_calendar.trading_dates if item <= decision_local_date
    )
    if not session_dates:
        raise ValueError("Decision Time precedes the canonical Trading Calendar")
    decision_session_date = session_dates[-1]
    marks = tuple(
        (observation, position)
        for observation in observations
        if observation.as_of_time > entry_time
        for position in observation.positions
        if position.symbol == symbol
    )
    if marks and Decimal(marks[-1][1].total_quantity) < quantity:
        raise ValueError("Physical Position is below allocated Strategy sleeves")
    prices = tuple(_observed_price(position) for _, position in marks)
    current_price = None if not prices else prices[-1]
    peak_price = max((average_cost, *prices))
    price_observed_at = None if not marks else marks[-1][0].as_of_time
    if not marks:
        price_freshness = PriceFreshnessStatus.NOT_ESTIMABLE
    elif (
        decision_local_date in trading_calendar.trading_dates
        and marks[-1][0].trading_date == decision_local_date
    ):
        price_freshness = PriceFreshnessStatus.FRESH
    else:
        price_freshness = PriceFreshnessStatus.STALE
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
        sessions_held=sum(
            entry_trading_date < trade_date <= decision_session_date
            for trade_date in trading_calendar.trading_dates
        ),
        add_count=len(
            {
                allocation.proposal_reference.artifact_id
                for _, allocation, action in scoped
                if action is CanonicalStrategyAction.ADD
            }
        ),
        reduce_count=len(
            {
                allocation.proposal_reference.artifact_id
                for _, allocation, action in scoped
                if action is CanonicalStrategyAction.REDUCE
            }
        ),
        source_allocation_references=allocation_references,
        source_fill_references=fill_references,
        price_observation_references=observation_references,
        available_quantity=Decimal(
            _available_quantity(
                scoped=scoped,
                trading_calendar=trading_calendar,
                decision_session_date=decision_session_date,
            )
        ),
        entry_time=entry_time,
        price_observed_at=price_observed_at,
        price_freshness=price_freshness,
        trading_calendar_reference=RuntimeArtifactReference(
            "TRADING_CALENDAR",
            trading_calendar.artifact_id,
            trading_calendar.content_hash,
        ),
    )


def _current_open_lifecycle(
    facts: tuple[
        tuple[FillAllocationBatch, FillAllocation, CanonicalStrategyAction], ...
    ],
) -> tuple[
    tuple[FillAllocationBatch, FillAllocation, CanonicalStrategyAction], ...
]:
    active: list[
        tuple[FillAllocationBatch, FillAllocation, CanonicalStrategyAction]
    ] = []
    quantity = 0
    for fact in facts:
        batch, allocation, action = fact
        if quantity == 0:
            if action is not CanonicalStrategyAction.ENTER:
                raise ValueError("open Strategy lifecycle must begin with ENTER")
            active = []
        if batch.side is TradeSide.BUY:
            quantity += allocation.allocated_quantity
        else:
            quantity -= allocation.allocated_quantity
        if quantity < 0:
            raise ValueError("Strategy lifecycle quantity cannot become negative")
        active.append(fact)
        if quantity == 0:
            active = []
    if not active:
        raise ValueError("open Strategy sleeve has no active lifecycle")
    return tuple(active)


def _available_quantity(
    *,
    scoped: tuple[
        tuple[FillAllocationBatch, FillAllocation, CanonicalStrategyAction], ...
    ],
    trading_calendar: TradingCalendarArtifact,
    decision_session_date: date,
) -> int:
    lots: list[_StrategyLot] = []
    for batch, allocation, _ in scoped:
        quantity = allocation.allocated_quantity
        if batch.side is TradeSide.BUY:
            trade_date = batch.occurred_at.astimezone(_TRADING_TIME_ZONE).date()
            if not trading_calendar.contains(trade_date):
                raise ValueError("BUY Fill occurrence is outside the canonical Trading Calendar")
            lots.append(_StrategyLot(quantity=quantity, trade_date=trade_date))
            continue
        remaining = quantity
        for lot in lots:
            consumed = min(lot.quantity, remaining)
            lot.quantity -= consumed
            remaining -= consumed
            if remaining == 0:
                break
        if remaining:
            raise ValueError("Strategy SELL Fill exceeds open sleeve lots")
    dates = trading_calendar.trading_dates
    available = 0
    for lot in lots:
        if lot.quantity == 0:
            continue
        sellable = next((item for item in dates if item > lot.trade_date), None)
        if sellable is not None and sellable <= decision_session_date:
            available += lot.quantity
    return available


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


def _strategy_outcome_payload(**values: Any) -> dict[str, Any]:
    payload = {
        "schema_version": values["schema_version"],
        "account_id": values["account_id"],
        "strategy_version_reference": values[
            "strategy_version_reference"
        ].to_canonical_dict(),
        "entry_proposal_reference": values[
            "entry_proposal_reference"
        ].to_canonical_dict(),
        "exit_proposal_reference": values[
            "exit_proposal_reference"
        ].to_canonical_dict(),
        "pre_exit_state_reference": values[
            "pre_exit_state_reference"
        ].to_canonical_dict(),
        "symbol": values["symbol"],
        "opened_at": canonical_datetime(values["opened_at"]),
        "closed_at": canonical_datetime(values["closed_at"]),
        "invested_notional": str(values["invested_notional"]),
        "gross_pnl": str(values["gross_pnl"]),
        "total_cost": str(values["total_cost"]),
        "net_pnl": str(values["net_pnl"]),
        "net_return": str(values["net_return"]),
        "source_allocation_references": [
            item.to_canonical_dict()
            for item in values["source_allocation_references"]
        ],
        "source_fill_references": [
            item.to_canonical_dict() for item in values["source_fill_references"]
        ],
        "settled_at": canonical_datetime(values["settled_at"]),
        "limitations": list(values["limitations"]),
    }
    if values["schema_version"] == "fill-derived-strategy-outcome/v2":
        supersedes = values["supersedes_outcome_reference"]
        payload.update(
            {
                "revision": values["revision"],
                "supersedes_outcome_reference": (
                    None if supersedes is None else supersedes.to_canonical_dict()
                ),
            }
        )
    return payload


def _reference(value: object) -> RuntimeArtifactReference:
    if not isinstance(value, Mapping):
        raise ValueError("expected Artifact reference")
    return RuntimeArtifactReference.from_canonical_dict(value)


def _sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return value


__all__ = [
    "FillDerivedStrategyOutcome",
    "project_strategy_position_states",
    "settle_fill_derived_strategy_outcomes",
]
