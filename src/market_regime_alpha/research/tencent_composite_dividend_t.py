"""Inject accepted Tencent composite frames into the existing dividend-T snapshot path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.data_sources.a_share_bars import LatestQuote
from market_regime_alpha.dividend_t.trend_snapshot import build_dividend_trend_snapshot


COMPOSITE_DATA_SOURCE = "tencent_current+local_history+baostock_gap_fill"
DIFF_FIELDS = (
    "status",
    "bar_time",
    "latest_price",
    "signal",
    "timing_action",
    "up_probability_1d",
    "up_probability_3d",
    "up_probability_5d",
    "support",
    "resistance",
    "stop_price",
    "scan_error",
)


@dataclass(frozen=True, slots=True)
class DividendTRefreshResult:
    """Legacy dividend-T snapshot and an additive before/after audit diff."""

    snapshot: dict[str, Any]
    diff: dict[str, Any]


class CompositeFrameProvider:
    """Read-only provider exposing only quality-gate-accepted symbols."""

    name = "tencent_composite_exploratory"
    data_source = COMPOSITE_DATA_SOURCE
    is_realtime = False

    def __init__(self, *, frames: Mapping[str, Any]) -> None:
        if not frames:
            raise ValueError("accepted composite frames must not be empty")
        self._frames = dict(frames)

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        if freq not in {"5", "5m", "5min"}:
            raise ValueError("CompositeFrameProvider exposes only 5-minute bars")
        if symbol not in self._frames:
            raise KeyError(f"symbol not accepted by composite quality gate: {symbol}")
        return _filter_frame(
            self._frames[symbol],
            start_date=start_date,
            end_date=end_date,
        )


def refresh_dividend_t_from_composite(
    *,
    watchlist_path: str | Path,
    frames: Mapping[str, Any],
    quotes: Mapping[str, LatestQuote],
    before_snapshot: Mapping[str, Any] | None,
    generated_at: datetime,
) -> DividendTRefreshResult:
    """Refresh unchanged dividend-T logic from the exact accepted composite frames."""

    snapshot = build_dividend_trend_snapshot(
        watchlist_path=watchlist_path,
        limit=20,
        provider=CompositeFrameProvider(frames=frames),
        quotes=dict(quotes),
        generated_at=generated_at,
    )
    if any("candidate_rank" in row for row in snapshot.get("rows", ())):
        raise RuntimeError("Candidate rank must remain separate from dividend-T actions")
    return DividendTRefreshResult(
        snapshot=snapshot,
        diff=compare_dividend_snapshots(before_snapshot or {}, snapshot),
    )


def compare_dividend_snapshots(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare operational display fields without reinterpreting strategy semantics."""

    before_rows = _rows_by_symbol(before)
    after_rows = _rows_by_symbol(after)
    symbols = tuple(sorted(set(before_rows) | set(after_rows)))
    symbol_diffs: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        before_row = before_rows.get(symbol, {})
        after_row = after_rows.get(symbol, {})
        changes = {
            field: {
                "before": before_row.get(field),
                "after": after_row.get(field),
            }
            for field in DIFF_FIELDS
            if before_row.get(field) != after_row.get(field)
        }
        symbol_diffs[symbol] = {
            "before_status": before_row.get("status", "missing"),
            "after_status": after_row.get("status", "missing"),
            "changed_fields": changes,
        }
    return {
        "before_row_count": len(before_rows),
        "after_row_count": len(after_rows),
        "before_successful_count": sum(
            row.get("status") == "ok" for row in before_rows.values()
        ),
        "after_successful_count": sum(
            row.get("status") == "ok" for row in after_rows.values()
        ),
        "symbols": symbol_diffs,
    }


def _filter_frame(
    frame: Any,
    *,
    start_date: str | None,
    end_date: str | None,
) -> Any:
    import pandas as pd

    data = frame.copy()
    required = {
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "source_freq",
    }
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"composite frame missing columns: {sorted(missing)}")
    timestamps = pd.to_datetime(data["timestamp"], errors="raise")
    if start_date is not None:
        data = data.loc[timestamps >= pd.Timestamp(start_date)]
        timestamps = pd.to_datetime(data["timestamp"], errors="raise")
    if end_date is not None:
        end = pd.Timestamp(end_date)
        if len(end_date) == 10:
            end += pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        data = data.loc[timestamps <= end]
    data = data.reset_index(drop=True)
    data.attrs["data_source"] = COMPOSITE_DATA_SOURCE
    return data


def _rows_by_symbol(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = snapshot.get("rows", ())
    if not isinstance(rows, (tuple, list)):
        return {}
    return {
        str(row["symbol"]): row
        for row in rows
        if isinstance(row, Mapping) and row.get("symbol")
    }
