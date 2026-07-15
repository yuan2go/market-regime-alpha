"""Compatibility adapter from the existing Legacy trading-calendar sidecar shape.

The adapter preserves the current sidecar invariant used by ``formal_dataset_builder.py``:
``trading_dates`` must equal the set of session records carrying ``session_close``.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingCalendarArtifact,
    TradingSession,
    build_trading_calendar_artifact,
)


class LegacyTradingCalendarAdapterError(ValueError):
    """Raised when a Legacy calendar sidecar cannot be adapted truthfully."""


def load_legacy_trading_calendar_sidecar(
    path: Path,
    *,
    source_dataset_id: DatasetId,
    market: str = "CN_A_SHARE",
    calendar_version: str,
    timezone_name: str = "Asia/Shanghai",
) -> TradingCalendarArtifact:
    """Load and validate the existing sidecar shape into the canonical calendar artifact."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyTradingCalendarAdapterError("TRADING_CALENDAR_INVALID") from exc
    return adapt_legacy_trading_calendar_mapping(
        raw,
        source_dataset_id=source_dataset_id,
        market=market,
        calendar_version=calendar_version,
        timezone_name=timezone_name,
    )


def adapt_legacy_trading_calendar_mapping(
    raw: dict[str, Any],
    *,
    source_dataset_id: DatasetId,
    market: str = "CN_A_SHARE",
    calendar_version: str,
    timezone_name: str = "Asia/Shanghai",
) -> TradingCalendarArtifact:
    """Adapt an already-loaded Legacy sidecar mapping."""

    if not isinstance(raw, dict):
        raise LegacyTradingCalendarAdapterError("TRADING_CALENDAR_INVALID")
    dates = raw.get("trading_dates")
    sessions = raw.get("sessions")
    if not isinstance(dates, list) or not isinstance(sessions, list) or not dates:
        raise LegacyTradingCalendarAdapterError("TRADING_CALENDAR_SESSION_CLOSE_REQUIRED")
    if not all(isinstance(value, str) and value for value in dates):
        raise LegacyTradingCalendarAdapterError("TRADING_CALENDAR_SESSION_CLOSE_REQUIRED")
    if len(dates) != len(set(dates)):
        raise LegacyTradingCalendarAdapterError("TRADING_CALENDAR_DUPLICATE_DATE")

    session_rows = [
        item
        for item in sessions
        if isinstance(item, dict) and item.get("trade_date") and item.get("session_close")
    ]
    session_dates = [str(item["trade_date"]) for item in session_rows]
    if set(dates) != set(session_dates) or len(session_dates) != len(set(session_dates)):
        raise LegacyTradingCalendarAdapterError("TRADING_CALENDAR_SESSION_CLOSE_REQUIRED")

    zone = ZoneInfo(timezone_name)
    adapted_sessions: list[TradingSession] = []
    for row in session_rows:
        trade_date_text = str(row["trade_date"])
        close_text = str(row["session_close"])
        try:
            trade_date = date.fromisoformat(trade_date_text)
            close_value = datetime.fromisoformat(close_text)
        except ValueError as exc:
            raise LegacyTradingCalendarAdapterError("TRADING_CALENDAR_SESSION_CLOSE_REQUIRED") from exc
        if close_value.tzinfo is None or close_value.utcoffset() is None:
            close_value = close_value.replace(tzinfo=zone)
        adapted_sessions.append(
            TradingSession(
                trade_date=trade_date,
                session_close=close_value,
            )
        )

    return build_trading_calendar_artifact(
        source_dataset_id=source_dataset_id,
        market=market,
        calendar_version=calendar_version,
        timezone_name=timezone_name,
        sessions=tuple(adapted_sessions),
    )
