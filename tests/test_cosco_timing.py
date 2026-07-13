from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.cosco_profile import CoscoProfile
from market_regime_alpha.dividend_t.cosco_timing import CoscoTimingEngine, sample_cosco_timing
from market_regime_alpha.dividend_t.cosco_timing_types import apply_timing_macd_policy, manual_candidate
from market_regime_alpha.dividend_t.macd import MACDCross, MACDHistogramTrend, MACDZeroAxis
from market_regime_alpha.dividend_t.models import Signal
from market_regime_alpha.dividend_t.signal_intent import (
    EntryConfirmation,
    MACDPolicyConfig,
    MACDPolicyState,
    PrimarySetupCode,
)
from market_regime_alpha.dividend_t.tuishen_volume_price import estimate_volume_price_structure


def _bars_for_buy_t() -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-06-01 09:35")
    price = 14.50
    for index in range(50):
        if index < 18:
            price += 0.012
        elif index < 44:
            price -= 0.025
        else:
            price += 0.003
        volume = 900_000
        if index > 45:
            volume = 1_600_000
        rows.append(_bar(base, index, price, volume))
    return pd.DataFrame(rows)


def _bars_for_buy_t_with_20d_uptrend() -> pd.DataFrame:
    trend_closes = [13.55 + day * 0.035 for day in range(20)]
    return pd.concat([_daily_context_rows_from("2026-05-01 09:35", trend_closes), _bars_for_buy_t()], ignore_index=True)


def _bars_for_sell_t() -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-06-01 09:35")
    price = 13.40
    for index in range(80):
        if index < 65:
            price += 0.018
        elif index < 76:
            price += 0.004
        else:
            price -= 0.002
        volume = 900_000
        if index > 68:
            volume = 1_900_000
        rows.append(_bar(base, index, price, volume))
    return pd.DataFrame(rows)


def _bars_for_sell_t_with_daily_strength() -> pd.DataFrame:
    return pd.concat([_daily_context_rows([12.20, 12.45, 12.72, 13.05]), _bars_for_sell_t()], ignore_index=True)


def _bars_for_strong_uptrend_near_resistance() -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-06-01 09:35")
    price = 13.40
    for index in range(90):
        price += 0.012
        rows.append(_bar(base, index, price, 900_000 + (index % 6) * 10_000))
    return pd.concat([_daily_context_rows([12.20, 12.45, 12.72, 13.05]), pd.DataFrame(rows)], ignore_index=True)


def _bars_for_breakout_buy() -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-06-01 09:35")
    price = 14.22
    for index in range(42):
        if index < 10:
            price += 0.006
        elif index < 22:
            price += 0.014
        else:
            price += 0.010
        volume = 1_550_000 if index >= 12 else 1_150_000
        rows.append(_bar(base, index, price, volume))
    return pd.concat([_daily_context_rows([13.82, 13.95, 14.05, 14.18, 14.24]), pd.DataFrame(rows)], ignore_index=True)


def _bars_for_pre_breakout_watch() -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-06-01 09:35")
    price = 14.18
    for index in range(70):
        if index < 20:
            price += 0.0015
        elif index < 45:
            price -= 0.0007
        else:
            price += 0.0040
        rows.append(_bar(base, index, price, 760_000))
    return pd.concat([_daily_context_rows([13.88, 14.02, 14.12, 14.24, 14.30]), pd.DataFrame(rows)], ignore_index=True)


def _bars_for_high_volume_stall() -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-06-01 09:35")
    price = 14.20
    for index in range(64):
        if index < 45:
            price += 0.010
            volume = 820_000
        elif index < 58:
            price += 0.001
            volume = 2_200_000
        else:
            price -= 0.002
            volume = 2_450_000
        rows.append(_bar(base, index, price, volume))
    return pd.concat([_daily_context_rows([13.72, 13.85, 13.96, 14.08]), pd.DataFrame(rows)], ignore_index=True)


def _bars_for_buy_t_with_daily_weakness() -> pd.DataFrame:
    return pd.concat([_daily_context_rows([16.20, 15.78, 15.22, 14.65]), _bars_for_buy_t()], ignore_index=True)


