from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.backtest import (  # noqa: E402
    ATTACK_BETA_HOLD,
    ATTACK_CONFIRMED,
    ATTACK_FULL,
    ATTACK_INACTIVE,
    ATTACK_WATCH,
    BacktestSignal,
    DEFAULT_SIGNAL_HISTORY_BARS,
    DividendTBacktestConfig,
    TradeExecutionConstraints,
    VOLUME_PRICE_DISTRIBUTION,
    VOLUME_PRICE_ROTATION,
    build_sample_cosco_backtest_bars,
    format_cosco_backtest_report,
    run_cosco_dividend_t_backtest,
    _apply_market_environment_filter,
    _apply_backtest_macd_sizing,
    _apply_risk_on_continuation_add,
    _beta_hold_blocks_soft_exit,
    _buy_t_failure_cooldown_blocks_signal,
    _buy_point_quality_score,
    _candidate_entry_confirm_signal,
    _effective_signal_config,
    _execute_action,
    _high_quality_breakout_add_signal,
    _main_rise_buy_quality_score,
    _next_attack_state,
    _next_core_position_floor_pct,
    _offensive_exit_sell_fraction,
    _pretrade_volume_price_window_features,
    _risk_on_core_floor_target_pct,
    _risk_on_secondary_add_confirmation_signal,
    _risk_on_target_add_confirmation_signal,
    _risk_on_position_target_pct,
    _sell_point_continuation_hold_signal,
    _signal_target_position_pct,
    _volume_price_distribution_state,
    validate_execution_after_signal,
)
from market_regime_alpha.dividend_t.market_environment import (  # noqa: E402
    MARKET_NEUTRAL,
    MARKET_RISK_OFF,
    MARKET_RISK_ON,
    MarketEnvironmentFilter,
    MarketEnvironmentPoint,
    build_market_environment_filter,
)
from market_regime_alpha.dividend_t.position_sizing import PositionBudget  # noqa: E402
from market_regime_alpha.dividend_t.signal_intent import CandidateContractError  # noqa: E402


