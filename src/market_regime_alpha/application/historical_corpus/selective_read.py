"""Bounded selective-read contracts for immutable Historical packages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalPartitionRecord,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.market_data.contracts import Timeframe

if TYPE_CHECKING:
    from market_regime_alpha.application.historical_corpus.artifacts import (
        HistoricalPackageIndex,
        HistoricalPartitionDescriptor,
    )


@dataclass(frozen=True, slots=True)
class HistoricalReadQuery:
    reference: ValidationArtifactReference
    timeframes: tuple[Timeframe, ...]
    first_market_date: date
    last_market_date: date
    symbols: tuple[str, ...] | None
    max_rows: int
    batch_size: int

    def __post_init__(self) -> None:
        if self.first_market_date > self.last_market_date:
            raise ValueError("Historical read date range is reversed")
        if not self.timeframes or self.timeframes != tuple(
            sorted(set(self.timeframes), key=lambda item: item.value)
        ):
            raise ValueError("Historical read timeframes must be sorted and unique")
        if self.symbols is not None:
            if not self.symbols or self.symbols != tuple(sorted(set(self.symbols))):
                raise ValueError("Historical read symbols must be sorted and unique")
        if isinstance(self.max_rows, bool) or self.max_rows <= 0:
            raise ValueError("Historical read max_rows must be positive")
        if isinstance(self.batch_size, bool) or not 1 <= self.batch_size <= self.max_rows:
            raise ValueError("Historical read batch_size must be within max_rows")

    @classmethod
    def create(
        cls,
        *,
        reference: ValidationArtifactReference,
        timeframes: tuple[Timeframe, ...],
        first_market_date: date,
        last_market_date: date,
        symbols: tuple[str, ...] | None,
        max_rows: int,
        batch_size: int = 8_192,
    ) -> HistoricalReadQuery:
        return cls(
            reference=reference,
            timeframes=tuple(sorted(set(timeframes), key=lambda item: item.value)),
            first_market_date=first_market_date,
            last_market_date=last_market_date,
            symbols=None if symbols is None else tuple(sorted(set(symbols))),
            max_rows=max_rows,
            batch_size=min(batch_size, max_rows),
        )


@dataclass(frozen=True, slots=True)
class HistoricalReadMetrics:
    candidate_partition_count: int
    candidate_partition_row_count: int
    verified_partition_count: int
    verified_bytes: int
    returned_row_count: int
    arrow_batch_count: int
    maximum_batch_row_count: int
    projected_columns: tuple[str, ...]
    predicate_pushdown: bool

    def __post_init__(self) -> None:
        counts = (
            self.candidate_partition_count,
            self.candidate_partition_row_count,
            self.verified_partition_count,
            self.verified_bytes,
            self.returned_row_count,
            self.arrow_batch_count,
            self.maximum_batch_row_count,
        )
        if any(isinstance(item, bool) or item < 0 for item in counts):
            raise ValueError("Historical read metrics must be non-negative")
        if self.verified_partition_count > self.candidate_partition_count:
            raise ValueError("verified partitions exceed candidate partitions")
        if self.projected_columns != tuple(sorted(set(self.projected_columns))):
            raise ValueError("projected columns must be sorted and unique")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "candidate_partition_count": self.candidate_partition_count,
            "candidate_partition_row_count": self.candidate_partition_row_count,
            "verified_partition_count": self.verified_partition_count,
            "verified_bytes": self.verified_bytes,
            "returned_row_count": self.returned_row_count,
            "arrow_batch_count": self.arrow_batch_count,
            "maximum_batch_row_count": self.maximum_batch_row_count,
            "projected_columns": list(self.projected_columns),
            "predicate_pushdown": self.predicate_pushdown,
        }


@dataclass(frozen=True, slots=True)
class HistoricalDataSlice:
    package: HistoricalPackageIndex
    query: HistoricalReadQuery
    partitions: tuple[HistoricalPartitionDescriptor, ...]
    records: tuple[HistoricalPartitionRecord, ...]
    metrics: HistoricalReadMetrics

    def __post_init__(self) -> None:
        if self.package.reference != self.query.reference:
            raise ValueError("Historical slice owner reference mismatch")
        if len(self.records) != self.metrics.returned_row_count:
            raise ValueError("Historical slice row metric mismatch")
        if len(self.records) > self.query.max_rows:
            raise ValueError("Historical slice exceeds max_rows")


__all__ = [
    "HistoricalDataSlice",
    "HistoricalReadMetrics",
    "HistoricalReadQuery",
]
