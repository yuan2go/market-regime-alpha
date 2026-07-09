#!/usr/bin/env python3
"""Build a drawdown report for the dividend T watchlist backtest."""

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
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "backtests" / "dividend_drawdown_report.md"


@dataclass(frozen=True)
class DrawdownInfo:
    max_drawdown: float
    peak_time: str
    trough_time: str
    recovery_time: str
    duration_bars: int
    recovered: bool


@dataclass(frozen=True)
class DrawdownRow:
    symbol: str
    name: str
    industry: str
    status: str
    total_return: float = 0.0
    benchmark_return: float = 0.0
    excess_return: float = 0.0
    model_drawdown: DrawdownInfo | None = None
    benchmark_drawdown: DrawdownInfo | None = None
    drawdown_improvement: float = 0.0
    trade_count: int = 0
    buyback_trade_count: int = 0
    gate_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    message: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a 3-month dividend T drawdown report.")
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
        signal_cache_tag=f"industry_{args.fundamental_source}",
    )
    rows = [
        _run_one(
            item,
            data_dir=args.data_dir,
            config=config,
            use_industry_params=not args.no_industry_params,
            fundamental_source=args.fundamental_source,
        )
        for item in items
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(_format_report(rows, config=config, data_dir=args.data_dir, fundamental_source=args.fundamental_source), encoding="utf-8")
    _write_csv(rows, args.report.with_suffix(".csv"))

    ok_rows = [row for row in rows if row.status == "ok"]
    print("Dividend Drawdown Report")
    print("=" * 30)
    print(f"Symbols: {len(rows)}, ok: {len(ok_rows)}, failed: {len(rows) - len(ok_rows)}")
    if ok_rows:
        worst = min(ok_rows, key=lambda item: item.model_drawdown.max_drawdown if item.model_drawdown else 0.0)
        print(f"Worst model drawdown: {worst.symbol} {worst.model_drawdown.max_drawdown:.2%}")
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
) -> DrawdownRow:
    try:
        bars = load_5min_bars_path(data_dir, symbol=item.symbol)
        profile = profile_for_watchlist_item(item)
        resolver = build_fundamental_resolver(profile, source=fundamental_source) if use_industry_params else None
        effective_config = _config_for_profile(config, profile=profile, fundamental_source=fundamental_source) if use_industry_params else config
        engine = CoscoTimingEngine(profile=profile, fundamental_resolver=resolver) if use_industry_params else None
        result = run_cosco_dividend_t_backtest(bars, config=effective_config, engine=engine)
        model_curve = [(point.timestamp, point.equity) for point in result.equity_curve]
        benchmark_curve = _benchmark_curve(bars, initial_cash=effective_config.initial_cash)
        model_drawdown = _drawdown_info(model_curve)
        benchmark_drawdown = _drawdown_info(benchmark_curve)
        return DrawdownRow(
            symbol=item.symbol,
            name=item.name,
            industry=item.industry,
            status="ok",
            total_return=result.total_return,
            benchmark_return=result.benchmark_return,
            excess_return=result.excess_return,
            model_drawdown=model_drawdown,
            benchmark_drawdown=benchmark_drawdown,
            drawdown_improvement=model_drawdown.max_drawdown - benchmark_drawdown.max_drawdown,
            trade_count=result.trade_count,
            buyback_trade_count=result.buyback_trade_count,
            gate_count=sum(result.gate_counts.values()),
            cache_hits=result.cache_hits,
            cache_misses=result.cache_misses,
        )
    except Exception as exc:  # noqa: BLE001
        return DrawdownRow(
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


def _benchmark_curve(bars: Any, *, initial_cash: float) -> list[tuple[str, float]]:
    data = bars.copy().sort_values("timestamp").reset_index(drop=True)
    open0 = float(data["open"].iloc[0])
    return [(str(row["timestamp"]), initial_cash * float(row["close"]) / open0) for _, row in data.iloc[1:].iterrows()]


def _drawdown_info(curve: list[tuple[str, float]]) -> DrawdownInfo:
    if not curve:
        return DrawdownInfo(0.0, "-", "-", "-", 0, True)
    peak_value = float(curve[0][1])
    peak_time = str(curve[0][0])
    active_peak_time = peak_time
    worst = 0.0
    worst_peak_time = peak_time
    trough_time = peak_time
    trough_index = 0
    peak_index_at_worst = 0
    for index, (timestamp, equity) in enumerate(curve):
        value = float(equity)
        if value > peak_value:
            peak_value = value
            active_peak_time = str(timestamp)
        drawdown = value / peak_value - 1.0 if peak_value > 0 else 0.0
        if drawdown < worst:
            worst = drawdown
            worst_peak_time = active_peak_time
            trough_time = str(timestamp)
            trough_index = index
            peak_index_at_worst = next((idx for idx, item in enumerate(curve) if str(item[0]) == worst_peak_time), 0)
    recovery_time = "-"
    recovered = worst == 0.0
    if worst < 0.0:
        peak_equity = next((float(item[1]) for item in curve if str(item[0]) == worst_peak_time), peak_value)
        for timestamp, equity in curve[trough_index + 1 :]:
            if float(equity) >= peak_equity:
                recovery_time = str(timestamp)
                recovered = True
                break
    duration_bars = max(trough_index - peak_index_at_worst, 0)
    return DrawdownInfo(
        max_drawdown=round(worst, 6),
        peak_time=worst_peak_time,
        trough_time=trough_time,
        recovery_time=recovery_time,
        duration_bars=duration_bars,
        recovered=recovered,
    )


def _format_report(rows: list[DrawdownRow], *, config: DividendTBacktestConfig, data_dir: Path, fundamental_source: str) -> str:
    ok_rows = [row for row in rows if row.status == "ok" and row.model_drawdown is not None and row.benchmark_drawdown is not None]
    failed_rows = [row for row in rows if row.status != "ok"]
    avg_model_dd = _average(row.model_drawdown.max_drawdown for row in ok_rows)
    avg_benchmark_dd = _average(row.benchmark_drawdown.max_drawdown for row in ok_rows)
    worst_rows = sorted(ok_rows, key=lambda row: row.model_drawdown.max_drawdown)[:5]
    improved_count = sum(1 for row in ok_rows if row.drawdown_improvement > 0)
    table = "\n".join(_table_row(row) for row in ok_rows)
    worst_table = "\n".join(_worst_row(row) for row in worst_rows)
    failures = "\n".join(f"- `{row.symbol}` {row.name}：{row.message}" for row in failed_rows) or "- 无"
    return (
        "# 红利观察池 3 个月回撤报告\n\n"
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
        f"- 基本面 F 来源：{fundamental_source}；Tushare 不可用时按单标的回退行业默认 F 并继续回测\n"
        f"- 信号评估步长：每 {config.signal_step_bars} 根 5 分钟 K 线评估一次\n"
        f"- 信号缓存：{config.signal_cache_dir or '关闭'}\n\n"
        "## 总览\n\n"
        f"- 平均模型最大回撤：{avg_model_dd:.2%}\n"
        f"- 平均买入持有最大回撤：{avg_benchmark_dd:.2%}\n"
        f"- 模型回撤小于基准数量：{improved_count} / {len(ok_rows)}\n"
        f"- 平均回撤改善：{(avg_model_dd - avg_benchmark_dd):.2%}\n\n"
        "## 最大回撤最差 5 只\n\n"
        "| 代码 | 名称 | 行业 | 模型最大回撤 | 峰值时间 | 谷底时间 | 是否恢复 | 基准最大回撤 |\n"
        "| --- | --- | --- | ---: | --- | --- | --- | ---: |\n"
        f"{worst_table or '| - | - | - | - | - | - | - | - |'}\n\n"
        "## 全量明细\n\n"
        "| 代码 | 名称 | 行业 | 总收益 | 基准收益 | 超额 | 模型最大回撤 | 基准最大回撤 | 回撤改善 | 峰值 -> 谷底 | 恢复时间 | 交易/买回/门控 | 缓存命中/未命中 |\n"
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: |\n"
        f"{table or '| - | - | - | - | - | - | - | - | - | - | - | - |'}\n\n"
        "## 数据失败\n\n"
        f"{failures}\n\n"
        "## 解读\n\n"
        "- 回撤为账户权益从阶段峰值到阶段低点的跌幅，包含底仓浮盈浮亏、手续费、印花税和滑点。\n"
        "- 回撤改善 = 模型最大回撤 - 买入持有最大回撤；因为二者通常为负数，正数代表模型回撤更小。\n"
        "- 该报告仍是研究口径，不包含真实盘口排队、涨跌停无法成交和分红除权再投资。\n"
    )


def _table_row(row: DrawdownRow) -> str:
    model = row.model_drawdown
    benchmark = row.benchmark_drawdown
    assert model is not None and benchmark is not None
    trade_gate = f"{row.trade_count}/{row.buyback_trade_count}/{row.gate_count}"
    cache = f"{row.cache_hits}/{row.cache_misses}"
    return (
        f"| `{row.symbol}` | {row.name} | {row.industry} | {row.total_return:.2%} | {row.benchmark_return:.2%} | "
        f"{row.excess_return:.2%} | {model.max_drawdown:.2%} | {benchmark.max_drawdown:.2%} | "
        f"{row.drawdown_improvement:.2%} | {model.peak_time} -> {model.trough_time} | "
        f"{model.recovery_time if model.recovered else '未恢复'} | {trade_gate} | {cache} |"
    )


def _worst_row(row: DrawdownRow) -> str:
    model = row.model_drawdown
    benchmark = row.benchmark_drawdown
    assert model is not None and benchmark is not None
    return (
        f"| `{row.symbol}` | {row.name} | {row.industry} | {model.max_drawdown:.2%} | "
        f"{model.peak_time} | {model.trough_time} | {'是' if model.recovered else '否'} | "
        f"{benchmark.max_drawdown:.2%} |"
    )


def _write_csv(rows: list[DrawdownRow], path: Path) -> None:
    payload: list[dict[str, object]] = []
    for row in rows:
        model = row.model_drawdown
        benchmark = row.benchmark_drawdown
        payload.append(
            {
                "symbol": row.symbol,
                "name": row.name,
                "industry": row.industry,
                "status": row.status,
                "total_return": row.total_return,
                "benchmark_return": row.benchmark_return,
                "excess_return": row.excess_return,
                "model_max_drawdown": model.max_drawdown if model else None,
                "benchmark_max_drawdown": benchmark.max_drawdown if benchmark else None,
                "drawdown_improvement": row.drawdown_improvement,
                "model_peak_time": model.peak_time if model else "",
                "model_trough_time": model.trough_time if model else "",
                "model_recovery_time": model.recovery_time if model else "",
                "model_recovered": model.recovered if model else None,
                "model_duration_bars": model.duration_bars if model else None,
                "trade_count": row.trade_count,
                "buyback_trade_count": row.buyback_trade_count,
                "gate_count": row.gate_count,
                "cache_hits": row.cache_hits,
                "cache_misses": row.cache_misses,
                "message": row.message,
            }
        )
    pd.DataFrame(payload).to_csv(path, index=False)


def _average(values: Any) -> float:
    numbers = list(values)
    return sum(numbers) / len(numbers) if numbers else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
