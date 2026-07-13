#!/usr/bin/env python3
"""Run the optimized COSCO dividend T timing backtest."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.a_share_bars import fetch_a_share_5min_with_fallback
from market_regime_alpha.dividend_t.backtest import (
    DEFAULT_SIGNAL_CACHE_DIR,
    DEFAULT_SIGNAL_HISTORY_BARS,
    DividendTBacktestConfig,
    build_sample_cosco_backtest_bars,
    format_cosco_backtest_report,
    load_5min_bars_csv,
    run_cosco_dividend_t_backtest,
)
from market_regime_alpha.dividend_t.cosco_timing import CoscoTimingEngine
from market_regime_alpha.dividend_t.signal_intent import MACD_PROFILE_NAMES, macd_policy_config_for_profile


DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports" / "backtests" / "cosco_dividend_t_backtest.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run COSCO long-term dividend T model backtest.")
    parser.add_argument("--data", type=Path, help="5-minute OHLCV CSV path. If omitted, use built-in sample data.")
    parser.add_argument("--symbol", default="601919.SH", help="Symbol to backtest.")
    parser.add_argument("--provider", choices=["auto", "qmt", "tencent", "eastmoney", "akshare", "baostock", "tushare"], help="Fetch 5-minute bars from a provider instead of CSV/sample.")
    parser.add_argument("--days", type=int, default=45, help="Provider fetch lookback days.")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--base-pct", type=float, default=0.10, help="Initial base position ratio, constrained to 0.05-0.10.")
    parser.add_argument("--t-pct", type=float, default=1.00, help="Legacy alias for the default total position cap after a BUY signal, constrained to <=1.00.")
    parser.add_argument("--min-t-pct", type=float, default=0.03, help="Minimum active-position probe increment above the base position.")
    parser.add_argument("--max-signal-position-pct", type=float, default=1.00)
    parser.add_argument("--strong-confirm-signals", type=int, default=3)
    parser.add_argument("--trend-exit-confirm-signals", type=int, default=4)
    parser.add_argument("--defensive-confirm-signals", type=int, default=2)
    parser.add_argument("--kelly-scale", type=float, default=0.65)
    parser.add_argument("--min-buy-strength", type=float, default=66.0)
    parser.add_argument("--min-lookback-bars", type=int, default=48)
    parser.add_argument("--max-history-bars", type=int, default=DEFAULT_SIGNAL_HISTORY_BARS)
    parser.add_argument("--signal-step-bars", type=int, default=1, help="Evaluate one signal every N bars. 1 means every 5-minute bar.")
    parser.add_argument("--base-rebalance-cooldown-bars", type=int, default=48, help="Cooldown before another base rebalance. 48 means about one trading day.")
    parser.add_argument("--no-reverse-t", action="store_true", help="Disable reverse-T sell and buyback loop.")
    parser.add_argument("--disable-profit-protection", action="store_true", help="Disable breakout profit protection.")
    parser.add_argument("--profit-protect-trigger-pct", type=float, default=0.012)
    parser.add_argument("--profit-protect-sell-fraction", type=float, default=0.50)
    parser.add_argument("--disable-attack-state-machine", action="store_true", help="Disable breakout attack state machine.")
    parser.add_argument("--attack-watch-position-pct", type=float, default=0.25)
    parser.add_argument("--attack-confirm-position-pct", type=float, default=0.70)
    parser.add_argument("--attack-full-position-pct", type=float, default=1.00)
    parser.add_argument("--attack-confirm-min-breakout-score", type=float, default=92.0)
    parser.add_argument("--attack-confirm-min-buy-strength", type=float, default=70.0)
    parser.add_argument("--attack-full-confirm-signals", type=int, default=1)
    parser.add_argument("--trend-follow-min-hold-bars", type=int, default=18)
    parser.add_argument("--confirmed-flow-position-bonus-pct", type=float, default=0.15)
    parser.add_argument("--signal-cache-dir", type=Path, default=DEFAULT_SIGNAL_CACHE_DIR)
    parser.add_argument("--signal-cache-tag", default="profile")
    parser.add_argument("--signal-cache-save-every", type=int, default=200)
    parser.add_argument("--no-signal-cache", action="store_true")
    parser.add_argument(
        "--macd-profile",
        choices=MACD_PROFILE_NAMES,
        default="baseline",
        help="MACD research profile; production default remains baseline.",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    if args.provider:
        bars = _fetch_provider_bars(args.symbol, provider=args.provider, days=args.days)
        data_note = f"provider={args.provider}"
    elif args.data:
        bars = load_5min_bars_csv(args.data, symbol=args.symbol)
        data_note = str(args.data)
    else:
        bars = build_sample_cosco_backtest_bars()
        data_note = "built-in deterministic sample"

    config = DividendTBacktestConfig(
        initial_cash=args.initial_cash,
        initial_base_position_pct=args.base_pct,
        t_trade_pct=args.t_pct,
        min_t_trade_pct=args.min_t_pct,
        max_signal_position_pct=args.max_signal_position_pct,
        strong_trend_confirm_signals=args.strong_confirm_signals,
        trend_exit_confirm_signals=args.trend_exit_confirm_signals,
        defensive_confirm_signals=args.defensive_confirm_signals,
        kelly_fraction_scale=args.kelly_scale,
        min_buy_signal_strength=args.min_buy_strength,
        min_lookback_bars=args.min_lookback_bars,
        max_history_bars=args.max_history_bars,
        signal_step_bars=args.signal_step_bars,
        base_rebalance_cooldown_bars=args.base_rebalance_cooldown_bars,
        allow_reverse_t=not args.no_reverse_t,
        enable_profit_protection=not args.disable_profit_protection,
        profit_protect_trigger_pct=args.profit_protect_trigger_pct,
        profit_protect_sell_fraction=args.profit_protect_sell_fraction,
        enable_attack_state_machine=not args.disable_attack_state_machine,
        attack_watch_position_pct=args.attack_watch_position_pct,
        attack_confirm_position_pct=args.attack_confirm_position_pct,
        attack_full_position_pct=args.attack_full_position_pct,
        attack_confirm_min_breakout_score=args.attack_confirm_min_breakout_score,
        attack_confirm_min_buy_strength=args.attack_confirm_min_buy_strength,
        attack_full_confirm_signals=args.attack_full_confirm_signals,
        trend_follow_min_hold_bars=args.trend_follow_min_hold_bars,
        confirmed_flow_position_bonus_pct=args.confirmed_flow_position_bonus_pct,
        signal_cache_dir=None if args.no_signal_cache else args.signal_cache_dir,
        signal_cache_tag=f"{args.signal_cache_tag}-{args.macd_profile}",
        signal_cache_save_every=args.signal_cache_save_every,
    )
    result = run_cosco_dividend_t_backtest(
        bars,
        config=config,
        engine=CoscoTimingEngine(macd_policy_config=macd_policy_config_for_profile(args.macd_profile)),
    )
    report = format_cosco_backtest_report(result)
    report += f"\n## 数据来源\n\n- {data_note}\n"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    print("COSCO Dividend T Backtest")
    print("=" * 36)
    print(f"Data: {data_note}")
    print(f"Symbol: {result.symbol}")
    print(f"Range: {result.start} to {result.end} ({result.rows} rows)")
    print(f"Final equity: {result.final_equity:,.2f}")
    print(f"Total return: {result.total_return:.2%}")
    print(f"Benchmark return: {result.benchmark_return:.2%}")
    print(f"Excess return: {result.excess_return:.2%}")
    print(f"Max drawdown: {result.max_drawdown:.2%}")
    print(f"Trades: {result.trade_count}, completed: {result.completed_trades}, win rate: {_fmt_pct(result.win_rate)}")
    print(f"Signal cache hits/misses: {result.cache_hits}/{result.cache_misses}")
    print(f"Gate counts: {result.gate_counts}")
    print(f"Report: {args.report}")
    return 0


def _fetch_provider_bars(symbol: str, *, provider: str, days: int) -> object:
    now = datetime.now()
    start = now - timedelta(days=days)
    providers = None if provider == "auto" else (provider,)
    return fetch_a_share_5min_with_fallback(
        symbol,
        start_date=start.strftime("%Y-%m-%d 09:00:00"),
        end_date=now.strftime("%Y-%m-%d %H:%M:%S"),
        providers=providers,
    ).bars


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


if __name__ == "__main__":
    raise SystemExit(main())
