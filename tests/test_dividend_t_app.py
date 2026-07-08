from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.a_share_bars import LatestQuote  # noqa: E402
from market_regime_alpha.web.dividend_t_app import (  # noqa: E402
    EvaluatePayload,
    PositionPayload,
    RetreatPayload,
    TechnicalPayload,
    TrendState,
    _evaluate_payload,
    sample_decisions,
)


class DividendTAppTests(unittest.TestCase):
    def test_evaluate_returns_signal_code_and_chinese_label(self) -> None:
        data = _evaluate_payload(
            EvaluatePayload(
                symbol="601919.SH",
                retreat=RetreatPayload(
                    market_attention=3.5,
                    upside_certainty=3.5,
                    risk_reward_ratio=1.2,
                    sell_pressure=4.2,
                ),
                technical=TechnicalPayload(
                    trend_state=TrendState.RANGE,
                    near_support=False,
                    near_resistance=True,
                    shrinking_pullback=False,
                    volume_stalling=True,
                    intraday_reversal=False,
                    sector_healthy=True,
                ),
                position=PositionPayload(
                    symbol_position_pct=0.12,
                    base_position_pct=0.10,
                    t_position_pct=0.02,
                    cash_pct=0.40,
                    available_cash_pct=0.40,
                    available_sell_pct=0.10,
                    is_cycle_stock=True,
                ),
            )
        )

        self.assertEqual(data["signal"], "SELL_T")
        self.assertEqual(data["signal_label"], "卖出 T 仓")
        self.assertEqual(data["order_intent"]["signal"], "SELL_T")
        self.assertEqual(data["order_intent"]["signal_label"], "卖出 T 仓")

    def test_sample_decisions_include_signal_label(self) -> None:
        with patch(
            "market_regime_alpha.web.dividend_t_app.fetch_tencent_latest_quotes",
            return_value={"601919.SH": LatestQuote(symbol="601919.SH", current_price=14.91, quote_time="20260602153528")},
        ), patch(
            "market_regime_alpha.web.dividend_t_app.TencentMinuteProvider.minute_bars",
            return_value=_watchlist_bars(),
        ):
            rows = sample_decisions()

        self.assertGreater(len(rows), 0)
        self.assertIn("signal_label", rows[0])
        self.assertEqual(rows[0]["latest_price"], 14.91)
        self.assertEqual(rows[0]["latest_price_time"], "20260602153528")
        self.assertEqual(rows[0]["scan_status"], "real_tencent_intraday")
        self.assertGreater(rows[0]["bar_count"], 30)

    def test_sample_decisions_fall_back_when_intraday_scan_fails(self) -> None:
        with patch(
            "market_regime_alpha.web.dividend_t_app.fetch_tencent_latest_quotes",
            return_value={},
        ), patch(
            "market_regime_alpha.web.dividend_t_app.TencentMinuteProvider.minute_bars",
            side_effect=RuntimeError("network blocked"),
        ):
            rows = sample_decisions()

        self.assertEqual(rows[0]["scan_status"], "fallback_static")
        self.assertIn("network blocked", rows[0]["scan_message"])


def _watchlist_bars() -> pd.DataFrame:
    base = pd.Timestamp("2026-06-03 09:30:00")
    rows = []
    price = 14.50
    for index in range(40):
        price += 0.01 if index < 20 else -0.002
        rows.append(
            {
                "symbol": "601919.SH",
                "timestamp": (base + pd.Timedelta(minutes=5 * index)).strftime("%Y-%m-%d %H:%M:%S"),
                "open": round(price - 0.01, 3),
                "high": round(price + 0.03, 3),
                "low": round(price - 0.03, 3),
                "close": round(price, 3),
                "volume": 1_000_000.0 + index * 1000,
                "amount": (1_000_000.0 + index * 1000) * price,
                "source_freq": "5min",
            }
        )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    unittest.main()