class DividendTBacktestTests(unittest.TestCase):
    def test_backtest_is_the_single_macd_sizing_owner(self) -> None:
        signal = replace(
            _risk_on_confirmed_signal(action="BUY_T_TIMING"),
            candidate_signal="BUY_T",
            candidate_setup_code="pullback_low_buy",
            primary_setup_code="pullback_low_buy",
            signal_intent="MEAN_REVERSION_T",
            entry_confirmations=("SUPPORT_HOLD",),
            risk_enforcement="NONE",
            macd_sizing_multiplier=0.5,
            sizing_adjustment_source="MACD_MEAN_REVERSION",
        )

        sized = _apply_backtest_macd_sizing(signal, original_trade_pct=0.20, minimum_trade_pct=0.01)

        self.assertEqual(sized.adjusted_suggested_trade_pct, 0.10)
        self.assertTrue(sized.trace.macd_sizing_applied)
        self.assertEqual(sized.trace.macd_sizing_owner, "dividend_t_backtest_execution")
        self.assertEqual(sized.trace.original_suggested_trade_pct, 0.20)
        self.assertEqual(sized.trace.adjusted_suggested_trade_pct, 0.10)

    def test_backtest_rejects_duplicate_macd_sizing(self) -> None:
        signal = replace(
            _risk_on_confirmed_signal(action="BUY_T_TIMING"),
            candidate_signal="BUY_T",
            candidate_setup_code="pullback_low_buy",
            primary_setup_code="pullback_low_buy",
            signal_intent="MEAN_REVERSION_T",
            entry_confirmations=("SUPPORT_HOLD",),
            risk_enforcement="NONE",
            macd_sizing_multiplier=0.5,
            macd_sizing_applied=True,
            macd_sizing_owner="unexpected_prior_owner",
        )

        with self.assertRaisesRegex(CandidateContractError, "DUPLICATE_SIZING_ADJUSTMENT"):
            _apply_backtest_macd_sizing(signal, original_trade_pct=0.20, minimum_trade_pct=0.01)

    def test_hard_risk_reduction_never_consumes_macd_multiplier(self) -> None:
        signal = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            candidate_signal="STOP_T",
            candidate_setup_code="stop_t",
            primary_setup_code="stop_t",
            signal_intent="RISK_REDUCTION",
            risk_enforcement="HARD",
            macd_sizing_multiplier=0.0,
        )

        sized = _apply_backtest_macd_sizing(signal, original_trade_pct=0.20, minimum_trade_pct=0.01)

        self.assertEqual(sized.final_signal.value, "STOP_T")
        self.assertEqual(sized.adjusted_suggested_trade_pct, 0.20)
        self.assertFalse(sized.trace.macd_sizing_applied)
        self.assertIsNone(sized.trace.macd_sizing_owner)

    def test_zero_macd_size_becomes_hold_before_order(self) -> None:
        signal = replace(
            _risk_on_confirmed_signal(action="BUY_T_TIMING"),
            candidate_signal="BUY_T",
            candidate_setup_code="pullback_low_buy",
            primary_setup_code="pullback_low_buy",
            signal_intent="MEAN_REVERSION_T",
            entry_confirmations=("SUPPORT_HOLD",),
            risk_enforcement="NONE",
            macd_sizing_multiplier=0.0,
            sizing_adjustment_source="MACD_MEAN_REVERSION",
        )

        sized = _apply_backtest_macd_sizing(signal, original_trade_pct=0.20, minimum_trade_pct=0.0)

        self.assertEqual(sized.final_signal.value, "HOLD")
        self.assertEqual(sized.adjusted_suggested_trade_pct, 0.0)
        self.assertEqual(sized.trace.downgrade_source, "MACD_SIZING_TO_ZERO")

    def test_execution_persists_single_macd_sizing_application(self) -> None:
        signal = replace(
            _risk_on_confirmed_signal(action="BUY_T_TIMING"),
            candidate_signal="BUY_T",
            candidate_setup_code="pullback_low_buy",
            primary_setup_code="pullback_low_buy",
            signal_intent="MEAN_REVERSION_T",
            entry_confirmations=("SUPPORT_HOLD",),
            risk_enforcement="NONE",
            macd_sizing_multiplier=0.5,
            sizing_adjustment_source="MACD_MEAN_REVERSION",
        )
        config = DividendTBacktestConfig(
            initial_base_position_pct=0.10,
            min_t_trade_pct=0.01,
            enable_a_share_constraints=False,
        )

        state = _execute_action(
            action="BUY_T_TIMING",
            execution={"timestamp": "2026-07-13 10:10:00", "open": 10.0, "close": 10.0, "low": 9.9},
            signal=signal,
            equity_before=100_000.0,
            cash=90_000.0,
            base_shares=1_000,
            base_locked_shares=0,
            t_shares=0,
            t_locked_shares=0,
            t_cost_basis=0.0,
            breakout_t_shares=0,
            breakout_t_locked_shares=0,
            breakout_t_cost_basis=0.0,
            pending_buyback_shares=0,
            pending_reverse_proceeds=0.0,
            pending_buyback_target_price=None,
            attack_state=ATTACK_INACTIVE,
            active_peak_profit_pct=0.0,
            constraints=TradeExecutionConstraints(),
            config=config,
        )

        trade = state["trade"]
        self.assertIsNotNone(trade)
        self.assertTrue(trade.macd_sizing_applied)
        self.assertEqual(trade.macd_sizing_owner, "dividend_t_backtest_execution")
        self.assertEqual(trade.macd_sizing_multiplier, 0.5)
        self.assertAlmostEqual(trade.adjusted_suggested_trade_pct, trade.original_suggested_trade_pct * 0.5)

    def test_execution_timestamp_must_be_after_signal_bar_close(self) -> None:
        validate_execution_after_signal("2026-07-13 10:05:00", "2026-07-13 10:10:00")
        with self.assertRaisesRegex(ValueError, "EXECUTION_NOT_AFTER_SIGNAL_BAR"):
            validate_execution_after_signal("2026-07-13 10:05:00", "2026-07-13 10:05:00")

    def test_backtest_signal_copies_candidate_identity_without_reclassification(self) -> None:
        snapshot = SimpleNamespace(
            timestamp="2026-07-13 10:05:00",
            action="WAIT_CONFIRMATION",
            daily_context=SimpleNamespace(
                state="STRONG",
                position_multiplier=1.0,
                fundamental_score=70.0,
                base_position_limit_pct=0.5,
            ),
            intraday_context=SimpleNamespace(state="SUPPORT_CONFIRMED"),
            prices=SimpleNamespace(
                buy_reference_price=14.0,
                sell_reference_price=None,
                buy_back_reference_price=None,
                stop_price=13.5,
            ),
            decision_trace=SimpleNamespace(
                candidate_signal="BUY_T",
                candidate_setup_code="pullback_low_buy",
                primary_setup_code="pullback_low_buy",
                candidate_signal_intent="MEAN_REVERSION_T",
                entry_confirmations=("SUPPORT_HOLD",),
                exit_confirmations=("NONE",),
                raw_candidate_action="BUY_T_TIMING",
                quality_filtered_action="WAIT_CONFIRMATION",
                macd_filtered_action="WAIT_CONFIRMATION",
                freshness_filtered_action="WAIT_CONFIRMATION",
                final_action="WAIT_CONFIRMATION",
            ),
            macd_diagnostics=SimpleNamespace(
                technical_score_without_macd=72.0,
                technical_score_with_macd=76.2,
                candidate_without_macd_score=SimpleNamespace(candidate_signal=None),
                candidate_with_macd_score=SimpleNamespace(candidate_signal="BUY_T"),
                macd_score_changed_candidate=True,
                macd_policy_changed_candidate=False,
            ),
        )

        signal = BacktestSignal.from_snapshot(snapshot)

        self.assertEqual(signal.primary_setup_code, "pullback_low_buy")
        self.assertEqual(signal.signal_intent, "MEAN_REVERSION_T")
        self.assertEqual(signal.raw_candidate_action, "BUY_T_TIMING")
        self.assertEqual(signal.final_action, "WAIT_CONFIRMATION")
        self.assertEqual(signal.technical_score_without_macd, 72.0)
        self.assertEqual(signal.technical_score_with_macd, 76.2)
        self.assertTrue(signal.macd_score_changed_candidate)
        self.assertFalse(signal.macd_policy_changed_candidate)

    def test_default_signal_history_covers_twenty_trading_days(self) -> None:
        self.assertEqual(DEFAULT_SIGNAL_HISTORY_BARS, 48 * 20)
        self.assertEqual(DividendTBacktestConfig().max_history_bars, DEFAULT_SIGNAL_HISTORY_BARS)

    def test_sample_backtest_runs_end_to_end(self) -> None:
        bars = _short_sample()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(initial_cash=100_000, min_lookback_bars=30),
        )

        self.assertEqual(result.symbol, "601919.SH")
        self.assertEqual(result.rows, len(bars))
        self.assertGreater(result.final_equity, 0)
        self.assertGreater(len(result.equity_curve), 0)
        self.assertIn("WAIT_CONFIRMATION", result.gate_counts)
        self.assertLessEqual(result.config.t_trade_pct, 1.0)

    def test_report_contains_time_scale_gate_summary(self) -> None:
        result = run_cosco_dividend_t_backtest(
            _short_sample(),
            config=DividendTBacktestConfig(min_lookback_bars=30),
        )

        report = format_cosco_backtest_report(result)

        self.assertIn("时间尺度门控", report)
        self.assertIn("WAIT_DAILY_WEAK", report)
        self.assertIn("WAIT_STRONG_TREND", report)
        self.assertIn("上一根 5 分钟 K 线生成信号", report)

    def test_config_rejects_invalid_t_position(self) -> None:
        with self.assertRaises(ValueError):
            run_cosco_dividend_t_backtest(
                build_sample_cosco_backtest_bars(),
                config=DividendTBacktestConfig(t_trade_pct=1.05),
            )

    def test_position_budget_names_base_active_and_total_separately(self) -> None:
        budget = PositionBudget.from_total_cap(base_target_pct=0.10, max_total_position_pct=0.80)

        self.assertEqual(budget.base_target_pct, 0.10)
        self.assertEqual(budget.active_position_cap_pct, 0.70)
        self.assertEqual(budget.max_total_position_pct, 0.80)
        self.assertEqual(budget.effective_total_cap_pct, 0.80)

    def test_signal_cache_reuses_timing_scores_without_changing_result(self) -> None:
        bars = build_sample_cosco_backtest_bars()
        with tempfile.TemporaryDirectory() as directory:
            config = DividendTBacktestConfig(
                initial_cash=100_000,
                min_lookback_bars=30,
                signal_step_bars=6,
                signal_cache_dir=Path(directory),
            )

            first = run_cosco_dividend_t_backtest(bars, config=config)
            second = run_cosco_dividend_t_backtest(bars, config=config)

        self.assertGreater(first.cache_misses, 0)
        self.assertEqual(first.cache_hits, 0)
        self.assertGreater(second.cache_hits, 0)
        self.assertEqual(second.cache_misses, 0)
        self.assertEqual(second.total_return, first.total_return)
        self.assertEqual(second.action_counts, first.action_counts)

    def test_reverse_t_buyback_closes_when_limit_price_is_touched(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(70).copy()
        bars.loc[6, "low"] = float(bars.loc[4, "close"]) * 0.975
        engine = _ScriptedEngine()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=1,
                signal_cache_dir=None,
                allow_reverse_t=True,
                enable_t_sell=True,
            ),
            engine=engine,
        )

        sides = [trade.side for trade in result.trades]
        self.assertIn("SELL_REVERSE_T", sides)
        self.assertIn("BUY_BACK_REVERSE_T", sides)
        reverse_sell = next(trade for trade in result.trades if trade.side == "SELL_REVERSE_T")
        self.assertEqual(reverse_sell.execution_setup_code, "reverse_t_sell")
        self.assertGreater(result.buyback_trade_count, 0)

    def test_strong_buy_signal_uses_fractional_kelly_position_size(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()
        engine = _ScriptedBuyEngine()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=0.80,
                min_t_trade_pct=0.03,
                kelly_fraction_scale=0.50,
                min_buy_signal_strength=56.0,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=1,
                signal_cache_dir=None,
            ),
            engine=engine,
        )

        buy_trades = [trade for trade in result.trades if trade.side == "BUY_T"]
        self.assertTrue(buy_trades)
        notional_pct = buy_trades[0].shares * buy_trades[0].price / 100_000
        self.assertGreaterEqual(notional_pct, 0.18)
        self.assertLessEqual(notional_pct, 0.95)
        self.assertIn("Kelly", buy_trades[0].reason)

    def test_risk_off_market_filter_blocks_new_buy_and_marks_points(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()
        engine = _ScriptedBuyEngine(strong_main_rise=False)
        market_filter = _falling_market_filter()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=0.80,
                min_buy_signal_strength=56.0,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=6,
                signal_cache_dir=None,
                enable_market_filter=True,
                market_filter_name=market_filter.name,
                strategy_mode="dynamic",
                stock_risk_on_hold_bars=12,
                stock_risk_on_sustain_bars=6,
                market_risk_off_passthrough_cap_pct=0.10,
            ),
            engine=engine,
            market_filter=market_filter,
        )

        self.assertFalse([trade for trade in result.trades if trade.side == "BUY_T"])
        self.assertGreater(result.action_counts.get("STOP_T_WAIT", 0), 0)
        self.assertGreater(result.strategy_mode_counts.get("defensive", 0), 0)
        filtered_points = [point for point in result.equity_curve if point.market_environment_state == MARKET_RISK_OFF]
        self.assertTrue(filtered_points)
        self.assertEqual(filtered_points[0].strategy_mode, "defensive")
        self.assertEqual(filtered_points[0].max_total_position_pct, 0.05)

    def test_risk_off_market_filter_allows_strong_stock_passthrough_with_cap(self) -> None:
        config = DividendTBacktestConfig(max_signal_position_pct=1.00)
        signal = replace(
            _risk_on_confirmed_signal(action="BREAKOUT_BUY_TIMING"),
            buy_signal_strength=88.0,
            breakout_score=94.0,
            breakout_confirmed=True,
            volume_price_score=78.0,
            volume_breakout_score=80.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=74.0,
            sell_pressure_score=48.0,
            down_probability_1d=0.45,
            down_probability_3d=0.46,
        )
        point = MarketEnvironmentPoint(
            trade_date=date(2026, 6, 26),
            state=MARKET_RISK_OFF,
            score=32.0,
            max_total_position_pct=0.10,
            allow_new_buy=False,
        )

        filtered = _apply_market_environment_filter(signal, point, config=config)

        self.assertEqual(filtered.market_environment_state, MARKET_RISK_ON)
        self.assertEqual(filtered.max_total_position_pct, 0.45)
        self.assertEqual(filtered.action, "BREAKOUT_BUY_TIMING")

    def test_dynamic_mode_uses_offensive_for_risk_on_confirmed_breakout(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()
        engine = _ScriptedBreakoutProfitEngine(weaken_after_first=False)
        market_filter = _rising_market_filter()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=1.00,
                max_signal_position_pct=1.00,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=6,
                signal_cache_dir=None,
                enable_market_filter=True,
                market_filter_name=market_filter.name,
                strategy_mode="dynamic",
                stock_risk_on_hold_bars=12,
                stock_risk_on_sustain_bars=6,
            ),
            engine=engine,
            market_filter=market_filter,
        )

        self.assertGreater(result.strategy_mode_counts.get("offensive", 0), 0)
        offensive_points = [point for point in result.equity_curve if point.strategy_mode == "offensive"]
        self.assertTrue(offensive_points)
        self.assertTrue([trade for trade in result.trades if trade.side == "BUY_RISK_ON_TARGET"])

    def test_dynamic_mode_allows_stock_level_risk_on_when_market_is_neutral(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()
        engine = _ScriptedBreakoutProfitEngine(weaken_after_first=False)
        market_filter = _constant_market_filter(MARKET_NEUTRAL, cap=0.35)

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=1.00,
                max_signal_position_pct=1.00,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=6,
                signal_cache_dir=None,
                enable_market_filter=True,
                market_filter_name=market_filter.name,
                strategy_mode="dynamic",
                stock_risk_on_hold_bars=12,
                stock_risk_on_sustain_bars=6,
            ),
            engine=engine,
            market_filter=market_filter,
        )

        self.assertGreater(result.strategy_mode_counts.get("offensive", 0), 1)
        self.assertTrue([trade for trade in result.trades if trade.side == "BUY_RISK_ON_TARGET"])
        stock_risk_on_points = [point for point in result.equity_curve if point.market_environment_state == MARKET_RISK_ON]
        self.assertGreater(len(stock_risk_on_points), result.strategy_mode_counts.get("offensive", 0))

    def test_confirmed_breakout_attack_can_use_nearly_all_cash(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()
        engine = _ScriptedBreakoutProfitEngine()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=1.00,
                max_signal_position_pct=1.00,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=1,
                signal_cache_dir=None,
                profit_protect_trigger_pct=0.05,
                enable_breakout_direct_buy=True,
                breakout_direct_buy_requires_risk_on_confirmation=False,
            ),
            engine=engine,
        )

        buy_trades = [trade for trade in result.trades if trade.side == "BUY_BREAKOUT"]
        self.assertTrue(buy_trades)
        first_buy_notional_pct = buy_trades[0].shares * buy_trades[0].price / 100_000
        self.assertGreaterEqual(first_buy_notional_pct, 0.85)
        self.assertTrue({"FULL_ATTACK", "BETA_HOLD"} & set(result.attack_counts))

    def test_strong_trend_regime_keeps_base_under_10_percent(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(50).copy()
        engine = _ScriptedStrongTrendEngine()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=0.80,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=1,
                signal_cache_dir=None,
            ),
            engine=engine,
        )

        self.assertIn("STRONG_TREND", result.regime_counts)
        last = result.equity_curve[-1]
        base_pct = last.base_shares * last.close / last.equity
        self.assertLessEqual(base_pct, 0.105)
        strong_points = [point for point in result.equity_curve if point.market_regime_state == "STRONG_TREND"]
        self.assertTrue(strong_points)
        self.assertEqual(strong_points[-1].max_total_position_pct, 0.80)
        self.assertEqual(strong_points[-1].active_position_cap_pct, 0.70)

    def test_base_rebalance_cooldown_reduces_churn(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(80).copy()

        no_cooldown = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                base_rebalance_threshold_pct=0.005,
                base_rebalance_cooldown_bars=0,
                min_base_rebalance_buy_quality_score=0.0,
                strong_trend_confirm_signals=1,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=1,
                signal_cache_dir=None,
            ),
            engine=_ScriptedRebalanceChurnEngine(),
        )
        with_cooldown = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                base_rebalance_threshold_pct=0.005,
                base_rebalance_cooldown_bars=48,
                min_base_rebalance_buy_quality_score=0.0,
                strong_trend_confirm_signals=1,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=1,
                signal_cache_dir=None,
            ),
            engine=_ScriptedRebalanceChurnEngine(),
        )

        no_cooldown_rebalances = [trade for trade in no_cooldown.trades if trade.action.startswith("REBALANCE_BASE")]
        cooldown_rebalances = [trade for trade in with_cooldown.trades if trade.action.startswith("REBALANCE_BASE")]
        self.assertGreater(len(no_cooldown_rebalances), len(cooldown_rebalances))
        defensive_points = [point for point in no_cooldown.equity_curve if point.market_regime_state == "DEFENSIVE"]
        self.assertTrue(defensive_points)
        self.assertEqual(defensive_points[0].active_position_cap_pct, 0.0)
        self.assertGreaterEqual(defensive_points[0].max_total_position_pct, defensive_points[0].base_target_pct)

    def test_breakout_profit_protection_sells_partial_breakout_position(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()
        bars.loc[5, ["open", "high", "low", "close"]] = [14.00, 14.05, 13.96, 14.02]
        bars.loc[6, ["open", "high", "low", "close"]] = [14.28, 14.32, 14.18, 14.25]

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=0.80,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=1,
                signal_cache_dir=None,
                profit_protect_trigger_pct=0.012,
                profit_protect_sell_fraction=0.50,
                offensive_hold_extension_enabled=False,
                enable_beta_hold_state=False,
                enable_a_share_constraints=False,
                enable_breakout_direct_buy=True,
                breakout_direct_buy_requires_risk_on_confirmation=False,
            ),
            engine=_ScriptedBreakoutProfitEngine(),
        )

        sides = [trade.side for trade in result.trades]
        self.assertIn("BUY_BREAKOUT", sides)
        self.assertIn("SELL_BREAKOUT_PROFIT", sides)

    def test_profit_protection_defers_when_breakout_trend_is_intact(self) -> None:
        config = DividendTBacktestConfig(
            initial_cash=100_000,
            initial_base_position_pct=0.10,
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            enable_a_share_constraints=False,
            profit_protect_trigger_pct=0.012,
            profit_protect_sell_fraction=0.50,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            market_regime_state="TREND_WATCH",
            buy_signal_strength=58.0,
            breakout_score=80.0,
            breakout_confirmed=False,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=78.0,
            capital_flow_confidence=0.78,
            force_ratio=0.80,
            force_weighted_score=52.0,
            volume_price_score=80.0,
            volume_breakout_score=78.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=74.0,
            chan_buy_point_type="none",
            sell_pressure_score=62.0,
            down_probability_1d=0.48,
            down_probability_3d=0.50,
        )

        state = _execute_action(
            action="WAIT_STRONG_TREND",
            execution={"timestamp": "2026-06-26 10:05:00", "open": 10.6, "close": 10.6, "low": 10.5},
            signal=signal,
            equity_before=100_000.0,
            cash=90_000.0,
            base_shares=0,
            base_locked_shares=0,
            t_shares=1_000,
            t_locked_shares=0,
            t_cost_basis=9_500.0,
            breakout_t_shares=1_000,
            breakout_t_locked_shares=0,
            breakout_t_cost_basis=9_500.0,
            pending_buyback_shares=0,
            pending_reverse_proceeds=0.0,
            pending_buyback_target_price=None,
            attack_state=ATTACK_CONFIRMED,
            active_peak_profit_pct=0.17,
            constraints=TradeExecutionConstraints(),
            config=config,
            core_position_floor_pct=0.0,
        )

        self.assertIsNone(state["trade"])
        self.assertEqual(state["blocked"], "PROTECT_BREAKOUT_PROFIT_TREND_HOLD")
        self.assertEqual(state["t_shares"], 1_000)

    def test_profit_protection_sells_when_exit_pressure_is_confirmed(self) -> None:
        config = DividendTBacktestConfig(
            initial_cash=100_000,
            initial_base_position_pct=0.10,
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            enable_a_share_constraints=False,
            profit_protect_trigger_pct=0.012,
            profit_protect_sell_fraction=0.50,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            market_regime_state="TREND_WATCH",
            buy_signal_strength=58.0,
            breakout_score=80.0,
            breakout_confirmed=False,
            force_ratio=0.78,
            force_weighted_score=50.0,
            volume_price_score=62.0,
            volume_breakout_score=60.0,
            post_breakout_volume_persistence_score=58.0,
            vwap_support_score=58.0,
            chan_buy_point_type="none",
            sell_pressure_score=90.0,
            down_probability_1d=0.69,
            down_probability_3d=0.68,
        )

        state = _execute_action(
            action="WAIT_STRONG_TREND",
            execution={"timestamp": "2026-06-26 10:05:00", "open": 10.6, "close": 10.6, "low": 10.5},
            signal=signal,
            equity_before=100_000.0,
            cash=90_000.0,
            base_shares=0,
            base_locked_shares=0,
            t_shares=1_000,
            t_locked_shares=0,
            t_cost_basis=9_500.0,
            breakout_t_shares=1_000,
            breakout_t_locked_shares=0,
            breakout_t_cost_basis=9_500.0,
            pending_buyback_shares=0,
            pending_reverse_proceeds=0.0,
            pending_buyback_target_price=None,
            attack_state=ATTACK_CONFIRMED,
            active_peak_profit_pct=0.17,
            constraints=TradeExecutionConstraints(),
            config=config,
            core_position_floor_pct=0.0,
        )

        self.assertIsNotNone(state["trade"])
        self.assertEqual(state["trade"].side, "SELL_BREAKOUT_PROFIT")
        self.assertLess(state["t_shares"], 1_000)

    def test_t1_blocks_same_day_active_position_sell(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=0.80,
                min_buy_signal_strength=56.0,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=1,
                signal_cache_dir=None,
            ),
            engine=_ScriptedBuyThenStopEngine(),
        )

        sides = [trade.side for trade in result.trades]
        self.assertIn("BUY_T", sides)
        self.assertNotIn("STOP_T", sides)
        self.assertGreater(result.execution_block_counts.get("STOP_T_WAIT_T1_LOCK", 0), 0)
        self.assertGreater(result.equity_curve[-1].t_shares, 0)
        self.assertEqual(result.equity_curve[-1].sellable_t_shares, 0)

    def test_limit_up_blocks_new_buy(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(60).copy()
        previous_close = float(bars.loc[47, "close"])
        limit_price = round(previous_close * 1.10, 3)
        bars.loc[48, ["open", "high", "low", "close"]] = [limit_price, limit_price, limit_price, limit_price]

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=0.80,
                min_buy_signal_strength=56.0,
                min_lookback_bars=48,
                max_history_bars=48,
                signal_step_bars=1,
                signal_cache_dir=None,
            ),
            engine=_ScriptedBuyEngine(),
        )

        self.assertFalse([trade for trade in result.trades if trade.side == "BUY_T"])
        self.assertGreater(result.execution_block_counts.get("BUY_T_TIMING_LIMIT_UP", 0), 0)

    def test_limit_down_blocks_sellable_t_position_exit(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(80).copy()
        previous_close = float(bars.loc[47, "close"])
        limit_price = round(previous_close * 0.90, 3)
        bars.loc[48:79, ["open", "high", "low", "close"]] = [limit_price, limit_price, limit_price, limit_price]

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=0.80,
                min_buy_signal_strength=56.0,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=1,
                signal_cache_dir=None,
            ),
            engine=_ScriptedBuyThenStopEngine(),
        )

        self.assertTrue([trade for trade in result.trades if trade.side == "BUY_T"])
        self.assertFalse([trade for trade in result.trades if trade.side == "STOP_T"])
        self.assertGreater(result.execution_block_counts.get("STOP_T_WAIT_LIMIT_DOWN", 0), 0)

    def test_risk_on_confirmed_setup_holds_through_soft_sell(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = _risk_on_confirmed_signal(action="SELL_T_TIMING")

        fraction = _offensive_exit_sell_fraction(
            action="SELL_T_TIMING",
            signal=signal,
            config=config,
            attack_state=ATTACK_CONFIRMED,
            active_profit_pct=0.02,
            active_peak_profit_pct=0.02,
        )

        self.assertEqual(fraction, 0.0)

    def test_risk_on_extension_holds_soft_sell_without_attack_state(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="SELL_T_TIMING"),
            buy_signal_strength=49.0,
            force_ratio=0.82,
            force_weighted_score=50.0,
            post_breakout_volume_persistence_score=72.0,
            vwap_support_score=72.0,
            sell_pressure_score=58.0,
        )

        fraction = _offensive_exit_sell_fraction(
            action="SELL_T_TIMING",
            signal=signal,
            config=config,
            attack_state=ATTACK_INACTIVE,
            active_profit_pct=0.01,
            active_peak_profit_pct=0.01,
        )

        self.assertEqual(fraction, 0.0)

    def test_low_quality_buy_point_gets_no_target_position(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            min_buy_signal_strength=62.0,
            min_buy_point_quality_score=0.40,
            enable_breakout_direct_buy=True,
        )
        weak = replace(
            _risk_on_confirmed_signal(action="BUY_T_TIMING"),
            buy_signal_strength=66.0,
            breakout_score=70.0,
            breakout_confirmed=False,
            chan_buy_point_type="none",
            chan_score=54.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=48.0,
            capital_flow_confidence=0.0,
            force_ratio=0.78,
            force_weighted_score=44.0,
            volume_price_score=48.0,
            volume_breakout_score=42.0,
            post_breakout_volume_persistence_score=44.0,
            vwap_support_score=46.0,
            sell_pressure_score=76.0,
            down_probability_1d=0.59,
            down_probability_3d=0.60,
        )
        strong = replace(
            _risk_on_confirmed_signal(action="BREAKOUT_BUY_TIMING"),
            buy_signal_strength=88.0,
            breakout_score=94.0,
            breakout_confirmed=True,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=82.0,
            capital_flow_confidence=0.82,
            volume_price_score=82.0,
            volume_breakout_score=82.0,
            post_breakout_volume_persistence_score=78.0,
            vwap_support_score=76.0,
            sell_pressure_score=48.0,
            down_probability_1d=0.45,
            down_probability_3d=0.46,
        )

        self.assertLess(_buy_point_quality_score(weak, config), config.min_buy_point_quality_score)
        self.assertEqual(_signal_target_position_pct(weak, config), 0.0)
        self.assertGreater(_buy_point_quality_score(strong, config), _buy_point_quality_score(weak, config))
        self.assertGreater(_signal_target_position_pct(strong, config, attack_state=ATTACK_CONFIRMED), 0.70)

    def test_main_rise_buy_quality_filters_low_elasticity_buy_point(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            min_buy_signal_strength=62.0,
            min_buy_point_quality_score=0.40,
            min_main_rise_buy_quality_score=0.46,
            enable_breakout_direct_buy=True,
        )
        low_elasticity = replace(
            _risk_on_confirmed_signal(action="BUY_T_TIMING"),
            buy_signal_strength=68.0,
            breakout_score=76.0,
            breakout_confirmed=False,
            force_ratio=0.72,
            force_weighted_score=44.0,
            attention_score=50.0,
            volume_price_score=56.0,
            volume_breakout_score=54.0,
            post_breakout_volume_persistence_score=54.0,
            vwap_support_score=58.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=54.0,
            capital_flow_confidence=0.20,
        )
        main_rise = replace(
            _risk_on_confirmed_signal(action="BREAKOUT_BUY_TIMING"),
            buy_signal_strength=86.0,
            breakout_score=92.0,
            breakout_confirmed=True,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=82.0,
            capital_flow_confidence=0.82,
            force_ratio=1.12,
            force_weighted_score=68.0,
            attention_score=76.0,
            volume_price_score=82.0,
            volume_breakout_score=80.0,
            post_breakout_volume_persistence_score=78.0,
            vwap_support_score=76.0,
            sell_pressure_score=48.0,
        )

        self.assertLess(_main_rise_buy_quality_score(low_elasticity, config), config.min_main_rise_buy_quality_score)
        self.assertEqual(_signal_target_position_pct(low_elasticity, config), 0.0)
        self.assertGreater(_main_rise_buy_quality_score(main_rise, config), config.min_main_rise_buy_quality_score)
        self.assertGreater(_signal_target_position_pct(main_rise, config, attack_state=ATTACK_CONFIRMED), 0.50)

    def test_risk_on_target_add_requires_breakout_vwap_volume_and_flow(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            risk_on_position_target_min_strength=45.0,
        )
        confirmed = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            breakout_score=90.0,
            breakout_confirmed=True,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=78.0,
            capital_flow_confidence=0.78,
            volume_price_score=78.0,
            volume_breakout_score=74.0,
            post_breakout_volume_persistence_score=74.0,
            vwap_support_score=74.0,
            sell_pressure_score=54.0,
            down_probability_1d=0.46,
            down_probability_3d=0.47,
        )
        weak_vwap = replace(confirmed, vwap_support_score=62.0)
        weak_flow = replace(
            confirmed,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=52.0,
            capital_flow_confidence=0.20,
        )

        self.assertTrue(_risk_on_target_add_confirmation_signal(confirmed, config))
        self.assertGreater(
            _risk_on_position_target_pct(
                confirmed,
                config,
                attack_state=ATTACK_CONFIRMED,
                current_position_pct=0.20,
            ),
            0.20,
        )
        self.assertFalse(_risk_on_target_add_confirmation_signal(weak_vwap, config))
        self.assertEqual(
            _risk_on_position_target_pct(
                weak_vwap,
                config,
                attack_state=ATTACK_CONFIRMED,
                current_position_pct=0.20,
            ),
            0.0,
        )
        self.assertFalse(_risk_on_target_add_confirmation_signal(weak_flow, config))

    def test_buy_volume_price_window_filter_blocks_flat_contract_entry(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            min_buy_signal_strength=62.0,
            min_buy_point_quality_score=0.30,
        )
        flat_contract = replace(
            _risk_on_confirmed_signal(action="BUY_T_TIMING"),
            buy_signal_strength=82.0,
            breakout_score=88.0,
            volume_price_score=78.0,
            volume_breakout_score=76.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=74.0,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=76.0,
            capital_flow_confidence=0.76,
            sell_pressure_score=52.0,
            pretrade_volume_price_state_12="flat_volume_contract",
            pretrade_price_return_pct_12=0.001,
            pretrade_volume_ratio_to_prev_12=0.62,
            pretrade_volume_price_state_24="flat_volume_contract",
            pretrade_price_return_pct_24=0.002,
            pretrade_volume_ratio_to_prev_24=0.58,
        )

        self.assertEqual(_signal_target_position_pct(flat_contract, config), 0.0)
        self.assertGreater(
            _signal_target_position_pct(
                flat_contract,
                replace(config, enable_buy_volume_price_window_filter=False),
            ),
            0.0,
        )

    def test_portfolio_profit_diffusion_lifts_main_rise_position_target(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            risk_on_mid_position_add_cap_pct=0.85,
            portfolio_main_rise_position_target_pct=0.95,
            risk_on_position_target_min_strength=45.0,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            market_regime_state="STRONG_TREND",
            buy_signal_strength=82.0,
            breakout_score=90.0,
            breakout_confirmed=True,
            volume_price_score=80.0,
            volume_breakout_score=78.0,
            post_breakout_volume_persistence_score=78.0,
            vwap_support_score=76.0,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=80.0,
            capital_flow_confidence=0.80,
            sell_pressure_score=50.0,
            market_model_state_score=74.0,
            model_holding_win_rate=0.60,
            model_holding_profit_spread=0.68,
            model_new_buy_success_rate=0.50,
            pretrade_volume_price_state_12="price_up_volume_up",
            pretrade_price_return_pct_12=0.014,
            pretrade_volume_ratio_to_prev_12=1.16,
            pretrade_volume_price_state_24="price_up_volume_up",
            pretrade_price_return_pct_24=0.026,
            pretrade_volume_ratio_to_prev_24=1.12,
        )

        target = _risk_on_position_target_pct(
            signal,
            config,
            attack_state=ATTACK_CONFIRMED,
            current_position_pct=0.45,
        )

        self.assertGreaterEqual(target, config.portfolio_main_rise_position_target_pct)

    def test_buy_t_failure_cooldown_blocks_ordinary_reentry(self) -> None:
        config = DividendTBacktestConfig()
        ordinary = replace(
            _risk_on_confirmed_signal(action="BUY_T_TIMING"),
            breakout_score=78.0,
            breakout_confirmed=False,
            vwap_support_score=64.0,
            post_breakout_volume_persistence_score=62.0,
        )
        main_rise = replace(
            _risk_on_confirmed_signal(action="BUY_T_TIMING"),
            market_regime_state="STRONG_TREND",
            breakout_score=90.0,
            breakout_confirmed=True,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=80.0,
            capital_flow_confidence=0.80,
            volume_price_score=80.0,
            volume_breakout_score=78.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=76.0,
            sell_pressure_score=50.0,
            down_probability_1d=0.46,
        )

        self.assertTrue(_buy_t_failure_cooldown_blocks_signal(ordinary, config, bars_remaining=12))
        self.assertFalse(_buy_t_failure_cooldown_blocks_signal(main_rise, config, bars_remaining=12))
        self.assertFalse(_buy_t_failure_cooldown_blocks_signal(ordinary, config, bars_remaining=0))

    def test_sell_point_continuation_hold_blocks_soft_stop_when_trend_intact(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            breakout_score=88.0,
            breakout_confirmed=True,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=76.0,
            capital_flow_confidence=0.76,
            volume_price_score=78.0,
            volume_breakout_score=76.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=74.0,
            sell_pressure_score=58.0,
            down_probability_1d=0.48,
            down_probability_3d=0.50,
        )

        self.assertTrue(
            _sell_point_continuation_hold_signal(
                action="STOP_T_WAIT",
                signal=signal,
                config=config,
                active_profit_pct=-0.01,
                active_peak_profit_pct=0.01,
            )
        )
        fraction = _offensive_exit_sell_fraction(
            action="STOP_T_WAIT",
            signal=signal,
            config=config,
            attack_state=ATTACK_INACTIVE,
            active_profit_pct=-0.01,
            active_peak_profit_pct=0.01,
        )

        self.assertEqual(fraction, 0.0)

    def test_stop_t_wait_uses_hard_soft_hold_exit_states(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        hold = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            breakout_score=88.0,
            breakout_confirmed=True,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=76.0,
            capital_flow_confidence=0.76,
            volume_price_score=78.0,
            volume_breakout_score=76.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=74.0,
            sell_pressure_score=58.0,
            down_probability_1d=0.48,
            down_probability_3d=0.50,
        )
        soft = replace(
            hold,
            trend_state="RANGE",
            market_regime_state="TREND_WATCH",
            buy_signal_strength=50.0,
            breakout_confirmed=False,
            breakout_score=76.0,
            chan_buy_point_type="none",
            chan_score=58.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=54.0,
            capital_flow_confidence=0.20,
            volume_price_score=60.0,
            volume_breakout_score=58.0,
            post_breakout_volume_persistence_score=58.0,
            vwap_support_score=58.0,
            sell_pressure_score=80.0,
            down_probability_1d=0.54,
            down_probability_3d=0.55,
        )
        hard = replace(
            soft,
            trend_state="DOWNTREND",
            market_regime_state="DEFENSIVE",
            sell_pressure_score=90.0,
            down_probability_1d=0.69,
            down_probability_3d=0.68,
        )

        self.assertEqual(
            _offensive_exit_sell_fraction(
                action="STOP_T_WAIT",
                signal=hold,
                config=config,
                attack_state=ATTACK_CONFIRMED,
                active_profit_pct=-0.01,
                active_peak_profit_pct=0.03,
            ),
            0.0,
        )
        self.assertEqual(
            _offensive_exit_sell_fraction(
                action="STOP_T_WAIT",
                signal=soft,
                config=config,
                attack_state=ATTACK_CONFIRMED,
                active_profit_pct=-0.05,
                active_peak_profit_pct=0.02,
            ),
            config.offensive_soft_stop_sell_fraction,
        )
        self.assertEqual(
            _offensive_exit_sell_fraction(
                action="STOP_T_WAIT",
                signal=hard,
                config=config,
                attack_state=ATTACK_CONFIRMED,
                active_profit_pct=-0.08,
                active_peak_profit_pct=0.02,
            ),
            1.0,
        )

    def test_stop_t_wait_requires_support_break_for_pressure_only_soft_exit(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        pressure_only = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            trend_state="RANGE",
            market_regime_state="TREND_WATCH",
            buy_signal_strength=50.0,
            breakout_confirmed=False,
            breakout_score=76.0,
            chan_buy_point_type="none",
            chan_score=58.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=54.0,
            capital_flow_confidence=0.20,
            volume_price_score=66.0,
            volume_breakout_score=58.0,
            post_breakout_volume_persistence_score=70.0,
            vwap_support_score=70.0,
            force_ratio=0.96,
            force_weighted_score=58.0,
            sell_pressure_score=80.0,
            down_probability_1d=0.54,
            down_probability_3d=0.55,
        )

        fraction = _offensive_exit_sell_fraction(
            action="STOP_T_WAIT",
            signal=pressure_only,
            config=config,
            attack_state=ATTACK_CONFIRMED,
            active_profit_pct=-0.02,
            active_peak_profit_pct=0.02,
        )

        self.assertEqual(fraction, 0.0)

    def test_stop_t_wait_deescalates_deep_loss_when_risk_features_are_mild(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            trend_state="DOWNTREND",
            market_regime_state="DEFENSIVE",
            buy_signal_strength=0.0,
            breakout_confirmed=False,
            breakout_score=8.0,
            chan_buy_point_type="none",
            chan_sell_point_type="none",
            chan_structure_type="pivot",
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=42.0,
            capital_flow_confidence=0.10,
            volume_price_score=54.0,
            post_breakout_volume_persistence_score=45.0,
            vwap_support_score=42.0,
            low_volume_pullback_score=91.0,
            sell_pressure_score=42.0,
            down_probability_1d=0.54,
            down_probability_3d=0.54,
        )

        fraction = _offensive_exit_sell_fraction(
            action="STOP_T_WAIT",
            signal=signal,
            config=config,
            attack_state=ATTACK_INACTIVE,
            active_profit_pct=-0.12,
            active_peak_profit_pct=0.00,
        )

        self.assertEqual(fraction, min(config.offensive_soft_stop_sell_fraction, config.beta_hold_soft_stop_sell_fraction))

    def test_stop_t_wait_deescalates_probability_only_false_break(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        mild_false_break = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            trend_state="EXHAUSTION",
            market_regime_state="DEFENSIVE",
            buy_signal_strength=0.0,
            breakout_confirmed=False,
            breakout_score=0.0,
            chan_buy_point_type="none",
            chan_sell_point_type="sell3",
            chan_structure_type="breakdown",
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=42.0,
            capital_flow_confidence=0.10,
            volume_price_score=50.0,
            post_breakout_volume_persistence_score=45.0,
            vwap_support_score=14.0,
            low_volume_pullback_score=71.0,
            sell_pressure_score=50.0,
            down_probability_1d=0.608,
            down_probability_3d=0.568,
            probability_state="DOWN_RISK",
        )
        hard_probability = replace(
            mild_false_break,
            down_probability_1d=config.attack_hard_exit_down_probability,
            down_probability_3d=config.attack_hard_exit_down_probability,
        )

        self.assertEqual(
            _offensive_exit_sell_fraction(
                action="STOP_T_WAIT",
                signal=mild_false_break,
                config=config,
                attack_state=ATTACK_INACTIVE,
                active_profit_pct=-0.01,
                active_peak_profit_pct=0.02,
            ),
            min(config.offensive_soft_stop_sell_fraction, config.beta_hold_soft_stop_sell_fraction),
        )
        self.assertEqual(
            _offensive_exit_sell_fraction(
                action="STOP_T_WAIT",
                signal=hard_probability,
                config=config,
                attack_state=ATTACK_INACTIVE,
                active_profit_pct=-0.01,
                active_peak_profit_pct=0.02,
            ),
            1.0,
        )

    def test_sell_t_timing_requires_exit_confirmation_before_soft_reduce(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        support_intact = replace(
            _risk_on_confirmed_signal(action="SELL_T_TIMING"),
            trend_state="RANGE",
            market_regime_state="TREND_WATCH",
            buy_signal_strength=50.0,
            breakout_confirmed=False,
            breakout_score=76.0,
            chan_buy_point_type="none",
            chan_score=58.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=54.0,
            capital_flow_confidence=0.20,
            volume_price_score=66.0,
            volume_breakout_score=58.0,
            post_breakout_volume_persistence_score=70.0,
            vwap_support_score=70.0,
            force_ratio=0.96,
            force_weighted_score=58.0,
            sell_pressure_score=80.0,
            down_probability_1d=0.54,
            down_probability_3d=0.55,
        )
        support_broken = replace(
            support_intact,
            volume_price_score=58.0,
            post_breakout_volume_persistence_score=58.0,
            vwap_support_score=58.0,
            force_ratio=0.72,
            force_weighted_score=46.0,
        )
        force_only_weak = replace(
            support_intact,
            volume_price_score=72.0,
            post_breakout_volume_persistence_score=70.0,
            vwap_support_score=88.0,
            low_volume_pullback_score=91.0,
            force_ratio=0.05,
            force_weighted_score=45.0,
        )

        self.assertEqual(
            _offensive_exit_sell_fraction(
                action="SELL_T_TIMING",
                signal=support_intact,
                config=config,
                attack_state=ATTACK_CONFIRMED,
                active_profit_pct=0.01,
                active_peak_profit_pct=0.02,
            ),
            0.0,
        )
        self.assertEqual(
            _offensive_exit_sell_fraction(
                action="SELL_T_TIMING",
                signal=force_only_weak,
                config=config,
                attack_state=ATTACK_CONFIRMED,
                active_profit_pct=0.01,
                active_peak_profit_pct=0.02,
            ),
            0.0,
        )
        self.assertEqual(
            _offensive_exit_sell_fraction(
                action="SELL_T_TIMING",
                signal=support_broken,
                config=config,
                attack_state=ATTACK_CONFIRMED,
                active_profit_pct=0.01,
                active_peak_profit_pct=0.02,
            ),
            config.offensive_soft_exit_sell_fraction,
        )

    def test_trailing_profit_takes_layered_partial_exit_after_pullback(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = _risk_on_confirmed_signal(action="SELL_T_TIMING")

        fraction = _offensive_exit_sell_fraction(
            action="SELL_T_TIMING",
            signal=signal,
            config=config,
            attack_state=ATTACK_CONFIRMED,
            active_profit_pct=0.06,
            active_peak_profit_pct=0.15,
        )

        self.assertEqual(fraction, config.offensive_trailing_mid_sell_fraction)

    def test_offensive_volume_distribution_does_not_downgrade_low_profit_full_attack(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            high_volume_stall_score=82.0,
            price_up_volume_down_score=86.0,
            volume_price_score=64.0,
            post_breakout_volume_persistence_score=58.0,
            vwap_support_score=54.0,
            sell_pressure_score=70.0,
            down_probability_1d=0.57,
            down_probability_3d=0.59,
        )

        next_state, confirm_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_FULL,
            confirm_streak=3,
            state_age_bars=30,
        )

        self.assertIn(next_state, {ATTACK_FULL, ATTACK_BETA_HOLD})
        self.assertGreaterEqual(confirm_streak, 3)

    def test_offensive_volume_distribution_absorption_keeps_full_attack(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            high_volume_stall_score=82.0,
            price_up_volume_down_score=86.0,
            volume_price_score=78.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=74.0,
            sell_pressure_score=58.0,
            down_probability_1d=0.48,
            down_probability_3d=0.50,
        )

        next_state, confirm_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_FULL,
            confirm_streak=3,
            state_age_bars=30,
        )

        self.assertEqual(next_state, ATTACK_BETA_HOLD)
        self.assertGreaterEqual(confirm_streak, 3)

    def test_absorbed_volume_distribution_still_allows_risk_on_target_add(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            risk_on_position_target_min_gap_pct=0.05,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            buy_signal_strength=82.0,
            breakout_score=90.0,
            breakout_confirmed=True,
            high_volume_stall_score=82.0,
            price_up_volume_down_score=86.0,
            volume_price_score=78.0,
            volume_breakout_score=78.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=74.0,
            sell_pressure_score=58.0,
            down_probability_1d=0.48,
            down_probability_3d=0.50,
        )

        target = _risk_on_position_target_pct(
            signal,
            config,
            attack_state=ATTACK_CONFIRMED,
            current_position_pct=0.20,
        )

        self.assertGreaterEqual(target, 0.60)
        self.assertLessEqual(target, config.risk_on_low_position_add_cap_pct)

    def test_hard_volume_distribution_exits_when_low_absorption_and_pressure_confirm(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            capital_flow_confirmation_state="CONFIRMED_OUTFLOW",
            capital_flow_confirmation_score=42.0,
            capital_flow_score=42.0,
            capital_flow_confidence=0.80,
            high_volume_stall_score=90.0,
            price_up_volume_down_score=90.0,
            volume_price_score=58.0,
            post_breakout_volume_persistence_score=54.0,
            vwap_support_score=52.0,
            chan_sell_point_type="sell3",
            chan_structure_type="breakdown",
            sell_pressure_score=84.0,
            down_probability_1d=0.65,
            down_probability_3d=0.64,
            force_ratio=0.62,
        )

        next_state, confirm_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_FULL,
            confirm_streak=3,
            state_age_bars=30,
            active_profit_pct=0.08,
            active_peak_profit_pct=0.12,
        )

        self.assertEqual(next_state, ATTACK_INACTIVE)
        self.assertEqual(confirm_streak, 0)

    def test_hard_volume_distribution_requires_breakdown_and_outflow_confirmation(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        stall_only = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            high_volume_stall_score=90.0,
            price_up_volume_down_score=90.0,
            volume_price_score=58.0,
            post_breakout_volume_persistence_score=54.0,
            vwap_support_score=52.0,
            sell_pressure_score=84.0,
            down_probability_1d=0.65,
            down_probability_3d=0.64,
            force_ratio=0.62,
        )

        next_state, confirm_streak = _next_attack_state(
            signal=stall_only,
            config=config,
            current_state=ATTACK_FULL,
            confirm_streak=3,
            state_age_bars=30,
            active_profit_pct=0.08,
            active_peak_profit_pct=0.12,
        )

        self.assertIn(next_state, {ATTACK_CONFIRMED, ATTACK_FULL, ATTACK_BETA_HOLD})
        self.assertGreaterEqual(confirm_streak, 2)

    def test_offensive_volume_distribution_ignores_non_profit_position_with_some_absorption(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            breakout_confirmed=False,
            breakout_score=76.0,
            chan_buy_point_type="none",
            chan_score=62.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=60.0,
            capital_flow_confidence=0.30,
            high_volume_stall_score=82.0,
            price_up_volume_down_score=86.0,
            volume_price_score=70.0,
            post_breakout_volume_persistence_score=68.0,
            vwap_support_score=68.0,
            sell_pressure_score=70.0,
            down_probability_1d=0.57,
            down_probability_3d=0.59,
        )

        next_state, confirm_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_FULL,
            confirm_streak=3,
            state_age_bars=30,
            active_profit_pct=0.01,
            active_peak_profit_pct=0.02,
        )

        self.assertEqual(next_state, ATTACK_FULL)
        self.assertEqual(confirm_streak, 3)

    def test_offensive_volume_distribution_keeps_high_profit_position_without_low_absorption(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            breakout_confirmed=False,
            breakout_score=76.0,
            chan_buy_point_type="none",
            chan_score=62.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=60.0,
            capital_flow_confidence=0.30,
            high_volume_stall_score=82.0,
            price_up_volume_down_score=86.0,
            volume_price_score=70.0,
            post_breakout_volume_persistence_score=68.0,
            vwap_support_score=68.0,
            sell_pressure_score=70.0,
            down_probability_1d=0.57,
            down_probability_3d=0.59,
        )

        next_state, confirm_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_FULL,
            confirm_streak=3,
            state_age_bars=30,
            active_profit_pct=0.08,
            active_peak_profit_pct=0.12,
        )

        self.assertIn(next_state, {ATTACK_FULL, ATTACK_BETA_HOLD})
        self.assertGreaterEqual(confirm_streak, 3)

    def test_offensive_volume_distribution_low_absorption_threshold_is_configurable(self) -> None:
        strict_config = DividendTBacktestConfig(
            attack_confirm_min_buy_strength=66.0,
            offensive_volume_distribution_low_vwap_score=58.0,
            offensive_volume_distribution_low_persistence_score=58.0,
        )
        loose_config = DividendTBacktestConfig(
            attack_confirm_min_buy_strength=66.0,
            offensive_volume_distribution_low_vwap_score=66.0,
            offensive_volume_distribution_low_persistence_score=66.0,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            high_volume_stall_score=82.0,
            price_up_volume_down_score=86.0,
            volume_price_score=68.0,
            post_breakout_volume_persistence_score=62.0,
            vwap_support_score=62.0,
            sell_pressure_score=70.0,
            down_probability_1d=0.57,
            down_probability_3d=0.59,
            force_ratio=0.80,
            force_weighted_score=48.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=60.0,
            capital_flow_confidence=0.30,
        )

        strict_state, _ = _next_attack_state(
            signal=signal,
            config=strict_config,
            current_state=ATTACK_FULL,
            confirm_streak=3,
            state_age_bars=30,
            active_profit_pct=0.01,
            active_peak_profit_pct=0.02,
        )
        loose_state, _ = _next_attack_state(
            signal=signal,
            config=loose_config,
            current_state=ATTACK_FULL,
            confirm_streak=3,
            state_age_bars=30,
            active_profit_pct=0.01,
            active_peak_profit_pct=0.02,
        )

        self.assertEqual(strict_state, ATTACK_FULL)
        self.assertEqual(loose_state, ATTACK_FULL)

    def test_offensive_volume_distribution_sell_uses_partial_reduce_fraction(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="SELL_T_TIMING"),
            high_volume_stall_score=82.0,
            price_up_volume_down_score=0.0,
            volume_price_score=64.0,
            post_breakout_volume_persistence_score=58.0,
            vwap_support_score=54.0,
            sell_pressure_score=70.0,
            down_probability_1d=0.57,
            down_probability_3d=0.59,
            force_ratio=0.74,
        )

        fraction = _offensive_exit_sell_fraction(
            action="SELL_T_TIMING",
            signal=signal,
            config=config,
            attack_state=ATTACK_CONFIRMED,
            active_profit_pct=0.08,
            active_peak_profit_pct=0.12,
        )

        self.assertEqual(fraction, config.offensive_volume_distribution_sell_fraction)

    def test_strong_trend_volume_distribution_keeps_beta_hold(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="SELL_T_TIMING"),
            high_volume_stall_score=82.0,
            price_up_volume_down_score=86.0,
            volume_price_score=60.0,
            volume_breakout_score=68.0,
            post_breakout_volume_persistence_score=64.0,
            vwap_support_score=62.0,
            sell_pressure_score=68.0,
            down_probability_1d=0.56,
            down_probability_3d=0.57,
            force_ratio=0.62,
            force_weighted_score=46.0,
        )

        next_state, confirm_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_BETA_HOLD,
            confirm_streak=3,
            state_age_bars=240,
            active_profit_pct=0.08,
            active_peak_profit_pct=0.12,
        )
        fraction = _offensive_exit_sell_fraction(
            action="SELL_T_TIMING",
            signal=signal,
            config=config,
            attack_state=ATTACK_BETA_HOLD,
            active_profit_pct=0.08,
            active_peak_profit_pct=0.12,
        )

        self.assertEqual(next_state, ATTACK_BETA_HOLD)
        self.assertGreaterEqual(confirm_streak, 3)
        self.assertEqual(fraction, 0.0)

    def test_beta_hold_main_rise_core_floor_survives_soft_stop_noise(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        signal = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            breakout_score=90.0,
            breakout_confirmed=True,
            volume_price_score=76.0,
            volume_breakout_score=78.0,
            post_breakout_volume_persistence_score=72.0,
            vwap_support_score=70.0,
            sell_pressure_score=80.0,
            down_probability_1d=0.61,
            down_probability_3d=0.58,
        )

        floor_target = _risk_on_core_floor_target_pct(signal, config, attack_state=ATTACK_BETA_HOLD)
        next_floor = _next_core_position_floor_pct(
            signal=signal,
            config=config,
            attack_state=ATTACK_BETA_HOLD,
            current_floor_pct=0.65,
            active_profit_pct=-0.02,
        )
        fraction = _offensive_exit_sell_fraction(
            action="STOP_T_WAIT",
            signal=signal,
            config=config,
            attack_state=ATTACK_BETA_HOLD,
            active_profit_pct=-0.02,
            active_peak_profit_pct=0.04,
        )

        self.assertGreaterEqual(floor_target, config.beta_hold_main_rise_core_floor_pct)
        self.assertGreaterEqual(next_floor, config.beta_hold_main_rise_core_floor_pct)
        self.assertEqual(fraction, 0.0)

    def test_beta_hold_core_floor_reduces_only_after_structure_vwap_outflow_break(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        hard_break = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            capital_flow_confirmation_state="CONFIRMED_OUTFLOW",
            capital_flow_confirmation_score=42.0,
            capital_flow_score=42.0,
            capital_flow_confidence=0.80,
            chan_sell_point_type="sell3",
            chan_structure_type="breakdown",
            post_breakout_volume_persistence_score=50.0,
            vwap_support_score=50.0,
            sell_pressure_score=82.0,
            down_probability_1d=0.62,
            down_probability_3d=0.63,
        )

        floor_target = _risk_on_core_floor_target_pct(hard_break, config, attack_state=ATTACK_BETA_HOLD)
        next_floor = _next_core_position_floor_pct(
            signal=hard_break,
            config=config,
            attack_state=ATTACK_BETA_HOLD,
            current_floor_pct=0.85,
            active_profit_pct=-0.03,
        )
        fraction = _offensive_exit_sell_fraction(
            action="STOP_T_WAIT",
            signal=hard_break,
            config=config,
            attack_state=ATTACK_BETA_HOLD,
            active_profit_pct=-0.03,
            active_peak_profit_pct=0.04,
        )

        self.assertEqual(floor_target, 0.0)
        self.assertLess(next_floor, 0.85)
        self.assertEqual(fraction, 1.0)

    def test_48bar_price_up_volume_down_is_main_rise_rotation_not_distribution(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        history = build_sample_cosco_backtest_bars().head(80).copy()
        start = 10.0
        for offset, idx in enumerate(history.tail(48).index):
            price = start * (1.0 + 0.0008 * offset)
            history.loc[idx, ["open", "high", "low", "close"]] = [price, price * 1.002, price * 0.998, price]
            history.loc[idx, "volume"] = 900_000 - offset * 6_000
            history.loc[idx, "amount"] = history.loc[idx, "close"] * history.loc[idx, "volume"]
        features = _pretrade_volume_price_window_features(
            history,
            lookback_bars=config.volume_price_continuation_lookback_bars,
            min_return_pct=config.volume_price_continuation_min_return_pct,
            max_volume_ratio=config.volume_price_continuation_max_volume_ratio,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            pretrade_volume_price_state=str(features["volume_price_state"]),
            pretrade_volume_price_lookback_bars=int(features["actual_bars"]),
            pretrade_price_return_pct=float(features["price_return_pct"]),
            pretrade_volume_ratio_to_prev=float(features["volume_ratio_to_prev"]),
            high_volume_stall_score=80.0,
            price_up_volume_down_score=86.0,
            volume_price_score=74.0,
            post_breakout_volume_persistence_score=66.0,
            vwap_support_score=66.0,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=68.0,
            capital_flow_confidence=0.70,
            sell_pressure_score=62.0,
            down_probability_1d=0.54,
            down_probability_3d=0.55,
        )

        self.assertEqual(features["volume_price_state"], "price_up_volume_down")
        self.assertEqual(_volume_price_distribution_state(signal, config), VOLUME_PRICE_ROTATION)

    def test_price_up_volume_down_distribution_requires_break_outflow_and_down_risk(self) -> None:
        config = DividendTBacktestConfig(attack_confirm_min_buy_strength=66.0)
        distribution = replace(
            _risk_on_confirmed_signal(action="SELL_T_TIMING"),
            pretrade_volume_price_state="price_up_volume_down",
            pretrade_volume_price_lookback_bars=48,
            pretrade_price_return_pct=0.035,
            pretrade_volume_ratio_to_prev=0.78,
            high_volume_stall_score=84.0,
            price_up_volume_down_score=90.0,
            volume_price_score=58.0,
            post_breakout_volume_persistence_score=54.0,
            vwap_support_score=54.0,
            capital_flow_confirmation_state="CONFIRMED_OUTFLOW",
            capital_flow_confirmation_score=42.0,
            capital_flow_score=42.0,
            capital_flow_confidence=0.80,
            force_ratio=0.62,
            force_weighted_score=44.0,
            chan_structure_type="weakening",
            sell_pressure_score=82.0,
            down_probability_1d=0.62,
            down_probability_3d=0.64,
        )

        self.assertEqual(_volume_price_distribution_state(distribution, config), VOLUME_PRICE_DISTRIBUTION)

    def test_only_high_quality_breakout_allows_secondary_risk_on_add(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            min_buy_signal_strength=62.0,
            attack_confirm_min_buy_strength=66.0,
        )
        qualified = replace(
            _risk_on_confirmed_signal(action="BREAKOUT_BUY_TIMING"),
            buy_signal_strength=82.0,
            breakout_score=90.0,
            breakout_confirmed=True,
            volume_price_score=74.0,
            volume_breakout_score=70.0,
            post_breakout_volume_persistence_score=72.0,
            vwap_support_score=72.0,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=68.0,
            capital_flow_confidence=0.70,
            force_weighted_score=60.0,
            sell_pressure_score=66.0,
            down_probability_1d=0.57,
            down_probability_3d=0.58,
        )
        high_quality = replace(
            qualified,
            buy_signal_strength=94.0,
            breakout_score=96.0,
            volume_price_score=84.0,
            volume_breakout_score=82.0,
            post_breakout_volume_persistence_score=80.0,
            vwap_support_score=80.0,
            capital_flow_confirmation_score=80.0,
            capital_flow_confidence=0.82,
            force_weighted_score=76.0,
            sell_pressure_score=48.0,
            down_probability_1d=0.48,
            down_probability_3d=0.50,
        )

        self.assertFalse(_high_quality_breakout_add_signal(qualified, config))
        self.assertFalse(_risk_on_secondary_add_confirmation_signal(qualified, config))
        self.assertTrue(_high_quality_breakout_add_signal(high_quality, config))
        self.assertTrue(_risk_on_secondary_add_confirmation_signal(high_quality, config))

    def test_signal_strength_maps_to_larger_position_and_allows_full_add(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            min_buy_signal_strength=60.0,
            attack_confirm_min_buy_strength=66.0,
            enable_breakout_direct_buy=True,
        )
        weak = replace(
            _risk_on_confirmed_signal(action="BUY_T_TIMING"),
            buy_signal_strength=66.0,
            breakout_score=70.0,
            breakout_confirmed=False,
            chan_buy_point_type="none",
            chan_score=50.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=52.0,
            capital_flow_confidence=0.0,
            force_ratio=1.0,
            force_weighted_score=52.0,
            volume_price_score=52.0,
            volume_breakout_score=50.0,
            post_breakout_volume_persistence_score=50.0,
            vwap_support_score=52.0,
            sell_pressure_score=62.0,
        )
        strong = replace(
            _risk_on_confirmed_signal(action="BREAKOUT_BUY_TIMING"),
            buy_signal_strength=94.0,
            breakout_score=96.0,
            breakout_confirmed=True,
            chan_score=84.0,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=82.0,
            capital_flow_confidence=0.82,
            force_ratio=1.32,
            force_weighted_score=78.0,
            volume_price_score=82.0,
            volume_breakout_score=84.0,
            post_breakout_volume_persistence_score=80.0,
            vwap_support_score=78.0,
            sell_pressure_score=42.0,
        )

        weak_target = _signal_target_position_pct(weak, config)
        strong_target = _signal_target_position_pct(strong, config, attack_state=ATTACK_FULL)

        self.assertGreater(strong_target, weak_target)
        self.assertLess(weak_target, 0.60)
        self.assertEqual(strong_target, 1.00)

    def test_risk_on_continuation_add_does_not_promote_breakout_watch_signal(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            min_buy_signal_strength=62.0,
            risk_on_continuation_min_strength=68.0,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            buy_signal_strength=78.0,
            breakout_score=90.0,
            breakout_confirmed=True,
            volume_price_score=78.0,
            volume_breakout_score=76.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=72.0,
            force_ratio=0.78,
            force_weighted_score=50.0,
            sell_pressure_score=58.0,
        )

        promoted = _apply_risk_on_continuation_add(signal, config)

        self.assertEqual(promoted.action, "WAIT_STRONG_TREND")

    def test_low_force_ratio_does_not_cap_confirmed_volume_price_add(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            min_buy_signal_strength=62.0,
            attack_confirm_min_buy_strength=66.0,
            risk_on_position_target_min_gap_pct=0.05,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="BREAKOUT_BUY_TIMING"),
            buy_signal_strength=86.0,
            breakout_score=94.0,
            breakout_confirmed=True,
            chan_score=82.0,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=80.0,
            capital_flow_confidence=0.78,
            force_ratio=0.72,
            force_weighted_score=76.0,
            volume_price_score=82.0,
            volume_breakout_score=84.0,
            post_breakout_volume_persistence_score=78.0,
            vwap_support_score=76.0,
            sell_pressure_score=54.0,
        )

        target = _risk_on_position_target_pct(
            signal,
            config,
            attack_state=ATTACK_CONFIRMED,
            current_position_pct=0.40,
        )

        self.assertGreaterEqual(target, 0.85)

    def test_breakout_direct_buy_disabled_by_default_but_keeps_risk_on_target_add(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            min_buy_signal_strength=62.0,
            attack_confirm_min_buy_strength=66.0,
            risk_on_position_target_min_gap_pct=0.05,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="BREAKOUT_BUY_TIMING"),
            buy_signal_strength=90.0,
            breakout_score=94.0,
            breakout_confirmed=True,
            chan_score=82.0,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=82.0,
            capital_flow_confidence=0.80,
            force_ratio=1.10,
            force_weighted_score=66.0,
            volume_price_score=82.0,
            volume_breakout_score=82.0,
            post_breakout_volume_persistence_score=78.0,
            vwap_support_score=76.0,
            sell_pressure_score=52.0,
            down_probability_1d=0.46,
            down_probability_3d=0.47,
        )

        direct_target = _signal_target_position_pct(signal, config, attack_state=ATTACK_BETA_HOLD)
        risk_on_target = _risk_on_position_target_pct(
            signal,
            config,
            attack_state=ATTACK_BETA_HOLD,
            current_position_pct=0.30,
        )

        self.assertEqual(direct_target, 0.0)
        self.assertGreaterEqual(risk_on_target, config.risk_on_mid_position_add_cap_pct)

    def test_breakout_direct_buy_probe_mode_caps_optional_entry(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            min_buy_signal_strength=62.0,
            attack_confirm_min_buy_strength=66.0,
            breakout_direct_buy_probe_target_pct=0.30,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="BREAKOUT_BUY_TIMING"),
            buy_signal_strength=90.0,
            breakout_score=94.0,
            breakout_confirmed=True,
            chan_score=82.0,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=82.0,
            capital_flow_confidence=0.80,
            force_ratio=1.10,
            force_weighted_score=66.0,
            volume_price_score=82.0,
            volume_breakout_score=82.0,
            post_breakout_volume_persistence_score=78.0,
            vwap_support_score=76.0,
            sell_pressure_score=52.0,
            down_probability_1d=0.46,
            down_probability_3d=0.47,
        )

        target = _signal_target_position_pct(signal, config, attack_state=ATTACK_CONFIRMED)

        self.assertGreater(target, 0.0)
        self.assertLessEqual(target, config.breakout_direct_buy_probe_target_pct)

    def test_risk_on_position_target_engine_sets_target_from_confirmations_and_gap(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            risk_on_position_target_min_gap_pct=0.05,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            buy_signal_strength=49.0,
            breakout_score=90.0,
            breakout_confirmed=True,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=78.0,
            capital_flow_confidence=0.76,
            force_ratio=0.72,
            force_weighted_score=48.0,
            volume_price_score=80.0,
            volume_breakout_score=78.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=74.0,
            sell_pressure_score=56.0,
        )

        target = _risk_on_position_target_pct(
            signal,
            config,
            attack_state=ATTACK_INACTIVE,
            current_position_pct=0.18,
        )

        self.assertGreaterEqual(target, 0.60)
        self.assertLessEqual(target, config.risk_on_low_position_add_cap_pct)

    def test_risk_on_position_target_engine_only_fills_high_position_on_extreme_confirmation(self) -> None:
        config = DividendTBacktestConfig(
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            risk_on_position_target_min_gap_pct=0.05,
        )
        weak_full_signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            buy_signal_strength=82.0,
            breakout_score=90.0,
            breakout_confirmed=True,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=78.0,
            capital_flow_confidence=0.76,
            volume_price_score=80.0,
            volume_breakout_score=78.0,
            post_breakout_volume_persistence_score=76.0,
            vwap_support_score=74.0,
            sell_pressure_score=56.0,
            down_probability_1d=0.48,
            down_probability_3d=0.50,
        )
        weak_target = _risk_on_position_target_pct(
            weak_full_signal,
            config,
            attack_state=ATTACK_FULL,
            current_position_pct=0.78,
        )
        self.assertEqual(weak_target, 0.0)

        strong_full_signal = replace(
            weak_full_signal,
            buy_signal_strength=100.0,
            breakout_score=100.0,
            vwap_support_score=92.0,
            volume_price_score=92.0,
            volume_breakout_score=92.0,
            post_breakout_volume_persistence_score=92.0,
            capital_flow_score=90.0,
            capital_flow_confirmation_score=92.0,
            capital_flow_confidence=0.92,
            force_ratio=1.45,
            force_weighted_score=90.0,
            attention_score=92.0,
            sell_pressure_score=40.0,
            up_probability_1d=0.66,
            up_probability_3d=0.66,
            down_probability_1d=0.42,
            down_probability_3d=0.44,
        )
        strong_target = _risk_on_position_target_pct(
            strong_full_signal,
            config,
            attack_state=ATTACK_FULL,
            current_position_pct=0.78,
        )
        self.assertEqual(strong_target, config.max_signal_position_pct)

    def test_core_position_floor_protects_trend_core_from_sell_t(self) -> None:
        config = DividendTBacktestConfig(
            initial_cash=100_000,
            initial_base_position_pct=0.10,
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            enable_a_share_constraints=False,
            enable_t_sell=True,
            enable_core_position_floor=True,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="SELL_T_TIMING"),
            breakout_confirmed=False,
            breakout_score=72.0,
            chan_buy_point_type="none",
            chan_score=58.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=50.0,
            capital_flow_confidence=0.0,
            force_ratio=0.72,
            force_weighted_score=46.0,
            volume_price_score=58.0,
            volume_breakout_score=52.0,
            post_breakout_volume_persistence_score=54.0,
            vwap_support_score=54.0,
            sell_pressure_score=80.0,
        )

        state = _execute_action(
            action="SELL_T_TIMING",
            execution={"timestamp": "2026-06-26 10:05:00", "open": 10.0, "close": 10.0, "low": 9.9},
            signal=signal,
            equity_before=100_000.0,
            cash=10_000.0,
            base_shares=1_000,
            base_locked_shares=0,
            t_shares=8_000,
            t_locked_shares=0,
            t_cost_basis=79_000.0,
            breakout_t_shares=0,
            breakout_t_locked_shares=0,
            breakout_t_cost_basis=0.0,
            pending_buyback_shares=0,
            pending_reverse_proceeds=0.0,
            pending_buyback_target_price=None,
            attack_state=ATTACK_CONFIRMED,
            active_peak_profit_pct=0.01,
            constraints=TradeExecutionConstraints(),
            config=config,
            core_position_floor_pct=0.85,
        )

        self.assertIsNotNone(state["trade"])
        self.assertEqual(state["t_shares"], 7_500)

    def test_t_sell_is_execution_disabled_by_default(self) -> None:
        config = DividendTBacktestConfig(
            initial_cash=100_000,
            initial_base_position_pct=0.10,
            t_trade_pct=1.00,
            max_signal_position_pct=1.00,
            enable_a_share_constraints=False,
        )
        state = _execute_action(
            action="SELL_T_TIMING",
            execution={"timestamp": "2026-06-26 10:05:00", "open": 10.0, "close": 10.0, "low": 9.9},
            signal=_risk_on_confirmed_signal(action="SELL_T_TIMING"),
            equity_before=100_000.0,
            cash=10_000.0,
            base_shares=1_000,
            base_locked_shares=0,
            t_shares=8_000,
            t_locked_shares=0,
            t_cost_basis=79_000.0,
            breakout_t_shares=0,
            breakout_t_locked_shares=0,
            breakout_t_cost_basis=0.0,
            pending_buyback_shares=0,
            pending_reverse_proceeds=0.0,
            pending_buyback_target_price=None,
            attack_state=ATTACK_CONFIRMED,
            active_peak_profit_pct=0.01,
            constraints=TradeExecutionConstraints(),
            config=config,
            core_position_floor_pct=0.0,
        )

        self.assertIsNone(state["trade"])
        self.assertEqual(state["blocked"], "SELL_T_TIMING_T_MODE_BLOCKED")
        self.assertEqual(state["t_shares"], 8_000)

    def test_beta_hold_exit_requires_confirmation_before_leaving_state(self) -> None:
        config = DividendTBacktestConfig(beta_hold_exit_confirm_bars=3)
        signal = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            capital_flow_confirmation_state="CONFIRMED_OUTFLOW",
            capital_flow_confirmation_score=42.0,
            capital_flow_score=42.0,
            capital_flow_confidence=0.80,
            chan_structure_type="breakdown",
            chan_sell_point_type="sell3",
            post_breakout_volume_persistence_score=50.0,
            vwap_support_score=50.0,
            sell_pressure_score=82.0,
            down_probability_1d=0.62,
            down_probability_3d=0.63,
        )

        unconfirmed_state, unconfirmed_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_BETA_HOLD,
            confirm_streak=3,
            state_age_bars=120,
            active_profit_pct=0.03,
            active_peak_profit_pct=0.10,
            beta_hold_exit_confirmed=False,
        )
        confirmed_state, confirmed_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_BETA_HOLD,
            confirm_streak=3,
            state_age_bars=120,
            active_profit_pct=0.03,
            active_peak_profit_pct=0.10,
            beta_hold_exit_confirmed=True,
        )

        self.assertEqual(unconfirmed_state, ATTACK_BETA_HOLD)
        self.assertGreaterEqual(unconfirmed_streak, 3)
        self.assertEqual(confirmed_state, ATTACK_INACTIVE)
        self.assertEqual(confirmed_streak, 0)

    def test_beta_hold_soft_exit_requires_confirmation_after_min_hold(self) -> None:
        config = DividendTBacktestConfig(beta_hold_soft_exit_confirm_bars=4)
        signal = replace(
            _risk_on_confirmed_signal(action="SELL_T_TIMING"),
            trend_state="RANGE",
            buy_signal_strength=50.0,
            breakout_confirmed=False,
            breakout_score=72.0,
            chan_buy_point_type="none",
            chan_score=58.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=50.0,
            capital_flow_confidence=0.0,
            volume_price_score=54.0,
            volume_breakout_score=50.0,
            post_breakout_volume_persistence_score=52.0,
            vwap_support_score=52.0,
            sell_pressure_score=72.0,
            down_probability_1d=0.55,
            down_probability_3d=0.56,
        )

        unconfirmed_state, unconfirmed_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_BETA_HOLD,
            confirm_streak=3,
            state_age_bars=config.beta_hold_min_bars + 1,
            active_profit_pct=0.02,
            active_peak_profit_pct=0.08,
            beta_hold_soft_exit_confirmed=False,
        )
        confirmed_state, confirmed_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_BETA_HOLD,
            confirm_streak=3,
            state_age_bars=config.beta_hold_min_bars + 1,
            active_profit_pct=0.02,
            active_peak_profit_pct=0.08,
            beta_hold_soft_exit_confirmed=True,
        )

        self.assertEqual(unconfirmed_state, ATTACK_BETA_HOLD)
        self.assertGreaterEqual(unconfirmed_streak, 3)
        self.assertEqual(confirmed_state, ATTACK_CONFIRMED)
        self.assertGreaterEqual(confirmed_streak, 1)

    def test_beta_hold_distribution_reduce_requires_confirmation(self) -> None:
        config = DividendTBacktestConfig(beta_hold_distribution_confirm_bars=3)
        signal = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            high_volume_stall_score=82.0,
            price_up_volume_down_score=0.0,
            volume_price_score=64.0,
            post_breakout_volume_persistence_score=58.0,
            vwap_support_score=54.0,
            sell_pressure_score=70.0,
            down_probability_1d=0.57,
            down_probability_3d=0.59,
            force_ratio=0.74,
        )

        unconfirmed_state, unconfirmed_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_BETA_HOLD,
            confirm_streak=3,
            state_age_bars=120,
            active_profit_pct=0.08,
            active_peak_profit_pct=0.12,
            beta_hold_distribution_confirmed=False,
        )
        confirmed_state, confirmed_streak = _next_attack_state(
            signal=signal,
            config=config,
            current_state=ATTACK_BETA_HOLD,
            confirm_streak=3,
            state_age_bars=120,
            active_profit_pct=0.08,
            active_peak_profit_pct=0.12,
            beta_hold_distribution_confirmed=True,
        )

        self.assertEqual(unconfirmed_state, ATTACK_BETA_HOLD)
        self.assertGreaterEqual(unconfirmed_streak, 3)
        self.assertEqual(confirmed_state, ATTACK_FULL)
        self.assertGreaterEqual(confirmed_streak, 1)

    def test_beta_hold_unconfirmed_hard_exit_blocks_sell_action(self) -> None:
        config = DividendTBacktestConfig(beta_hold_exit_confirm_bars=4)
        signal = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            capital_flow_confirmation_state="CONFIRMED_OUTFLOW",
            capital_flow_confirmation_score=42.0,
            capital_flow_score=42.0,
            capital_flow_confidence=0.80,
            chan_structure_type="breakdown",
            chan_sell_point_type="sell3",
            post_breakout_volume_persistence_score=50.0,
            vwap_support_score=50.0,
            sell_pressure_score=82.0,
            down_probability_1d=0.62,
            down_probability_3d=0.63,
        )

        blocked = _beta_hold_blocks_soft_exit(
            signal=signal,
            config=config,
            attack_state=ATTACK_BETA_HOLD,
            state_age_bars=config.beta_hold_min_bars + 1,
            active_profit_pct=0.04,
            active_peak_profit_pct=0.12,
            beta_hold_exit_confirmed=False,
        )
        unblocked = _beta_hold_blocks_soft_exit(
            signal=signal,
            config=config,
            attack_state=ATTACK_BETA_HOLD,
            state_age_bars=config.beta_hold_min_bars + 1,
            active_profit_pct=0.04,
            active_peak_profit_pct=0.12,
            beta_hold_exit_confirmed=True,
        )

        self.assertTrue(blocked)
        self.assertFalse(unblocked)

    def test_dynamic_defensive_mode_preserves_existing_attack_state_machine(self) -> None:
        config = DividendTBacktestConfig(strategy_mode="dynamic")
        market_environment = MarketEnvironmentPoint(
            trade_date=date(2026, 6, 26),
            state=MARKET_RISK_OFF,
            score=28.0,
            max_total_position_pct=0.10,
            allow_new_buy=False,
        )
        signal = replace(
            _risk_on_confirmed_signal(action="STOP_T_WAIT"),
            trend_state="DOWNTREND",
            market_regime_state="DEFENSIVE",
            market_environment_state=MARKET_RISK_OFF,
            breakout_confirmed=False,
            breakout_score=44.0,
            chan_buy_point_type="none",
            chan_score=42.0,
            buy_signal_strength=38.0,
            capital_flow_confirmation_state="UNCONFIRMED",
            capital_flow_confirmation_score=35.0,
            capital_flow_confidence=0.0,
        )

        inactive_config = _effective_signal_config(
            config,
            signal=signal,
            market_environment=market_environment,
            attack_state=ATTACK_INACTIVE,
        )
        held_state_config = _effective_signal_config(
            config,
            signal=signal,
            market_environment=market_environment,
            attack_state=ATTACK_WATCH,
        )

        self.assertEqual(inactive_config.strategy_mode, "defensive")
        self.assertFalse(inactive_config.enable_attack_state_machine)
        self.assertEqual(held_state_config.strategy_mode, "defensive")
        self.assertTrue(held_state_config.enable_attack_state_machine)
        self.assertLessEqual(held_state_config.max_signal_position_pct, 0.45)

    def test_risk_on_position_target_engine_adds_on_non_buy_signal(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()
        market_filter = _rising_market_filter()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=1.00,
                max_signal_position_pct=1.00,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=6,
                signal_cache_dir=None,
                enable_market_filter=True,
                market_filter_name=market_filter.name,
                strategy_mode="dynamic",
                risk_on_position_target_min_gap_pct=0.05,
            ),
            engine=_ScriptedRiskOnTargetEngine(),
            market_filter=market_filter,
        )

        target_trades = [trade for trade in result.trades if trade.side == "BUY_RISK_ON_TARGET"]
        self.assertTrue(target_trades)
        self.assertGreater(result.action_counts.get("RISK_ON_TARGET_ADD", 0), 0)

    def test_candidate_entry_builds_start_position_after_selection(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=1.00,
                max_signal_position_pct=1.00,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=6,
                signal_cache_dir=None,
                enable_candidate_entry=True,
                candidate_entry_start_target_pct=0.55,
                candidate_entry_confirm_target_pct=0.55,
            ),
            engine=_ScriptedEngine(),
        )

        start_trades = [trade for trade in result.trades if trade.side == "BUY_CANDIDATE_START"]

        self.assertTrue(start_trades)
        self.assertGreater(result.action_counts.get("CANDIDATE_ENTRY_START", 0), 0)

    def test_candidate_entry_start_respects_market_cap(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()
        market_filter = _constant_market_filter(MARKET_RISK_OFF, cap=0.10)

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=1.00,
                max_signal_position_pct=1.00,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=6,
                signal_cache_dir=None,
                enable_market_filter=True,
                market_filter_name=market_filter.name,
                enable_candidate_entry=True,
                candidate_entry_start_target_pct=0.55,
                candidate_entry_confirm_target_pct=0.55,
            ),
            engine=_ScriptedEngine(),
            market_filter=market_filter,
        )

        start_trades = [trade for trade in result.trades if trade.side == "BUY_CANDIDATE_START"]

        self.assertFalse(start_trades)
        self.assertEqual(result.action_counts.get("CANDIDATE_ENTRY_START", 0), 0)

    def test_candidate_entry_adds_on_first_strong_confirmation(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=1.00,
                max_signal_position_pct=1.00,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=6,
                signal_cache_dir=None,
                enable_candidate_entry=True,
                candidate_entry_start_target_pct=0.10,
                candidate_entry_confirm_target_pct=0.80,
                candidate_entry_confirm_min_strength=45.0,
            ),
            engine=_ScriptedRiskOnTargetEngine(),
        )

        confirm_trades = [trade for trade in result.trades if trade.side == "BUY_CANDIDATE_CONFIRM"]

        self.assertTrue(confirm_trades)
        self.assertGreater(result.action_counts.get("CANDIDATE_ENTRY_CONFIRM_ADD", 0), 0)

    def test_candidate_entry_confirm_requires_real_follow_through_not_market_only(self) -> None:
        config = DividendTBacktestConfig(
            enable_candidate_entry=True,
            candidate_entry_confirm_min_strength=64.0,
            candidate_entry_confirm_min_confirmations=2,
            candidate_entry_confirm_requires_follow_through=True,
            candidate_entry_confirm_market_passthrough=False,
        )
        market_only = replace(
            _risk_on_confirmed_signal(action="WAIT_STRONG_TREND"),
            breakout_score=78.0,
            breakout_confirmed=False,
            volume_price_score=66.0,
            volume_breakout_score=62.0,
            post_breakout_volume_persistence_score=64.0,
            vwap_support_score=70.0,
            capital_flow_confirmation_state="CONFIRMED_INFLOW",
            capital_flow_confirmation_score=72.0,
            capital_flow_confidence=0.72,
        )
        follow_through = replace(
            market_only,
            breakout_score=90.0,
            breakout_confirmed=True,
            volume_price_score=80.0,
            volume_breakout_score=78.0,
            post_breakout_volume_persistence_score=76.0,
        )

        self.assertEqual(market_only.market_environment_state, MARKET_RISK_ON)
        self.assertFalse(_candidate_entry_confirm_signal(market_only, config))
        self.assertTrue(_candidate_entry_confirm_signal(follow_through, config))

    def test_candidate_entry_hold_blocks_soft_exit_after_selection(self) -> None:
        bars = build_sample_cosco_backtest_bars().head(30).copy()

        result = run_cosco_dividend_t_backtest(
            bars,
            config=DividendTBacktestConfig(
                initial_cash=100_000,
                initial_base_position_pct=0.10,
                t_trade_pct=1.00,
                max_signal_position_pct=1.00,
                min_lookback_bars=5,
                max_history_bars=5,
                signal_step_bars=6,
                signal_cache_dir=None,
                enable_candidate_entry=True,
                candidate_entry_start_target_pct=0.55,
                candidate_entry_confirm_target_pct=0.55,
                candidate_entry_min_hold_bars=60,
                candidate_entry_hard_stop_loss_pct=0.50,
            ),
            engine=_ScriptedSoftExitEngine(),
        )

        exit_trades = [trade for trade in result.trades if trade.side in {"SELL_T", "STOP_T"}]

        self.assertFalse(exit_trades)
        self.assertGreater(result.action_counts.get("WAIT_CANDIDATE_ENTRY_HOLD", 0), 0)


