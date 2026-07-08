from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.universe import LargecapUniverseConfig, build_largecap_universe  # noqa: E402


class LargecapUniverseTests(unittest.TestCase):
    def test_build_largecap_universe_filters_and_sorts(self) -> None:
        basic = pd.DataFrame(
            [
                {"ts_code": "600001.SH", "name": "大盘一", "industry": "银行", "market": "主板", "list_date": "20100101"},
                {"ts_code": "000002.SZ", "name": "大盘二", "industry": "煤炭", "market": "主板", "list_date": "20100101"},
                {"ts_code": "300003.SZ", "name": "大盘三", "industry": "软件", "market": "创业板", "list_date": "20100101"},
                {"ts_code": "688004.SH", "name": "ST问题", "industry": "科技", "market": "科创板", "list_date": "20100101"},
                {"ts_code": "830005.BJ", "name": "北交", "industry": "制造", "market": "北交所", "list_date": "20100101"},
                {"ts_code": "600006.SH", "name": "新股", "industry": "消费", "market": "主板", "list_date": "20251201"},
                {"ts_code": "600007.SH", "name": "低成交", "industry": "消费", "market": "主板", "list_date": "20100101"},
            ]
        )
        daily_basic = pd.DataFrame(
            [
                {"ts_code": "600001.SH", "total_mv": 9000, "circ_mv": 8000},
                {"ts_code": "000002.SZ", "total_mv": 12000, "circ_mv": 7000},
                {"ts_code": "300003.SZ", "total_mv": 7000, "circ_mv": 6000},
                {"ts_code": "688004.SH", "total_mv": 30000, "circ_mv": 25000},
                {"ts_code": "830005.BJ", "total_mv": 40000, "circ_mv": 30000},
                {"ts_code": "600006.SH", "total_mv": 50000, "circ_mv": 45000},
                {"ts_code": "600007.SH", "total_mv": 60000, "circ_mv": 55000},
            ]
        )
        quote = pd.DataFrame(
            [
                {"ts_code": "600001.SH", "amount": 80_000},
                {"ts_code": "000002.SZ", "amount": 90_000},
                {"ts_code": "300003.SZ", "amount": 70_000},
                {"ts_code": "688004.SH", "amount": 200_000},
                {"ts_code": "830005.BJ", "amount": 200_000},
                {"ts_code": "600006.SH", "amount": 200_000},
                {"ts_code": "600007.SH", "amount": 10_000},
            ]
        )

        frame, diagnostics = build_largecap_universe(
            stock_basic=basic,
            daily_basic=daily_basic,
            daily_quote=quote,
            config=LargecapUniverseConfig(trade_date="20260625", limit=3, min_amount=50_000),
        )

        self.assertEqual(frame["symbol"].tolist(), ["000002.SZ", "600001.SH", "300003.SZ"])
        self.assertEqual(int(diagnostics["selected"]), 3)
        self.assertTrue(frame.loc[frame["symbol"] == "000002.SZ", "is_cycle_stock"].iloc[0])
        self.assertIn("not point-in-time", frame["bias_notes"].iloc[0])


if __name__ == "__main__":
    unittest.main()
