from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.a_share_bars import LatestQuote  # noqa: E402
from market_regime_alpha.dividend_t.trend_snapshot import (  # noqa: E402
    build_dividend_trend_snapshot,
    normalize_dividend_trend_snapshot,
    write_dividend_trend_snapshot,
)


class DividendTrendSnapshotTests(unittest.TestCase):
    def test_build_snapshot_scans_watchlist_and_serializes_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            watchlist = Path(directory) / "watchlist.csv"
            watchlist.write_text(
                "symbol,name,industry,is_cycle_stock,notes\n"
                "601919.SH,中远海控,航运,true,核心观察\n"
                "600900.SH,长江电力,电力,false,公用事业\n",
                encoding="utf-8",
            )
            snapshot = build_dividend_trend_snapshot(
                watchlist_path=watchlist,
                limit=20,
                provider=FakeProvider(),
                quotes={
                    "601919.SH": LatestQuote(symbol="601919.SH", current_price=14.92, change_pct=0.012, quote_time="20260709100500"),
                    "600900.SH": LatestQuote(symbol="600900.SH", current_price=31.2, change_pct=-0.004, quote_time="20260709100500"),
                },
                generated_at=datetime(2026, 7, 9, 10, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

        self.assertEqual(snapshot["row_count"], 2)
        self.assertEqual(snapshot["schema_version"], 2)
        self.assertEqual(snapshot["model_metadata"]["daily_macd_config"]["bar_interval"], "1d")
        self.assertEqual(snapshot["model_metadata"]["timing_5m_macd_config"]["bar_interval"], "5m")
        self.assertEqual(snapshot["model_metadata"]["daily_macd_config"]["closed_bars_only"], True)
        self.assertEqual(snapshot["successful_count"], 2)
        self.assertEqual(snapshot["failed_count"], 0)
        self.assertEqual(snapshot["horizon"], "未来1/3/5日上涨概率与1/3/5日历史命中率")
        self.assertIn("point_hit_rates", snapshot)
        self.assertEqual(snapshot["rows"][0]["symbol"], "601919.SH")
        self.assertIn(snapshot["rows"][0]["future_trend"], {"bullish", "neutral", "bearish", "risk_off"})
        self.assertIn("signal_label", snapshot["rows"][0])
        self.assertIn("timing_action_label", snapshot["rows"][0])
        self.assertIn("up_probability_1d", snapshot["rows"][0])
        self.assertIn("up_probability_3d", snapshot["rows"][0])
        self.assertIn("up_probability_5d", snapshot["rows"][0])
        self.assertEqual(snapshot["rows"][0]["latest_price"], 14.92)
        self.assertFalse(snapshot["rows"][0]["macd_data_ready"])
        self.assertEqual(snapshot["rows"][0]["macd_data_reason"], "INSUFFICIENT_BARS")
        self.assertEqual(snapshot["rows"][0]["macd_score"], 50.0)
        self.assertEqual(snapshot["rows"][0]["macd_cross"], "NONE")
        self.assertIsNone(snapshot["rows"][0]["macd_cross_age"])

    def test_symbol_error_is_returned_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            watchlist = Path(directory) / "watchlist.csv"
            watchlist.write_text("symbol,name,industry,is_cycle_stock,notes\n601919.SH,中远海控,航运,true,核心观察\n", encoding="utf-8")
            snapshot = build_dividend_trend_snapshot(watchlist_path=watchlist, provider=FailingProvider(), quotes={})

        self.assertEqual(snapshot["successful_count"], 0)
        self.assertEqual(snapshot["failed_count"], 1)
        self.assertEqual(snapshot["rows"][0]["status"], "error")
        self.assertIn("network blocked", snapshot["rows"][0]["scan_error"])

    def test_write_snapshot_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "docs" / "data" / "dividend_trends.json"
            written = write_dividend_trend_snapshot({"schema_version": 1, "rows": []}, output_path=path)

            self.assertEqual(written, path)
            self.assertIn('"schema_version": 1', path.read_text(encoding="utf-8"))

    def test_schema_1_snapshot_is_upgraded_additively_with_neutral_macd(self) -> None:
        legacy = {
            "schema_version": 1,
            "generated_at": "2026-07-09T10:10:00+08:00",
            "row_count": 1,
            "rows": [{"symbol": "601919.SH", "signal": "BUY_T", "suggested_trade_pct": 0.03, "reasons": ["legacy"]}],
        }

        normalized = normalize_dividend_trend_snapshot(legacy)

        self.assertEqual(normalized["schema_version"], 2)
        self.assertEqual(normalized["generated_at"], legacy["generated_at"])
        self.assertEqual(normalized["rows"][0]["symbol"], "601919.SH")
        self.assertEqual(normalized["rows"][0]["signal"], "BUY_T")
        self.assertEqual(normalized["rows"][0]["suggested_trade_pct"], 0.03)
        self.assertEqual(normalized["rows"][0]["reasons"], ["legacy"])
        self.assertFalse(normalized["rows"][0]["macd_data_ready"])
        self.assertEqual(normalized["rows"][0]["macd_score"], 50.0)
        self.assertEqual(normalized["rows"][0]["macd_cross"], "NONE")
        self.assertIsNone(normalized["rows"][0]["macd_cross_age"])

    def test_schema_1_upgrade_does_not_overwrite_existing_additive_values(self) -> None:
        snapshot = {
            "schema_version": 1,
            "rows": [{"symbol": "601919.SH", "macd_data_ready": False, "macd_data_reason": "INVALID_CLOSE", "macd_score": 50.0}],
        }

        normalized = normalize_dividend_trend_snapshot(snapshot)

        self.assertEqual(normalized["rows"][0]["macd_data_reason"], "INVALID_CLOSE")


class FakeProvider:
    name = "fake"
    data_source = "fake_5min"
    is_realtime = False

    def minute_bars(self, symbol: str, *, freq: str = "5min", start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
        base = pd.Timestamp("2026-07-09 09:30:00")
        rows = []
        price = 12.0 if symbol == "601919.SH" else 30.0
        for index in range(80):
            price += 0.03 if index < 60 else -0.005
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": (base + pd.Timedelta(minutes=5 * index)).strftime("%Y-%m-%d %H:%M:%S"),
                    "open": round(price - 0.02, 3),
                    "high": round(price + 0.04, 3),
                    "low": round(price - 0.04, 3),
                    "close": round(price, 3),
                    "volume": 900_000.0 + index * 2_000,
                    "amount": (900_000.0 + index * 2_000) * price,
                    "source_freq": "5min",
                }
            )
        return pd.DataFrame(rows)


class FailingProvider:
    name = "failing"
    data_source = "failing"
    is_realtime = False

    def minute_bars(self, symbol: str, *, freq: str = "5min", start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
        raise RuntimeError("network blocked")


if __name__ == "__main__":
    unittest.main()
