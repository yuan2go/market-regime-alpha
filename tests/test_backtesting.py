from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.backtesting import load_ohlcv_csv, run_moving_average_crossover


class BacktestingTests(unittest.TestCase):
    def test_sample_data_runs_end_to_end(self) -> None:
        bars = load_ohlcv_csv(PROJECT_ROOT / "data" / "raw" / "sample_etf_ohlcv.csv", symbol="SAMPLE_ETF")

        result = run_moving_average_crossover(bars, fast_window=3, slow_window=8)

        self.assertEqual(result.symbol, "SAMPLE_ETF")
        self.assertEqual(result.rows, 40)
        self.assertGreater(result.final_equity, 0)
        self.assertGreaterEqual(result.trade_events, 1)

    def test_fast_window_must_be_smaller_than_slow_window(self) -> None:
        bars = load_ohlcv_csv(PROJECT_ROOT / "data" / "raw" / "sample_etf_ohlcv.csv", symbol="SAMPLE_ETF")

        with self.assertRaises(ValueError):
            run_moving_average_crossover(bars, fast_window=8, slow_window=8)


if __name__ == "__main__":
    unittest.main()

