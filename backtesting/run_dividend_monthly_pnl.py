#!/usr/bin/env python3
"""Build monthly PnL report for the dividend T model."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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
from market_regime_alpha.dividend_t.storage import load_watchlist  # noqa: E402


DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "dividend_t_5min"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "backtests" / "dividend_monthly_100k_pnl.md"


@dataclass(frozen=True)
class MonthlyPnlRow:
    symbol: str
    name: str
    industry: str
    status: str
    total_pnl: float = 0.0
    total_return: float = 0.0
    benchmark_return: float = 0.0
    max_drawdown: float = 0.0
    trade_count: int = 0
    buyback_trade_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    weekly_pnl: dict[str, float] | None = None
    monthly_pnl: dict[str, float] | None = None
    message: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build per-symbol monthly PnL report for the dividend T model.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
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
    parser.add_argument("--signal-step-bars", type=int, default=24)
    parser.add_argument("--base-rebalance-cooldown-bars", type=int, default=48)
    parser.add_argument("--no-reverse-t", action="store_true")
    parser.add_argument("--disable-profit-protection", action="store_true")
    parser.add_argument("--profit-protect-trigger-pct", type=float, default=0.012)
    parser.add_argument("--profit-protect-sell-fraction", type=float, default=0.50)
    parser.add_argument("--disable-attack-state-machine", action="store_true")
    parser.add_argument("--attack-watch-position-pct", type=float, default=0.25)
    parser.add_argument("--attack-confirm-position-pct", type=float, default=0.70)
    parser.add_argument("--attack-full-position-pct", type=float, default=1.00)
    parser.add_argument("--attack-confirm-min-breakout-score", type=float, default=92.0)
    parser.add_argument("--attack-confirm-min-buy-strength", type=float, default=70.0)
    parser.add_argument("--attack-full-confirm-signals", type=int, default=1)
    parser.add_argument("--signal-cache-dir", type=Path, default=DEFAULT_SIGNAL_CACHE_DIR)
    parser.add_argument("--no-signal-cache", action="store_true")
    parser.add_argument("--no-industry-params", action="store_true")
    parser.add_argument("--fundamental-source", choices=["auto", "tushare", "profile"], default="auto")
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    items = load_watchlist()
    if args.symbols:
        symbols = {symbol.upper() for symbol in args.symbols}
        items = [item for item in items if item.symbol.upper() in symbols]

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
        signal_cache_dir=None if args.no_signal_cache else args.signal_cache_dir,
    )
    rows: list[MonthlyPnlRow] = []
    weeks: set[str] = set()
    months: set[str] = set()
    for item in items:
        row = _run_one(
            item,
            data_dir=args.data_dir,
            config=config,
            use_industry_params=not args.no_industry_params,
            fundamental_source=args.fundamental_source,
        )
        rows.append(row)
        if row.weekly_pnl:
            weeks.update(row.weekly_pnl)
        if row.monthly_pnl:
            months.update(row.monthly_pnl)

    sorted_weeks = sorted(weeks)
    sorted_months = sorted(months)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        _format_report(
            rows,
            weeks=sorted_weeks,
            months=sorted_months,
            config=config,
            data_dir=args.data_dir,
            fundamental_source=args.fundamental_source,
        ),
        encoding="utf-8",
    )
    _write_csv(rows, weeks=sorted_weeks, months=sorted_months, path=args.report.with_suffix(".csv"))

    ok_rows = [row for row in rows if row.status == "ok"]
    total_pnl = sum(row.total_pnl for row in ok_rows)
    print("Dividend Monthly PnL")
    print("=" * 28)
    print(f"Symbols: {len(rows)}, ok: {len(ok_rows)}, failed: {len(rows) - len(ok_rows)}")
    print(f"Initial cash per symbol: {config.initial_cash:,.2f}")
    print(f"Total model PnL: {total_pnl:,.2f}")
    print(f"Report: {args.report}")
    print(f"CSV: {args.report.with_suffix('.csv')}")
    return 0


def _run_one(
    item: Any,
    *,
    data_dir: Path,
    config: DividendTBacktestConfig,
    use_industry_params: bool,
    fundamental_source: str,
) -> MonthlyPnlRow:
    try:
        bars = load_5min_bars_path(data_dir, symbol=item.symbol)
        profile = profile_for_watchlist_item(item)
        resolver = build_fundamental_resolver(profile, source=fundamental_source) if use_industry_params else None
        effective_config = _config_for_profile(config, profile=profile, fundamental_source=fundamental_source) if use_industry_params else config
        engine = CoscoTimingEngine(profile=profile, fundamental_resolver=resolver) if use_industry_params else None
        result = run_cosco_dividend_t_backtest(bars, config=effective_config, engine=engine)
        weekly_pnl = _period_pnl(result.equity_curve, initial_cash=effective_config.initial_cash, period="week")
        monthly_pnl = _period_pnl(result.equity_curve, initial_cash=effective_config.initial_cash, period="month")
        return MonthlyPnlRow(
            symbol=item.symbol,
            name=item.name,
            industry=item.industry,
            status="ok",
            total_pnl=round(result.final_equity - effective_config.initial_cash, 2),
            total_return=result.total_return,
            benchmark_return=result.benchmark_return,
            max_drawdown=result.max_drawdown,
            trade_count=result.trade_count,
            buyback_trade_count=result.buyback_trade_count,
            cache_hits=result.cache_hits,
            cache_misses=result.cache_misses,
            weekly_pnl=weekly_pnl,
            monthly_pnl=monthly_pnl,
        )
    except Exception as exc:  # noqa: BLE001
        return MonthlyPnlRow(
            symbol=item.symbol,
            name=item.name,
            industry=item.industry,
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )


def _config_for_profile(config: DividendTBacktestConfig, *, profile: Any, fundamental_source: str) -> DividendTBacktestConfig:
    return replace(
        config,
        initial_base_position_pct=min(config.initial_base_position_pct, profile.default_base_position_pct),
        signal_cache_tag=f"industry_{fundamental_source}",
    )


def _period_pnl(equity_curve: Any, *, initial_cash: float, period: str) -> dict[str, float]:
    rows = [point.to_dict() for point in equity_curve]
    if not rows:
        return {}
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    if period == "week":
        frame["period"] = frame["timestamp"].dt.strftime("%G-W%V")
    elif period == "month":
        frame["period"] = frame["timestamp"].dt.strftime("%Y-%m")
    else:
        raise ValueError("period must be week or month")
    period_end = frame.groupby("period", sort=True)["equity"].last()
    pnl: dict[str, float] = {}
    previous_equity = float(initial_cash)
    for key, equity in period_end.items():
        equity_value = float(equity)
        pnl[str(key)] = round(equity_value - previous_equity, 2)
        previous_equity = equity_value
    return pnl


def _format_report(
    rows: list[MonthlyPnlRow],
    *,
    weeks: list[str],
    months: list[str],
    config: DividendTBacktestConfig,
    data_dir: Path,
    fundamental_source: str,
) -> str:
    ok_rows = [row for row in rows if row.status == "ok"]
    failed_rows = [row for row in rows if row.status != "ok"]
    total_pnl = sum(row.total_pnl for row in ok_rows)
    weekly_total = {week: sum((row.weekly_pnl or {}).get(week, 0.0) for row in ok_rows) for week in weeks}
    monthly_total = {month: sum((row.monthly_pnl or {}).get(month, 0.0) for row in ok_rows) for month in months}
    positive_count = sum(1 for row in ok_rows if row.total_pnl > 0)
    table = "\n".join(_table_row(row, months=months) for row in ok_rows)
    if not table:
        table = "| - | - | - | - | - | - | - |\n"
    failures = "\n".join(f"- `{row.symbol}` {row.name}：{row.message}" for row in failed_rows) or "- 无"
    week_header = " | ".join(weeks)
    week_total_row = " | ".join(_fmt_money(weekly_total[week]) for week in weeks)
    month_header = " | ".join(months)
    total_row = " | ".join(_fmt_money(monthly_total[month]) for month in months)
    weekly_symbol_table = "\n".join(_weekly_table_row(row, weeks=weeks) for row in ok_rows)
    if not weekly_symbol_table:
        weekly_symbol_table = "| - | - | - |\n"

    return (
        "# 红利观察池 10 万元单票周度 / 月度盈亏分析\n\n"
        "## 口径\n\n"
        f"- 数据来源：CSV目录 `{data_dir}`\n"
        f"- 成功标的：{len(ok_rows)} / {len(rows)}\n"
        f"- 每只股票初始资金：{config.initial_cash:,.2f} 元\n"
        f"- 防守/震荡初始底仓比例：{config.initial_base_position_pct:.0%}\n"
        f"- 底仓目标上限：{config.strong_trend_base_position_pct:.0%}\n"
        f"- 全局最大总仓位硬上限：{config.max_signal_position_pct:.0%}\n"
        f"- 强趋势/趋势观察/震荡目标上限：{config.strong_trend_signal_position_pct:.0%} / "
        f"{config.trend_watch_signal_position_pct:.0%} / {config.range_signal_position_pct:.0%}\n"
        f"- 进攻状态机：{'开启' if config.enable_attack_state_machine else '关闭'}；"
        f"预警 {config.attack_watch_position_pct:.0%} / 确认 {config.attack_confirm_position_pct:.0%} / 满攻 {config.attack_full_position_pct:.0%}\n"
        f"- 满攻触发：突破分 ≥ {config.attack_confirm_min_breakout_score:.1f}，买入强度 ≥ {config.attack_confirm_min_buy_strength:.1f}，确认 {config.attack_full_confirm_signals} 次\n"
        f"- 单次底仓再平衡步长：{config.base_rebalance_step_pct:.0%}\n"
        f"- 底仓再平衡冷却：{config.base_rebalance_cooldown_bars} 根 5 分钟 K 线\n"
        f"- 强趋势确认次数：{config.strong_trend_confirm_signals}\n"
        f"- 趋势退出确认次数：{config.trend_exit_confirm_signals}\n"
        f"- 防守确认次数：{config.defensive_confirm_signals}\n"
        f"- 默认买入后总仓位上限：{config.default_buy_total_cap_pct:.0%}（legacy `t_trade_pct`）\n"
        f"- 默认主动增量上限：{config.default_active_position_cap_pct:.0%}（总仓位上限 - 初始底仓）\n"
        f"- 最小主动试探增量：{config.min_t_trade_pct:.0%}\n"
        f"- Kelly 折扣：{config.kelly_fraction_scale:.0%}\n"
        f"- 最低买入强度：{config.min_buy_signal_strength:.1f}\n"
        f"- 倒 T 闭环：{'开启' if config.allow_reverse_t else '关闭'}\n"
        f"- 突破仓利润保护：{'开启' if config.enable_profit_protection else '关闭'}，触发浮盈 {config.profit_protect_trigger_pct:.1%}，卖出比例 {config.profit_protect_sell_fraction:.0%}\n"
        f"- 信号评估步长：每 {config.signal_step_bars} 根 5 分钟 K 线评估一次\n"
        f"- 基本面 F 来源：{fundamental_source}；Tushare 不可用时按单标的回退行业默认 F 并继续回测\n"
        f"- 信号缓存：{config.signal_cache_dir or '关闭'}\n"
        "- 周度 / 月度盈亏 = 本周期最后一根回测权益 - 上周期最后一根回测权益，包含浮盈浮亏、手续费、印花税和滑点。\n"
        "- 首个周期为数据起始后的部分周期，最后周期为截至数据最后一根 K 线的部分周期。\n\n"
        "## 总览\n\n"
        f"- 总投入：{len(ok_rows) * config.initial_cash:,.2f} 元\n"
        f"- 模型总盈亏：{total_pnl:,.2f} 元\n"
        f"- 模型总收益率：{total_pnl / (len(ok_rows) * config.initial_cash):.2%}\n"
        f"- 盈利股票数：{positive_count} / {len(ok_rows)}\n"
        f"- 缓存命中/未命中：{sum(row.cache_hits for row in ok_rows)} / {sum(row.cache_misses for row in ok_rows)}\n\n"
        "## 周度合计\n\n"
        f"| {week_header} | 合计 |\n"
        f"| {' | '.join(['---:'] * len(weeks))} | ---: |\n"
        f"| {week_total_row} | {_fmt_money(total_pnl)} |\n\n"
        "## 月度合计\n\n"
        f"| {month_header} | 合计 |\n"
        f"| {' | '.join(['---:'] * len(months))} | ---: |\n"
        f"| {total_row} | {_fmt_money(total_pnl)} |\n\n"
        "## 单票月度明细\n\n"
        f"| 代码 | 名称 | 行业 | {' | '.join(months)} | 合计 | 收益率 | 基准收益率 | 交易次数 | 买回次数 |\n"
        f"| --- | --- | --- | {' | '.join(['---:'] * len(months))} | ---: | ---: | ---: | ---: | ---: |\n"
        f"{table}\n\n"
        "## 单票周度明细\n\n"
        f"| 代码 | 名称 | {' | '.join(weeks)} | 合计 |\n"
        f"| --- | --- | {' | '.join(['---:'] * len(weeks))} | ---: |\n"
        f"{weekly_symbol_table}\n\n"
        "## 数据失败\n\n"
        f"{failures}\n\n"
        "## 解读\n\n"
        "- 正数代表按模型持有和做 T 后，当月账户权益增加；负数代表账户权益下降。\n"
        "- 这里不是已实现现金收益，而是回测权益口径，包含底仓浮动盈亏。\n"
        "- 10 万元口径会受到 A 股 100 股最小交易单位影响，高价股可能无法建立底仓或只能极低仓位参与。\n"
    )


def _write_csv(rows: list[MonthlyPnlRow], *, weeks: list[str], months: list[str], path: Path) -> None:
    payload: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "symbol": row.symbol,
            "name": row.name,
            "industry": row.industry,
            "status": row.status,
            "total_pnl": row.total_pnl,
            "total_return": row.total_return,
            "benchmark_return": row.benchmark_return,
            "max_drawdown": row.max_drawdown,
            "trade_count": row.trade_count,
            "buyback_trade_count": row.buyback_trade_count,
            "cache_hits": row.cache_hits,
            "cache_misses": row.cache_misses,
            "message": row.message,
        }
        for week in weeks:
            item[f"week_{week}"] = (row.weekly_pnl or {}).get(week)
        for month in months:
            item[f"month_{month}"] = (row.monthly_pnl or {}).get(month)
        payload.append(item)
    pd.DataFrame(payload).to_csv(path, index=False)


def _table_row(row: MonthlyPnlRow, *, months: list[str]) -> str:
    monthly = row.monthly_pnl or {}
    month_values = " | ".join(_fmt_money(monthly.get(month, 0.0)) for month in months)
    return (
        f"| `{row.symbol}` | {row.name} | {row.industry} | {month_values} | "
        f"{_fmt_money(row.total_pnl)} | {row.total_return:.2%} | {row.benchmark_return:.2%} | {row.trade_count} | {row.buyback_trade_count} |"
    )


def _weekly_table_row(row: MonthlyPnlRow, *, weeks: list[str]) -> str:
    weekly = row.weekly_pnl or {}
    week_values = " | ".join(_fmt_money(weekly.get(week, 0.0)) for week in weeks)
    return f"| `{row.symbol}` | {row.name} | {week_values} | {_fmt_money(row.total_pnl)} |"


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