class _ScriptedEngine:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, bars, **_kwargs):
        self.calls += 1
        close = float(bars["close"].iloc[-1])
        if self.calls == 1:
            action = "SELL_T_TIMING"
            buyback = round(close * 0.985, 3)
        else:
            action = "WAIT"
            buyback = None
        return SimpleNamespace(
            timestamp=str(bars["timestamp"].iloc[-1]),
            action=action,
            daily_context=SimpleNamespace(
                state="STRONG",
                position_multiplier=1.0,
                fundamental_score=76.0,
                base_position_limit_pct=0.60,
            ),
            intraday_context=SimpleNamespace(state="RESISTANCE_CONFIRMED"),
            trend_probability=SimpleNamespace(
                up_1d=0.50,
                up_3d=0.50,
                down_1d=0.50,
                down_3d=0.50,
                state="RANGE",
            ),
            prices=SimpleNamespace(
                buy_reference_price=None,
                sell_reference_price=round(close, 3),
                buy_back_reference_price=buyback,
                stop_price=round(close * 1.02, 3),
            ),
        )


class _ScriptedBuyEngine:
    def __init__(self, *, strong_main_rise: bool = True) -> None:
        self.calls = 0
        self.strong_main_rise = strong_main_rise

    def evaluate(self, bars, **_kwargs):
        self.calls += 1
        close = float(bars["close"].iloc[-1])
        action = "BUY_T_TIMING" if self.calls == 1 else "WAIT"
        buy_strength = 80.0 if self.strong_main_rise else 72.0
        breakout_score = 86.0 if self.strong_main_rise else 70.0
        volume_score = 78.0 if self.strong_main_rise else 58.0
        return SimpleNamespace(
            timestamp=str(bars["timestamp"].iloc[-1]),
            action=action,
            daily_context=SimpleNamespace(
                state="STRONG",
                position_multiplier=1.0,
                fundamental_score=76.0,
                base_position_limit_pct=0.10,
            ),
            intraday_context=SimpleNamespace(state="SUPPORT_CONFIRMED"),
            trend_state="UPTREND",
            market_regime=SimpleNamespace(
                state="STRONG_TREND",
                base_position_target_pct=0.10,
                t_trade_limit_pct=0.80,
            ),
            multi_period_trend=SimpleNamespace(score=72.0),
            capital_flow=SimpleNamespace(
                score=68.0 if self.strong_main_rise else 54.0,
                confirmation_score=72.0 if self.strong_main_rise else 52.0,
                confirmation_state="CONFIRMED_INFLOW" if self.strong_main_rise else "UNCONFIRMED",
                confidence=0.72 if self.strong_main_rise else 0.20,
                source_type="REAL_MONEY_FLOW",
            ),
            force=SimpleNamespace(force_ratio=1.25, weighted_score=72.0),
            attention=SimpleNamespace(score=70.0),
            certainty=SimpleNamespace(score=68.0),
            memory=SimpleNamespace(score=62.0),
            sell_pressure=SimpleNamespace(score=38.0),
            trend_probability=SimpleNamespace(
                up_1d=0.58,
                up_3d=0.56,
                down_1d=0.46,
                down_3d=0.47,
                state="UP_PROBABLE",
            ),
            breakout_setup=SimpleNamespace(
                score=breakout_score,
                state="BREAKOUT_WATCH" if self.strong_main_rise else "NONE",
                breakout_confirmed=False,
                pre_breakout_watch=self.strong_main_rise,
            ),
            volume_price_structure=SimpleNamespace(
                score=volume_score,
                state="VOLUME_BREAKOUT" if self.strong_main_rise else "NEUTRAL",
                volume_breakout_score=76.0 if self.strong_main_rise else 54.0,
                low_volume_pullback_score=66.0 if self.strong_main_rise else 52.0,
                high_volume_stall_score=28.0,
                price_up_volume_down_score=20.0,
                vwap_support_score=74.0 if self.strong_main_rise else 56.0,
                post_breakout_volume_persistence_score=74.0 if self.strong_main_rise else 54.0,
            ),
            chan_structure=SimpleNamespace(
                score=78.0,
                structure_type="pivot_up",
                trend_direction="up",
                divergence_type="none",
                buy_point_type="buy3",
                sell_point_type="none",
                pivot_low=round(close * 0.96, 3),
                pivot_high=round(close * 1.04, 3),
                invalid_price=round(close * 0.95, 3),
            ),
            signal_strength=SimpleNamespace(
                score=buy_strength,
                kelly_fraction=0.30,
                estimated_win_rate=0.55,
            ),
            prices=SimpleNamespace(
                buy_reference_price=round(close, 3),
                sell_reference_price=round(close * 1.02, 3),
                buy_back_reference_price=None,
                stop_price=round(close * 0.98, 3),
            ),
        )


