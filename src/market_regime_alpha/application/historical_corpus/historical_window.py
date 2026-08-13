"""Bounded Decision/Outcome windows over an exact Historical corpus owner."""

from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class _CachedDailyMonth:
    records: tuple[HistoricalNormalizedBar, ...]
    daily_dates: tuple[date, ...]
    read_lineage: Mapping[str, Any]


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
        daily_history_sessions: int = 61,
        daily_month_cache_size: int = 9,
        maximum_daily_lookback_calendar_days: int = 180,
    ) -> None:
        if maximum_daily_rows <= 0 or maximum_minute_session_rows <= 0:
            raise ValueError("Historical window row limits must be positive")
        if minute_session_cache_size < 3:
            raise ValueError("Historical minute cache must hold Decision and T+1 sessions")
        if daily_history_sessions < 61:
            raise ValueError("Historical Daily history cannot lower the 61-session Canonical maximum")
        if daily_month_cache_size < 3:
            raise ValueError("Historical Daily cache must hold adjacent session months")
        if maximum_daily_lookback_calendar_days < 90:
            raise ValueError(
                "Historical Daily lookback must allow the 61-session Canonical window"
            )
        self._repository = repository
        self._maximum_daily_rows = maximum_daily_rows
        self._maximum_minute_session_rows = maximum_minute_session_rows
        self._minute_session_cache_size = minute_session_cache_size
        self._daily_history_sessions = daily_history_sessions
        self._daily_month_cache_size = daily_month_cache_size
        self._maximum_daily_lookback_calendar_days = (
            maximum_daily_lookback_calendar_days
        )
        self._indexes: dict[ValidationArtifactReference, HistoricalDatasetWindowIndex] = {}
        self._daily_months: OrderedDict[
            tuple[ValidationArtifactReference, int, int, tuple[str, ...]],
            _CachedDailyMonth,
        ] = OrderedDict()
        self._minute_sessions: OrderedDict[
            tuple[ValidationArtifactReference, date, tuple[str, ...]],
            _CachedMinuteSession,
        ] = OrderedDict()
        self._aggregate_metrics: HistoricalReadMetrics | None = None
        self._physical_read_count = 0
        self._active_lineage: list[Mapping[str, Any]] = []

    def begin_stage(self) -> None:
        self._active_lineage = []

    def index(self, reference: ValidationArtifactReference) -> HistoricalDatasetWindowIndex:
        cached = self._indexes.get(reference)
        if cached is not None:
            return cached
        package = self._repository.open_index(reference)
        index = HistoricalDatasetWindowIndex(package=package)
        self._indexes[reference] = index
        return index

    def decision_bars(
        self,
        reference: ValidationArtifactReference,
        decision_time: datetime,
        *,
        symbols: tuple[str, ...],
    ) -> tuple[HistoricalNormalizedBar, ...]:
        result: list[HistoricalNormalizedBar] = []
        market_date = decision_time.astimezone(ZoneInfo("Asia/Shanghai")).date()
        daily, daily_dates = self._daily_window(
            reference,
            market_date,
            symbols=symbols,
        )
        result.extend(item for item in daily if item.event_end <= decision_time)
        requested_symbols = tuple(sorted(set(symbols)))
        current = self._minute_session(reference, market_date, requested_symbols)
        prior_date = next(
            (item for item in reversed(daily_dates) if item < market_date),
            None,
        )
        prior = (
            ()
            if prior_date is None
            else self._minute_session(reference, prior_date, requested_symbols)
        )
        if not prior:
            prior = self._prior_minute_session(
                reference,
                market_date,
                requested_symbols,
            )
        result.extend(item for item in (*prior, *current) if item.event_end <= decision_time and item.symbol in symbols)
        return tuple(sorted(result, key=_bar_key))

    def next_session(
        self,
        reference: ValidationArtifactReference,
        trading_date: date,
        *,
        symbols: tuple[str, ...],
    ) -> date | None:
        requested_symbols = tuple(sorted(set(symbols)))
        if not requested_symbols:
            raise ValueError("Historical next-session lookup requires symbols")
        package = self.index(reference).package
        search_end = min(package.last_market_date, trading_date + timedelta(days=40))
        dates: set[date] = set()
        for year, month in _month_keys(trading_date, search_end):
            daily = self._daily_month(
                reference,
                year,
                month,
                requested_symbols,
            )
            dates.update(daily.daily_dates)
        return next((item for item in sorted(dates) if item > trading_date), None)

    def outcome_bars(
        self,
        reference: ValidationArtifactReference,
        *,
        decision_time: datetime,
        next_session: date,
        symbols: tuple[str, ...],
    ) -> tuple[HistoricalNormalizedBar, ...]:
        market_date = decision_time.astimezone(ZoneInfo("Asia/Shanghai")).date()
        daily, _dates = self._daily_window(
            reference,
            market_date,
            symbols=symbols,
        )
        requested_symbols = tuple(sorted(set(symbols)))
        next_daily = self._daily_month(
            reference,
            next_session.year,
            next_session.month,
            requested_symbols,
        )
        self._record_lineage(next_daily.read_lineage)
        result = [item for item in daily if item.event_end <= decision_time]
        result.extend(item for item in next_daily.records if item.market_date == next_session and item.symbol in symbols)
        result.extend(
            self._minute_session(reference, next_session, requested_symbols)
        )
        return tuple(sorted(result, key=_bar_key))

    def metrics(self) -> tuple[HistoricalReadMetrics, ...]:
        return () if self._aggregate_metrics is None else (self._aggregate_metrics,)

    def stage_lineage_payload(self) -> list[Mapping[str, Any]]:
        keyed = {canonical_hash(item): item for item in self._active_lineage}
        return [keyed[key] for key in sorted(keyed)]

    def cache_metrics(self) -> Mapping[str, int]:
        return {
            "daily_history_session_requirement": self._daily_history_sessions,
            "daily_month_cache_limit": self._daily_month_cache_size,
            "daily_lookback_calendar_day_limit": (
                self._maximum_daily_lookback_calendar_days
            ),
            "daily_month_cache_entries": len(self._daily_months),
            "daily_cached_row_count": sum(len(item.records) for item in self._daily_months.values()),
            "minute_session_cache_limit": self._minute_session_cache_size,
            "minute_session_cache_entries": len(self._minute_sessions),
            "minute_cached_row_count": sum(len(item.records) for item in self._minute_sessions.values()),
            "physical_read_count": self._physical_read_count,
            "read_metric_objects_retained": int(self._aggregate_metrics is not None),
        }

    def _daily_window(
        self,
        reference: ValidationArtifactReference,
        market_date: date,
        *,
        symbols: tuple[str, ...],
    ) -> tuple[tuple[HistoricalNormalizedBar, ...], tuple[date, ...]]:
        requested_symbols = tuple(sorted(set(symbols)))
        if not requested_symbols:
            raise ValueError("Historical Daily window requires symbols")
        package = self.index(reference).package
        last = min(package.last_market_date, market_date)
        first = max(
            package.first_market_date,
            last - timedelta(days=self._maximum_daily_lookback_calendar_days - 1),
        )
        if first > last:
            return (), ()
        data_slice = self._read_normalized(
            HistoricalReadQuery.create(
                reference=reference,
                timeframes=(Timeframe.DAILY,),
                first_market_date=first,
                last_market_date=last,
                symbols=requested_symbols,
                max_rows=self._maximum_daily_rows,
            ),
            record_lineage=False,
        )
        self._record_lineage(_slice_lineage(data_slice))
        by_symbol: dict[str, list[HistoricalNormalizedBar]] = {
            symbol: [] for symbol in requested_symbols
        }
        dates: set[date] = set()
        daily_records = tuple(
            item
            for item in data_slice.records
            if isinstance(item, HistoricalNormalizedBar)
            and item.timeframe is Timeframe.DAILY
            and item.market_date <= last
        )
        for item in reversed(sorted(daily_records, key=_bar_key)):
            values = by_symbol.get(item.symbol)
            if values is not None and len(values) < self._daily_history_sessions:
                values.append(item)
                dates.add(item.market_date)
        records = tuple(item for symbol in requested_symbols for item in by_symbol[symbol])
        return tuple(sorted(records, key=_bar_key)), tuple(sorted(dates))

    def _daily_month(
        self,
        reference: ValidationArtifactReference,
        year: int,
        month: int,
        symbols: tuple[str, ...],
    ) -> _CachedDailyMonth:
        requested_symbols = tuple(sorted(set(symbols)))
        if not requested_symbols:
            raise ValueError("Historical Daily month requires symbols")
        key = (reference, year, month, requested_symbols)
        cached = self._daily_months.get(key)
        if cached is not None:
            self._daily_months.move_to_end(key)
            return cached
        package = self.index(reference).package
        first, last = _month_bounds(year, month)
        first = max(first, package.first_market_date)
        last = min(last, package.last_market_date)
        if first > last:
            raise ValueError("Historical Daily month is outside the frozen Dataset")
        data_slice = self._read_normalized(
            HistoricalReadQuery.create(
                reference=reference,
                timeframes=(Timeframe.DAILY,),
                first_market_date=first,
                last_market_date=last,
                symbols=requested_symbols,
                max_rows=self._maximum_daily_rows,
            ),
            record_lineage=False,
        )
        records = tuple(item for item in data_slice.records if isinstance(item, HistoricalNormalizedBar))
        grouped: dict[tuple[str, Timeframe], list[HistoricalNormalizedBar]] = {}
        for bar in records:
            grouped.setdefault((bar.symbol, bar.timeframe), []).append(bar)
        series = {series_key: tuple(sorted(values, key=_bar_key)) for series_key, values in grouped.items()}
        cached = _CachedDailyMonth(
            records=tuple(sorted(records, key=_bar_key)),
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
            read_lineage=_slice_lineage(data_slice),
        )
        self._daily_months[key] = cached
        self._daily_months.move_to_end(key)
        while len(self._daily_months) > self._daily_month_cache_size:
            self._daily_months.popitem(last=False)
        return cached

    def _minute_session(
        self,
        reference: ValidationArtifactReference,
        session_date: date,
        symbols: tuple[str, ...],
    ) -> tuple[HistoricalNormalizedBar, ...]:
        requested_symbols = tuple(sorted(set(symbols)))
        if not requested_symbols:
            raise ValueError("Historical minute session requires symbols")
        key = (reference, session_date, requested_symbols)
        cached = self._minute_sessions.get(key)
        if cached is not None:
            self._minute_sessions.move_to_end(key)
            self._record_lineage(cached.read_lineage)
            return cached.records
        values, lineage = self._read_minute_range(
            reference,
            first_date=session_date,
            last_date=session_date,
            symbols=requested_symbols,
        )
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
        symbols: tuple[str, ...],
    ) -> tuple[HistoricalNormalizedBar, ...]:
        values, lineage = self._read_minute_range(
            reference,
            first_date=market_date - timedelta(days=20),
            last_date=market_date - timedelta(days=1),
            symbols=symbols,
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
        symbols: tuple[str, ...],
    ) -> tuple[tuple[HistoricalNormalizedBar, ...], Mapping[str, Any]]:
        data_slice = self._read_normalized(
            HistoricalReadQuery.create(
                reference=reference,
                timeframes=(Timeframe.MINUTE_5,),
                first_market_date=first_date,
                last_market_date=last_date,
                symbols=tuple(sorted(set(symbols))),
                max_rows=self._maximum_minute_session_rows,
            ),
            record_lineage=False,
        )
        values = tuple(item for item in data_slice.records if isinstance(item, HistoricalNormalizedBar))
        return values, _slice_lineage(data_slice)

    def _read_normalized(self, query: HistoricalReadQuery, *, record_lineage: bool) -> HistoricalDataSlice:
        data_slice = self._repository.read(query)
        self._physical_read_count += 1
        self._aggregate_metrics = _merge_read_metrics(
            self._aggregate_metrics,
            data_slice.metrics,
        )
        if any(not isinstance(item, HistoricalNormalizedBar) for item in data_slice.records):
            raise ValueError("Historical materialization requires normalized bars")
        if record_lineage:
            self._record_lineage(_slice_lineage(data_slice))
        return data_slice

    def _record_lineage(self, lineage: Mapping[str, Any]) -> None:
        self._active_lineage.append(lineage)


