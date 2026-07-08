from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.models import FundamentalInputs, PositionState, RetreatInputs, Signal, TechnicalInputs, TrendState
from market_regime_alpha.dividend_t.strategy import DividendTStrategy


class DividendTStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = DividendTStrategy()
        self.good_fundamental = FundamentalInputs(78, 75, 72, 78, 70)

    def test_buy_t_signal_when_support_and_scores_are_strong(self) -> None:
        decision = self.strategy.evaluate(
            symbol="601919.SH",
            fundamental=self.good_fundamental,
            retreat=RetreatInputs(4.0, 3.8, 2.3, 2.2),
            technical=TechnicalInputs(
                82,
                78,
                78,
                80,
                trend_state=TrendState.RANGE,
                near_support=True,
                shrinking_pullback=True,
                intraday_reversal=True,
                sector_healthy=True,
            ),
            position=PositionState(symbol_position_pct=0.12, available_cash_pct=0.45, available_sell_pct=0.10),
        )

        self.assertEqual(decision.signal, Signal.BUY_T)
        self.assertIsNotNone(decision.order_intent)
        self.assertGreater(decision.score.total_score, 75)
        self.assertGreater(decision.score.C_score, 0)

    def test_buy3_can_trigger_without_near_support_when_other_gates_pass(self) -> None:
        decision = self.strategy.evaluate(
            symbol="601919.SH",
            fundamental=self.good_fundamental,
            retreat=RetreatInputs(4.2, 4.0, 2.4, 2.1),
            technical=TechnicalInputs(
                80,
                82,
                82,
                72,
                chan_score=84,
                trend_state=TrendState.BREAKOUT,
                near_support=False,
                shrinking_pullback=False,
                intraday_reversal=False,
                sector_healthy=True,
                chan_structure_type="breakout",
                chan_trend_direction="up",
                chan_buy_point_type="buy3",
                chan_pivot_low=10.2,
                chan_pivot_high=10.8,
                chan_invalid_price=10.75,
            ),
            position=PositionState(symbol_position_pct=0.12, available_cash_pct=0.45, available_sell_pct=0.10),
        )

        self.assertEqual(decision.signal, Signal.BUY_T)
        self.assertIn("buy3", " ".join(decision.reasons))

    def test_chan_sell_point_blocks_buy_and_stops_t(self) -> None:
        decision = self.strategy.evaluate(
            symbol="601919.SH",
            fundamental=self.good_fundamental,
            retreat=RetreatInputs(4.2, 4.0, 2.4, 2.1),
            technical=TechnicalInputs(
                82,
                78,
                78,
                80,
                chan_score=32,
                trend_state=TrendState.RANGE,
                near_support=True,
                shrinking_pullback=True,
                intraday_reversal=True,
                sector_healthy=True,
                chan_structure_type="breakdown",
                chan_sell_point_type="sell3",
                chan_divergence_type="top",
            ),
            position=PositionState(symbol_position_pct=0.20, t_position_pct=0.05, available_sell_pct=0.10),
        )

        self.assertEqual(decision.signal, Signal.STOP_T)
        self.assertIsNone(decision.order_intent)

    def test_sell_t_signal_when_pressure_area_gets_stalled(self) -> None:
        decision = self.strategy.evaluate(
            symbol="601919.SH",
            fundamental=self.good_fundamental,
            retreat=RetreatInputs(3.0, 3.2, 1.2, 4.3),
            technical=TechnicalInputs(
                55,
                45,
                70,
                50,
                trend_state=TrendState.EXHAUSTION,
                near_resistance=True,
                volume_stalling=True,
                sector_healthy=True,
            ),
            position=PositionState(symbol_position_pct=0.20, t_position_pct=0.04, available_sell_pct=0.12),
        )

        self.assertEqual(decision.signal, Signal.SELL_T)
        self.assertIsNotNone(decision.order_intent)

    def test_stop_t_when_trend_breaks(self) -> None:
        decision = self.strategy.evaluate(
            symbol="601919.SH",
            fundamental=self.good_fundamental,
            retreat=RetreatInputs(3.5, 3.5, 2.1, 2.5),
            technical=TechnicalInputs(
                50,
                50,
                35,
                45,
                trend_state=TrendState.DOWNTREND,
                sector_healthy=False,
            ),
            position=PositionState(symbol_position_pct=0.20),
        )

        self.assertEqual(decision.signal, Signal.STOP_T)
        self.assertIsNone(decision.order_intent)

    def test_clear_when_fundamental_fails(self) -> None:
        decision = self.strategy.evaluate(
            symbol="601919.SH",
            fundamental=FundamentalInputs(40, 45, 35, 45, 40),
            retreat=RetreatInputs(3.0, 3.0, 2.0, 3.0),
            technical=TechnicalInputs(70, 70, 70, 70),
            position=PositionState(symbol_position_pct=0.20, available_sell_pct=0.20),
        )

        self.assertEqual(decision.signal, Signal.CLEAR)
        self.assertIsNotNone(decision.order_intent)


if __name__ == "__main__":
    unittest.main()
