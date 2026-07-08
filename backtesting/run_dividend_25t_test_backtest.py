#!/usr/bin/env python3
"""Run the standalone 2.5% dividend T-grid test on 20 dividend stocks."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.grid_25t_test import (  # noqa: E402
    Grid25TConfig,
    Grid25TResult,
    max_drawdown,
    run_grid_25t_backtest,
)


DEFAULT_WATCHLIST = PROJECT_ROOT / "data" / "external" / "watchlists" / "dividend_t_watchlist.csv"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "top1000_largecap_5min_2y_parquet"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "backtests" / "dividend_25t_test_2y.md"


@dataclass(frozen=True)
class WatchlistItem:
    symbol: str
    name: str
    industry: str


@dataclass(frozen=True)
class BacktestRow:
    symbol: str
    name: str
    industry: str
    status: str
    rows: int = 0
    start: str = "-"
    end: str = "-"
    total_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    annualized_return: float | None = None
    max_drawdown: float | None = None
    trade_count: int = 0
    completed_cycles: int = 0
    win_rate: float | None = None
    realized_pnl: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    daily_drop_buy_count: int = 0
    ladder_buy_count: int = 0
    target_sell_count: int = 0
    daily_clear_count: int = 0
    cash_exhausted_count: int = 0
    t1_blocked_closeout_shares: int = 0
    ma_filter_blocked_ladder_count: int = 0
    daily_clear_skipped_layer_count: int = 0
    dividend_event_count: int = 0
    cash_dividend_total: float = 0.0
    share_bonus_total: int = 0
    final_equity: float = 0.0
    message: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run standalone 2.5% T-grid tests on dividend stocks.")
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--symbols", nargs="*", default=None, help="Optional symbol filter, for example 601919.SH 600900.SH.")
    parser.add_argument("--initial-cash", type=float, default=500_000.0)
    parser.add_argument("--base-pct", type=float, default=0.0)
    parser.add_argument("--daily-drop-trigger-pct", type=float, default=0.02)
    parser.add_argument("--daily-drop-cash-pct", type=float, default=0.30)
    parser.add_argument("--daily-rise-clear-pct", type=float, default=0.03)
    parser.add_argument("--daily-clear-min-realized-return-pct", type=float, default=-0.005)
    parser.add_argument("--grid-pct", type=float, default=0.025)
    parser.add_argument("--layer-cash-pct", type=float, default=0.10)
    parser.add_argument("--disable-ladder-ma-filter", action="store_true")
    parser.add_argument("--ma-window-days", type=int, default=20)
    parser.add_argument("--disable-dividend-reinvestment", action="store_true")
    parser.add_argument("--commission-rate", type=float, default=0.00025)
    parser.add_argument("--stamp-duty-rate", type=float, default=0.0005)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--min-lot", type=int, default=100)
    args = parser.parse_args()

    items = _load_watchlist(args.watchlist)
    if args.symbols:
        allowed = {symbol.upper() for symbol in args.symbols}
        items = [item for item in items if item.symbol.upper() in allowed]
    if args.limit > 0:
        items = items[: args.limit]

    config = Grid25TConfig(
        initial_cash=args.initial_cash,
        initial_base_position_pct=args.base_pct,
        daily_drop_buy_trigger_pct=args.daily_drop_trigger_pct,
        daily_drop_cash_pct=args.daily_drop_cash_pct,
        daily_rise_clear_pct=args.daily_rise_clear_pct,
        daily_clear_min_realized_return_pct=args.daily_clear_min_realized_return_pct,
        grid_pct=args.grid_pct,
        layer_cash_pct=args.layer_cash_pct,
        enable_ladder_ma_filter=not args.disable_ladder_ma_filter,
        ma_window_days=args.ma_window_days,
        enable_dividend_reinvestment=not args.disable_dividend_reinvestment,
        commission_rate=args.commission_rate,
        stamp_duty_rate=args.stamp_duty_rate,
        slippage_bps=args.slippage_bps,
        min_lot=args.min_lot,
    )
    rows: list[BacktestRow] = []
    results: list[tuple[WatchlistItem, Grid25TResult]] = []
    for item in items:
        try:
            bars = _load_symbol_bars(args.data_dir, item.symbol)
            result = run_grid_25t_backtest(bars, config=config)
            results.append((item, result))
            rows.append(_row_from_result(item, result))
        except Exception as exc:  # noqa: BLE001 - report batch failures per symbol.
            rows.append(BacktestRow(symbol=item.symbol, name=item.name, industry=item.industry, status="failed", message=str(exc)))

    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = _format_report(rows, results, config=config, data_dir=args.data_dir)
    args.report.write_text(report, encoding="utf-8")
    csv_path = args.report.with_suffix(".csv")
    _write_csv(rows, csv_path)
    trades_path = args.report.with_name(f"{args.report.stem}_trades.csv")
    _write_trades_csv(results, trades_path)

    ok_rows = [row for row in rows if row.status == "ok"]
    print("Dividend 2.5% T-grid Test")
    print("=" * 32)
    print(f"Symbols: {len(rows)}, ok: {len(ok_rows)}, failed: {len(rows) - len(ok_rows)}")
    if ok_rows:
        portfolio = _portfolio_summary(results)
        print(f"Portfolio total return: {portfolio['total_return']:.2%}")
        print(f"Portfolio benchmark return: {portfolio['benchmark_return']:.2%}")
        print(f"Portfolio excess return: {portfolio['excess_return']:.2%}")
        print(f"Portfolio max drawdown: {portfolio['max_drawdown']:.2%}")
    print(f"Report: {args.report}")
    print(f"CSV: {csv_path}")
    print(f"Trades CSV: {trades_path}")
    return 0


def _load_watchlist(path: Path) -> list[WatchlistItem]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            WatchlistItem(
                symbol=str(row["symbol"]).upper(),
                name=row.get("name", ""),
                industry=row.get("industry", ""),
            )
            for row in reader
        ]


def _load_symbol_bars(data_dir: Path, symbol: str) -> pd.DataFrame:
    parquet_path = data_dir / f"{symbol}_5min.parquet"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    csv_path = data_dir / f"{symbol}_5min.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path)
    short_csv_path = data_dir / f"{symbol}.csv"
    if short_csv_path.exists():
        return pd.read_csv(short_csv_path)
    raise FileNotFoundError(f"no 5-minute bars found for {symbol} in {data_dir}")


def _row_from_result(item: WatchlistItem, result: Grid25TResult) -> BacktestRow:
    return BacktestRow(
        symbol=item.symbol,
        name=item.name,
        industry=item.industry,
        status="ok",
        rows=result.rows,
        start=result.start,
        end=result.end,
        total_return=result.total_return,
        benchmark_return=result.benchmark_return,
        excess_return=result.excess_return,
        annualized_return=result.annualized_return,
        max_drawdown=result.max_drawdown,
        trade_count=result.trade_count,
        completed_cycles=result.completed_cycles,
        win_rate=result.win_rate,
        realized_pnl=result.realized_pnl,
        buy_count=result.buy_count,
        sell_count=result.sell_count,
        daily_drop_buy_count=result.daily_drop_buy_count,
        ladder_buy_count=result.ladder_buy_count,
        target_sell_count=result.target_sell_count,
        daily_clear_count=result.daily_clear_count,
        cash_exhausted_count=result.cash_exhausted_count,
        t1_blocked_closeout_shares=result.t1_blocked_closeout_shares,
        ma_filter_blocked_ladder_count=result.ma_filter_blocked_ladder_count,
        daily_clear_skipped_layer_count=result.daily_clear_skipped_layer_count,
        dividend_event_count=result.dividend_event_count,
        cash_dividend_total=result.cash_dividend_total,
        share_bonus_total=result.share_bonus_total,
        final_equity=result.final_equity,
    )


def _portfolio_summary(results: list[tuple[WatchlistItem, Grid25TResult]]) -> dict[str, float]:
    if not results:
        return {"total_return": 0.0, "benchmark_return": 0.0, "excess_return": 0.0, "max_drawdown": 0.0}
    initial = sum(result.initial_cash for _, result in results)
    final = sum(result.final_equity for _, result in results)
    benchmark_final = sum(result.initial_cash * (1.0 + result.benchmark_return) for _, result in results)
    curves: list[pd.Series] = []
    for _, result in results:
        frame = pd.DataFrame(point.to_dict() for point in result.equity_curve)
        if frame.empty:
            continue
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        curves.append(frame.set_index("timestamp")["equity"].rename(result.symbol))
    if curves:
        portfolio_curve = pd.concat(curves, axis=1).sort_index().ffill().bfill().sum(axis=1)
        portfolio_drawdown = max_drawdown(tuple(float(value) for value in portfolio_curve))
    else:
        portfolio_drawdown = 0.0
    total_return = final / initial - 1.0
    benchmark_return = benchmark_final / initial - 1.0
    return {
        "total_return": total_return,
        "benchmark_return": benchmark_return,
        "excess_return": total_return - benchmark_return,
        "max_drawdown": portfolio_drawdown,
    }


def _format_report(
    rows: list[BacktestRow],
    results: list[tuple[WatchlistItem, Grid25TResult]],
    *,
    config: Grid25TConfig,
    data_dir: Path,
) -> str:
    ok_rows = [row for row in rows if row.status == "ok"]
    failed_rows = [row for row in rows if row.status != "ok"]
    portfolio = _portfolio_summary(results)
    lines = [
        "# Dividend 2.5% T-grid Test Backtest",
        "",
        f"- Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Data directory: `{data_dir}`",
        f"- Symbols: {len(rows)}, ok: {len(ok_rows)}, failed: {len(failed_rows)}",
        f"- Initial cash per symbol: {config.initial_cash:,.0f}",
        "- Initial base position: 0%; the model starts with cash and does not keep a base position.",
        "- Decision frequency: once per trading day, on the last 5-minute bar.",
        f"- Daily drop buy: close/open <= -{config.daily_drop_buy_trigger_pct:.1%}, buy {config.daily_drop_cash_pct:.0%} of remaining cash.",
        f"- Ladder buy: if no sell fires, each further {config.grid_pct:.1%} slide from the last add reference buys {config.layer_cash_pct:.0%} of initial cash.",
        f"- Ladder MA filter: {'enabled' if config.enable_ladder_ma_filter else 'disabled'}; close below {config.ma_window_days}-day MA blocks ladder buys.",
        f"- Daily clear: close/open > {config.daily_rise_clear_pct:.1%}, clear sellable layers only when realized return >= {config.daily_clear_min_realized_return_pct:.2%}.",
        f"- Target sell: mature layers sell after a {config.grid_pct:.1%} daily-close rebound.",
        f"- Dividend reinvestment: {'enabled' if config.enable_dividend_reinvestment else 'disabled'}; cash dividends are added to cash before the daily decision.",
        "- Stop loss: disabled; cash exhaustion stops new buys.",
        "- A-share T+1 is enabled; same-day buys are not sellable and blocked clearout shares are counted.",
        "",
        "## Portfolio Summary",
        "",
        f"- Total return: {portfolio['total_return']:.2%}",
        f"- Buy-and-hold benchmark return: {portfolio['benchmark_return']:.2%}",
        f"- Excess return: {portfolio['excess_return']:.2%}",
        f"- Max drawdown: {portfolio['max_drawdown']:.2%}",
        f"- Cash dividends received: {sum(row.cash_dividend_total for row in ok_rows):,.2f}",
        f"- Dividend events: {sum(row.dividend_event_count for row in ok_rows)}",
        "",
        "## Symbol Results",
        "",
        "| Symbol | Name | Industry | Return | Benchmark | Excess | Max DD | Trades | Dividends | Drop Buys | Ladder Buys | MA Blocks | Target Sells | Clear Sells | Skipped Clear | Cycles | Win Rate |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(ok_rows, key=lambda item: item.excess_return if item.excess_return is not None else -999, reverse=True):
        lines.append(
            "| "
            f"{row.symbol} | {row.name} | {row.industry} | "
            f"{_fmt_pct(row.total_return)} | {_fmt_pct(row.benchmark_return)} | {_fmt_pct(row.excess_return)} | "
            f"{_fmt_pct(row.max_drawdown)} | {row.trade_count} | {row.cash_dividend_total:,.0f} | "
            f"{row.daily_drop_buy_count} | {row.ladder_buy_count} | {row.ma_filter_blocked_ladder_count} | "
            f"{row.target_sell_count} | {row.daily_clear_count} | {row.daily_clear_skipped_layer_count} | "
            f"{row.completed_cycles} | {_fmt_pct(row.win_rate)} |"
        )
    if failed_rows:
        lines += ["", "## Failed Symbols", ""]
        for row in failed_rows:
            lines.append(f"- `{row.symbol}` {row.name}: {row.message}")
    return "\n".join(lines) + "\n"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2%}"


def _write_csv(rows: list[BacktestRow], path: Path) -> None:
    fieldnames = list(BacktestRow.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: getattr(row, field) for field in fieldnames})


def _write_trades_csv(results: list[tuple[WatchlistItem, Grid25TResult]], path: Path) -> None:
    fieldnames = ["symbol", "name", "industry", "timestamp", "action", "side", "shares", "price", "cash_after", "equity_after", "reason", "layer_id", "realized_pnl"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item, result in results:
            for trade in result.trades:
                row: dict[str, Any] = trade.to_dict()
                row.update({"symbol": item.symbol, "name": item.name, "industry": item.industry})
                writer.writerow({field: row.get(field, "") for field in fieldnames})


if __name__ == "__main__":
    raise SystemExit(main())
