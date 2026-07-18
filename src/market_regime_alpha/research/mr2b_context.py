"""Leak-free exact-14:50 auxiliary-watchlist Context evidence for MR-2B."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
import math
from typing import Iterable
from zoneinfo import ZoneInfo

from market_regime_alpha.research.mr2b_excess import WatchlistDirection
from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash
from market_regime_alpha.research.tencent_composite_contracts import CompositeBar


MR2B_CONTEXT_SCHEMA_VERSION = "mr-2b-auxiliary-watchlist-context-v1"
MR2B_CONTEXT_DEFINITION_ID = "mr2b-accepted-watchlist-exact-1450-context-v1"
MR2B_CONTEXT_GRID_DEFINITION_ID = "a-share-5m-end-labeled-grid-to-1450-v1"
MR2B_CONTEXT_COVERAGE_POLICY_ID = "full-accepted-watchlist-coverage-required-v1"
MR2B_DIRECTION_LABEL_POLICY_ID = "mr2b-direction-sign-epsilon-1e-12-v1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _inclusive_times(start: time, end: time) -> tuple[time, ...]:
    anchor = date(2000, 1, 1)
    current = datetime.combine(anchor, start)
    finish = datetime.combine(anchor, end)
    output: list[time] = []
    while current <= finish:
        output.append(current.time())
        current += timedelta(minutes=5)
    return tuple(output)


CONTEXT_GRID = (
    *_inclusive_times(time(9, 35), time(11, 30)),
    *_inclusive_times(time(13, 5), time(14, 50)),
)


class ContextDataStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ContextMissingReason(str, Enum):
    EXACT_1450_ENDPOINT_MISSING = "EXACT_1450_ENDPOINT_MISSING"
    INCOMPLETE_CUTOFF_GRID = "INCOMPLETE_CUTOFF_GRID"
    PRIOR_SESSION_INCOMPLETE_CUTOFF_GRID = "PRIOR_SESSION_INCOMPLETE_CUTOFF_GRID"
    PRIOR_SESSION_CLOSE_MISSING = "PRIOR_SESSION_CLOSE_MISSING"


@dataclass(frozen=True, slots=True)
class AuxiliaryWatchlistContext:
    decision_date: date
    decision_time: datetime
    cutoff_time: datetime
    dataset_id: str
    watchlist_id: str
    context_id: str
    expected_symbol_count: int
    available_symbol_count: int
    coverage: float
    expected_bar_count_per_symbol: int
    available_bar_count_per_symbol: int
    grid_status: str
    data_status: ContextDataStatus
    missing_reason: ContextMissingReason | None
    watchlist_direction_return: float | None
    watchlist_direction: WatchlistDirection | None
    watchlist_breadth_at_cutoff: float | None
    watchlist_intraday_range_to_cutoff: float | None
    watchlist_amount_to_cutoff: float | None
    prior_watchlist_amount_same_cutoff: float | None
    watchlist_amount_change_same_cutoff: float | None
    definition_id: str = MR2B_CONTEXT_DEFINITION_ID
    grid_definition_id: str = MR2B_CONTEXT_GRID_DEFINITION_ID
    data_eligibility: str = "EXPLORATORY"
    schema_version: str = MR2B_CONTEXT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MR2B_CONTEXT_SCHEMA_VERSION:
            raise ValueError("unsupported auxiliary-watchlist Context schema")
        if self.definition_id != MR2B_CONTEXT_DEFINITION_ID:
            raise ValueError("unsupported auxiliary-watchlist Context definition")
        if self.grid_definition_id != MR2B_CONTEXT_GRID_DEFINITION_ID:
            raise ValueError("unsupported auxiliary-watchlist grid definition")
        if self.data_eligibility != "EXPLORATORY":
            raise ValueError("auxiliary-watchlist Context authority must remain EXPLORATORY")
        if self.decision_time.tzinfo is None or self.cutoff_time.tzinfo is None:
            raise ValueError("Context times must be timezone-aware")
        if self.cutoff_time.time() != time(14, 50) or self.decision_time.time() != time(14, 55):
            raise ValueError("Context requires exact 14:50 cutoff and 14:55 Decision Time")
        if self.expected_bar_count_per_symbol != 46:
            raise ValueError("Context grid must contain exactly 46 bars")
        if not 0.0 <= self.coverage <= 1.0:
            raise ValueError("Context coverage must be within [0, 1]")
        if self.data_status is ContextDataStatus.AVAILABLE:
            if self.missing_reason is not None or self.watchlist_direction is None:
                raise ValueError("available Context must have metrics and no missing reason")
            if self.available_symbol_count != self.expected_symbol_count or self.coverage != 1.0:
                raise ValueError("available Context requires full accepted-watchlist coverage")
            values = (
                self.watchlist_direction_return,
                self.watchlist_breadth_at_cutoff,
                self.watchlist_intraday_range_to_cutoff,
                self.watchlist_amount_to_cutoff,
                self.prior_watchlist_amount_same_cutoff,
                self.watchlist_amount_change_same_cutoff,
            )
            if any(value is None or not math.isfinite(value) for value in values):
                raise ValueError("available Context metrics must be finite")


def build_auxiliary_watchlist_context(
    *,
    dataset_id: str,
    accepted_symbols: Iterable[str],
    session_dates: Iterable[date],
    bars: Iterable[CompositeBar],
    decision_dates: Iterable[date],
) -> tuple[AuxiliaryWatchlistContext, ...]:
    """Construct one exact-cutoff Context per Decision Date without future-threshold state."""

    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("dataset_id must be non-empty")
    symbols = tuple(sorted(accepted_symbols))
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("accepted symbols must be non-empty and unique")
    calendar = tuple(session_dates)
    decisions = tuple(decision_dates)
    if calendar != tuple(sorted(calendar)) or len(calendar) != len(set(calendar)):
        raise ValueError("session dates must be chronological and unique")
    if decisions != tuple(sorted(decisions)) or len(decisions) != len(set(decisions)):
        raise ValueError("Decision Dates must be chronological and unique")
    if any(day not in calendar or calendar.index(day) == 0 for day in decisions):
        raise ValueError("each Decision Date requires a previous identified session")
    bar_rows = tuple(bars)
    keys = tuple((bar.symbol, bar.timestamp) for bar in bar_rows)
    if len(keys) != len(set(keys)):
        raise ValueError("Context bar symbol/timestamp keys must be unique")
    indexed = {(bar.symbol, bar.timestamp.date(), _local_time(bar)): bar for bar in bar_rows}
    watchlist_id = canonical_identity_hash(
        {"definition": "accepted-watchlist-symbols-v1", "dataset_id": dataset_id, "symbols": symbols}
    )
    output = [
        _context_for_day(
            dataset_id=dataset_id,
            watchlist_id=watchlist_id,
            symbols=symbols,
            decision_day=day,
            previous_day=calendar[calendar.index(day) - 1],
            bars=indexed,
        )
        for day in decisions
    ]
    return tuple(output)


def _context_for_day(
    *,
    dataset_id: str,
    watchlist_id: str,
    symbols: tuple[str, ...],
    decision_day: date,
    previous_day: date,
    bars: dict[tuple[str, date, time], CompositeBar],
) -> AuxiliaryWatchlistContext:
    current_counts: list[int] = []
    valid_symbols: list[str] = []
    reason: ContextMissingReason | None = None
    for symbol in symbols:
        current = tuple(bars.get((symbol, decision_day, endpoint)) for endpoint in CONTEXT_GRID)
        previous = tuple(bars.get((symbol, previous_day, endpoint)) for endpoint in CONTEXT_GRID)
        current_counts.append(sum(item is not None for item in current))
        if current[-1] is None:
            reason = reason or ContextMissingReason.EXACT_1450_ENDPOINT_MISSING
            continue
        if any(item is None for item in current):
            reason = reason or ContextMissingReason.INCOMPLETE_CUTOFF_GRID
            continue
        if any(item is None for item in previous):
            reason = reason or ContextMissingReason.PRIOR_SESSION_INCOMPLETE_CUTOFF_GRID
            continue
        if bars.get((symbol, previous_day, time(15, 0))) is None:
            reason = reason or ContextMissingReason.PRIOR_SESSION_CLOSE_MISSING
            continue
        valid_symbols.append(symbol)
    expected = len(symbols)
    available = len(valid_symbols)
    common = {
        "decision_date": decision_day,
        "decision_time": datetime.combine(decision_day, time(14, 55), tzinfo=_SHANGHAI),
        "cutoff_time": datetime.combine(decision_day, time(14, 50), tzinfo=_SHANGHAI),
        "dataset_id": dataset_id,
        "watchlist_id": watchlist_id,
        "expected_symbol_count": expected,
        "available_symbol_count": available,
        "coverage": available / expected,
        "expected_bar_count_per_symbol": len(CONTEXT_GRID),
        "available_bar_count_per_symbol": min(current_counts),
    }
    if available != expected:
        return _identified_context(
            **common,
            grid_status="INCOMPLETE",
            data_status=ContextDataStatus.UNAVAILABLE,
            missing_reason=reason or ContextMissingReason.INCOMPLETE_CUTOFF_GRID,
        )
    symbol_returns: list[float] = []
    ranges: list[float] = []
    current_amount = 0.0
    previous_amount = 0.0
    for symbol in symbols:
        current_complete = tuple(
            bars[(symbol, decision_day, endpoint)] for endpoint in CONTEXT_GRID
        )
        previous_complete = tuple(
            bars[(symbol, previous_day, endpoint)] for endpoint in CONTEXT_GRID
        )
        close_1450 = current_complete[-1].close
        prior_close = bars[(symbol, previous_day, time(15, 0))].close
        symbol_returns.append(close_1450 / prior_close - 1.0)
        ranges.append(
            (max(item.high for item in current_complete) - min(item.low for item in current_complete))
            / close_1450
        )
        current_amount += sum(item.amount for item in current_complete)
        previous_amount += sum(item.amount for item in previous_complete)
    if previous_amount <= 0.0:
        raise ValueError("previous-session same-cutoff amount must be positive")
    direction_return = sum(symbol_returns) / expected
    direction = (
        WatchlistDirection.UP
        if direction_return > 1e-12
        else WatchlistDirection.DOWN
        if direction_return < -1e-12
        else WatchlistDirection.FLAT
    )
    return _identified_context(
        **common,
        grid_status="COMPLETE",
        data_status=ContextDataStatus.AVAILABLE,
        missing_reason=None,
        watchlist_direction_return=direction_return,
        watchlist_direction=direction,
        watchlist_breadth_at_cutoff=sum(value > 0.0 for value in symbol_returns) / expected,
        watchlist_intraday_range_to_cutoff=sum(ranges) / expected,
        watchlist_amount_to_cutoff=current_amount,
        prior_watchlist_amount_same_cutoff=previous_amount,
        watchlist_amount_change_same_cutoff=current_amount / previous_amount - 1.0,
    )


def _identified_context(**values: object) -> AuxiliaryWatchlistContext:
    metrics = {
        "watchlist_direction_return": None,
        "watchlist_direction": None,
        "watchlist_breadth_at_cutoff": None,
        "watchlist_intraday_range_to_cutoff": None,
        "watchlist_amount_to_cutoff": None,
        "prior_watchlist_amount_same_cutoff": None,
        "watchlist_amount_change_same_cutoff": None,
        **values,
    }
    identity_values = {
        key: (value.value if isinstance(value, Enum) else value.isoformat() if isinstance(value, (date, datetime)) else value)
        for key, value in metrics.items()
        if key != "context_id"
    }
    context_id = canonical_identity_hash(
        {
            "schema_version": MR2B_CONTEXT_SCHEMA_VERSION,
            "definition_id": MR2B_CONTEXT_DEFINITION_ID,
            "grid_definition_id": MR2B_CONTEXT_GRID_DEFINITION_ID,
            "coverage_policy_id": MR2B_CONTEXT_COVERAGE_POLICY_ID,
            "direction_label_policy_id": MR2B_DIRECTION_LABEL_POLICY_ID,
            "evidence": identity_values,
        }
    )
    return AuxiliaryWatchlistContext(context_id=context_id, **metrics)  # type: ignore[arg-type]


def context_record(context: AuxiliaryWatchlistContext) -> dict[str, object]:
    """Return a stable Parquet-ready record."""

    row = asdict(context)
    for key, value in tuple(row.items()):
        if isinstance(value, Enum):
            row[key] = value.value
        elif isinstance(value, (date, datetime)):
            row[key] = value.isoformat()
    return row


def _local_time(bar: CompositeBar) -> time:
    return bar.timestamp.astimezone(_SHANGHAI).time().replace(tzinfo=None)
