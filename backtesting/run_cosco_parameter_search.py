#!/usr/bin/env python3
"""Parameter search, out-of-sample test, and rolling validation for COSCO."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.backtest import (  # noqa: E402
    DEFAULT_SIGNAL_CACHE_DIR,
    DividendTBacktestConfig,
    DividendTBacktestResult,
    load_5min_bars_csv,
    run_cosco_dividend_t_backtest,
)


DEFAULT_DATA = PROJECT_ROOT / "data" / "raw" / "dividend_t_5min" / "601919.SH_5min.csv"
DEFAULT_RESULTS = PROJECT_ROOT / "reports" / "backtests" / "cosco_parameter_search_results.csv"
DEFAULT_ROLLING = PROJECT_ROOT / "reports" / "backtests" / "cosco_parameter_rolling_results.csv"
DEFAULT_WALK_FORWARD = PROJECT_ROOT / "reports" / "backtests" / "cosco_parameter_walk_forward_results.csv"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "backtests" / "cosco_parameter_search_walk_forward.md"


@dataclass(frozen=True)
class Candidate:
    name: str
    min_buy_signal_strength: float
    attack_confirm_min_breakout_score: float
    attack_confirm_min_buy_strength: float
    max_signal_position_pct: float
    strong_trend_signal_position_pct: float
    trend_watch_signal_position_pct: float
    attack_watch_position_pct: float
    attack_confirm_position_pct: float
    attack_full_position_pct: float
    attack_min_hold_bars: int
    trend_follow_min_hold_bars: int
    profit_protect_trigger_pct: float
    profit_protect_sell_fraction: float
    attack_exit_sell_pressure_score: float
    attack_exit_down_probability: float
    confirmed_flow_position_bonus_pct: float

    def to_config(self, *, cache_tag: str, cache_dir: Path | None) -> DividendTBacktestConfig:
        return DividendTBacktestConfig(
            initial_cash=100_000.0,
            initial_base_position_pct=0.10,
            t_trade_pct=1.00,
            max_signal_position_pct=self.max_signal_position_pct,
            strong_trend_signal_position_pct=self.strong_trend_signal_position_pct,
            trend_watch_signal_position_pct=self.trend_watch_signal_position_pct,
            range_signal_position_pct=min(0.35, self.trend_watch_signal_position_pct),
            min_buy_signal_strength=self.min_buy_signal_strength,
            attack_watch_position_pct=self.attack_watch_position_pct,
            attack_confirm_position_pct=self.attack_confirm_position_pct,
            attack_full_position_pct=self.attack_full_position_pct,
            attack_confirm_min_breakout_score=self.attack_confirm_min_breakout_score,
            attack_confirm_min_buy_strength=self.attack_confirm_min_buy_strength,
            attack_min_hold_bars=self.attack_min_hold_bars,
            trend_follow_min_hold_bars=self.trend_follow_min_hold_bars,
            profit_protect_trigger_pct=self.profit_protect_trigger_pct,
            profit_protect_sell_fraction=self.profit_protect_sell_fraction,
            attack_exit_sell_pressure_score=self.attack_exit_sell_pressure_score,
            attack_exit_down_probability=self.attack_exit_down_probability,
            attack_hard_exit_sell_pressure_score=max(88.0, self.attack_exit_sell_pressure_score + 8.0),
            attack_hard_exit_down_probability=max(0.68, self.attack_exit_down_probability + 0.08),
            confirmed_flow_position_bonus_pct=self.confirmed_flow_position_bonus_pct,
            min_lookback_bars=48,
            max_history_bars=240,
            signal_step_bars=1,
            base_rebalance_cooldown_bars=48,
            signal_cache_dir=cache_dir,
            signal_cache_tag=cache_tag,
            signal_cache_save_every=500,
        )


@dataclass(frozen=True)
class DateSplit:
    name: str
    start_date: object
    end_date: object


def main() -> int:
    parser = argparse.ArgumentParser(description="Search COSCO dividend-T parameters with walk-forward validation.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--symbol", default="601919.SH")
    parser.add_argument("--max-candidates", type=int, default=81)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--no-signal-cache", action="store_true")
    parser.add_argument("--signal-cache-dir", type=Path, default=DEFAULT_SIGNAL_CACHE_DIR)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--rolling-results", type=Path, default=DEFAULT_ROLLING)
    parser.add_argument("--walk-forward-results", type=Path, default=DEFAULT_WALK_FORWARD)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    bars = load_5min_bars_csv(args.data, symbol=args.symbol)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    dates = tuple(sorted(bars["timestamp"].dt.date.unique()))
    if len(dates) < 30:
        raise SystemExit("not enough trading days for parameter search")

    splits = build_train_valid_test_splits(dates)
    candidates = build_candidates(limit=args.max_candidates)
    cache_dir = None if args.no_signal_cache else args.signal_cache_dir
    rows: list[dict[str, object]] = []

    print(f"Loaded {len(bars)} bars, {len(dates)} trading days")
    print("Splits:", ", ".join(f"{item.name}={item.start_date}..{item.end_date}" for item in splits))
    print(f"Candidates: {len(candidates)}")

    for index, candidate in enumerate(candidates, start=1):
        print(f"[{index}/{len(candidates)}] {candidate.name}", flush=True)
        for split in splits:
            frame = filter_by_split(bars, split)
            result = run_candidate(candidate, frame, cache_tag=f"param_{split.name}", cache_dir=cache_dir)
            rows.append(result_row(candidate, split.name, result))

    results = pd.DataFrame(rows)
    results["selection_score"] = results.apply(selection_score, axis=1)
    summary = summarize_candidates(results)
    selected_name = str(summary.iloc[0]["candidate"])
    selected = next(item for item in candidates if item.name == selected_name)
    rolling_rows = run_rolling_validation(bars, selected=selected, cache_dir=cache_dir)
    rolling = pd.DataFrame(rolling_rows)
    walk_forward_rows = run_walk_forward_validation(bars, candidates=candidates, cache_dir=cache_dir)
    walk_forward = pd.DataFrame(walk_forward_rows)

    args.results.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.results, index=False)
    rolling.to_csv(args.rolling_results, index=False)
    walk_forward.to_csv(args.walk_forward_results, index=False)
    args.report.write_text(
        format_report(
            data_path=args.data,
            bars=bars,
            splits=splits,
            results=results,
            summary=summary,
            rolling=rolling,
            walk_forward=walk_forward,
            selected=selected,
        ),
        encoding="utf-8",
    )

    selected_rows = results[results["candidate"] == selected.name].set_index("split")
    print("Selected:", selected.name)
    for split_name in ("train", "valid", "test"):
        row = selected_rows.loc[split_name]
        print(
            f"{split_name}: return={row['total_return']:.2%}, benchmark={row['benchmark_return']:.2%}, "
            f"excess={row['excess_return']:.2%}, mdd={row['max_drawdown']:.2%}, trades={int(row['trade_count'])}"
        )
    print("Report:", args.report)
    return 0


def build_train_valid_test_splits(dates: tuple[object, ...]) -> tuple[DateSplit, ...]:
    train_end = max(1, int(len(dates) * 0.60)) - 1
    valid_end = max(train_end + 1, int(len(dates) * 0.80)) - 1
    return (
        DateSplit("train", dates[0], dates[train_end]),
        DateSplit("valid", dates[train_end + 1], dates[valid_end]),
        DateSplit("test", dates[valid_end + 1], dates[-1]),
    )


def build_candidates(*, limit: int) -> tuple[Candidate, ...]:
    values = product(
        (62.0, 66.0, 70.0),
        ((92.0, 70.0),),
        ((0.45, 0.32, 0.22), (0.70, 0.50, 0.25), (1.00, 0.70, 0.25)),
        (6, 10, 18),
        (0.008, 0.012, 0.018),
        (0.50,),
        ((78.0, 0.60), (84.0, 0.64)),
    )
    candidates: list[Candidate] = []
    for idx, (
        min_strength,
        attack_pair,
        position_pair,
        hold_bars,
        protect_trigger,
        protect_fraction,
        exit_pair,
    ) in enumerate(values, start=1):
        breakout_score, breakout_strength = attack_pair
        attack_full, attack_confirm, attack_watch = position_pair
        exit_pressure, exit_down_prob = exit_pair
        candidates.append(
            Candidate(
                name=f"p{idx:03d}",
                min_buy_signal_strength=min_strength,
                attack_confirm_min_breakout_score=breakout_score,
                attack_confirm_min_buy_strength=breakout_strength,
                max_signal_position_pct=attack_full,
                strong_trend_signal_position_pct=min(0.80, attack_full),
                trend_watch_signal_position_pct=min(0.50, attack_full),
                attack_watch_position_pct=attack_watch,
                attack_confirm_position_pct=attack_confirm,
                attack_full_position_pct=attack_full,
                attack_min_hold_bars=hold_bars,
                trend_follow_min_hold_bars=max(18, hold_bars * 2),
                profit_protect_trigger_pct=protect_trigger,
                profit_protect_sell_fraction=protect_fraction,
                attack_exit_sell_pressure_score=exit_pressure,
                attack_exit_down_probability=exit_down_prob,
                confirmed_flow_position_bonus_pct=0.15,
            )
        )
    baseline = Candidate(
        name="baseline_current",
        min_buy_signal_strength=66.0,
        attack_confirm_min_breakout_score=92.0,
        attack_confirm_min_buy_strength=70.0,
        max_signal_position_pct=1.00,
        strong_trend_signal_position_pct=0.80,
        trend_watch_signal_position_pct=0.50,
        attack_watch_position_pct=0.25,
        attack_confirm_position_pct=0.70,
        attack_full_position_pct=1.00,
        attack_min_hold_bars=6,
        trend_follow_min_hold_bars=18,
        profit_protect_trigger_pct=0.012,
        profit_protect_sell_fraction=0.50,
        attack_exit_sell_pressure_score=78.0,
        attack_exit_down_probability=0.60,
        confirmed_flow_position_bonus_pct=0.15,
    )
    ordered = [baseline, *[item for item in candidates if item != baseline]]
    return tuple(ordered[:limit])


def filter_by_split(frame: pd.DataFrame, split: DateSplit) -> pd.DataFrame:
    dates = frame["timestamp"].dt.date
    return frame[(dates >= split.start_date) & (dates <= split.end_date)].copy()


def run_candidate(
    candidate: Candidate,
    frame: pd.DataFrame,
    *,
    cache_tag: str,
    cache_dir: Path | None,
) -> DividendTBacktestResult:
    return run_cosco_dividend_t_backtest(
        frame,
        config=candidate.to_config(cache_tag=cache_tag, cache_dir=cache_dir),
    )


def result_row(candidate: Candidate, split: str, result: DividendTBacktestResult) -> dict[str, object]:
    return {
        **asdict(candidate),
        "candidate": candidate.name,
        "split": split,
        "start": result.start,
        "end": result.end,
        "rows": result.rows,
        "final_equity": result.final_equity,
        "total_return": result.total_return,
        "benchmark_return": result.benchmark_return,
        "excess_return": result.excess_return,
        "max_drawdown": result.max_drawdown,
        "annualized_return": result.annualized_return,
        "trade_count": result.trade_count,
        "completed_trades": result.completed_trades,
        "win_rate": result.win_rate,
        "realized_pnl": result.realized_pnl,
        "buyback_trade_count": result.buyback_trade_count,
        "cache_hits": result.cache_hits,
        "cache_misses": result.cache_misses,
    }


def selection_score(row: pd.Series) -> float:
    trade_penalty = 0.006 if row["trade_count"] < 3 else 0.0
    drawdown_penalty = abs(float(row["max_drawdown"])) * 0.35
    return float(row["total_return"]) + 0.35 * float(row["excess_return"]) - drawdown_penalty - trade_penalty


def summarize_candidates(results: pd.DataFrame) -> pd.DataFrame:
    pivot = results.pivot_table(
        index="candidate",
        columns="split",
        values=["selection_score", "total_return", "benchmark_return", "excess_return", "max_drawdown", "trade_count"],
        aggfunc="first",
    )
    pivot.columns = [f"{metric}_{split}" for metric, split in pivot.columns]
    pivot = pivot.reset_index()
    candidate_params = results.drop_duplicates("candidate")[
        [
            "candidate",
            "min_buy_signal_strength",
            "attack_confirm_min_breakout_score",
            "attack_confirm_min_buy_strength",
            "max_signal_position_pct",
            "attack_full_position_pct",
            "attack_confirm_position_pct",
            "attack_min_hold_bars",
            "trend_follow_min_hold_bars",
            "profit_protect_trigger_pct",
            "attack_exit_sell_pressure_score",
            "attack_exit_down_probability",
            "confirmed_flow_position_bonus_pct",
        ]
    ]
    summary = candidate_params.merge(pivot, on="candidate", how="left")
    summary["robust_score"] = (
        summary["selection_score_valid"]
        + 0.20 * summary["selection_score_train"].clip(upper=0.04)
        - 0.25 * summary["max_drawdown_valid"].abs()
    )
    summary["valid_positive"] = summary["total_return_valid"] > 0
    summary["train_not_bad"] = summary["total_return_train"] > -0.03
    return summary.sort_values(
        by=["valid_positive", "train_not_bad", "robust_score", "excess_return_valid"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def run_rolling_validation(
    frame: pd.DataFrame,
    *,
    selected: Candidate,
    cache_dir: Path | None,
) -> list[dict[str, object]]:
    dates = tuple(sorted(frame["timestamp"].dt.date.unique()))
    windows = build_rolling_windows(dates, train_days=16, test_days=4, step_days=8)
    rows: list[dict[str, object]] = []
    for window_index, window in enumerate(windows, start=1):
        split = DateSplit(f"rolling_{window_index}", window[0], window[1])
        frame_slice = filter_by_split(frame, split)
        result = run_candidate(selected, frame_slice, cache_tag=f"rolling_{window_index}", cache_dir=cache_dir)
        rows.append(
            {
                **result_row(selected, split.name, result),
                "window_index": window_index,
                "window_start": window[0],
                "window_end": window[1],
                "is_selected": True,
            }
        )
    return rows


def run_walk_forward_validation(
    frame: pd.DataFrame,
    *,
    candidates: tuple[Candidate, ...],
    cache_dir: Path | None,
) -> list[dict[str, object]]:
    dates = tuple(sorted(frame["timestamp"].dt.date.unique()))
    windows = build_walk_forward_windows(dates, train_days=24, test_days=8, step_days=8)
    rows: list[dict[str, object]] = []
    for window_index, (train_start, train_end, test_start, test_end) in enumerate(windows, start=1):
        train_split = DateSplit(f"walk_forward_{window_index}_train", train_start, train_end)
        test_split = DateSplit(f"walk_forward_{window_index}_test", test_start, test_end)
        train_frame = filter_by_split(frame, train_split)
        test_frame = filter_by_split(frame, test_split)
        train_rows: list[dict[str, object]] = []
        for candidate in candidates:
            train_result = run_candidate(
                candidate,
                train_frame,
                cache_tag=f"wf{window_index}_train",
                cache_dir=cache_dir,
            )
            row = result_row(candidate, train_split.name, train_result)
            row["selection_score"] = selection_score(pd.Series(row))
            train_rows.append(row)
        train_results = pd.DataFrame(train_rows).sort_values(
            by=["selection_score", "excess_return", "total_return"],
            ascending=[False, False, False],
        )
        selected_name = str(train_results.iloc[0]["candidate"])
        selected = next(item for item in candidates if item.name == selected_name)
        test_result = run_candidate(
            selected,
            test_frame,
            cache_tag=f"wf{window_index}_test",
            cache_dir=cache_dir,
        )
        selected_train = train_results.iloc[0]
        rows.append(
            {
                **result_row(selected, test_split.name, test_result),
                "window_index": window_index,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "selected_candidate": selected.name,
                "train_selection_score": float(selected_train["selection_score"]),
                "train_total_return": float(selected_train["total_return"]),
                "train_benchmark_return": float(selected_train["benchmark_return"]),
                "train_excess_return": float(selected_train["excess_return"]),
                "train_max_drawdown": float(selected_train["max_drawdown"]),
            }
        )
    return rows


def build_rolling_windows(
    dates: tuple[object, ...],
    *,
    train_days: int,
    test_days: int,
    step_days: int,
) -> tuple[tuple[object, object], ...]:
    # The signal engine already needs lookback bars inside each slice. These
    # rolling windows are validation windows, not nested optimization windows.
    width = train_days + test_days
    output: list[tuple[object, object]] = []
    start = 0
    while start + width <= len(dates):
        output.append((dates[start], dates[start + width - 1]))
        start += step_days
    if not output and dates:
        output.append((dates[0], dates[-1]))
    return tuple(output)


def build_walk_forward_windows(
    dates: tuple[object, ...],
    *,
    train_days: int,
    test_days: int,
    step_days: int,
) -> tuple[tuple[object, object, object, object], ...]:
    output: list[tuple[object, object, object, object]] = []
    start = 0
    while start + train_days + test_days <= len(dates):
        train_start = dates[start]
        train_end = dates[start + train_days - 1]
        test_start = dates[start + train_days]
        test_end = dates[start + train_days + test_days - 1]
        output.append((train_start, train_end, test_start, test_end))
        start += step_days
    return tuple(output)


def format_report(
    *,
    data_path: Path,
    bars: pd.DataFrame,
    splits: tuple[DateSplit, ...],
    results: pd.DataFrame,
    summary: pd.DataFrame,
    rolling: pd.DataFrame,
    walk_forward: pd.DataFrame,
    selected: Candidate,
) -> str:
    selected_rows = results[results["candidate"] == selected.name].set_index("split")
    top = summary.head(10)
    selected_rolling = rolling[rolling["is_selected"]]
    rolling_positive = float((selected_rolling["total_return"] > 0).mean()) if len(selected_rolling) else 0.0
    rolling_avg = float(selected_rolling["total_return"].mean()) if len(selected_rolling) else 0.0
    rolling_mdd = float(selected_rolling["max_drawdown"].min()) if len(selected_rolling) else 0.0
    wf_positive = float((walk_forward["total_return"] > 0).mean()) if len(walk_forward) else 0.0
    wf_avg = float(walk_forward["total_return"].mean()) if len(walk_forward) else 0.0
    wf_excess_avg = float(walk_forward["excess_return"].mean()) if len(walk_forward) else 0.0
    wf_mdd = float(walk_forward["max_drawdown"].min()) if len(walk_forward) else 0.0
    split_lines = "\n".join(
        f"- `{item.name}`：`{item.start_date}` 至 `{item.end_date}`" for item in splits
    )
    selected_table = markdown_table(
        [
            {
                "阶段": name,
                "策略收益": pct(row["total_return"]),
                "基准收益": pct(row["benchmark_return"]),
                "超额": pct(row["excess_return"]),
                "最大回撤": pct(row["max_drawdown"]),
                "交易次数": int(row["trade_count"]),
            }
            for name, row in selected_rows.iterrows()
        ],
        ("阶段", "策略收益", "基准收益", "超额", "最大回撤", "交易次数"),
    )
    top_table = markdown_table(
        [
            {
                "候选": row["candidate"],
                "valid收益": pct(row["total_return_valid"]),
                "valid超额": pct(row["excess_return_valid"]),
                "test收益": pct(row["total_return_test"]),
                "test超额": pct(row["excess_return_test"]),
                "冷却": int(row["attack_min_hold_bars"]),
                "买强": f"{row['min_buy_signal_strength']:.0f}",
                "满攻": pct(row["attack_full_position_pct"]),
                "保护": pct(row["profit_protect_trigger_pct"]),
            }
            for _, row in top.iterrows()
        ],
        ("候选", "valid收益", "valid超额", "test收益", "test超额", "冷却", "买强", "满攻", "保护"),
    )
    candidate_stats = candidate_stability_stats(summary)
    rolling_table = markdown_table(
        [
            {
                "窗口": int(row["window_index"]),
                "开始": row["window_start"],
                "结束": row["window_end"],
                "收益": pct(row["total_return"]),
                "基准": pct(row["benchmark_return"]),
                "超额": pct(row["excess_return"]),
                "回撤": pct(row["max_drawdown"]),
            }
            for _, row in selected_rolling.iterrows()
        ],
        ("窗口", "开始", "结束", "收益", "基准", "超额", "回撤"),
    )
    walk_forward_table = markdown_table(
        [
            {
                "窗口": int(row["window_index"]),
                "训练段": f"{row['train_start']}~{row['train_end']}",
                "测试段": f"{row['test_start']}~{row['test_end']}",
                "入选": row["selected_candidate"],
                "训练收益": pct(row["train_total_return"]),
                "测试收益": pct(row["total_return"]),
                "测试基准": pct(row["benchmark_return"]),
                "测试超额": pct(row["excess_return"]),
                "回撤": pct(row["max_drawdown"]),
            }
            for _, row in walk_forward.iterrows()
        ],
        ("窗口", "训练段", "测试段", "入选", "训练收益", "测试收益", "测试基准", "测试超额", "回撤"),
    )
    return (
        "# 中远海控参数寻优、样本外回测与滚动验证\n\n"
        "## 数据\n\n"
        f"- 数据文件：`{data_path}`\n"
        f"- 数据范围：`{bars['timestamp'].min()}` 至 `{bars['timestamp'].max()}`\n"
        f"- 5 分钟 K 线：{len(bars)} 根\n"
        f"- 交易日：{bars['timestamp'].dt.date.nunique()} 天\n\n"
        "## 样本切分\n\n"
        f"{split_lines}\n\n"
        "选参只看 `train + valid`，`test` 作为最后样本外检验，不参与排序。\n\n"
        "## 入选参数\n\n"
        f"- 候选：`{selected.name}`\n"
        f"- 最低买入强度：{selected.min_buy_signal_strength:.1f}\n"
        f"- 突破确认分：{selected.attack_confirm_min_breakout_score:.1f}\n"
        f"- 突破确认买入强度：{selected.attack_confirm_min_buy_strength:.1f}\n"
        f"- 最大进攻仓位：{selected.max_signal_position_pct:.0%}\n"
        f"- 满攻/确认/预警仓位：{selected.attack_full_position_pct:.0%} / "
        f"{selected.attack_confirm_position_pct:.0%} / {selected.attack_watch_position_pct:.0%}\n"
        f"- 进攻仓冷却：{selected.attack_min_hold_bars} 根 5 分钟 K\n"
        f"- 趋势跟随持有冷却：{selected.trend_follow_min_hold_bars} 根 5 分钟 K\n"
        f"- 资金确认仓位加成：{selected.confirmed_flow_position_bonus_pct:.0%}\n"
        f"- 利润保护触发：{selected.profit_protect_trigger_pct:.1%}\n"
        f"- 软退出卖压：{selected.attack_exit_sell_pressure_score:.1f}\n"
        f"- 软退出 1 日下跌概率：{selected.attack_exit_down_probability:.0%}\n\n"
        "## 入选参数分段表现\n\n"
        f"{selected_table}\n\n"
        "## 验证集排序前 10\n\n"
        f"{top_table}\n\n"
        "## 候选参数稳定性诊断\n\n"
        f"- 候选总数：{candidate_stats['count']}\n"
        f"- 验证集正收益候选：{candidate_stats['valid_positive']}\n"
        f"- 测试集正收益候选：{candidate_stats['test_positive']}\n"
        f"- 验证集和测试集同时正收益候选：{candidate_stats['valid_and_test_positive']}\n"
        f"- 测试集超额收益为正候选：{candidate_stats['test_excess_positive']}\n\n"
        "## 滚动验证\n\n"
        "这里使用入选参数做固定参数滚动窗口验证，观察同一组参数在不同阶段是否稳定。\n\n"
        f"- 滚动窗口正收益比例：{rolling_positive:.1%}\n"
        f"- 滚动窗口平均收益：{rolling_avg:.2%}\n"
        f"- 滚动窗口最差回撤：{rolling_mdd:.2%}\n\n"
        f"{rolling_table}\n\n"
        "## 滚动寻优样本外验证\n\n"
        "每个窗口先用历史训练段选参数，再只在后续测试段验证，避免未来数据参与选择。\n\n"
        f"- 样本外窗口正收益比例：{wf_positive:.1%}\n"
        f"- 样本外平均收益：{wf_avg:.2%}\n"
        f"- 样本外平均超额：{wf_excess_avg:.2%}\n"
        f"- 样本外最差回撤：{wf_mdd:.2%}\n\n"
        f"{walk_forward_table}\n\n"
        "## 判断\n\n"
        "- 若 `valid` 和 `test` 同时为正，并且滚动正收益比例超过 50%，说明参数有初步稳定性。\n"
        "- 若滚动寻优样本外正收益比例超过 50%，并且平均超额为正，说明调参流程有初步可迁移性。\n"
        "- 若只在 `valid` 盈利、`test` 或滚动验证转弱，说明仍存在过拟合，不能作为定型策略。\n"
        "- 该报告仍只用于手动参考模型研究，不代表自动下单或收益保证。\n"
    )


def candidate_stability_stats(summary: pd.DataFrame) -> dict[str, int]:
    valid_positive = summary["total_return_valid"] > 0
    test_positive = summary["total_return_test"] > 0
    return {
        "count": int(len(summary)),
        "valid_positive": int(valid_positive.sum()),
        "test_positive": int(test_positive.sum()),
        "valid_and_test_positive": int((valid_positive & test_positive).sum()),
        "test_excess_positive": int((summary["excess_return_test"] > 0).sum()),
    }


def markdown_table(rows: list[dict[str, object]], columns: tuple[str, ...]) -> str:
    if not rows:
        return "无数据"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(str(row.get(col, "")) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def pct(value: object) -> str:
    try:
        return f"{float(value):.2%}"
    except Exception:  # noqa: BLE001
        return "n/a"


if __name__ == "__main__":
    raise SystemExit(main())
