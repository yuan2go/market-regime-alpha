from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.tushare_client import (
    TushareConfigError,
    get_tushare_token,
    normalize_daily_date,
    normalize_minute_datetime,
    normalize_minute_freq,
    normalize_ts_code,
)


class TushareClientUtilityTests(unittest.TestCase):
    def test_normalize_ts_code(self) -> None:
        self.assertEqual(normalize_ts_code("600000"), "600000.SH")
        self.assertEqual(normalize_ts_code("000001"), "000001.SZ")
        self.assertEqual(normalize_ts_code("300750"), "300750.SZ")
        self.assertEqual(normalize_ts_code("SH600519"), "600519.SH")
        self.assertEqual(normalize_ts_code(" 688001.sh "), "688001.SH")

    def test_invalid_ts_code(self) -> None:
        with self.assertRaises(ValueError):
            normalize_ts_code("abc")

    def test_normalize_dates(self) -> None:
        self.assertEqual(normalize_daily_date("2026-05-18"), "20260518")
        self.assertEqual(normalize_daily_date("20260518"), "20260518")
        self.assertEqual(normalize_minute_datetime("20260518", is_end=False), "2026-05-18 09:00:00")
        self.assertEqual(normalize_minute_datetime("2026-05-18", is_end=True), "2026-05-18 15:30:00")
        self.assertEqual(normalize_minute_datetime("2026-05-18T10:15", is_end=True), "2026-05-18 10:15:00")

    def test_normalize_minute_freq(self) -> None:
        self.assertEqual(normalize_minute_freq("1m"), "1min")
        self.assertEqual(normalize_minute_freq("60"), "60min")
        with self.assertRaises(ValueError):
            normalize_minute_freq("2min")

    def test_missing_token_message(self) -> None:
        with self.assertRaises(TushareConfigError):
            get_tushare_token(env={})


if __name__ == "__main__":
    unittest.main()

