"""Exact bounded Market input for daily historical factor materialization."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest_dataset import BacktestFeatureDependency
from market_regime_alpha.research_qualification.domain.exploratory import ExploratoryRetrospectiveDatasetScope
from market_regime_alpha.research_qualification.domain.historical_features import HistoricalDailyPoint


@dataclass(frozen=True, slots=True)
class HistoricalFeatureSnapshot:
    sessions: tuple[tuple[date, UUID, datetime], ...]
    population: dict[UUID, tuple[HistoricalDailyPoint, ...]]
    dependencies: dict[tuple[UUID, date, str], tuple[BacktestFeatureDependency, ...]]
    problems: dict[tuple[UUID, date, str], str]
    failed_request_gap_ids: frozenset[UUID] = frozenset()


class HistoricalFeatureInputReadPort(Protocol):
    def snapshot(self, *, scope: ExploratoryRetrospectiveDatasetScope,
                 instruments: tuple[UUID, ...], session_date: date) -> HistoricalFeatureSnapshot: ...
