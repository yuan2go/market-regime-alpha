from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from pydantic import ValidationError

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
from market_regime_alpha.dividend_t.macd import MACDDataReason  # noqa: E402


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
        self.assertEqual(data["signal_label"], "卖点")
        self.assertEqual(data["order_intent"]["signal"], "SELL_T")
        self.assertEqual(data["order_intent"]["signal_label"], "卖点")

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

    def test_legacy_api_payload_defaults_to_neutral_macd(self) -> None:
        payload = EvaluatePayload.model_validate(
            {
                "symbol": "601919.SH",
                "technical": {
                    "position_quality": 80,
                    "volume_structure": 75,
                    "trend_quality": 75,
                    "intraday_support": 75,
                },
            }
        )

        result = _evaluate_payload(payload)

        self.assertFalse(result["macd"]["data_ready"])
        self.assertEqual(result["macd"]["data_reason"], "INSUFFICIENT_BARS")
        self.assertEqual(result["macd"]["score"], 50.0)
        self.assertEqual(result["macd"]["cross"], "NONE")
        self.assertIsNone(result["macd"]["cross_age"])
        self.assertIsNone(result["macd"]["bar_interval"])

    def test_explicit_neutral_api_fields_are_digit_equal_to_legacy_output(self) -> None:
        base = {
            "symbol": "601919.SH",
            "retreat": {"market_attention": 3.5, "upside_certainty": 3.5, "risk_reward_ratio": 1.2, "sell_pressure": 4.2},
            "technical": {
                "trend_state": "RANGE",
                "near_support": False,
                "near_resistance": True,
                "shrinking_pullback": False,
                "volume_stalling": True,
                "intraday_reversal": False,
                "sector_healthy": True,
            },
        }
        explicit = {
            **base,
            "technical": {
                **base["technical"],
                "macd_dif": None,
                "macd_dea": None,
                "macd_histogram": None,
                "macd_histogram_delta": None,
                "macd_histogram_trend": "FLAT",
                "macd_cross": "NONE",
                "macd_cross_age": None,
                "macd_zero_axis": "STRADDLING",
                "macd_data_ready": False,
                "macd_data_reason": "INSUFFICIENT_BARS",
                "macd_score": 50.0,
            },
        }

        legacy_result = _evaluate_payload(EvaluatePayload.model_validate(base))
        explicit_result = _evaluate_payload(EvaluatePayload.model_validate(explicit))

        for field in ("signal", "score", "suggested_trade_pct", "reasons", "warnings", "order_intent"):
            self.assertEqual(explicit_result[field], legacy_result[field])
        self.assertEqual(legacy_result["signal"], "SELL_T")
        self.assertEqual(
            legacy_result["score"],
            {"F_score": 71.5, "G_score": 3.5, "Z_score": 3.5, "K_score": 2.0, "S_score": 4.2, "R_score": 51.7, "T_score": 74.4, "total_score": 65.44, "C_score": 65.0},
        )
        self.assertEqual(legacy_result["suggested_trade_pct"], 0.02)

    def test_api_requires_interval_when_raw_macd_values_are_supplied(self) -> None:
        with self.assertRaisesRegex(ValidationError, "bar_interval is required with MACD values"):
            TechnicalPayload(macd_dif=0.1, macd_dea=0.05, macd_histogram=0.1, macd_data_ready=True, macd_data_reason="READY")

    def test_api_preserves_unready_data_reasons(self) -> None:
        for reason in (
            MACDDataReason.INSUFFICIENT_BARS,
            MACDDataReason.INVALID_CLOSE,
            MACDDataReason.PRICE_ADJUSTMENT_UNAVAILABLE,
            MACDDataReason.EXPECTED_BAR_MISSING,
        ):
            with self.subTest(reason=reason):
                payload = EvaluatePayload(technical=TechnicalPayload(macd_data_reason=reason))
                result = _evaluate_payload(payload)
                self.assertEqual(result["macd"]["data_reason"], reason.value)

    def test_api_serialization_preserves_unrounded_macd_values(self) -> None:
        payload = EvaluatePayload(
            technical=TechnicalPayload(
                bar_interval="1d",
                macd_dif=1e-15,
                macd_dea=2e-15,
                macd_histogram=3e-16,
                macd_zero_axis="ABOVE",
                macd_data_ready=True,
                macd_data_reason="READY",
                macd_score=80.0,
            )
        )

        result = _evaluate_payload(payload)

        self.assertEqual(result["macd"]["dif"], 1e-15)
        self.assertEqual(result["macd"]["dea"], 2e-15)
        self.assertEqual(result["macd"]["histogram"], 3e-16)
        self.assertEqual(result["macd"]["effective_config"]["bar_interval"], "1d")


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
