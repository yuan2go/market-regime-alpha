from __future__ import annotations

from datetime import date

import pytest

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.legacy.trading_calendar_adapter import (
    LegacyTradingCalendarAdapterError,
    adapt_legacy_trading_calendar_mapping,
)


def test_legacy_calendar_sidecar_adapts_to_canonical_calendar() -> None:
    calendar = adapt_legacy_trading_calendar_mapping(
        {
            "trading_dates": ["2026-07-15", "2026-07-20"],
            "sessions": [
                {"trade_date": "2026-07-15", "session_close": "2026-07-15T15:00:00"},
                {"trade_date": "2026-07-20", "session_close": "2026-07-20T15:00:00"},
            ],
        },
        source_dataset_id=DatasetId("dataset-legacy-calendar-v1"),
        calendar_version="legacy-sidecar-v1",
    )

    assert calendar.trading_dates == (date(2026, 7, 15), date(2026, 7, 20))
    assert calendar.timezone_name == "Asia/Shanghai"


def test_legacy_calendar_sidecar_rejects_date_session_set_mismatch() -> None:
    with pytest.raises(LegacyTradingCalendarAdapterError, match="TRADING_CALENDAR_SESSION_CLOSE_REQUIRED"):
        adapt_legacy_trading_calendar_mapping(
            {
                "trading_dates": ["2026-07-15", "2026-07-16"],
                "sessions": [
                    {"trade_date": "2026-07-15", "session_close": "2026-07-15T15:00:00"},
                ],
            },
            source_dataset_id=DatasetId("dataset-legacy-calendar-v1"),
            calendar_version="legacy-sidecar-v1",
        )


def test_legacy_calendar_sidecar_rejects_duplicate_dates() -> None:
    with pytest.raises(LegacyTradingCalendarAdapterError, match="TRADING_CALENDAR_DUPLICATE_DATE"):
        adapt_legacy_trading_calendar_mapping(
            {
                "trading_dates": ["2026-07-15", "2026-07-15"],
                "sessions": [
                    {"trade_date": "2026-07-15", "session_close": "2026-07-15T15:00:00"},
                ],
            },
            source_dataset_id=DatasetId("dataset-legacy-calendar-v1"),
            calendar_version="legacy-sidecar-v1",
        )