class _ScriptedRiskOnTargetEngine:
    def evaluate(self, bars, **_kwargs):
        close = float(bars["close"].iloc[-1])
        return SimpleNamespace(
            timestamp=str(bars["timestamp"].iloc[-1]),
            action="WAIT_STRONG_TREND",
            daily_context=SimpleNamespace(
                state="STRONG",
                score=76.0,
                position_multiplier=1.0,
                fundamental_score=78.0,
                base_position_limit_pct=0.10,
            ),
            intraday_context=SimpleNamespace(state="BREAKOUT_CONFIRMED"),
            trend_state="UPTREND",
            market_regime=SimpleNamespace(
                state="STRONG_TREND",
                base_position_target_pct=0.10,
                t_trade_limit_pct=1.00,
                active_position_cap_pct=0.90,
                max_total_position_pct=1.00,
            ),
            multi_period_trend=SimpleNamespace(score=78.0),
            capital_flow=SimpleNamespace(
                score=76.0,
                confirmation_score=78.0,
                confirmation_state="CONFIRMED_INFLOW",
                confidence=0.76,
                source_type="REAL_MONEY_FLOW",
            ),
            force=SimpleNamespace(force_ratio=0.72, weighted_score=48.0),
            attention=SimpleNamespace(score=76.0),
            certainty=SimpleNamespace(score=72.0),
            memory=SimpleNamespace(score=66.0),
            sell_pressure=SimpleNamespace(score=56.0),
            trend_probability=SimpleNamespace(
                up_1d=0.56,
                up_3d=0.56,
                down_1d=0.46,
                down_3d=0.47,
                state="UP_PROBABLE",
            ),
            breakout_setup=SimpleNamespace(
                score=90.0,
                state="BREAKOUT_CONFIRMED",
                breakout_confirmed=True,
                pre_breakout_watch=False,
            ),
            volume_price_structure=SimpleNamespace(
                score=80.0,
                state="VOLUME_BREAKOUT",
                volume_breakout_score=78.0,
                low_volume_pullback_score=62.0,
                high_volume_stall_score=32.0,
                price_up_volume_down_score=22.0,
                vwap_support_score=74.0,
                post_breakout_volume_persistence_score=76.0,
            ),
            chan_structure=SimpleNamespace(
                score=80.0,
                structure_type="pivot_up",
                trend_direction="up",
                divergence_type="none",
                buy_point_type="buy3",
                sell_point_type="none",
                pivot_low=round(close * 0.96, 3),
                pivot_high=round(close * 1.04, 3),
                invalid_price=round(close * 0.95, 3),
            ),
            signal_strength=SimpleNamespace(
                score=49.0,
                kelly_fraction=0.08,
                estimated_win_rate=0.52,
            ),
            prices=SimpleNamespace(
                buy_reference_price=None,
                sell_reference_price=round(close * 1.02, 3),
                buy_back_reference_price=None,
                stop_price=round(close * 0.96, 3),
            ),
        )


