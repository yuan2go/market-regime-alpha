from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from market_regime_alpha.dividend_t.point_hit_rate import (
    LEGACY_DIAGNOSTIC_ONLY,
    build_point_hit_rate_events,
    point_type_for_action,
    summarize_point_hit_rate_events,
)


def test_point_hit_rate_is_explicitly_legacy_diagnostic_only() -> None:
    assert LEGACY_DIAGNOSTIC_ONLY is True


def test_point_type_for_action_classifies_buy_and_sell_points() -> None:
    assert point_type_for_action("BUY_T_TIMING") == "buy"
    assert point_type_for_action("BREAKOUT_BUY_TIMING") == "buy"
    assert point_type_for_action("SELL_T_TIMING") == "sell"
    assert point_type_for_action("STOP_T_WAIT") == "sell"
    assert point_type_for_action("WAIT_DAILY_WEAK") == "sell"
    assert point_type_for_action("WAIT") is None


def test_build_point_hit_rate_events_uses_1_3_5_day_forward_returns() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:35:00", periods=10, freq="5min"),
            "open": [100.0] * 10,
            "close": [100.0, 100.0, 100.0, 102.0, 100.0, 98.0, 100.0, 106.0, 100.0, 95.0],
        }
    )
    points = [
        SimpleNamespace(timestamp=str(bars["timestamp"].iloc[2]), action="BUY_T_TIMING"),
        SimpleNamespace(timestamp=str(bars["timestamp"].iloc[3]), action="BUY_T_TIMING"),
        SimpleNamespace(timestamp=str(bars["timestamp"].iloc[4]), action="SELL_T_TIMING"),
        SimpleNamespace(timestamp=str(bars["timestamp"].iloc[6]), action="WAIT"),
    ]

    events = build_point_hit_rate_events(
        symbol="TEST.SH",
        name="测试",
        bars=bars,
        equity_curve=points,
        min_lookback_bars=2,
        signal_step_bars=2,
        horizon_days=(1, 3, 5),
        bars_per_trading_day=1,
    )

    assert len(events) == 6
    buy_events = [event for event in events if event.point_type == "buy"]
    sell_events = [event for event in events if event.point_type == "sell"]
    assert [event.hit for event in buy_events] == [True, False, True]
    assert [event.hit for event in sell_events] == [True, False, True]
    assert [event.horizon_days for event in buy_events] == [1, 3, 5]
    assert buy_events[0].future_return == 0.02
    assert sell_events[0].future_return == -0.02


def test_summarize_point_hit_rate_events_returns_point_and_action_views() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:35:00", periods=8, freq="5min"),
            "open": [100.0] * 8,
            "close": [100.0, 100.0, 100.0, 101.0, 100.0, 99.0, 100.0, 98.0],
        }
    )
    points = [
        SimpleNamespace(timestamp=str(bars["timestamp"].iloc[2]), action="BUY_T_TIMING"),
        SimpleNamespace(timestamp=str(bars["timestamp"].iloc[4]), action="STOP_T_WAIT"),
    ]
    events = build_point_hit_rate_events(
        symbol="TEST.SH",
        name="测试",
        bars=bars,
        equity_curve=points,
        min_lookback_bars=2,
        signal_step_bars=2,
        horizon_days=(1,),
        bars_per_trading_day=1,
    )

    point_summary = summarize_point_hit_rate_events(events)
    action_summary = summarize_point_hit_rate_events(events, group_by_action=True)

    assert [(row.group, row.point_type, row.horizon_days, row.sample_count, row.hit_rate) for row in point_summary] == [
        ("buy", "buy", 1, 1, 1.0),
        ("sell", "sell", 1, 1, 1.0),
    ]
    assert [(row.group, row.point_type, row.horizon_days, row.sample_count, row.hit_rate) for row in action_summary] == [
        ("BUY_T_TIMING", "buy", 1, 1, 1.0),
        ("STOP_T_WAIT", "sell", 1, 1, 1.0),
    ]
