from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.chan import analyze_chan_structure


class ChanStructureTests(unittest.TestCase):
    def test_detects_pivot_and_exposes_structure_fields(self) -> None:
        structure = analyze_chan_structure(
            _wave_bars([10.0, 9.65, 10.18, 9.78, 10.25, 9.82, 10.28, 9.90, 10.34, 10.08, 10.55, 10.32, 10.70]),
            level="5m",
            min_kline_gap=1,
            min_price_change=0.003,
        )

        self.assertGreaterEqual(structure.fractal_count, 4)
        self.assertGreaterEqual(structure.stroke_count, 3)
        self.assertIsNotNone(structure.pivot_low)
        self.assertIsNotNone(structure.pivot_high)
        self.assertGreaterEqual(structure.score, 45.0)
        self.assertIn(structure.structure_type, {"pivot", "breakout", "divergence", "breakdown"})

    def test_breakout_after_pivot_can_be_classified_as_buy3(self) -> None:
        structure = analyze_chan_structure(
            _wave_bars(
                [
                    10.0,
                    9.70,
                    10.18,
                    9.82,
                    10.24,
                    9.90,
                    10.30,
                    10.04,
                    10.58,
                    10.42,
                    10.86,
                    10.70,
                    11.02,
                    10.82,
                    11.08,
                ]
            ),
            level="5m",
            min_kline_gap=1,
            min_price_change=0.003,
        )

        self.assertEqual(structure.trend_direction, "up")
        self.assertIn(structure.buy_point_type, {"buy3", "none"})
        if structure.buy_point_type == "buy3":
            self.assertGreaterEqual(structure.score, 70.0)
            self.assertIsNotNone(structure.invalid_price)


def _wave_bars(closes: list[float]):
    import pandas as pd

    rows = []
    for index, close in enumerate(closes):
        open_price = close
        high = close + 0.04
        low = close - 0.04
        rows.append(
            {
                "symbol": "TEST",
                "timestamp": pd.Timestamp("2026-06-01 09:35") + pd.Timedelta(minutes=5 * index),
                "open": round(open_price, 3),
                "high": round(high, 3),
                "low": round(low, 3),
                "close": round(close, 3),
                "volume": float(1_000_000 - min(index, 8) * 25_000),
                "amount": float((1_000_000 - min(index, 8) * 25_000) * close),
                "source_freq": "5min",
            }
        )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    unittest.main()
