from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from market_regime_alpha.core.time import AvailabilityTime, DecisionTime


def test_semantic_time_requires_timezone_awareness() -> None:
    with pytest.raises(ValueError):
        DecisionTime(datetime(2026, 7, 15, 14, 55))


def test_semantic_time_preserves_semantics_and_can_convert_to_utc() -> None:
    shanghai = timezone(timedelta(hours=8))
    value = datetime(2026, 7, 15, 14, 55, tzinfo=shanghai)
    decision = DecisionTime(value)
    availability = AvailabilityTime(value)

    assert decision != availability
    assert decision.isoformat() == "2026-07-15T14:55:00+08:00"
    assert decision.as_utc() == datetime(2026, 7, 15, 6, 55, tzinfo=timezone.utc)
