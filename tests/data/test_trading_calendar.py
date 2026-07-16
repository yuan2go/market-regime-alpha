from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.trading_calendar import TradingSession, build_trading_calendar_artifact


TZ = ZoneInfo("Asia/Shanghai")


def _session(trade_date: date) -> TradingSession:
    return TradingSession(
        trade_date=trade_date,
        session_close=datetime(trade_date.year, trade_date.month, trade_date.day, 15, 0, tzinfo=TZ),
    )


def test_calendar_resolves_next_explicit_session_without_weekday_inference() -> None:
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version="fixture-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            _session(date(2026, 7, 15)),
            _session(date(2026, 7, 20)),
            _session(date(2026, 7, 21)),
        ),
    )

    resolved = calendar.resolve_next_session_date(
        DecisionTime(datetime(2026, 7, 15, 14, 55, tzinfo=TZ))
    )

    assert resolved == date(2026, 7, 20)
    assert not calendar.contains(date(2026, 7, 16))
    assert not calendar.contains(date(2026, 7, 17))


def test_calendar_resolves_exact_following_exchange_sessions() -> None:
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version="fixture-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            _session(date(2026, 7, 15)),
            _session(date(2026, 7, 20)),
            _session(date(2026, 7, 21)),
        ),
    )
    decision_time = DecisionTime(datetime(2026, 7, 15, 14, 55, tzinfo=TZ))

    assert calendar.resolve_following_session_dates(decision_time, 2) == (
        date(2026, 7, 20),
        date(2026, 7, 21),
    )


def test_calendar_artifact_identity_is_deterministic_under_input_ordering() -> None:
    sessions = (
        _session(date(2026, 7, 15)),
        _session(date(2026, 7, 16)),
    )
    first = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version="fixture-v1",
        timezone_name="Asia/Shanghai",
        sessions=sessions,
    )
    second = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version="fixture-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(reversed(sessions)),
    )

    assert first.artifact_id == second.artifact_id
    assert first.sessions == second.sessions


def test_calendar_fails_when_no_later_explicit_session_exists() -> None:
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version="fixture-v1",
        timezone_name="Asia/Shanghai",
        sessions=(_session(date(2026, 7, 15)),),
    )

    with pytest.raises(LookupError, match="no later trading session"):
        calendar.resolve_next_session_date(
            DecisionTime(datetime(2026, 7, 15, 14, 55, tzinfo=TZ))
        )


@pytest.mark.parametrize("count", (True, 1.5, "2"))
def test_calendar_rejects_non_integer_following_session_count(count: object) -> None:
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version="fixture-v1",
        timezone_name="Asia/Shanghai",
        sessions=(_session(date(2026, 7, 15)), _session(date(2026, 7, 16))),
    )

    with pytest.raises(TypeError, match="count must be an integer"):
        calendar.resolve_following_session_dates(
            DecisionTime(datetime(2026, 7, 15, 14, 55, tzinfo=TZ)),
            count,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("count", (0, -1))
def test_calendar_rejects_non_positive_following_session_count(count: int) -> None:
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version="fixture-v1",
        timezone_name="Asia/Shanghai",
        sessions=(_session(date(2026, 7, 15)), _session(date(2026, 7, 16))),
    )

    with pytest.raises(ValueError, match="count must be positive"):
        calendar.resolve_following_session_dates(
            DecisionTime(datetime(2026, 7, 15, 14, 55, tzinfo=TZ)),
            count,
        )


def test_calendar_fails_closed_when_following_session_coverage_is_insufficient() -> None:
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version="fixture-v1",
        timezone_name="Asia/Shanghai",
        sessions=(_session(date(2026, 7, 15)), _session(date(2026, 7, 16))),
    )

    with pytest.raises(LookupError, match="insufficient later trading sessions"):
        calendar.resolve_following_session_dates(
            DecisionTime(datetime(2026, 7, 15, 14, 55, tzinfo=TZ)),
            2,
        )
