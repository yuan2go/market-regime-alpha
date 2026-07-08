from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.grid_25t_test import Grid25TConfig, run_grid_25t_backtest  # noqa: E402


class Grid25TTestBacktestTests(unittest.TestCase):
    def test_intraday_drop_does_not_trade_when_close_does_not_trigger(self) -> None:
        bars = pd.DataFrame(
            [
                _bar("2026-01-02 09:35:00", open_=10.00, high=10.02, low=9.70, close=9.80),
                _bar("2026-01-02 15:00:00", open_=9.80, high=10.02, low=9.80, close=9.95),
            ]
        )

        result = run_grid_25t_backtest(bars, config=_test_config())

        self.assertEqual(result.trade_count, 0)
        self.assertEqual(result.buy_count, 0)
        self.assertEqual(len(result.equity_curve), 1)

    def test_daily_close_drop_buys_half_remaining_cash_once(self) -> None:
        bars = pd.DataFrame(
            [
                _bar("2026-01-02 09:35:00", open_=10.00, high=10.00, low=9.90, close=9.90),
                _bar("2026-01-02 15:00:00", open_=9.90, high=9.92, low=9.75, close=9.75),
            ]
        )

        result = run_grid_25t_backtest(bars, config=_test_config())

        self.assertEqual(result.daily_drop_buy_count, 1)
        self.assertEqual(result.ladder_buy_count, 0)
        self.assertEqual(result.sell_count, 0)
        self.assertAlmostEqual(result.trades[0].price, 9.75)
        self.assertGreater(result.trades[0].shares * result.trades[0].price, 29_000)
        self.assertLess(result.trades[0].shares * result.trades[0].price, 31_000)

    def test_ladder_buy_happens_on_later_daily_close_slide(self) -> None:
        bars = pd.DataFrame(
            [
                _bar("2026-01-02 09:35:00", open_=10.00, high=10.00, low=9.90, close=9.90),
                _bar("2026-01-02 15:00:00", open_=9.90, high=9.92, low=9.75, close=9.75),
                _bar("2026-01-05 09:35:00", open_=9.68, high=9.74, low=9.60, close=9.60),
                _bar("2026-01-05 15:00:00", open_=9.60, high=9.60, low=9.50, close=9.50),
            ]
        )

        result = run_grid_25t_backtest(bars, config=_test_config())

        self.assertEqual(result.daily_drop_buy_count, 1)
        self.assertEqual(result.ladder_buy_count, 1)
        self.assertEqual(result.buy_count, 2)

    def test_ladder_buy_is_blocked_below_moving_average(self) -> None:
        bars = pd.DataFrame(
            [
                _bar("2026-01-02 09:35:00", open_=10.00, high=10.00, low=9.90, close=9.90),
                _bar("2026-01-02 15:00:00", open_=9.90, high=9.92, low=9.75, close=9.75),
                _bar("2026-01-05 09:35:00", open_=9.68, high=9.74, low=9.60, close=9.60),
                _bar("2026-01-05 15:00:00", open_=9.60, high=9.60, low=9.50, close=9.50),
            ]
        )

        result = run_grid_25t_backtest(bars, config=_test_config(ma_window_days=2))

        self.assertEqual(result.daily_drop_buy_count, 1)
        self.assertEqual(result.ladder_buy_count, 0)
        self.assertEqual(result.ma_filter_blocked_ladder_count, 1)

    def test_daily_close_rise_clears_sellable_position(self) -> None:
        bars = pd.DataFrame(
            [
                _bar("2026-01-02 09:35:00", open_=10.00, high=10.00, low=9.90, close=9.90),
                _bar("2026-01-02 15:00:00", open_=9.90, high=9.92, low=9.75, close=9.75),
                _bar("2026-01-05 09:35:00", open_=9.75, high=9.80, low=9.75, close=9.80),
                _bar("2026-01-05 15:00:00", open_=9.80, high=10.10, low=9.80, close=10.07),
            ]
        )

        result = run_grid_25t_backtest(bars, config=_test_config())

        self.assertEqual(result.daily_drop_buy_count, 1)
        self.assertEqual(result.daily_clear_count, 1)
        self.assertEqual(result.target_sell_count, 0)
        self.assertEqual(result.sell_count, 1)
        self.assertEqual(result.t1_blocked_closeout_shares, 0)
        self.assertEqual(result.equity_curve[-1].active_layer_count, 0)

    def test_daily_close_rise_does_not_clear_losing_layer(self) -> None:
        bars = pd.DataFrame(
            [
                _bar("2026-01-02 09:35:00", open_=10.00, high=10.00, low=9.90, close=9.90),
                _bar("2026-01-02 15:00:00", open_=9.90, high=9.92, low=9.75, close=9.75),
                _bar("2026-01-05 09:35:00", open_=8.50, high=8.55, low=8.48, close=8.55),
                _bar("2026-01-05 15:00:00", open_=8.55, high=8.90, low=8.55, close=8.85),
            ]
        )

        result = run_grid_25t_backtest(bars, config=_test_config())

        self.assertEqual(result.daily_clear_count, 0)
        self.assertGreater(result.daily_clear_skipped_layer_count, 0)
        self.assertEqual(result.equity_curve[-1].active_layer_count, 1)

    def test_cash_dividend_is_added_before_reinvestment(self) -> None:
        bars = pd.DataFrame(
            [
                _bar("2026-01-02 09:35:00", open_=10.00, high=10.00, low=9.90, close=9.90),
                _bar("2026-01-02 15:00:00", open_=9.90, high=9.92, low=9.75, close=9.75),
                _bar("2026-01-05 09:35:00", open_=9.75, high=9.80, low=9.75, close=9.80, cash_dividend_per_share=0.50),
                _bar("2026-01-05 15:00:00", open_=9.80, high=9.82, low=9.75, close=9.78),
            ]
        )

        result = run_grid_25t_backtest(bars, config=_test_config())

        self.assertEqual(result.dividend_event_count, 1)
        self.assertGreater(result.cash_dividend_total, 0)
        self.assertAlmostEqual(result.cash_dividend_total, result.trades[0].shares * 0.50)


def _test_config(*, ma_window_days: int = 20) -> Grid25TConfig:
    return Grid25TConfig(
        initial_cash=100_000,
        initial_base_position_pct=0.0,
        daily_drop_buy_trigger_pct=0.02,
        daily_drop_cash_pct=0.30,
        daily_rise_clear_pct=0.03,
        daily_clear_min_realized_return_pct=-0.005,
        layer_cash_pct=0.10,
        grid_pct=0.025,
        ma_window_days=ma_window_days,
        commission_rate=0.0,
        stamp_duty_rate=0.0,
        slippage_bps=0.0,
    )


def _bar(
    timestamp: str,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    cash_dividend_per_share: float = 0.0,
    share_bonus_ratio: float = 0.0,
) -> dict[str, object]:
    return {
        "symbol": "601919.SH",
        "timestamp": timestamp,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000,
        "amount": close * 1000,
        "cash_dividend_per_share": cash_dividend_per_share,
        "share_bonus_ratio": share_bonus_ratio,
    }


if __name__ == "__main__":
    unittest.main()