class _ScriptedSoftExitEngine:
    def evaluate(self, bars, **_kwargs):
        close = float(bars["close"].iloc[-1])
        return SimpleNamespace(
            timestamp=str(bars["timestamp"].iloc[-1]),
            action="WAIT_DAILY_WEAK",
            daily_context=SimpleNamespace(
                state="WEAK",
                position_multiplier=0.5,
                fundamental_score=76.0,
                base_position_limit_pct=0.10,
            ),
            intraday_context=SimpleNamespace(state="RANGE"),
            trend_state="RANGE",
            market_regime=SimpleNamespace(
                state="TREND_WATCH",
                base_position_target_pct=0.10,
                t_trade_limit_pct=1.00,
                active_position_cap_pct=0.90,
                max_total_position_pct=1.00,
            ),
            multi_period_trend=SimpleNamespace(score=58.0),
            capital_flow=SimpleNamespace(
                score=56.0,
                confirmation_score=58.0,
                confirmation_state="UNCONFIRMED",
                confidence=0.30,
                source_type="REAL_MONEY_FLOW",
            ),
            force=SimpleNamespace(force_ratio=0.96, weighted_score=54.0),
            attention=SimpleNamespace(score=54.0),
            certainty=SimpleNamespace(score=52.0),
            memory=SimpleNamespace(score=52.0),
            sell_pressure=SimpleNamespace(score=58.0),
            trend_probability=SimpleNamespace(
                up_1d=0.50,
                up_3d=0.50,
                down_1d=0.52,
                down_3d=0.53,
                state="RANGE",
            ),
            breakout_setup=SimpleNamespace(
                score=50.0,
                state="NONE",
                breakout_confirmed=False,
                pre_breakout_watch=False,
            ),
            volume_price_structure=SimpleNamespace(
                score=54.0,
                state="NEUTRAL",
                volume_breakout_score=50.0,
                low_volume_pullback_score=58.0,
                high_volume_stall_score=38.0,
                price_up_volume_down_score=38.0,
                vwap_support_score=58.0,
                post_breakout_volume_persistence_score=52.0,
            ),
            chan_structure=SimpleNamespace(
                score=54.0,
                structure_type="range",
                trend_direction="range",
                divergence_type="none",
                buy_point_type="none",
                sell_point_type="none",
                pivot_low=round(close * 0.95, 3),
                pivot_high=round(close * 1.05, 3),
                invalid_price=round(close * 0.92, 3),
            ),
            signal_strength=SimpleNamespace(
                score=0.0,
                kelly_fraction=0.0,
                estimated_win_rate=0.50,
            ),
            prices=SimpleNamespace(
                buy_reference_price=None,
                sell_reference_price=round(close * 1.01, 3),
                buy_back_reference_price=None,
                stop_price=round(close * 0.92, 3),
            ),
        )


