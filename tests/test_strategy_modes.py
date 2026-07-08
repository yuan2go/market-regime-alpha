from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.backtest import DividendTBacktestConfig  # noqa: E402
from market_regime_alpha.dividend_t.strategy_modes import apply_strategy_mode  # noqa: E402


class StrategyModeTests(unittest.TestCase):
    def test_defensive_mode_caps_active_position_and_disables_attack(self) -> None:
        config = apply_strategy_mode(DividendTBacktestConfig(), "defensive")

        self.assertEqual(config.strategy_mode, "defensive")
        self.assertFalse(config.enable_attack_state_machine)
        self.assertLessEqual(config.max_signal_position_pct, 0.45)
        self.assertLessEqual(config.kelly_fraction_scale, 0.45)
        self.assertGreaterEqual(config.min_buy_signal_strength, 72.0)

    def test_offensive_mode_keeps_full_attack_budget_available(self) -> None:
        config = apply_strategy_mode(DividendTBacktestConfig(max_signal_position_pct=0.80), "offensive")

        self.assertEqual(config.strategy_mode, "offensive")
        self.assertTrue(config.enable_attack_state_machine)
        self.assertEqual(config.max_signal_position_pct, 1.00)
        self.assertEqual(config.attack_full_position_pct, 1.00)
        self.assertLessEqual(config.min_buy_signal_strength, 62.0)

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            apply_strategy_mode(DividendTBacktestConfig(), "fast")

    def test_dynamic_mode_keeps_base_profile_for_runtime_switching(self) -> None:
        base = DividendTBacktestConfig(max_signal_position_pct=0.80)

        config = apply_strategy_mode(base, "dynamic")

        self.assertEqual(config.strategy_mode, "dynamic")
        self.assertEqual(config.max_signal_position_pct, 0.80)
        self.assertEqual(config.enable_attack_state_machine, base.enable_attack_state_machine)


if __name__ == "__main__":
    unittest.main()
