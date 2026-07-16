from __future__ import annotations

from datetime import date, datetime
import math
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.time import AvailabilityTime, FinalizationTime
from market_regime_alpha.data.path_evidence import (
    RehearsalFutureDailyBar,
    RehearsalFutureSuspensionEvidence,
)


TZ = ZoneInfo("Asia/Shanghai")


def _available(hour: int = 15, minute: int = 5) -> AvailabilityTime:
    return AvailabilityTime(datetime(2026, 7, 20, hour, minute, tzinfo=TZ))


def _finalized(hour: int = 15, minute: int = 1) -> FinalizationTime:
    return FinalizationTime(datetime(2026, 7, 20, hour, minute, tzinfo=TZ))


def test_future_daily_bar_preserves_finality_availability_and_price_basis() -> None:
    bar = RehearsalFutureDailyBar(
        symbol="000001.SZ",
        session_date=date(2026, 7, 20),
        open=10.0,
        high=10.4,
        low=9.8,
        close=10.2,
        price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
        available_at=_available(),
        finalized_at=_finalized(),
    )

    assert bar.available_at.value >= bar.finalized_at.value
    assert bar.price_adjustment_basis == "RAW_UNADJUSTED_TRADABLE_PRICE_V1"


def test_future_daily_bar_rejects_availability_before_finality() -> None:
    with pytest.raises(ValueError, match="available_at must not precede finalized_at"):
        RehearsalFutureDailyBar(
            symbol="000001.SZ",
            session_date=date(2026, 7, 20),
            open=10.0,
            high=10.4,
            low=9.8,
            close=10.2,
            price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
            available_at=_available(15, 0),
            finalized_at=_finalized(15, 1),
        )


def test_future_path_evidence_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RehearsalFutureDailyBar(
            symbol="000001.SZ",
            session_date=date(2026, 7, 20),
            open=10.0,
            high=10.4,
            low=9.8,
            close=10.2,
            price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
            available_at=AvailabilityTime(datetime(2026, 7, 20, 15, 5)),
            finalized_at=_finalized(),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("open", 0.0),
        ("high", math.inf),
        ("low", -1.0),
        ("close", math.nan),
    ),
)
def test_future_daily_bar_rejects_invalid_price(
    field: str,
    value: float,
) -> None:
    values = {"open": 10.0, "high": 10.4, "low": 9.8, "close": 10.2}
    values[field] = value

    with pytest.raises(ValueError, match=f"{field} must be positive and finite"):
        RehearsalFutureDailyBar(
            symbol="000001.SZ",
            session_date=date(2026, 7, 20),
            price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
            available_at=_available(),
            finalized_at=_finalized(),
            **values,
        )


@pytest.mark.parametrize(
    ("open_price", "high", "low", "close"),
    (
        (10.5, 10.4, 9.8, 10.2),
        (10.0, 10.4, 9.8, 9.7),
        (10.0, 9.7, 9.8, 9.75),
    ),
)
def test_future_daily_bar_rejects_invalid_ohlc_ordering(
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> None:
    with pytest.raises(ValueError, match="future daily OHLC"):
        RehearsalFutureDailyBar(
            symbol="000001.SZ",
            session_date=date(2026, 7, 20),
            open=open_price,
            high=high,
            low=low,
            close=close,
            price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
            available_at=_available(),
            finalized_at=_finalized(),
        )


def test_future_suspension_evidence_requires_boolean_and_time_ordering() -> None:
    evidence = RehearsalFutureSuspensionEvidence(
        symbol="000001.SZ",
        session_date=date(2026, 7, 20),
        is_suspended=True,
        available_at=_available(),
        finalized_at=_finalized(),
    )
    assert evidence.is_suspended is True

    with pytest.raises(TypeError, match="is_suspended must be boolean"):
        RehearsalFutureSuspensionEvidence(
            symbol="000001.SZ",
            session_date=date(2026, 7, 20),
            is_suspended=1,  # type: ignore[arg-type]
            available_at=_available(),
            finalized_at=_finalized(),
        )