def _daily_context_rows(closes: list[float]) -> pd.DataFrame:
    rows = []
    start = pd.Timestamp("2026-05-26 09:35")
    for day_index, close in enumerate(closes):
        base = start + pd.Timedelta(days=day_index)
        for bar_index in range(4):
            price = close + (bar_index - 3) * 0.004
            rows.append(_bar(base, bar_index, price, 780_000))
    return pd.DataFrame(rows)


def _daily_context_rows_from(start: str, closes: list[float]) -> pd.DataFrame:
    rows = []
    start_time = pd.Timestamp(start)
    for day_index, close in enumerate(closes):
        base = start_time + pd.Timedelta(days=day_index)
        for bar_index in range(4):
            price = close + (bar_index - 3) * 0.004
            rows.append(_bar(base, bar_index, price, 780_000))
    return pd.DataFrame(rows)


def _bar(base: pd.Timestamp, index: int, price: float, volume: float) -> dict[str, object]:
    return {
        "symbol": "601919.SH",
        "timestamp": base + pd.Timedelta(minutes=5 * index),
        "open": round(price - 0.015, 3),
        "high": round(price + 0.035, 3),
        "low": round(price - 0.035, 3),
        "close": round(price, 3),
        "volume": float(volume),
        "amount": float(volume * price),
        "source_freq": "5min",
    }


