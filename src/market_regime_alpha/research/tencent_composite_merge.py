"""Normalize and merge Tencent/local/BaoStock exploratory market rows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeMergeResult,
    CompositeSourceConflict,
    CompositeSourceKind,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
SOURCE_PRIORITY = {
    CompositeSourceKind.BAOSTOCK: 1,
    CompositeSourceKind.LOCAL: 2,
    CompositeSourceKind.TENCENT: 3,
}
REQUIRED_COLUMNS = frozenset(
    {
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    }
)


def normalize_composite_frame(
    frame: Any,
    *,
    source: CompositeSourceKind,
) -> tuple[CompositeBar, ...]:
    """Validate one normalized pandas frame and attach explicit source identity."""

    if not isinstance(source, CompositeSourceKind):
        raise TypeError("source must be a CompositeSourceKind")
    if not hasattr(frame, "columns"):
        raise TypeError("composite frame must expose pandas-style columns")
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"composite frame missing columns: {sorted(missing)}")

    bars: list[CompositeBar] = []
    keys: set[tuple[str, datetime]] = set()
    for row in frame.itertuples(index=False):
        timestamp = _aware_shanghai_timestamp(getattr(row, "timestamp"))
        symbol = str(getattr(row, "symbol"))
        key = (symbol, timestamp)
        if key in keys:
            raise ValueError(f"composite frame contains duplicate symbol/timestamp key: {symbol} {timestamp.isoformat()}")
        keys.add(key)
        bars.append(
            CompositeBar(
                symbol=symbol,
                timestamp=timestamp,
                open=float(getattr(row, "open")),
                high=float(getattr(row, "high")),
                low=float(getattr(row, "low")),
                close=float(getattr(row, "close")),
                volume=float(getattr(row, "volume")),
                amount=float(getattr(row, "amount")),
                source=source,
            )
        )
    return tuple(sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol)))


def merge_composite_bars(
    *,
    tencent: tuple[CompositeBar, ...],
    local: tuple[CompositeBar, ...],
    baostock: tuple[CompositeBar, ...],
    current_session: date,
) -> CompositeMergeResult:
    """Merge rows under Tencent-current, local-history, BaoStock-gap precedence."""

    if not isinstance(current_session, date):
        raise TypeError("current_session must be a date")
    selected: dict[tuple[str, datetime], CompositeBar] = {}
    conflicts: list[CompositeSourceConflict] = []
    candidates = sorted(
        (*baostock, *local, *tencent),
        key=lambda bar: (bar.timestamp, bar.symbol, SOURCE_PRIORITY[bar.source]),
    )
    for candidate in candidates:
        if candidate.source is CompositeSourceKind.TENCENT and candidate.timestamp.date() != current_session:
            continue
        key = (candidate.symbol, candidate.timestamp)
        existing = selected.get(key)
        if existing is None:
            selected[key] = candidate
            continue

        candidate_wins = SOURCE_PRIORITY[candidate.source] >= SOURCE_PRIORITY[existing.source]
        winning = candidate if candidate_wins else existing
        losing = existing if candidate_wins else candidate
        if _numeric_payload(existing) != _numeric_payload(candidate):
            conflicts.append(
                CompositeSourceConflict(
                    key=key,
                    selected=winning,
                    rejected=losing,
                )
            )
        selected[key] = winning

    return CompositeMergeResult(
        bars=tuple(sorted(selected.values(), key=lambda bar: (bar.timestamp, bar.symbol))),
        conflicts=tuple(
            sorted(
                conflicts,
                key=lambda item: (
                    item.key[1],
                    item.key[0],
                    item.selected.source.value,
                    item.rejected.source.value,
                ),
            )
        ),
    )


def _aware_shanghai_timestamp(raw: object) -> datetime:
    try:
        timestamp = pd.Timestamp(raw)
    except Exception as exc:  # noqa: BLE001 - normalize all parser failures to one contract error.
        raise ValueError(f"invalid composite timestamp: {raw!r}") from exc
    if pd.isna(timestamp):
        raise ValueError("invalid composite timestamp: missing value")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        timestamp = timestamp.tz_localize(SHANGHAI_TZ)
    else:
        timestamp = timestamp.tz_convert(SHANGHAI_TZ)
    return timestamp.to_pydatetime()


def _numeric_payload(bar: CompositeBar) -> tuple[float, ...]:
    return (
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        bar.amount,
    )