class _ScriptedBuyThenStopEngine:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, bars, **_kwargs):
        self.calls += 1
        close = float(bars["close"].iloc[-1])
        action = "BUY_T_TIMING" if self.calls == 1 else "STOP_T_WAIT"
        return SimpleNamespace(
            timestamp=str(bars["timestamp"].iloc[-1]),
            action=action,
            daily_context=SimpleNamespace(
                state="STRONG",
                position_multiplier=1.0,
                fundamental_score=76.0,
                base_position_limit_pct=0.10,
            ),
            intraday_context=SimpleNamespace(state="SUPPORT_CONFIRMED"),
            trend_state="UPTREND" if self.calls == 1 else "DOWNTREND",
            market_regime=SimpleNamespace(
                state="STRONG_TREND" if self.calls == 1 else "DEFENSIVE",
                base_position_target_pct=0.10 if self.calls == 1 else 0.05,
                t_trade_limit_pct=0.80 if self.calls == 1 else 0.0,
            ),
            multi_period_trend=SimpleNamespace(score=72.0),
            capital_flow=SimpleNamespace(
                score=68.0 if self.calls == 1 else 42.0,
                confirmation_score=72.0 if self.calls == 1 else 40.0,
                confirmation_state="CONFIRMED_INFLOW" if self.calls == 1 else "UNCONFIRMED",
                confidence=0.72 if self.calls == 1 else 0.10,
                source_type="REAL_MONEY_FLOW",
            ),
            force=SimpleNamespace(force_ratio=1.25, weighted_score=72.0),
            attention=SimpleNamespace(score=70.0),
            certainty=SimpleNamespace(score=68.0),
            memory=SimpleNamespace(score=62.0),
            sell_pressure=SimpleNamespace(score=38.0 if self.calls == 1 else 90.0),
            trend_probability=SimpleNamespace(
                up_1d=0.58 if self.calls == 1 else 0.40,
                up_3d=0.56 if self.calls == 1 else 0.40,
                down_1d=0.46 if self.calls == 1 else 0.72,
                down_3d=0.47 if self.calls == 1 else 0.72,
                state="UP_PROBABLE" if self.calls == 1 else "DOWN_RISK",
            ),
            breakout_setup=SimpleNamespace(
                score=86.0 if self.calls == 1 else 42.0,
                state="BREAKOUT_WATCH" if self.calls == 1 else "NONE",
                breakout_confirmed=False,
                pre_breakout_watch=self.calls == 1,
            ),
            volume_price_structure=SimpleNamespace(
                score=78.0 if self.calls == 1 else 42.0,
                state="VOLUME_BREAKOUT" if self.calls == 1 else "WEAK",
                volume_breakout_score=76.0 if self.calls == 1 else 40.0,
                low_volume_pullback_score=66.0 if self.calls == 1 else 40.0,
                high_volume_stall_score=28.0 if self.calls == 1 else 76.0,
                price_up_volume_down_score=20.0 if self.calls == 1 else 80.0,
                vwap_support_score=74.0 if self.calls == 1 else 42.0,
                post_breakout_volume_persistence_score=74.0 if self.calls == 1 else 40.0,
            ),
            chan_structure=SimpleNamespace(
                score=78.0 if self.calls == 1 else 42.0,
                structure_type="pivot_up" if self.calls == 1 else "breakdown",
                trend_direction="up" if self.calls == 1 else "down",
                divergence_type="none",
                buy_point_type="buy3" if self.calls == 1 else "none",
                sell_point_type="none" if self.calls == 1 else "sell3",
                pivot_low=round(close * 0.96, 3),
                pivot_high=round(close * 1.04, 3),
                invalid_price=round(close * 0.95, 3),
            ),
            signal_strength=SimpleNamespace(
                score=80.0 if self.calls == 1 else 0.0,
                kelly_fraction=0.30 if self.calls == 1 else 0.0,
                estimated_win_rate=0.55 if self.calls == 1 else 0.0,
            ),
            prices=SimpleNamespace(
                buy_reference_price=round(close, 3) if self.calls == 1 else None,
                sell_reference_price=round(close * 1.02, 3),
                buy_back_reference_price=None,
                stop_price=round(close * 0.98, 3),
            ),
        )


