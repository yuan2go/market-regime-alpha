from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.models import OrderIntent, PositionState, Signal
from market_regime_alpha.dividend_t.risk import RiskEngine, RiskLimits


class DividendTRiskTests(unittest.TestCase):
    def test_buy_order_can_use_all_cash_in_attack_mode_defaults(self) -> None:
        engine = RiskEngine()
        result = engine.validate_order(
            OrderIntent("601919.SH", "BUY", "t", Signal.BUY_T, 1.00, "test"),
            position=PositionState(symbol_position_pct=0.20, available_cash_pct=0.80, is_cycle_stock=True),
            base_position_limit_pct=1.00,
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.final_notional_pct, 0.80)
        self.assertTrue(result.warnings)

    def test_buy_order_keeps_configured_minimum_cash(self) -> None:
        engine = RiskEngine(RiskLimits(min_cash_pct=0.10))
        result = engine.validate_order(
            OrderIntent("600900.SH", "BUY", "t", Signal.BUY_T, 0.10, "test"),
            position=PositionState(symbol_position_pct=0.10, available_cash_pct=0.13, is_cycle_stock=False),
            base_position_limit_pct=0.80,
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.final_notional_pct, 0.03)

    def test_sell_order_rejects_when_no_available_shares(self) -> None:
        engine = RiskEngine()
        result = engine.validate_order(
            OrderIntent("601919.SH", "SELL", "t", Signal.SELL_T, 0.10, "test"),
            position=PositionState(symbol_position_pct=0.20, available_sell_pct=0.0),
            base_position_limit_pct=0.70,
        )

        self.assertFalse(result.allowed)
        self.assertIn("没有可卖仓位，可能受 T+1 或持仓不足限制。", result.violations)


if __name__ == "__main__":
    unittest.main()