def _merge_read_metrics(
    aggregate: HistoricalReadMetrics | None,
    current: HistoricalReadMetrics,
) -> HistoricalReadMetrics:
    if aggregate is None:
        return current
    return HistoricalReadMetrics(
        candidate_partition_count=(
            aggregate.candidate_partition_count + current.candidate_partition_count
        ),
        candidate_partition_row_count=(
            aggregate.candidate_partition_row_count
            + current.candidate_partition_row_count
        ),
        verified_partition_count=(
            aggregate.verified_partition_count + current.verified_partition_count
        ),
        verified_bytes=aggregate.verified_bytes + current.verified_bytes,
        returned_row_count=(
            aggregate.returned_row_count + current.returned_row_count
        ),
        arrow_batch_count=aggregate.arrow_batch_count + current.arrow_batch_count,
        maximum_batch_row_count=max(
            aggregate.maximum_batch_row_count,
            current.maximum_batch_row_count,
        ),
        projected_columns=tuple(
            sorted(set(aggregate.projected_columns) | set(current.projected_columns))
        ),
        predicate_pushdown=aggregate.predicate_pushdown and current.predicate_pushdown,
    )


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


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first, next_month - timedelta(days=1)


def _month_keys(first: date, last: date) -> tuple[tuple[int, int], ...]:
    if first > last:
        raise ValueError("Historical month range is reversed")
    current = date(first.year, first.month, 1)
    result: list[tuple[int, int]] = []
    while current <= last:
        result.append((current.year, current.month))
        current = date(current.year + 1, 1, 1) if current.month == 12 else date(current.year, current.month + 1, 1)
    return tuple(result)


def _bar_key(item: HistoricalNormalizedBar) -> tuple[str, str, datetime, str]:
    return item.symbol, item.timeframe.value, item.event_end, str(item.bar_id)


def _is_etf_symbol(symbol: str) -> bool:
    return symbol.startswith(("15", "16", "50", "51", "56", "58"))


__all__ = ["HistoricalDatasetWindowIndex", "HistoricalWindowReader"]