class _ScriptedStrongTrendEngine:
    def evaluate(self, bars, **_kwargs):
        close = float(bars["close"].iloc[-1])
        return SimpleNamespace(
            timestamp=str(bars["timestamp"].iloc[-1]),
            action="WAIT_STRONG_TREND",
            trend_state="UPTREND",
            daily_context=SimpleNamespace(
                state="STRONG",
                position_multiplier=1.0,
                fundamental_score=78.0,
                base_position_limit_pct=0.80,
            ),
            intraday_context=SimpleNamespace(state="UNCONFIRMED"),
            market_regime=SimpleNamespace(
                state="STRONG_TREND",
                base_position_target_pct=0.10,
                t_trade_limit_pct=0.80,
            ),
            trend_probability=SimpleNamespace(
                up_1d=0.55,
                up_3d=0.55,
                down_1d=0.48,
                down_3d=0.48,
                state="UP_PROBABLE",
            ),
            signal_strength=SimpleNamespace(
                score=49.0,
                kelly_fraction=0.0,
                estimated_win_rate=0.0,
            ),
            prices=SimpleNamespace(
                buy_reference_price=None,
                sell_reference_price=None,
                buy_back_reference_price=None,
                stop_price=round(close * 0.98, 3),
            ),
        )


class _ScriptedRebalanceChurnEngine:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, bars, **_kwargs):
        self.calls += 1
        close = float(bars["close"].iloc[-1])
        defensive = self.calls % 2 == 0
        return SimpleNamespace(
            timestamp=str(bars["timestamp"].iloc[-1]),
            action="WAIT",
            trend_state="DOWNTREND" if defensive else "UPTREND",
            daily_context=SimpleNamespace(
                state="WEAK" if defensive else "STRONG",
                position_multiplier=0.6 if defensive else 1.0,
                fundamental_score=76.0,
                base_position_limit_pct=0.10,
            ),
            intraday_context=SimpleNamespace(state="UNCONFIRMED"),
            market_regime=SimpleNamespace(
                state="DEFENSIVE" if defensive else "STRONG_TREND",
                base_position_target_pct=0.05 if defensive else 0.10,
                t_trade_limit_pct=0.0 if defensive else 0.80,
            ),
            trend_probability=SimpleNamespace(
                up_1d=0.48 if defensive else 0.56,
                up_3d=0.48 if defensive else 0.55,
                down_1d=0.58 if defensive else 0.46,
                down_3d=0.58 if defensive else 0.46,
                state="DOWN_RISK" if defensive else "UP_PROBABLE",
            ),
            signal_strength=SimpleNamespace(
                score=0.0,
                kelly_fraction=0.0,
                estimated_win_rate=0.0,
            ),
            prices=SimpleNamespace(
                buy_reference_price=None,
                sell_reference_price=None,
                buy_back_reference_price=None,
                stop_price=round(close * 0.98, 3),
            ),
        )


