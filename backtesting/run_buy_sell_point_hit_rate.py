#!/usr/bin/env python3
"""Report 1/3/5-day hit rates for buy and sell timing points."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.backtest import (  # noqa: E402
    DEFAULT_SIGNAL_CACHE_DIR,
    DEFAULT_SIGNAL_HISTORY_BARS,
    DividendTBacktestConfig,
    load_5min_bars_path,
    run_cosco_dividend_t_backtest,
)
from market_regime_alpha.dividend_t.cosco_profile import profile_for_watchlist_item  # noqa: E402
from market_regime_alpha.dividend_t.cosco_timing import CoscoTimingEngine  # noqa: E402
from market_regime_alpha.dividend_t.fundamentals import build_fundamental_resolver  # noqa: E402
from market_regime_alpha.dividend_t.market_environment import MarketEnvironmentFilter, build_market_environment_filter  # noqa: E402
from market_regime_alpha.dividend_t.point_hit_rate import (  # noqa: E402
    DEFAULT_BARS_PER_TRADING_DAY,
    DEFAULT_HORIZON_DAYS,
    PointHitRateEvent,
    PointHitRateSummary,
    build_point_hit_rate_events,
    summarize_point_hit_rate_events,
)
from market_regime_alpha.dividend_t.storage import load_watchlist  # noqa: E402
from market_regime_alpha.dividend_t.strategy_modes import STRATEGY_MODES, apply_strategy_mode  # noqa: E402


DEFAULT_WATCHLIST = PROJECT_ROOT / "data" / "external" / "watchlists" / "dividend_t_watchlist.csv"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "dividend_t_5min_1y"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "backtests" / "buy_sell_point_hit_rate.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--symbols", nargs="*", default=None, help="Optional symbol filter, for example 601919.SH 600900.SH.")
    parser.add_argument("--limit", type=int, default=0, help="Limit watchlist symbols. 0 means all.")
    parser.add_argument("--strategy-mode", choices=STRATEGY_MODES, default="dynamic")
    parser.add_argument("--market-filter", choices=["none", "equal-weight"], default="equal-weight")
    parser.add_argument("--fundamental-source", choices=["auto", "tushare", "profile"], default="profile")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--base-pct", type=float, default=0.10)
    parser.add_argument("--t-pct", type=float, default=1.00)
    parser.add_argument("--min-t-pct", type=float, default=0.03)
    parser.add_argument("--max-signal-position-pct", type=float, default=1.00)
    parser.add_argument("--min-lookback-bars", type=int, default=48)
    parser.add_argument("--max-history-bars", type=int, default=DEFAULT_SIGNAL_HISTORY_BARS)
    parser.add_argument("--signal-step-bars", type=int, default=24, help="Evaluate one signal every N 5-minute bars.")
    parser.add_argument("--horizons", default="1,3,5", help="Comma-separated trading-day horizons.")
    parser.add_argument("--bars-per-trading-day", type=int, default=DEFAULT_BARS_PER_TRADING_DAY)
    parser.add_argument("--signal-cache-dir", type=Path, default=DEFAULT_SIGNAL_CACHE_DIR)
    parser.add_argument("--signal-cache-tag", default=None)
    parser.add_argument("--no-signal-cache", action="store_true")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    items = load_watchlist(args.watchlist)
    if args.symbols:
        symbols = {symbol.upper() for symbol in args.symbols}
        items = [item for item in items if item.symbol.upper() in symbols]
    if args.limit > 0:
        items = items[: args.limit]

    horizons = _parse_horizons(args.horizons)
    signal_cache_tag = args.signal_cache_tag or f"industry_{args.fundamental_source}"
    config = DividendTBacktestConfig(
        initial_cash=args.initial_cash,
        initial_base_position_pct=args.base_pct,
        t_trade_pct=args.t_pct,
        min_t_trade_pct=args.min_t_pct,
        max_signal_position_pct=args.max_signal_position_pct,
        strategy_mode=args.strategy_mode,
        enable_point_hit_rate_sell_calibration=True,
        min_lookback_bars=args.min_lookback_bars,
        max_history_bars=args.max_history_bars,
        signal_step_bars=args.signal_step_bars,
        signal_cache_dir=None if args.no_signal_cache else args.signal_cache_dir,
        signal_cache_tag=signal_cache_tag,
    )
    config = apply_strategy_mode(config, args.strategy_mode)
    market_filter = _build_market_filter(args.market_filter, items=items, data_dir=args.data_dir)
    if market_filter is not None:
        config = replace(config, enable_market_filter=True, market_filter_name=market_filter.name)

    events: list[PointHitRateEvent] = []
    failures: list[tuple[str, str, str]] = []
    symbol_rows: list[dict[str, object]] = []
    for item in items:
        try:
            bars = load_5min_bars_path(args.data_dir, symbol=item.symbol)
            profile = profile_for_watchlist_item(item)
            resolver = build_fundamental_resolver(profile, source=args.fundamental_source)
            effective_config = replace(
                config,
                initial_base_position_pct=min(config.initial_base_position_pct, profile.default_base_position_pct),
                signal_cache_tag=signal_cache_tag,
            )
            engine = CoscoTimingEngine(profile=profile, fundamental_resolver=resolver)
            result = run_cosco_dividend_t_backtest(bars, config=effective_config, engine=engine, market_filter=market_filter)
            symbol_events = build_point_hit_rate_events(
                symbol=item.symbol,
                name=item.name,
                bars=bars,
                equity_curve=result.equity_curve,
                min_lookback_bars=effective_config.min_lookback_bars,
                signal_step_bars=effective_config.signal_step_bars,
                horizon_days=horizons,
                bars_per_trading_day=args.bars_per_trading_day,
            )
            events.extend(symbol_events)
            symbol_rows.append(
                {
                    "symbol": item.symbol,
                    "name": item.name,
                    "rows": result.rows,
                    "start": result.start,
                    "end": result.end,
                    "event_count": len(symbol_events),
                    "trade_count": result.trade_count,
                    "completed_trades": result.completed_trades,
                    "trade_win_rate": result.win_rate,
                    "total_return": result.total_return,
                    "benchmark_return": result.benchmark_return,
                    "excess_return": result.excess_return,
                    "cache_hits": result.cache_hits,
                    "cache_misses": result.cache_misses,
                }
            )
        except Exception as exc:  # noqa: BLE001
            failures.append((item.symbol, item.name, f"{type(exc).__name__}: {exc}"))

    point_summary = summarize_point_hit_rate_events(events)
    action_summary = summarize_point_hit_rate_events(events, group_by_action=True)
    buy_subtype_summary = summarize_point_hit_rate_events(
        [event for event in events if event.point_type == "buy"],
        group_by_buy_subtype=True,
    )
    _write_outputs(
        args.report,
        events=events,
        point_summary=point_summary,
        action_summary=action_summary,
        buy_subtype_summary=buy_subtype_summary,
        symbol_rows=symbol_rows,
        failures=failures,
        config=config,
        args=args,
    )
    print(f"Buy/sell point hit-rate report: {args.report}")
    print(f"Events: {len(events)}, symbols: {len(symbol_rows)}, failures: {len(failures)}")
    return 0 if not failures else 1


def _parse_horizons(raw: str) -> tuple[int, ...]:
    values: list[int] = []
    for item in str(raw).split(","):
        stripped = item.strip()
        if not stripped:
            continue
        value = int(stripped)
        if value <= 0:
            raise ValueError("--horizons must contain positive integers")
        values.append(value)
    return tuple(sorted(set(values))) or DEFAULT_HORIZON_DAYS


def _build_market_filter(mode: str, *, items: list[Any], data_dir: Path) -> MarketEnvironmentFilter | None:
    if mode == "none":
        return None
    daily_frames: list[pd.DataFrame] = []
    for item in items:
        try:
            bars = load_5min_bars_path(data_dir, symbol=item.symbol)
        except FileNotFoundError:
            continue
        daily = _daily_market_filter_frame(bars, symbol=item.symbol, industry=item.industry)
        if not daily.empty:
            daily_frames.append(daily)
    if not daily_frames:
        raise ValueError(f"no local CSV files available to build market filter in {data_dir}")
    return build_market_environment_filter(pd.concat(daily_frames, ignore_index=True), name=f"composite_equal_weight:{len(daily_frames)}")


def _daily_market_filter_frame(bars: pd.DataFrame, *, symbol: str, industry: str) -> pd.DataFrame:
    data = bars.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data["trade_date"] = data["timestamp"].dt.date
    if "amount" not in data.columns:
        data["amount"] = pd.to_numeric(data["close"], errors="coerce") * pd.to_numeric(data.get("volume", 0.0), errors="coerce")
    daily = (
        data.sort_values("timestamp")
        .groupby("trade_date", sort=True)
        .agg(
            close=("close", "last"),
            amount=("amount", "sum"),
        )
        .reset_index()
    )
    daily["timestamp"] = [pd.Timestamp(trade_date) + pd.Timedelta(hours=15) for trade_date in daily["trade_date"]]
    daily["symbol"] = symbol
    daily["industry"] = industry or "UNKNOWN"
    return daily[["timestamp", "symbol", "industry", "close", "amount"]]


def _write_outputs(
    report_path: Path,
    *,
    events: list[PointHitRateEvent],
    point_summary: list[PointHitRateSummary],
    action_summary: list[PointHitRateSummary],
    buy_subtype_summary: list[PointHitRateSummary],
    symbol_rows: list[dict[str, object]],
    failures: list[tuple[str, str, str]],
    config: DividendTBacktestConfig,
    args: argparse.Namespace,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = report_path.with_name(f"{report_path.stem}_summary.csv")
    action_summary_path = report_path.with_name(f"{report_path.stem}_action_summary.csv")
    buy_subtype_summary_path = report_path.with_name(f"{report_path.stem}_buy_subtype_summary.csv")
    events_path = report_path.with_name(f"{report_path.stem}_events.csv")
    symbols_path = report_path.with_name(f"{report_path.stem}_symbols.csv")

    pd.DataFrame([row.to_dict() for row in point_summary]).to_csv(summary_path, index=False)
    pd.DataFrame([row.to_dict() for row in action_summary]).to_csv(action_summary_path, index=False)
    pd.DataFrame([row.to_dict() for row in buy_subtype_summary]).to_csv(buy_subtype_summary_path, index=False)
    pd.DataFrame([event.to_dict() for event in events]).to_csv(events_path, index=False)
    pd.DataFrame(symbol_rows).to_csv(symbols_path, index=False)

    report_path.write_text(
        _format_report(
            events=events,
            point_summary=point_summary,
            action_summary=action_summary,
            buy_subtype_summary=buy_subtype_summary,
            symbol_rows=symbol_rows,
            failures=failures,
            config=config,
            args=args,
            summary_path=summary_path,
            action_summary_path=action_summary_path,
            buy_subtype_summary_path=buy_subtype_summary_path,
            events_path=events_path,
            symbols_path=symbols_path,
        ),
        encoding="utf-8",
    )


def _format_report(
    *,
    events: list[PointHitRateEvent],
    point_summary: list[PointHitRateSummary],
    action_summary: list[PointHitRateSummary],
    buy_subtype_summary: list[PointHitRateSummary],
    symbol_rows: list[dict[str, object]],
    failures: list[tuple[str, str, str]],
    config: DividendTBacktestConfig,
    args: argparse.Namespace,
    summary_path: Path,
    action_summary_path: Path,
    buy_subtype_summary_path: Path,
    events_path: Path,
    symbols_path: Path,
) -> str:
    ok_symbols = len(symbol_rows)
    total_cache_hits = sum(int(row["cache_hits"]) for row in symbol_rows)
    total_cache_misses = sum(int(row["cache_misses"]) for row in symbol_rows)
    failure_text = "\n".join(f"- `{symbol}` {name}: {message}" for symbol, name, message in failures) or "- 无"
    return (
        "# A 股买卖点识别模型命中率报告\n\n"
        "## 数据与口径\n\n"
        f"- 数据目录：`{args.data_dir}`\n"
        f"- 观察池：`{args.watchlist}`\n"
        f"- 成功标的：{ok_symbols} / {ok_symbols + len(failures)}\n"
        f"- 策略模式：{config.strategy_mode}\n"
        f"- 市场过滤：{'开启' if config.enable_market_filter else '关闭'}（{config.market_filter_name}）\n"
        f"- 信号步长：每 {config.signal_step_bars} 根 5 分钟 K 线评估一次\n"
        f"- 未来窗口：{', '.join(str(day) for day in _parse_horizons(args.horizons))} 个交易日；"
        f"每交易日 {args.bars_per_trading_day} 根 5 分钟 K 线\n"
        f"- 买点动作：`BUY_T_TIMING`、`BREAKOUT_BUY_TIMING`；买点子类型按 5 日命中率优先口径拆分\n"
        f"- 卖点动作：`SELL_T_TIMING`、`STOP_T_WAIT`、`WAIT_DAILY_WEAK`\n"
        f"- 命中定义：买点后未来收盘高于执行价算命中；卖点后未来收盘低于执行价算命中。\n"
        f"- 信号缓存命中/未命中：{total_cache_hits} / {total_cache_misses}\n\n"
        "## 买卖点总览\n\n"
        f"{_summary_table(point_summary)}\n\n"
        "## 动作拆分\n\n"
        f"{_summary_table(action_summary)}\n\n"
        "## 买点子类型拆分\n\n"
        f"{_summary_table([row for row in buy_subtype_summary if row.point_type == 'buy'])}\n\n"
        "## 输出文件\n\n"
        f"- 总览 CSV：`{summary_path}`\n"
        f"- 动作拆分 CSV：`{action_summary_path}`\n"
        f"- 买点子类型 CSV：`{buy_subtype_summary_path}`\n"
        f"- 事件明细 CSV：`{events_path}`\n"
        f"- 标的明细 CSV：`{symbols_path}`\n\n"
        "## 数据失败\n\n"
        f"{failure_text}\n\n"
        "## 读取建议\n\n"
        f"- 样本总数：{len(events)}。命中率必须和样本数、平均未来收益一起看。\n"
        "- 如果买点命中率高但平均未来收益低，说明买点方向对但空间不足，需要优化盈亏比过滤。\n"
        "- 如果卖点命中率低且平均未来收益为正，说明卖点过早，应优先延迟或削弱该卖点动作。\n"
    )


def _summary_table(rows: list[PointHitRateSummary]) -> str:
    if not rows:
        return "_无事件_"
    lines = [
        "| 分组 | 类型 | 未来窗口 | 样本数 | 命中数 | 命中率 | 平均未来收益 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.group}`",
                    "买点" if row.point_type == "buy" else "卖点",
                    f"{row.horizon_days}日",
                    str(row.sample_count),
                    str(row.hit_count),
                    _fmt_pct(row.hit_rate),
                    _fmt_pct(row.average_future_return),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


if __name__ == "__main__":
    raise SystemExit(main())
