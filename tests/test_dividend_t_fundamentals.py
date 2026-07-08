from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.cosco_profile import CoscoProfile
from market_regime_alpha.dividend_t.fundamentals import (  # noqa: E402
    TushareFundamentalScorer,
    apply_fundamental_snapshot,
    fallback_fundamental_snapshot,
)


class DividendTFundamentalTests(unittest.TestCase):
    def test_tushare_tables_build_profile_scores_without_future_daily_basic(self) -> None:
        profile = CoscoProfile(symbol="601919.SH", name="中远海控", industry="航运")
        with tempfile.TemporaryDirectory() as directory:
            scorer = TushareFundamentalScorer(cache_dir=Path(directory), provider=_FakeProvider())

            snapshot = scorer.score(profile, as_of_date="2026-05-15")
            updated = apply_fundamental_snapshot(profile, snapshot)

        self.assertEqual(snapshot.source, "tushare")
        self.assertEqual(updated.fundamental_source, "tushare")
        self.assertEqual(updated.fundamental_as_of, "2026-05-15")
        self.assertGreater(snapshot.f_score, 55)
        self.assertEqual(snapshot.metrics["daily_basic_rows"], 2.0)
        self.assertEqual(updated.base_fundamental_score, snapshot.f_score)
        self.assertTrue(any("Tushare 基本面" in item for item in updated.fundamental_notes))

    def test_fallback_snapshot_uses_profile_scores_and_records_reason(self) -> None:
        profile = CoscoProfile(base_fundamental_score=70.0, dividend_sustainability_score=68.0)

        snapshot = fallback_fundamental_snapshot(profile, as_of_date="2026-06-04", reason="permission denied")

        self.assertEqual(snapshot.source, "industry_profile_fallback")
        self.assertIn("permission denied", snapshot.notes[0])
        self.assertGreater(snapshot.f_score, 0)


class _FakeProvider:
    def daily_basic(self, symbol: str, *, start_date: str | None = None, end_date: str | None = None):
        return pd.DataFrame(
            [
                {"ts_code": symbol, "trade_date": "20260510", "pe_ttm": 12.0, "pe": 13.0, "pb": 1.2, "dv_ttm": 4.8, "dv_ratio": 4.5},
                {"ts_code": symbol, "trade_date": "20260515", "pe_ttm": 11.0, "pe": 12.0, "pb": 1.1, "dv_ttm": 5.2, "dv_ratio": 5.0},
                {"ts_code": symbol, "trade_date": "20260520", "pe_ttm": 9.0, "pe": 10.0, "pb": 0.9, "dv_ttm": 6.5, "dv_ratio": 6.1},
            ]
        )

    def dividends(self, symbol: str):
        return pd.DataFrame(
            [
                {"ts_code": symbol, "ann_date": "20250401", "end_date": "20241231", "cash_div_tax": 0.52},
                {"ts_code": symbol, "ann_date": "20260401", "end_date": "20251231", "cash_div_tax": 0.58},
            ]
        )

    def financial_indicator(self, symbol: str):
        return pd.DataFrame(
            [
                {
                    "ts_code": symbol,
                    "ann_date": "20250420",
                    "end_date": "20241231",
                    "roe": 9.0,
                    "debt_to_assets": 50.0,
                    "ocfps": 1.2,
                    "netprofit_yoy": 8.0,
                    "or_yoy": 6.0,
                },
                {
                    "ts_code": symbol,
                    "ann_date": "20260420",
                    "end_date": "20251231",
                    "roe": 12.0,
                    "debt_to_assets": 48.0,
                    "ocfps": 1.6,
                    "netprofit_yoy": 12.0,
                    "or_yoy": 8.0,
                },
            ]
        )


if __name__ == "__main__":
    unittest.main()
