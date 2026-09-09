#!/usr/bin/env python3
"""Compare TopN walk-forward stability across capture-bias experiments."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_EXPERIMENTS = (
    "baseline=reports/backtests/codex_full_baseline_trend_capture_equal_20260701",
    "relaxed_volume=reports/backtests/codex_full_relaxed_volume_distribution_equal_20260701",
    "lifecycle_search=reports/backtests/codex_full_lifecycle_rule_search_equal_20260701",
    "lifecycle_relaxed=reports/backtests/codex_full_lifecycle_relaxed_volume_equal_20260701",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="baseline", help="Experiment label used as the baseline for deltas.")
    parser.add_argument("--experiment", action="append", default=[], help="LABEL=PREFIX without the _summary.csv suffix.")
    parser.add_argument("--top-n", nargs="*", type=int, default=[50, 100])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/backtests/capture_bias_stability_20260702.md"),
    )
    args = parser.parse_args()

    experiment_specs = args.experiment or list(DEFAULT_EXPERIMENTS)
    experiments = [_parse_experiment_spec(spec) for spec in experiment_specs]
    top_n_values = sorted({value for value in args.top_n if value > 0})
    if not top_n_values:
        raise SystemExit("--top-n must contain at least one positive value")

    data = {label: _load_experiment(prefix) for label, prefix in experiments}
    if args.baseline not in data:
        raise SystemExit(f"baseline label {args.baseline!r} is not present in experiments")

    baseline_portfolio = data[args.baseline]["portfolio"]
    rows: list[dict[str, object]] = []
    for label, frames in data.items():
        summary = frames["summary"]
        portfolio = frames["portfolio"]
        for top_n in top_n_values:
            summary_row = summary[summary["top_n"].astype(int) == top_n]
            if summary_row.empty:
                continue
            summary_row = summary_row.iloc[0]
            top_portfolio = portfolio[portfolio["top_n"].astype(int) == top_n].copy()
            baseline_top = baseline_portfolio[baseline_portfolio["top_n"].astype(int) == top_n].copy()
            rows.append(_stability_row(label, top_n, summary_row, top_portfolio, baseline_top))

    stability = pd.DataFrame(rows).sort_values(["top_n", "return_delta_pct"], ascending=[True, False])
    csv_path = args.output.with_suffix(".csv")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stability.to_csv(csv_path, index=False)
    args.output.write_text(_format_report(stability, csv_path=csv_path, baseline=args.baseline), encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Wrote {csv_path}")
    return 0


def _parse_experiment_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise SystemExit(f"--experiment must use LABEL=PREFIX: {spec}")
    label, prefix = spec.split("=", 1)
    label = label.strip()
    prefix = prefix.strip()
    if not label or not prefix:
        raise SystemExit(f"--experiment must use LABEL=PREFIX: {spec}")
    return label, Path(prefix)


def _load_experiment(prefix: Path) -> dict[str, pd.DataFrame]:
    summary_path = prefix.with_name(f"{prefix.name}_summary.csv")
    portfolio_path = prefix.with_name(f"{prefix.name}_portfolio.csv")
    if not summary_path.exists():
        raise SystemExit(f"missing summary CSV: {summary_path}")
    if not portfolio_path.exists():
        raise SystemExit(f"missing portfolio CSV: {portfolio_path}")
    return {
        "summary": pd.read_csv(summary_path),
        "portfolio": pd.read_csv(portfolio_path),
    }


def _stability_row(
    label: str,
    top_n: int,
    summary_row: pd.Series,
    portfolio: pd.DataFrame,
    baseline_portfolio: pd.DataFrame,
) -> dict[str, object]:
    returns = pd.to_numeric(portfolio["valid_total_return"], errors="coerce").fillna(0.0)
    baseline = baseline_portfolio[["window_id", "valid_total_return"]].rename(columns={"valid_total_return": "baseline_return"})
    joined = portfolio[["window_id", "valid_total_return"]].merge(baseline, on="window_id", how="inner")
    deltas = pd.to_numeric(joined["valid_total_return"], errors="coerce") - pd.to_numeric(joined["baseline_return"], errors="coerce")
    rule_counts = portfolio["rule_id"].astype(str).value_counts()
    total_return = float(summary_row["walkforward_total_return"])
    baseline_total = _compound_return(pd.to_numeric(baseline_portfolio["valid_total_return"], errors="coerce").fillna(0.0))
    return {
        "experiment": label,
        "top_n": top_n,
        "walkforward_return_pct": total_return * 100.0,
        "return_delta_pct": (total_return - baseline_total) * 100.0,
        "window_win_rate_pct": float(summary_row["window_win_rate"]) * 100.0,
        "windows_beating_baseline": int((deltas > 0).sum()),
        "window_count": int(len(portfolio)),
        "avg_window_delta_pct": float(deltas.mean() * 100.0) if not deltas.empty else 0.0,
        "median_window_return_pct": float(returns.median() * 100.0) if not returns.empty else 0.0,
        "min_window_return_pct": float(returns.min() * 100.0) if not returns.empty else 0.0,
        "window_return_std_pct": float(returns.std(ddof=0) * 100.0) if not returns.empty else 0.0,
        "worst_drawdown_pct": float(summary_row["worst_window_max_drawdown"]) * 100.0,
        "avg_drawdown_pct": float(summary_row["avg_window_max_drawdown"]) * 100.0,
        "positive_constituent_rate_pct": float(summary_row["avg_constituent_positive_rate"]) * 100.0,
        "unique_rule_count": int(rule_counts.size),
        "dominant_rule": str(rule_counts.index[0]) if not rule_counts.empty else "",
        "dominant_rule_share_pct": float(rule_counts.iloc[0] / len(portfolio) * 100.0) if len(portfolio) else 0.0,
        "leave_one_window_out_min_pct": _leave_one_window_out_min(returns),
    }


def _compound_return(returns: pd.Series) -> float:
    value = 1.0
    for period_return in returns:
        value *= 1.0 + float(period_return)
    return value - 1.0


def _leave_one_window_out_min(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    values = []
    for index in returns.index:
        values.append(_compound_return(returns.drop(index)) * 100.0)
    return float(min(values)) if values else 0.0


def _format_report(stability: pd.DataFrame, *, csv_path: Path, baseline: str) -> str:
    lines = [
        "# Capture-bias Top50/100 稳定性验证",
        "",
        f"- 基准实验：`{baseline}`",
        f"- 明细 CSV：`{csv_path}`",
        "- 判断口径：walk-forward 复利收益、相对基准增量、逐窗口跑赢次数、最差窗口收益/回撤、规则集中度、leave-one-window-out 下限。",
        "",
        "## 汇总",
        "",
        _markdown_table(stability),
        "",
        "## 读取建议",
        "",
        "- Top100 优先看 `walkforward_return_pct`、`return_delta_pct` 和 `leave_one_window_out_min_pct`，避免单窗口贡献过大。",
        "- Top50 优先看 `windows_beating_baseline` 和 `avg_window_delta_pct`，小幅收益提升必须有足够窗口覆盖才值得固化。",
        "- `dominant_rule_share_pct` 过高说明规则池可能过窄；`unique_rule_count` 过高且收益不稳说明选择器可能过度切换。",
    ]
    return "\n".join(lines) + "\n"


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_无数据_"
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append(f"{value:.2f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
