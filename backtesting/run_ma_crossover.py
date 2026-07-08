#!/usr/bin/env python3
"""Run the sample ETF moving-average crossover experiment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.backtesting import load_ohlcv_csv, run_moving_average_crossover


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a simple ETF moving-average crossover backtest.")
    parser.add_argument(
        "--data",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "sample_etf_ohlcv.csv",
        help="OHLCV CSV path that follows docs/Data-Spec.md.",
    )
    parser.add_argument("--symbol", default="SAMPLE_ETF", help="Symbol to load from the CSV.")
    parser.add_argument("--fast-window", type=int, default=3, help="Fast moving-average window.")
    parser.add_argument("--slow-window", type=int, default=8, help="Slow moving-average window.")
    parser.add_argument("--initial-cash", type=float, default=10_000.0, help="Starting cash.")
    args = parser.parse_args()

    bars = load_ohlcv_csv(args.data, symbol=args.symbol)
    result = run_moving_average_crossover(
        bars,
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        initial_cash=args.initial_cash,
    )

    print("ETF Moving-Average Crossover Backtest")
    print("=" * 42)
    print(f"Data: {args.data}")
    print(f"Symbol: {result.symbol}")
    print(f"Range: {result.start.date()} to {result.end.date()} ({result.rows} rows)")
    print(f"Rule: long when MA({result.fast_window}) > MA({result.slow_window}); otherwise cash")
    print()
    print(f"Initial cash:        ${result.initial_cash:,.2f}")
    print(f"Final equity:        ${result.final_equity:,.2f}")
    print(f"Total return:        {_format_percent(result.total_return)}")
    print(f"Annualized return:   {_format_percent(result.annualized_return)}")
    print(f"Max drawdown:        {_format_percent(result.max_drawdown)}")
    print(f"Sharpe ratio:        {_format_optional_number(result.sharpe)}")
    print(f"Trade events:        {result.trade_events}")
    print(f"Completed trades:    {result.completed_trades}")
    print(f"Win rate:            {_format_optional_percent(result.win_rate)}")
    print()
    print("Interpretation: this sample proves the data contract and backtest loop run end to end.")
    print("The CSV is synthetic, so the metrics are not evidence that the strategy works in live markets.")
    return 0


def _format_percent(value: float) -> str:
    return f"{value * 100:,.2f}%"


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return _format_percent(value)


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.2f}"


if __name__ == "__main__":
    raise SystemExit(main())

