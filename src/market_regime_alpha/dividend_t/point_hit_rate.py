"""Buy/sell point hit-rate analysis for timing signals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any, Iterable

import pandas as pd


BUY_POINT_ACTIONS = frozenset({"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"})
SELL_POINT_ACTIONS = frozenset({"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK"})
DEFAULT_HORIZON_DAYS = (1, 3, 5)
DEFAULT_BARS_PER_TRADING_DAY = 48


@dataclass(frozen=True)
class PointHitRateEvent:
    symbol: str
    name: str
    point_type: str
    action: str
    buy_point_subtype: str
    timestamp: str
    execution_price: float
    horizon_days: int
    horizon_bars: int
    future_return: float
    hit: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PointHitRateSummary:
    group: str
    point_type: str
    horizon_days: int
    sample_count: int
    hit_count: int
    hit_rate: float | None
    average_future_return: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def point_type_for_action(action: str) -> str | None:
    normalized = str(action).strip().upper()
    if normalized in BUY_POINT_ACTIONS:
        return "buy"
    if normalized in SELL_POINT_ACTIONS:
        return "sell"
    return None


def build_point_hit_rate_events(
    *,
    symbol: str,
    name: str,
    bars: Any,
    equity_curve: Iterable[Any],
    min_lookback_bars: int,
    signal_step_bars: int,
    horizon_days: Iterable[int] = DEFAULT_HORIZON_DAYS,
    bars_per_trading_day: int = DEFAULT_BARS_PER_TRADING_DAY,
) -> list[PointHitRateEvent]:
    """Build forward-return events from evaluated buy/sell timing points."""

    if bars_per_trading_day <= 0:
        raise ValueError("bars_per_trading_day must be positive")
    if signal_step_bars <= 0:
        raise ValueError("signal_step_bars must be positive")

    data = bars.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values("timestamp").reset_index(drop=True)
    open_prices = pd.to_numeric(data["open"], errors="coerce")
    close_prices = pd.to_numeric(data["close"], errors="coerce")
    index_by_timestamp = {pd.Timestamp(timestamp): index for index, timestamp in enumerate(data["timestamp"])}
    normalized_horizons = tuple(sorted({int(day) for day in horizon_days if int(day) > 0}))

    events: list[PointHitRateEvent] = []
    for point in equity_curve:
        action = str(getattr(point, "action", ""))
        point_type = point_type_for_action(action)
        if point_type is None:
            continue

        timestamp = pd.Timestamp(getattr(point, "timestamp"))
        index = index_by_timestamp.get(timestamp)
        if index is None:
            continue
        if index < min_lookback_bars:
            continue
        if (index - min_lookback_bars) % signal_step_bars != 0:
            continue

        execution_price = float(open_prices.iloc[index])
        if not execution_price or execution_price <= 0:
            continue

        for horizon_day in normalized_horizons:
            horizon_bars = horizon_day * bars_per_trading_day
            future_index = index + horizon_bars
            if future_index >= len(data):
                continue
            future_close = float(close_prices.iloc[future_index])
            if not future_close or future_close <= 0:
                continue
            future_return = future_close / execution_price - 1.0
            hit = future_return > 0.0 if point_type == "buy" else future_return < 0.0
            events.append(
                PointHitRateEvent(
                    symbol=symbol,
                    name=name,
                    point_type=point_type,
                    action=action,
                    buy_point_subtype=str(getattr(point, "buy_point_subtype", "none")),
                    timestamp=str(timestamp),
                    execution_price=round(execution_price, 4),
                    horizon_days=horizon_day,
                    horizon_bars=horizon_bars,
                    future_return=round(future_return, 8),
                    hit=hit,
                )
            )
    return events


def summarize_point_hit_rate_events(
    events: Iterable[PointHitRateEvent],
    *,
    group_by_action: bool = False,
    group_by_buy_subtype: bool = False,
) -> list[PointHitRateSummary]:
    grouped: dict[tuple[str, str, int], list[PointHitRateEvent]] = {}
    for event in events:
        if group_by_buy_subtype and event.point_type == "buy":
            group = event.buy_point_subtype or "none"
        else:
            group = event.action if group_by_action else event.point_type
        key = (group, event.point_type, event.horizon_days)
        grouped.setdefault(key, []).append(event)

    summaries: list[PointHitRateSummary] = []
    for (group, point_type, horizon_days), group_events in sorted(grouped.items(), key=lambda item: (item[0][1], item[0][2], item[0][0])):
        hit_count = sum(1 for event in group_events if event.hit)
        summaries.append(
            PointHitRateSummary(
                group=group,
                point_type=point_type,
                horizon_days=horizon_days,
                sample_count=len(group_events),
                hit_count=hit_count,
                hit_rate=round(hit_count / len(group_events), 6) if group_events else None,
                average_future_return=round(mean(event.future_return for event in group_events), 8) if group_events else None,
            )
        )
    return summaries
