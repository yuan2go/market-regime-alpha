"""Bounded Decision/Outcome windows over an exact Historical corpus owner."""

from __future__ import annotations

from bisect import bisect_right
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.historical_corpus.artifacts import (
    HistoricalPackageIndex,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalNormalizedBar,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_corpus.selective_read import (
    HistoricalDataSlice,
    HistoricalReadMetrics,
    HistoricalReadQuery,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data import Timeframe


@dataclass(frozen=True, slots=True)
class HistoricalDatasetWindowIndex:
    package: HistoricalPackageIndex
    series: Mapping[tuple[str, Timeframe], tuple[HistoricalNormalizedBar, ...]]
    event_ends: Mapping[tuple[str, Timeframe], tuple[datetime, ...]]
    daily_dates: tuple[date, ...]
    daily_read_lineage: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _CachedMinuteSession:
    records: tuple[HistoricalNormalizedBar, ...]
    read_lineage: Mapping[str, Any]


class HistoricalWindowReader:
    """Own selective reads, bounded caches and their exact persisted lineage."""

    def __init__(
        self,
        repository: PostgresHistoricalCorpusRepository,
        *,
        maximum_daily_rows: int,
        maximum_minute_session_rows: int,
        minute_session_cache_size: int,
    ) -> None:
        if maximum_daily_rows <= 0 or maximum_minute_session_rows <= 0:
            raise ValueError("Historical window row limits must be positive")
        if minute_session_cache_size < 3:
            raise ValueError("Historical minute cache must hold Decision and T+1 sessions")
        self._repository = repository
        self._maximum_daily_rows = maximum_daily_rows
        self._maximum_minute_session_rows = maximum_minute_session_rows
        self._minute_session_cache_size = minute_session_cache_size
        self._indexes: dict[ValidationArtifactReference, HistoricalDatasetWindowIndex] = {}
        self._minute_sessions: OrderedDict[tuple[ValidationArtifactReference, date], _CachedMinuteSession] = OrderedDict()
        self._metrics: list[HistoricalReadMetrics] = []
        self._active_lineage: list[Mapping[str, Any]] = []

    def begin_stage(self) -> None:
        self._active_lineage = []

    def index(self, reference: ValidationArtifactReference) -> HistoricalDatasetWindowIndex:
        cached = self._indexes.get(reference)
        if cached is not None:
            return cached
        package = self._repository.open_index(reference)
        daily_slice = self._read_normalized(
            HistoricalReadQuery.create(
                reference=reference,
                timeframes=(Timeframe.DAILY,),
                first_market_date=package.first_market_date,
                last_market_date=package.last_market_date,
                symbols=package.coverage.expected_symbols,
                max_rows=self._maximum_daily_rows,
            ),
            record_lineage=False,
        )
        grouped: dict[tuple[str, Timeframe], list[HistoricalNormalizedBar]] = {}
        for bar in daily_slice.records:
            assert isinstance(bar, HistoricalNormalizedBar)
            grouped.setdefault((bar.symbol, bar.timeframe), []).append(bar)
        series = {key: tuple(sorted(values, key=_bar_key)) for key, values in grouped.items()}
        index = HistoricalDatasetWindowIndex(
            package=package,
            series=series,
            event_ends={key: tuple(item.event_end for item in values) for key, values in series.items()},
            daily_dates=tuple(
                sorted(
                    {
                        item.market_date
                        for (symbol, timeframe), values in series.items()
                        if timeframe is Timeframe.DAILY and not _is_etf_symbol(symbol)
                        for item in values
                    }
                )
            ),
            daily_read_lineage=_slice_lineage(daily_slice),
        )
        self._indexes[reference] = index
        return index

    def decision_bars(
        self,
        reference: ValidationArtifactReference,
        decision_time: datetime,
    ) -> tuple[HistoricalNormalizedBar, ...]:
        index = self.index(reference)
        self._record_lineage(index.daily_read_lineage)
        result: list[HistoricalNormalizedBar] = []
        market_date = decision_time.astimezone(ZoneInfo("Asia/Shanghai")).date()
        for key, values in index.series.items():
            result.extend(values[: bisect_right(index.event_ends[key], decision_time)])
        current = self._minute_session(reference, market_date)
        prior_date = next(
            (item for item in reversed(index.daily_dates) if item < market_date),
            None,
        )
        prior = () if prior_date is None else self._minute_session(reference, prior_date)
        if not prior:
            prior = self._prior_minute_session(reference, market_date)
        result.extend(item for item in (*prior, *current) if item.event_end <= decision_time)
        return tuple(sorted(result, key=_bar_key))

    def next_session(self, reference: ValidationArtifactReference, trading_date: date) -> date | None:
        return next(
            (item for item in self.index(reference).daily_dates if item > trading_date),
            None,
        )

    def outcome_bars(
        self,
        reference: ValidationArtifactReference,
        *,
        decision_time: datetime,
        next_session: date,
    ) -> tuple[HistoricalNormalizedBar, ...]:
        index = self.index(reference)
        self._record_lineage(index.daily_read_lineage)
        result = [
            item
            for values in index.series.values()
            for item in values
            if item.event_end <= decision_time or item.market_date == next_session
        ]
        result.extend(self._minute_session(reference, next_session))
        return tuple(sorted(result, key=_bar_key))

    def metrics(self) -> tuple[HistoricalReadMetrics, ...]:
        return tuple(self._metrics)

    def stage_lineage_payload(self) -> list[Mapping[str, Any]]:
        keyed = {canonical_hash(item): item for item in self._active_lineage}
        return [keyed[key] for key in sorted(keyed)]

    def _minute_session(
        self,
        reference: ValidationArtifactReference,
        session_date: date,
    ) -> tuple[HistoricalNormalizedBar, ...]:
        key = (reference, session_date)
        cached = self._minute_sessions.get(key)
        if cached is not None:
            self._minute_sessions.move_to_end(key)
            self._record_lineage(cached.read_lineage)
            return cached.records
        values, lineage = self._read_minute_range(reference, first_date=session_date, last_date=session_date)
        self._record_lineage(lineage)
        self._minute_sessions[key] = _CachedMinuteSession(values, lineage)
        self._minute_sessions.move_to_end(key)
        while len(self._minute_sessions) > self._minute_session_cache_size:
            self._minute_sessions.popitem(last=False)
        return values

    def _prior_minute_session(
        self,
        reference: ValidationArtifactReference,
        market_date: date,
    ) -> tuple[HistoricalNormalizedBar, ...]:
        values, lineage = self._read_minute_range(
            reference,
            first_date=market_date - timedelta(days=20),
            last_date=market_date - timedelta(days=1),
        )
        self._record_lineage(lineage)
        grouped: dict[date, list[HistoricalNormalizedBar]] = {}
        for item in values:
            grouped.setdefault(item.market_date, []).append(item)
        if not grouped:
            return ()
        return tuple(sorted(grouped[max(grouped)], key=_bar_key))

    def _read_minute_range(
        self,
        reference: ValidationArtifactReference,
        *,
        first_date: date,
        last_date: date,
    ) -> tuple[tuple[HistoricalNormalizedBar, ...], Mapping[str, Any]]:
        package = self.index(reference).package
        data_slice = self._read_normalized(
            HistoricalReadQuery.create(
                reference=reference,
                timeframes=(Timeframe.MINUTE_5,),
                first_market_date=first_date,
                last_market_date=last_date,
                symbols=package.coverage.expected_symbols,
                max_rows=self._maximum_minute_session_rows,
            ),
            record_lineage=False,
        )
        values = tuple(item for item in data_slice.records if isinstance(item, HistoricalNormalizedBar))
        return values, _slice_lineage(data_slice)

    def _read_normalized(self, query: HistoricalReadQuery, *, record_lineage: bool) -> HistoricalDataSlice:
        data_slice = self._repository.read(query)
        self._metrics.append(data_slice.metrics)
        if any(not isinstance(item, HistoricalNormalizedBar) for item in data_slice.records):
            raise ValueError("Historical materialization requires normalized bars")
        if record_lineage:
            self._record_lineage(_slice_lineage(data_slice))
        return data_slice

    def _record_lineage(self, lineage: Mapping[str, Any]) -> None:
        self._active_lineage.append(lineage)


def _slice_lineage(data_slice: HistoricalDataSlice) -> dict[str, Any]:
    query = data_slice.query
    checksums = dict(data_slice.package.checksums)
    symbols = query.symbols
    return {
        "owner_reference": query.reference.to_canonical_dict(),
        "query": {
            "timeframes": [item.value for item in query.timeframes],
            "first_market_date": query.first_market_date.isoformat(),
            "last_market_date": query.last_market_date.isoformat(),
            "symbol_count": None if symbols is None else len(symbols),
            "symbols_hash": (None if symbols is None else canonical_hash({"symbols": list(symbols)})),
            "max_rows": query.max_rows,
            "batch_size": query.batch_size,
        },
        "selected_partitions": [
            {
                **item.reference_dict(),
                "physical_checksum": checksums[item.relative_path],
            }
            for item in data_slice.partitions
        ],
        "metrics": data_slice.metrics.to_canonical_dict(),
    }


def _bar_key(item: HistoricalNormalizedBar) -> tuple[str, str, datetime, str]:
    return item.symbol, item.timeframe.value, item.event_end, str(item.bar_id)


def _is_etf_symbol(symbol: str) -> bool:
    return symbol.startswith(("15", "16", "50", "51", "56", "58"))


__all__ = ["HistoricalDatasetWindowIndex", "HistoricalWindowReader"]