class CoscoTimingTests(unittest.TestCase):
    def test_timing_policy_records_multiplier_but_does_not_apply_sizing(self) -> None:
        candidate = manual_candidate(
            "BUY_T_TIMING",
            Signal.BUY_T,
            PrimarySetupCode.PULLBACK_LOW_BUY,
            decision_bar_time="2026-07-13 10:05:00",
            entry_confirmations=frozenset({EntryConfirmation.SUPPORT_HOLD}),
        )
        state = MACDPolicyState(
            True,
            MACDCross.BEARISH,
            MACDZeroAxis.BELOW,
            -0.2,
            MACDHistogramTrend.EXPANDING,
        )

        action, decision = apply_timing_macd_policy(
            candidate,
            quality_filtered_action="BUY_T_TIMING",
            macd=state,
            config=MACDPolicyConfig(conflict_gate_enabled=True),
        )

        self.assertEqual(action, "BUY_T_TIMING")
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.macd_sizing_multiplier, 0.5)
        self.assertTrue(decision.trace.macd_policy_applied)
        self.assertFalse(decision.trace.macd_sizing_applied)
        self.assertIsNone(decision.trace.macd_sizing_owner)

    def test_timing_policy_does_not_reopen_quality_filtered_candidate(self) -> None:
        candidate = manual_candidate(
            "BUY_T_TIMING",
            Signal.BUY_T,
            PrimarySetupCode.PULLBACK_LOW_BUY,
            decision_bar_time="2026-07-13 10:05:00",
            entry_confirmations=frozenset({EntryConfirmation.SUPPORT_HOLD}),
        )

        action, decision = apply_timing_macd_policy(
            candidate,
            quality_filtered_action="WAIT_CONFIRMATION",
            macd=MACDPolicyState.neutral(),
            config=MACDPolicyConfig(conflict_gate_enabled=True),
        )

        self.assertEqual(action, "WAIT_CONFIRMATION")
        self.assertIsNone(decision)

    def test_high_volume_stall_pullback_is_downgraded_from_real_buy_point(self) -> None:
        snapshot = CoscoTimingEngine().evaluate(_bars_for_buy_t_with_20d_uptrend())

        self.assertEqual(snapshot.action, "WAIT_CONFIRMATION")
        self.assertEqual(snapshot.multi_period_trend.trend_5_20_state, "PULLBACK_IN_UPTREND")
        self.assertTrue(snapshot.manual_only)
        self.assertFalse(snapshot.is_realtime)
        self.assertEqual(snapshot.data_source, "input_5min_bars")
        self.assertGreaterEqual(snapshot.data_age_minutes, 0)
        self.assertGreater(snapshot.force.force_ratio, 1.0)
        self.assertEqual(snapshot.intraday_context.state, "SUPPORT_CONFIRMED")
        self.assertEqual(snapshot.volume_price_structure.state, "HIGH_VOLUME_STALL")
        self.assertGreater(snapshot.signal_strength.score, 0)
        self.assertGreaterEqual(snapshot.signal_strength.kelly_fraction, 0)
        self.assertGreater(snapshot.trend_probability.up_1d, 0.50)
        self.assertEqual(snapshot.signal_strength.label, "弱")
        self.assertIsNone(snapshot.prices.buy_reference_price)
        self.assertIsNone(snapshot.prices.sell_reference_price)
        self.assertTrue(any("非支撑/回踩型买点" in item for item in snapshot.reasons))

    def test_one_day_context_does_not_emit_real_buy_point(self) -> None:
        snapshot = CoscoTimingEngine().evaluate(_bars_for_buy_t())

        self.assertEqual(snapshot.action, "WAIT_CONFIRMATION")
        self.assertEqual(snapshot.multi_period_trend.trend_5_20_state, "INSUFFICIENT")
        self.assertIsNone(snapshot.prices.buy_reference_price)
        self.assertTrue(any("5-20 日趋势" in item for item in snapshot.reasons))

    def test_unconfirmed_sell_timing_with_insufficient_daily_context_is_downgraded(self) -> None:
        snapshot = CoscoTimingEngine().evaluate(_bars_for_sell_t())

        self.assertEqual(snapshot.action, "WAIT_CONFIRMATION")
        self.assertTrue(snapshot.manual_only)
        self.assertLess(snapshot.force.force_ratio, 1.0)
        self.assertIsNone(snapshot.prices.sell_reference_price)
        self.assertIsNone(snapshot.prices.buy_back_reference_price)
        self.assertEqual(snapshot.daily_context.state, "INSUFFICIENT")
        self.assertTrue(any("卖点质量过滤" in item for item in snapshot.warnings))

    def test_unconfirmed_sell_timing_when_daily_context_is_strong_is_downgraded(self) -> None:
        snapshot = CoscoTimingEngine().evaluate(_bars_for_sell_t_with_daily_strength())

        self.assertEqual(snapshot.action, "WAIT_CONFIRMATION")
        self.assertEqual(snapshot.daily_context.state, "STRONG")
        self.assertIsNone(snapshot.prices.buy_back_reference_price)
        self.assertTrue(any("卖点质量过滤" in item for item in snapshot.warnings))

    def test_strong_trend_protection_blocks_premature_reverse_t(self) -> None:
        snapshot = CoscoTimingEngine().evaluate(_bars_for_strong_uptrend_near_resistance())

        self.assertEqual(snapshot.action, "WAIT_STRONG_TREND")
        self.assertEqual(snapshot.trend_state, "UPTREND")
        self.assertEqual(snapshot.daily_context.state, "STRONG")
        self.assertEqual(snapshot.market_regime.state, "STRONG_TREND")
        self.assertEqual(snapshot.market_regime.base_position_target_pct, 0.10)
        self.assertEqual(snapshot.market_regime.t_trade_limit_pct, 0.80)
        self.assertEqual(snapshot.market_regime.active_position_cap_pct, 0.70)
        self.assertEqual(snapshot.market_regime.max_total_position_pct, 0.80)
        self.assertIsNone(snapshot.prices.sell_reference_price)
        self.assertTrue(any("强趋势保护" in item for item in snapshot.warnings))

    def test_breakout_signal_is_downgraded_to_watch_for_5d_hit_rate(self) -> None:
        snapshot = CoscoTimingEngine().evaluate(_bars_for_breakout_buy())

        self.assertEqual(snapshot.action, "WATCH_BREAKOUT_NEXT_DAY")
        self.assertEqual(snapshot.buy_point_subtype, "breakout_watch")
        self.assertEqual(snapshot.breakout_setup.state, "BREAKOUT_CONFIRMED")
        self.assertTrue(snapshot.breakout_setup.breakout_confirmed)
        self.assertGreaterEqual(snapshot.breakout_setup.score, 68.0)
        self.assertGreaterEqual(snapshot.volume_price_structure.volume_breakout_score, 60.0)
        self.assertIn("volume_price_structure", snapshot.to_dict())
        self.assertIsNotNone(snapshot.prices.buy_reference_price)
        self.assertIsNotNone(snapshot.prices.stop_price)
        self.assertIsNone(snapshot.prices.sell_reference_price)
        self.assertLess(snapshot.signal_strength.estimated_win_rate, 0.50)
        self.assertEqual(snapshot.decision_trace.primary_setup_code, "breakout_confirmed")
        self.assertEqual(snapshot.decision_trace.candidate_signal_intent, "TREND_FOLLOWING")
        self.assertEqual(snapshot.decision_trace.raw_candidate_action, "BREAKOUT_BUY_TIMING")
        self.assertEqual(snapshot.decision_trace.quality_filtered_action, "WATCH_BREAKOUT_NEXT_DAY")
        self.assertEqual(snapshot.decision_trace.macd_filtered_action, "WATCH_BREAKOUT_NEXT_DAY")
        self.assertEqual(snapshot.decision_trace.final_action, "WATCH_BREAKOUT_NEXT_DAY")
        self.assertFalse(snapshot.decision_trace.macd_policy_applied)

    def test_volume_price_structure_flags_high_volume_stall(self) -> None:
        structure = estimate_volume_price_structure(_bars_for_high_volume_stall())

        self.assertGreaterEqual(structure.high_volume_stall_score, 60.0)
        self.assertIn(structure.state, {"HIGH_VOLUME_STALL", "NEUTRAL", "VWAP_ACCUMULATION"})
        self.assertGreater(structure.volume_expansion_ratio, 1.0)

    def test_pre_breakout_watch_does_not_buy_before_confirmation(self) -> None:
        snapshot = CoscoTimingEngine().evaluate(_bars_for_pre_breakout_watch())

        self.assertEqual(snapshot.action, "WATCH_BREAKOUT_NEXT_DAY")
        self.assertEqual(snapshot.breakout_setup.state, "PRE_BREAKOUT_WATCH")
        self.assertTrue(snapshot.breakout_setup.pre_breakout_watch)
        self.assertIsNotNone(snapshot.prices.buy_reference_price)
        self.assertTrue(any("不是买入信号" in item for item in snapshot.warnings))

    def test_real_money_flow_columns_are_used_before_ohlcv_proxy(self) -> None:
        bars = _bars_for_breakout_buy().copy()
        bars["main_net_inflow"] = bars["amount"] * 0.08

        snapshot = CoscoTimingEngine().evaluate(bars)

        self.assertEqual(snapshot.capital_flow.source_type, "REAL_MONEY_FLOW")
        self.assertGreaterEqual(snapshot.capital_flow.confidence, 0.80)
        self.assertGreater(snapshot.capital_flow.confirmation_score, 50.0)
        self.assertTrue(any("真实资金流" in item for item in snapshot.capital_flow.reasons))

    def test_weak_daily_context_blocks_intraday_buy_timing(self) -> None:
        snapshot = CoscoTimingEngine().evaluate(_bars_for_buy_t_with_daily_weakness())

        self.assertEqual(snapshot.action, "WAIT_CONFIRMATION")
        self.assertEqual(snapshot.daily_context.state, "WEAK")
        self.assertTrue(snapshot.intraday_context.support_confirmed)
        self.assertIsNone(snapshot.prices.buy_reference_price)
        self.assertTrue(any("WAIT_DAILY_WEAK 降级为观察" in item for item in snapshot.warnings))

    def test_low_fundamental_profile_blocks_low_buy_timing(self) -> None:
        weak_profile = CoscoProfile(base_fundamental_score=52.0, dividend_sustainability_score=50.0)
        snapshot = CoscoTimingEngine(profile=weak_profile).evaluate(_bars_for_buy_t())

        self.assertEqual(snapshot.action, "WAIT_CONFIRMATION")
        self.assertLess(snapshot.daily_context.fundamental_score, 55.0)
        self.assertEqual(snapshot.daily_context.position_multiplier, 0.0)
        self.assertTrue(any("WAIT_DAILY_WEAK 降级为观察" in item for item in snapshot.warnings))

    def test_freshness_gate_blocks_stale_sell_signal(self) -> None:
        snapshot = CoscoTimingEngine().evaluate(
            _bars_for_sell_t(),
            require_fresh=True,
            freshness_limit_minutes=10,
            generated_at=datetime(2026, 6, 1, 16, 30),
        )

        self.assertEqual(snapshot.action, "WAIT_STALE_DATA")
        self.assertFalse(snapshot.data_fresh)
        self.assertEqual(snapshot.freshness_status, "stale")
        self.assertTrue(snapshot.signal_blocked)
        self.assertEqual(snapshot.confidence, 0.0)
        self.assertIsNone(snapshot.prices.sell_reference_price)
        self.assertTrue(any("数据已过期" in item for item in snapshot.reasons))
        self.assertEqual(snapshot.decision_trace.candidate_signal, "SELL_T")
        self.assertEqual(snapshot.decision_trace.primary_setup_code, "pressure_sell_t")
        self.assertEqual(snapshot.decision_trace.candidate_signal_intent, "MEAN_REVERSION_T")
        self.assertEqual(snapshot.decision_trace.raw_candidate_action, "SELL_T_TIMING")
        self.assertEqual(snapshot.decision_trace.quality_filtered_action, "WAIT_CONFIRMATION")
        self.assertEqual(snapshot.decision_trace.freshness_filtered_action, "WAIT_STALE_DATA")
        self.assertEqual(snapshot.decision_trace.final_action, "WAIT_STALE_DATA")
        self.assertEqual(snapshot.decision_trace.decision_bar_time, snapshot.timestamp)
        self.assertEqual(snapshot.decision_trace.confirmation_bar_time, snapshot.timestamp)

    def test_freshness_gate_allows_fresh_evaluation_before_sell_quality_filter(self) -> None:
        bars = _bars_for_sell_t()
        last_time = pd.to_datetime(bars.iloc[-1]["timestamp"]).to_pydatetime()

        snapshot = CoscoTimingEngine().evaluate(
            bars,
            require_fresh=True,
            freshness_limit_minutes=10,
            generated_at=last_time + timedelta(minutes=5),
        )

        self.assertEqual(snapshot.action, "WAIT_CONFIRMATION")
        self.assertTrue(snapshot.data_fresh)
        self.assertFalse(snapshot.signal_blocked)
        self.assertTrue(any("卖点质量过滤" in item for item in snapshot.warnings))

    def test_sample_snapshot_is_serializable(self) -> None:
        data = sample_cosco_timing().to_dict()

        self.assertEqual(data["symbol"], "601919.SH")
        self.assertEqual(data["data_source"], "sample_static_5min")
        self.assertFalse(data["is_realtime"])
        self.assertIn("generated_at", data)
        self.assertIn("data_age_minutes", data)
        self.assertIn("data_fresh", data)
        self.assertIn("freshness_status", data)
        self.assertIn("signal_blocked", data)
        self.assertIn("daily_context", data)
        self.assertIn("intraday_context", data)
        self.assertIn("market_regime", data)
        self.assertIn("multi_period_trend", data)
        self.assertIn("capital_flow", data)
        self.assertIn("trend_probability", data)
        self.assertIn("breakout_setup", data)
        self.assertIn("up_1d", data["trend_probability"])
        self.assertIn("state", data["breakout_setup"])
        self.assertIn("base_position_target_pct", data["market_regime"])
        self.assertIn("active_position_cap_pct", data["market_regime"])
        self.assertIn("max_total_position_pct", data["market_regime"])
        self.assertIn("force_ratio", data["force"])
        self.assertIn("kelly_fraction", data["signal_strength"])
        self.assertIn("buy_reference_price", data["prices"])
        self.assertTrue(any("样例数据" in item for item in data["warnings"]))


if __name__ == "__main__":
    unittest.main()
