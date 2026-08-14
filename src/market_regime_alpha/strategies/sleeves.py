"""Strategy Sleeve projection derived exclusively from allocated observed Fills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, FillId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.execution.manual import Fill, TradeSide


@dataclass(frozen=True, slots=True)
class FillAllocation:
    allocation_id: ArtifactId
    allocation_hash: str
    fill_reference: RuntimeArtifactReference
    strategy_version_reference: RuntimeArtifactReference
    proposal_reference: RuntimeArtifactReference
    allocated_quantity: int
    schema_version: str = "strategy-fill-allocation/v1"

    def __post_init__(self) -> None:
        require_sha256("allocation_hash", self.allocation_hash)
        if self.allocated_quantity <= 0:
            raise ValueError("allocated Fill quantity must be positive")
        if canonical_hash(self.identity_payload()) != self.allocation_hash:
            raise ValueError("Fill Allocation hash mismatch")
        if str(self.allocation_id) != f"strategy-fill-allocation:{self.allocation_hash[7:]}":
            raise ValueError("Fill Allocation identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        fill_reference: RuntimeArtifactReference,
        strategy_version_reference: RuntimeArtifactReference,
        proposal_reference: RuntimeArtifactReference,
        allocated_quantity: int,
    ) -> FillAllocation:
        payload = _allocation_payload(
            fill_reference=fill_reference,
            strategy_version_reference=strategy_version_reference,
            proposal_reference=proposal_reference,
            allocated_quantity=allocated_quantity,
            schema_version="strategy-fill-allocation/v1",
        )
        digest = canonical_hash(payload)
        return cls(
            allocation_id=ArtifactId(f"strategy-fill-allocation:{digest[7:]}"),
            allocation_hash=digest,
            fill_reference=fill_reference,
            strategy_version_reference=strategy_version_reference,
            proposal_reference=proposal_reference,
            allocated_quantity=allocated_quantity,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _allocation_payload(
            fill_reference=self.fill_reference,
            strategy_version_reference=self.strategy_version_reference,
            proposal_reference=self.proposal_reference,
            allocated_quantity=self.allocated_quantity,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "allocation_id": str(self.allocation_id),
            "allocation_hash": self.allocation_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FillAllocation:
        return cls(
            allocation_id=ArtifactId(str(payload["allocation_id"])),
            allocation_hash=str(payload["allocation_hash"]),
            fill_reference=_reference(payload["fill_reference"]),
            strategy_version_reference=_reference(payload["strategy_version_reference"]),
            proposal_reference=_reference(payload["proposal_reference"]),
            allocated_quantity=int(payload["allocated_quantity"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class FillAllocationBatch:
    batch_id: ArtifactId
    batch_hash: str
    source_fill_id: FillId
    source_fill_hash: str
    correction_of_fill_id: FillId | None
    account_id: str
    symbol: str
    side: TradeSide
    quantity: int
    price: Decimal
    fees: Decimal
    occurred_at: datetime
    recorded_at: datetime
    allocations: tuple[FillAllocation, ...]
    schema_version: str = "strategy-fill-allocation-batch/v1"

    def __post_init__(self) -> None:
        require_sha256("batch_hash", self.batch_hash)
        require_sha256("source_fill_hash", self.source_fill_hash)
        require_text("account_id", self.account_id)
        require_text("symbol", self.symbol)
        canonical_datetime(self.occurred_at)
        canonical_datetime(self.recorded_at)
        if self.quantity <= 0 or self.price <= 0 or self.fees < 0:
            raise ValueError("allocated Fill economics are invalid")
        allocation_ids = tuple(str(item.allocation_id) for item in self.allocations)
        if allocation_ids != tuple(sorted(set(allocation_ids))):
            raise ValueError("Fill allocations must be unique and sorted")
        if sum(item.allocated_quantity for item in self.allocations) != self.quantity:
            raise ValueError("observed Fill must be fully allocated")
        if any(
            item.fill_reference.artifact_id != ArtifactId(str(self.source_fill_id))
            or item.fill_reference.content_hash != self.source_fill_hash
            for item in self.allocations
        ):
            raise ValueError("Fill Allocation source lineage mismatch")
        if canonical_hash(self.identity_payload()) != self.batch_hash:
            raise ValueError("Fill Allocation Batch hash mismatch")
        if str(self.batch_id) != f"strategy-fill-batch:{self.batch_hash[7:]}":
            raise ValueError("Fill Allocation Batch identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_fill_id": str(self.source_fill_id),
            "source_fill_hash": self.source_fill_hash,
            "correction_of_fill_id": (None if self.correction_of_fill_id is None else str(self.correction_of_fill_id)),
            "account_id": self.account_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": str(self.price),
            "fees": str(self.fees),
            "occurred_at": canonical_datetime(self.occurred_at),
            "recorded_at": canonical_datetime(self.recorded_at),
            "allocations": [item.to_canonical_dict() for item in self.allocations],
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "batch_id": str(self.batch_id),
            "batch_hash": self.batch_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FillAllocationBatch:
        correction = payload["correction_of_fill_id"]
        return cls(
            batch_id=ArtifactId(str(payload["batch_id"])),
            batch_hash=str(payload["batch_hash"]),
            source_fill_id=FillId(str(payload["source_fill_id"])),
            source_fill_hash=str(payload["source_fill_hash"]),
            correction_of_fill_id=(None if correction is None else FillId(str(correction))),
            account_id=str(payload["account_id"]),
            symbol=str(payload["symbol"]),
            side=TradeSide(str(payload["side"])),
            quantity=int(payload["quantity"]),
            price=Decimal(str(payload["price"])),
            fees=Decimal(str(payload["fees"])),
            occurred_at=datetime.fromisoformat(str(payload["occurred_at"])),
            recorded_at=datetime.fromisoformat(str(payload["recorded_at"])),
            allocations=tuple(FillAllocation.from_canonical_dict(_mapping(item)) for item in _sequence(payload["allocations"])),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class StrategySleevePosition:
    strategy_version_reference: RuntimeArtifactReference
    account_id: str
    symbol: str
    quantity: int
    average_cost: Decimal | None
    source_allocation_ids: tuple[ArtifactId, ...]
    source_fill_ids: tuple[FillId, ...]
    as_of: datetime

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("Strategy Sleeve quantity cannot be negative")
        if (self.quantity == 0) != (self.average_cost is None):
            raise ValueError("Strategy Sleeve average cost must match open state")
        if not self.source_fill_ids or not self.source_allocation_ids:
            raise ValueError("Strategy Sleeve requires observed Fill lineage")
        canonical_datetime(self.as_of)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "strategy_version_reference": self.strategy_version_reference.to_canonical_dict(),
            "account_id": self.account_id,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_cost": (None if self.average_cost is None else str(self.average_cost)),
            "source_allocation_ids": [str(item) for item in self.source_allocation_ids],
            "source_fill_ids": [str(item) for item in self.source_fill_ids],
            "as_of": canonical_datetime(self.as_of),
        }


def allocate_observed_fill(
    *,
    fill: Fill,
    allocations: tuple[tuple[RuntimeArtifactReference, RuntimeArtifactReference, int], ...],
) -> FillAllocationBatch:
    fill_payload = fill.to_canonical_dict()
    fill_hash = canonical_hash(fill_payload)
    fill_reference = RuntimeArtifactReference("MANUAL_FILL", ArtifactId(str(fill.fill_id)), fill_hash)
    rows = tuple(
        sorted(
            (
                FillAllocation.create(
                    fill_reference=fill_reference,
                    strategy_version_reference=version_reference,
                    proposal_reference=proposal_reference,
                    allocated_quantity=quantity,
                )
                for version_reference, proposal_reference, quantity in allocations
            ),
            key=lambda item: str(item.allocation_id),
        )
    )
    values = {
        "schema_version": "strategy-fill-allocation-batch/v1",
        "source_fill_id": str(fill.fill_id),
        "source_fill_hash": fill_hash,
        "correction_of_fill_id": (None if fill.correction_of_fill_id is None else str(fill.correction_of_fill_id)),
        "account_id": fill.account_id,
        "symbol": fill.symbol,
        "side": fill.side.value,
        "quantity": fill.quantity,
        "price": str(Decimal(str(fill.price))),
        "fees": str(Decimal(str(fill.fees))),
        "occurred_at": canonical_datetime(fill.occurred_at),
        "recorded_at": canonical_datetime(fill.recorded_at),
        "allocations": [item.to_canonical_dict() for item in rows],
    }
    digest = canonical_hash(values)
    return FillAllocationBatch(
        batch_id=ArtifactId(f"strategy-fill-batch:{digest[7:]}"),
        batch_hash=digest,
        source_fill_id=fill.fill_id,
        source_fill_hash=fill_hash,
        correction_of_fill_id=fill.correction_of_fill_id,
        account_id=fill.account_id,
        symbol=fill.symbol,
        side=fill.side,
        quantity=fill.quantity,
        price=Decimal(str(fill.price)),
        fees=Decimal(str(fill.fees)),
        occurred_at=fill.occurred_at,
        recorded_at=fill.recorded_at,
        allocations=rows,
    )


def project_strategy_sleeves(
    batches: tuple[FillAllocationBatch, ...],
) -> tuple[StrategySleevePosition, ...]:
    effective = effective_fill_allocation_batches(batches)
    states: dict[
        tuple[str, str, str],
        tuple[RuntimeArtifactReference, int, Decimal, list[ArtifactId], list[FillId]],
    ] = {}
    for batch in effective:
        for allocation in batch.allocations:
            key = (
                str(allocation.strategy_version_reference.artifact_id),
                batch.account_id,
                batch.symbol,
            )
            version_reference, quantity, cost, allocation_ids, fill_ids = states.get(
                key,
                (
                    allocation.strategy_version_reference,
                    0,
                    Decimal("0"),
                    [],
                    [],
                ),
            )
            allocated_quantity = allocation.allocated_quantity
            if batch.side is TradeSide.BUY:
                allocated_fees = batch.fees * Decimal(allocated_quantity) / Decimal(batch.quantity)
                quantity += allocated_quantity
                cost += batch.price * Decimal(allocated_quantity) + allocated_fees
            else:
                if allocated_quantity > quantity:
                    raise ValueError("allocated SELL exceeds Strategy Sleeve quantity")
                unit_cost = Decimal("0") if quantity == 0 else cost / Decimal(quantity)
                quantity -= allocated_quantity
                cost = unit_cost * Decimal(quantity)
            allocation_ids.append(allocation.allocation_id)
            fill_ids.append(batch.source_fill_id)
            states[key] = (
                version_reference,
                quantity,
                cost,
                allocation_ids,
                fill_ids,
            )
    if not effective:
        return ()
    as_of = max(item.recorded_at for item in effective)
    return tuple(
        StrategySleevePosition(
            strategy_version_reference=version_reference,
            account_id=account_id,
            symbol=symbol,
            quantity=quantity,
            average_cost=(None if quantity == 0 else cost / Decimal(quantity)),
            source_allocation_ids=tuple(allocation_ids),
            source_fill_ids=tuple(fill_ids),
            as_of=as_of,
        )
        for (version_id, account_id, symbol), (
            version_reference,
            quantity,
            cost,
            allocation_ids,
            fill_ids,
        ) in sorted(states.items())
    )


def effective_fill_allocation_batches(
    batches: tuple[FillAllocationBatch, ...],
) -> tuple[FillAllocationBatch, ...]:
    executions: dict[FillId, FillAllocationBatch] = {}
    corrections: dict[FillId, FillAllocationBatch] = {}
    seen: set[FillId] = set()
    ordered = sorted(
        batches,
        key=lambda item: (item.recorded_at, str(item.source_fill_id)),
    )
    for batch in ordered:
        if batch.source_fill_id in seen:
            raise ValueError("duplicate Fill Allocation Batch")
        seen.add(batch.source_fill_id)
        if batch.correction_of_fill_id is None:
            executions[batch.source_fill_id] = batch
    for batch in ordered:
        if batch.correction_of_fill_id is None:
            continue
        original = executions.get(batch.correction_of_fill_id)
        if original is None:
            raise ValueError(
                "Fill Allocation correction references unknown execution: "
                f"{batch.correction_of_fill_id}; executions="
                f"{tuple(sorted(str(item) for item in executions))}"
            )
        if batch.correction_of_fill_id in corrections:
            raise ValueError("Fill Allocation execution has multiple corrections")
        if batch.account_id != original.account_id or batch.symbol != original.symbol or batch.side is not original.side:
            raise ValueError("Fill Allocation correction scope mismatch")
        if batch.recorded_at < original.recorded_at:
            raise ValueError("Fill Allocation correction predates execution")
        corrections[batch.correction_of_fill_id] = batch
    return tuple(
        sorted(
            (corrections.get(fill_id, batch) for fill_id, batch in executions.items()),
            key=lambda item: (item.occurred_at, str(item.source_fill_id)),
        )
    )


def _allocation_payload(
    *,
    fill_reference: RuntimeArtifactReference,
    strategy_version_reference: RuntimeArtifactReference,
    proposal_reference: RuntimeArtifactReference,
    allocated_quantity: int,
    schema_version: str,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "fill_reference": fill_reference.to_canonical_dict(),
        "strategy_version_reference": strategy_version_reference.to_canonical_dict(),
        "proposal_reference": proposal_reference.to_canonical_dict(),
        "allocated_quantity": allocated_quantity,
    }


def _reference(value: object) -> RuntimeArtifactReference:
    if not isinstance(value, Mapping):
        raise ValueError("expected Artifact reference")
    return RuntimeArtifactReference.from_canonical_dict(value)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return value


__all__ = [
    "FillAllocation",
    "FillAllocationBatch",
    "StrategySleevePosition",
    "allocate_observed_fill",
    "effective_fill_allocation_batches",
    "project_strategy_sleeves",
]
