from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.market_environment import (  # noqa: E402
    MARKET_NEUTRAL,
    MARKET_RISK_OFF,
    MARKET_RISK_ON,
    MarketEnvironmentPoint,
    build_market_environment_filter,
    market_environment_point_with_model_state,
)


class MarketEnvironmentTests(unittest.TestCase):
    def test_builder_classifies_sustained_uptrend_as_risk_on(self) -> None:
        market_filter = build_market_environment_filter(_market_frame(step=0.8), name="up")

        self.assertEqual(market_filter.points[-1].state, MARKET_RISK_ON)
        self.assertTrue(market_filter.points[-1].allow_new_buy)
        self.assertEqual(market_filter.points[-1].max_total_position_pct, 1.00)

    def test_builder_classifies_sustained_downtrend_as_risk_off(self) -> None:
        market_filter = build_market_environment_filter(_market_frame(step=-1.2), name="down")

        self.assertEqual(market_filter.points[-1].state, MARKET_RISK_OFF)
        self.assertFalse(market_filter.points[-1].allow_new_buy)
        self.assertEqual(market_filter.points[-1].max_total_position_pct, 0.10)

    def test_composite_builder_requires_broad_participation_for_risk_on(self) -> None:
        market_filter = build_market_environment_filter(
            _composite_market_frame({"000001.SH": 0.030, "000002.SH": -0.002, "000003.SH": -0.002, "000004.SH": -0.002, "000005.SH": -0.002, "000006.SH": -0.002}),
            name="narrow",
        )

        self.assertNotEqual(market_filter.points[-1].state, MARKET_RISK_ON)
        self.assertLess(market_filter.points[-1].breadth_score, 42.0)

    def test_composite_builder_classifies_broad_uptrend_as_risk_on(self) -> None:
        market_filter = build_market_environment_filter(
            _composite_market_frame(
                {
                    "000001.SH": 0.004,
                    "000002.SH": 0.005,
                    "000003.SH": 0.004,
                    "000004.SH": 0.006,
                    "000005.SH": 0.003,
                    "000006.SH": 0.004,
                }
            ),
            name="broad",
        )

        point = market_filter.points[-1]
        self.assertEqual(point.state, MARKET_RISK_ON)
        self.assertGreaterEqual(point.breadth_score, 80.0)
        self.assertGreaterEqual(point.industry_diffusion_score, 80.0)
        self.assertEqual(point.max_total_position_pct, 1.00)

    def test_composite_builder_uses_model_self_state_as_risk_on_gate(self) -> None:
        market_filter = build_market_environment_filter(
            _composite_market_frame(
                {
                    "000001.SH": 0.004,
                    "000002.SH": 0.005,
                    "000003.SH": 0.004,
                    "000004.SH": 0.006,
                    "000005.SH": 0.003,
                    "000006.SH": 0.004,
                },
                model_holding_win_rate=0.20,
                model_holding_profit_spread=0.25,
                model_new_buy_success_rate=0.20,
            ),
            name="weak-model-state",
        )

        point = market_filter.points[-1]
        self.assertNotEqual(point.state, MARKET_RISK_ON)
        self.assertLess(point.model_state_score, 45.0)

    def test_model_self_state_overlay_can_downgrade_existing_risk_on_point(self) -> None:
        market_filter = build_market_environment_filter(
            _composite_market_frame(
                {
                    "000001.SH": 0.004,
                    "000002.SH": 0.005,
                    "000003.SH": 0.004,
                    "000004.SH": 0.006,
                    "000005.SH": 0.003,
                    "000006.SH": 0.004,
                }
            ),
            name="broad",
        )
        original = market_filter.points[-1]

        downgraded = market_environment_point_with_model_state(
            original,
            model_holding_win_rate=0.10,
            model_holding_profit_spread=0.10,
            model_new_buy_success_rate=0.10,
        )

        self.assertEqual(original.state, MARKET_RISK_ON)
        self.assertNotEqual(downgraded.state, MARKET_RISK_ON)
        self.assertLess(downgraded.model_state_score, 45.0)

    def test_model_profit_diffusion_can_upgrade_neutral_market_to_risk_on(self) -> None:
        original = MarketEnvironmentPoint(
            trade_date=pd.Timestamp("2026-06-26").date(),
            state=MARKET_NEUTRAL,
            score=56.0,
            max_total_position_pct=0.70,
            allow_new_buy=True,
            trend_score=56.0,
            breadth_score=48.0,
            amount_score=46.0,
            limit_structure_score=48.0,
            industry_diffusion_score=48.0,
            limit_up_ratio=0.010,
            limit_down_ratio=0.004,
            model_state_score=50.0,
            model_holding_win_rate=0.50,
            model_holding_profit_spread=0.50,
            model_new_buy_success_rate=0.50,
        )

        upgraded = market_environment_point_with_model_state(
            original,
            model_holding_win_rate=0.64,
            model_holding_profit_spread=0.72,
            model_new_buy_success_rate=0.58,
        )

        self.assertEqual(upgraded.state, MARKET_RISK_ON)
        self.assertGreaterEqual(upgraded.max_total_position_pct, 0.95)
        self.assertGreaterEqual(upgraded.model_state_score, 60.0)


def _market_frame(*, step: float):
    dates = pd.bdate_range("2026-01-01", periods=80)
    return pd.DataFrame(
        {
            "timestamp": dates + pd.Timedelta(hours=15),
            "close": [100.0 + index * step for index in range(len(dates))],
        }
    )


def _composite_market_frame(
    daily_steps: dict[str, float],
    *,
    model_holding_win_rate: float = 0.55,
    model_holding_profit_spread: float = 0.55,
    model_new_buy_success_rate: float = 0.55,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    dates = pd.bdate_range("2026-01-01", periods=80)
    industries = ["半导体", "银行", "新能源"]
    for symbol_index, (symbol, step) in enumerate(daily_steps.items()):
        industry = industries[symbol_index % len(industries)]
        price = 100.0 + symbol_index
        for index, trade_date in enumerate(dates):
            price *= 1.0 + step
            amount = 1_000_000.0 * (1.0 + index / len(dates) * 0.30)
            rows.append(
                {
                    "timestamp": trade_date + pd.Timedelta(hours=15),
                    "symbol": symbol,
                    "industry": industry,
                    "close": round(price, 4),
                    "amount": amount,
                    "model_holding_win_rate": model_holding_win_rate,
                    "model_holding_profit_spread": model_holding_profit_spread,
                    "model_new_buy_success_rate": model_new_buy_success_rate,
                }
            )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    unittest.main()