class _ScriptedBreakoutProfitEngine:
    def __init__(self, *, weaken_after_first: bool = True) -> None:
        self.calls = 0
        self.weaken_after_first = weaken_after_first

    def evaluate(self, bars, **_kwargs):
        self.calls += 1
        close = float(bars["close"].iloc[-1])
        action = "BREAKOUT_BUY_TIMING" if self.calls == 1 else "WAIT_STRONG_TREND"
        weakening = self.weaken_after_first and self.calls > 1
        return SimpleNamespace(
            timestamp=str(bars["timestamp"].iloc[-1]),
            action=action,
            daily_context=SimpleNamespace(
                state="STRONG",
                position_multiplier=1.0,
                fundamental_score=78.0,
                base_position_limit_pct=0.10,
            ),
            intraday_context=SimpleNamespace(state="BREAKOUT_CONFIRMED" if self.calls == 1 else "UNCONFIRMED"),
            trend_state="UPTREND",
            market_regime=SimpleNamespace(
                state="BREAKOUT_ATTACK",
                base_position_target_pct=0.10,
                t_trade_limit_pct=0.80,
            ),
            multi_period_trend=SimpleNamespace(score=78.0),
            capital_flow=SimpleNamespace(
                score=76.0 if not weakening else 48.0,
                confirmation_score=82.0 if not weakening else 48.0,
                confirmation_state="CONFIRMED_INFLOW" if not weakening else "UNCONFIRMED",
                confidence=0.82 if not weakening else 0.10,
                source_type="REAL_MONEY_FLOW",
            ),
            force=SimpleNamespace(force_ratio=0.72 if weakening else 1.35, weighted_score=48.0 if weakening else 76.0),
            attention=SimpleNamespace(score=76.0),
            certainty=SimpleNamespace(score=72.0),
            memory=SimpleNamespace(score=66.0),
            sell_pressure=SimpleNamespace(score=66.0 if weakening else 42.0),
            trend_probability=SimpleNamespace(
                up_1d=0.58,
                up_3d=0.56,
                down_1d=0.45,
                down_3d=0.46,
                state="UP_PROBABLE",
            ),
            breakout_setup=SimpleNamespace(
                score=94.0 if not weakening else 76.0,
                state="BREAKOUT_CONFIRMED" if not weakening else "BREAKOUT_FADE",
                breakout_confirmed=not weakening,
                pre_breakout_watch=False,
            ),
            volume_price_structure=SimpleNamespace(
                score=84.0 if not weakening else 62.0,
                state="VOLUME_BREAKOUT" if not weakening else "WEAK_FOLLOW",
                volume_breakout_score=84.0 if not weakening else 58.0,
                low_volume_pullback_score=66.0,
                high_volume_stall_score=34.0 if not weakening else 66.0,
                price_up_volume_down_score=22.0 if not weakening else 72.0,
                vwap_support_score=80.0 if not weakening else 58.0,
                post_breakout_volume_persistence_score=80.0 if not weakening else 58.0,
            ),
            chan_structure=SimpleNamespace(
                score=82.0 if not weakening else 56.0,
                structure_type="pivot_up" if not weakening else "range",
                trend_direction="up" if not weakening else "range",
                divergence_type="none",
                buy_point_type="buy3" if not weakening else "none",
                sell_point_type="none",
                pivot_low=round(close * 0.96, 3),
                pivot_high=round(close * 1.05, 3),
                invalid_price=round(close * 0.95, 3),
            ),
            signal_strength=SimpleNamespace(
                score=88.0 if not weakening else 48.0,
                kelly_fraction=0.32 if not weakening else 0.0,
                estimated_win_rate=0.58 if not weakening else 0.50,
            ),
            prices=SimpleNamespace(
                buy_reference_price=round(close, 3),
                sell_reference_price=round(close * 1.02, 3),
                buy_back_reference_price=None,
                stop_price=round(close * 0.98, 3),
            ),
        )


def _short_sample():
    return build_sample_cosco_backtest_bars().head(96).copy()


def _risk_on_confirmed_signal(*, action: str) -> BacktestSignal:
    return BacktestSignal(
        timestamp="2026-06-26 10:00:00",
        action=action,
        daily_state="STRONG",
        intraday_state="BREAKOUT_CONFIRMED",
        trend_state="UPTREND",
        market_regime_state="BREAKOUT_ATTACK",
        position_multiplier=1.0,
        fundamental_score=78.0,
        base_position_limit_pct=0.10,
        base_position_target_pct=0.10,
        t_trade_limit_pct=1.0,
        active_position_cap_pct=0.90,
        max_total_position_pct=1.0,
        capital_flow_confirmation_score=72.0,
        capital_flow_confirmation_state="CONFIRMED_INFLOW",
        capital_flow_confidence=0.72,
        force_ratio=1.05,
        force_weighted_score=62.0,
        sell_pressure_score=58.0,
        down_probability_1d=0.46,
        down_probability_3d=0.48,
        buy_signal_strength=78.0,
        breakout_score=88.0,
        breakout_confirmed=True,
        chan_buy_point_type="buy3",
        chan_score=78.0,
        market_environment_state=MARKET_RISK_ON,
        market_environment_score=72.0,
    )


def _falling_market_filter():
    import pandas as pd

    dates = pd.bdate_range("2026-04-01", "2026-05-25")
    frame = pd.DataFrame(
        {
            "timestamp": dates + pd.Timedelta(hours=15),
            "close": [100.0 - index * 1.2 for index in range(len(dates))],
        }
    )
    return build_market_environment_filter(frame, name="falling-test")


def _rising_market_filter():
    import pandas as pd

    dates = pd.bdate_range("2026-01-01", periods=100)
    frame = pd.DataFrame(
        {
            "timestamp": dates + pd.Timedelta(hours=15),
            "close": [100.0 + index * 0.8 for index in range(len(dates))],
        }
    )
    return build_market_environment_filter(frame, name="rising-test")


def _constant_market_filter(state: str, *, cap: float) -> MarketEnvironmentFilter:
    return MarketEnvironmentFilter(
        name=f"constant-{state.lower()}",
        points=(
            MarketEnvironmentPoint(
                trade_date=date.min,
                state=state,
                score=55.0,
                max_total_position_pct=cap,
                allow_new_buy=True,
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
