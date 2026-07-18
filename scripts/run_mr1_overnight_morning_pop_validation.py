#!/usr/bin/env python3
"""Run MR-1 from one immutable EXPLORATORY PRR Dataset without provider access."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_regime_alpha.research.mr1_morning_pop import (  # noqa: E402
    MR1ExitTime,
    build_mr1_targets,
    replay_mr1_fixed_portfolios,
)
from market_regime_alpha.research.prr_mvp_1 import ExploratoryExecutionCostConfig  # noqa: E402
from market_regime_alpha.research.tencent_composite_contracts import (  # noqa: E402
    CompositeBar,
    CompositeSourceKind,
    PreparedCompositeData,
    PreparedCompositeSession,
)


TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_ROOT = PROJECT_ROOT / "data" / "processed" / "mr1_morning_pop_runs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--top-k", type=int, default=5)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset = args.dataset.resolve()
    manifest = _read_json(dataset / "dataset_manifest.json")
    if manifest.get("data_eligibility") != "EXPLORATORY":
        raise SystemExit("MR-1 only accepts an EXPLORATORY Dataset")
    _verify_dataset(dataset)
    prepared, bars, rankings, decision_dates = _load_dataset(dataset)
    targets = build_mr1_targets(prepared=prepared, bars=bars, decision_dates=decision_dates)
    all_orders: list[dict[str, Any]] = []
    all_fills: list[dict[str, Any]] = []
    all_trades: list[dict[str, Any]] = []
    all_equity: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    comparison: dict[str, Any] = {"schema_version": "mr-1-exit-time-comparison-v1", "descriptive_only": True, "results": []}
    baseline = _candidate_baseline(targets)
    for scenario, costs in _cost_scenarios().items():
        for exit_time in MR1ExitTime:
            replay = replay_mr1_fixed_portfolios(
                prepared=prepared,
                ranking_rows=rankings,
                target_rows=targets,
                decision_dates=decision_dates,
                top_k=args.top_k,
                exit_time=exit_time,
                cost_scenario=scenario,
                cost_config=costs,
            )
            all_orders.extend(replay.orders)
            all_fills.extend(replay.fills)
            all_trades.extend(replay.trades)
            all_equity.extend(replay.daily_equity)
            for model_id, metrics in replay.metrics["models"].items():
                row = {
                    "model_id": model_id,
                    "exit_time": exit_time.value,
                    "cost_scenario": scenario,
                    **metrics,
                    "candidate_baseline_cumulative_return": baseline.get(exit_time.value),
                }
                metric_rows.append(row)
                comparison["results"].append(row)
    _add_chronological_diagnostics(metric_rows, all_equity, baseline)
    _apply_failure_labels(metric_rows, all_equity)
    run_id = _run_id(dataset, args.top_k)
    final = _write_run(
        root=args.output_root,
        run_id=run_id,
        dataset=dataset,
        dataset_manifest=manifest,
        targets=targets,
        orders=all_orders,
        fills=all_fills,
        trades=all_trades,
        equity=all_equity,
        metrics=metric_rows,
        comparison=comparison,
        top_k=args.top_k,
    )
    print(f"MR-1 completed: {final}")
    return 0


def _load_dataset(dataset: Path) -> tuple[PreparedCompositeData, tuple[CompositeBar, ...], tuple[dict[str, Any], ...], tuple[date, ...]]:
    prepared_frame = pd.read_parquet(dataset / "prepared_sessions.parquet")
    bars_frame = pd.read_parquet(dataset / "bars.parquet")
    rankings_frame = pd.read_parquet(dataset / "candidate_rankings.parquet")
    sessions = tuple(
        PreparedCompositeSession(
            symbol=str(row.symbol), session_date=date.fromisoformat(str(row.session_date)),
            open=float(row.open), high=float(row.high), low=float(row.low), close=float(row.close), amount=float(row.amount),
            reference_price=float(row.reference_price), reference_timestamp=datetime.fromisoformat(str(row.reference_timestamp)),
            source_kinds=(CompositeSourceKind(str(row.source_kinds)),),
        )
        for row in prepared_frame.itertuples(index=False)
    )
    symbols = tuple(sorted({session.symbol for session in sessions}))
    dates = tuple(sorted({session.session_date for session in sessions}))
    prepared = PreparedCompositeData(
        accepted_symbols=symbols, common_session_dates=dates, sessions=sessions,
        quality=type("MR1Quality", (), {"accepted_symbols": symbols})(), limitations=("AUXILIARY_DATA_ONLY",),
    )
    bars = tuple(
        CompositeBar(
            symbol=str(row.symbol), timestamp=datetime.fromisoformat(str(row.timestamp)),
            open=float(row.open), high=float(row.high), low=float(row.low), close=float(row.close), volume=float(row.volume), amount=float(row.amount),
            source=CompositeSourceKind(str(row.source)),
        )
        for row in bars_frame.itertuples(index=False)
    )
    ranking_rows = tuple(rankings_frame.to_dict(orient="records"))
    # Candidate materialization has 60 dates and one following session for every date.
    decision_dates = tuple(sorted(date.fromisoformat(str(item)) for item in rankings_frame["decision_date"].unique()))
    return prepared, bars, ranking_rows, decision_dates


def _cost_scenarios() -> dict[str, ExploratoryExecutionCostConfig]:
    return {
        "LOW": ExploratoryExecutionCostConfig(buy_commission_bps=1.0, sell_commission_bps=1.0, minimum_commission=1.0, sell_stamp_duty_bps=2.5, entry_slippage_bps=1.0, exit_slippage_bps=1.0),
        "BASE": ExploratoryExecutionCostConfig(),
        "HIGH": ExploratoryExecutionCostConfig(buy_commission_bps=10.0, sell_commission_bps=10.0, minimum_commission=10.0, sell_stamp_duty_bps=10.0, entry_slippage_bps=15.0, exit_slippage_bps=15.0),
    }


def _candidate_baseline(targets: tuple[dict[str, Any], ...]) -> dict[str, float | None]:
    exit_targets = {"09:35": "NEXT_SESSION_0935_RETURN", "10:00": "NEXT_SESSION_1000_RETURN", "10:30": "NEXT_SESSION_1030_RETURN", "CLOSE": "NEXT_SESSION_CLOSE_RETURN"}
    result: dict[str, float | None] = {}
    for exit_time, target_id in exit_targets.items():
        by_date: dict[str, list[float]] = {}
        for row in targets:
            if row["target_id"] == target_id and row["status"] == "AVAILABLE":
                by_date.setdefault(str(row["decision_date"]), []).append(float(row["value"]))
        if len(by_date) == 0:
            result[exit_time] = None
        else:
            equity = 1.0
            for values in by_date.values():
                equity *= 1.0 + sum(values) / len(values)
            result[exit_time] = equity - 1.0
    return result


def _add_chronological_diagnostics(metrics: list[dict[str, Any]], equity: list[dict[str, Any]], baseline: dict[str, float | None]) -> None:
    rows_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in equity:
        rows_by_key.setdefault((str(row["model_id"]), str(row["exit_time"]), str(row["cost_scenario"])), []).append(row)
    for metric in metrics:
        rows = sorted(rows_by_key[(metric["model_id"], metric["exit_time"], metric["cost_scenario"])], key=lambda item: item["session_date"])
        segments = [rows[:20], rows[20:40], rows[40:60]]
        segment_returns = [(_compound(segment) if segment else None) for segment in segments]
        metric["first_20_return"], metric["middle_20_return"], metric["last_20_return"] = segment_returns
        metric["rolling_20_date_stability"] = [round(_compound(rows[index:index + 20]), 12) for index in range(max(0, len(rows) - 19))]
        metric["maximum_losing_streak"] = _maximum_losing_streak(rows)
        metric["top5_excess_over_candidate_baseline"] = (
            metric["net_cumulative_return"] - baseline[metric["exit_time"]]
            if baseline[metric["exit_time"]] is not None else None
        )


def _apply_failure_labels(metrics: list[dict[str, Any]], equity: list[dict[str, Any]]) -> None:
    scenario_index = {(row["model_id"], row["exit_time"], row["cost_scenario"]): row for row in metrics}
    for row in metrics:
        if row["cost_scenario"] != "BASE":
            continue
        scenarios = [scenario_index[(row["model_id"], row["exit_time"], scenario)] for scenario in ("LOW", "BASE", "HIGH")]
        segments = [row["first_20_return"], row["middle_20_return"], row["last_20_return"]]
        daily = [item for item in equity if item["model_id"] == row["model_id"] and item["exit_time"] == row["exit_time"] and item["cost_scenario"] == "BASE"]
        positive_sum = sum(max(float(item["net_return"]), 0.0) for item in daily)
        concentrated = positive_sum > 0.0 and max((max(float(item["net_return"]), 0.0) for item in daily), default=0.0) / positive_sum > 0.5
        promising = (
            row["top5_excess_over_candidate_baseline"] is not None and row["top5_excess_over_candidate_baseline"] > 0.0
            and all(value is not None and value > 0.0 for value in segments)
            and row["maximum_drawdown"] >= -0.15
            and all(item["net_cumulative_return"] > 0.0 for item in scenarios)
            and not concentrated
        )
        failed = row["net_cumulative_return"] <= 0.0 or scenarios[-1]["net_cumulative_return"] <= 0.0 or row["maximum_drawdown"] < -0.25
        label = "PROMISING_EXPLORATORY" if promising else "FAILED_EXPLORATORY" if failed else "INCONCLUSIVE"
        for scenario in scenarios:
            scenario["exploratory_assessment"] = label
            scenario["assessment_rule_version"] = "mr-1-assessment-v1"
            scenario["assessment_notice"] = "DESCRIPTIVE ONLY — NO MODEL SELECTION"


def _compound(rows: list[dict[str, Any]]) -> float:
    value = 1.0
    for row in rows:
        value *= 1.0 + float(row["net_return"])
    return value - 1.0


def _maximum_losing_streak(rows: list[dict[str, Any]]) -> int:
    longest = current = 0
    for row in rows:
        current = current + 1 if float(row["net_return"]) < 0.0 else 0
        longest = max(longest, current)
    return longest


def _run_id(dataset: Path, top_k: int) -> str:
    payload = (
        f"{dataset.resolve()}:{_file_hash(dataset / 'dataset_manifest.json')}:{top_k}:"
        f"{_file_hash(Path(__file__))}"
    ).encode()
    return f"mr1-{sha256(payload).hexdigest()[:20]}"


def _write_run(*, root: Path, run_id: str, dataset: Path, dataset_manifest: dict[str, Any], targets: tuple[dict[str, Any], ...], orders: list[dict[str, Any]], fills: list[dict[str, Any]], trades: list[dict[str, Any]], equity: list[dict[str, Any]], metrics: list[dict[str, Any]], comparison: dict[str, Any], top_k: int) -> Path:
    final = root / run_id
    stage = root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError(f"MR-1 run is immutable: {final}")
    stage.mkdir(parents=True)
    try:
        _write_json(stage / "manifest.json", {"schema_version": "mr-1-run-v1", "run_id": run_id, "dataset_id": dataset_manifest["dataset_id"], "dataset_path": str(dataset), "dataset_manifest_hash": _file_hash(dataset / "dataset_manifest.json"), "data_eligibility": "EXPLORATORY", "top_k": top_k, "exit_times": [item.value for item in MR1ExitTime], "cost_scenarios": ["LOW", "BASE", "HIGH"]})
        _write_json(stage / "limitations.json", ["CURRENT_WATCHLIST_BACKFILL_BIAS", "HISTORICAL_PIT_NOT_VERIFIED", "HISTORICAL_BUYABILITY_NOT_VERIFIED", "REFERENCE_MARK_NOT_FILL_PROOF", "NO_LEVEL2_OR_ORDER_BOOK", "FEE_ASSUMPTIONS_REQUIRE_CURRENT_VERIFICATION", "AUXILIARY_DATA_ONLY", "FORMAL_OOS_NOT_ESTABLISHED"])
        _write_parquet(stage / "morning_targets.parquet", targets)
        _write_parquet(stage / "orders.parquet", orders)
        _write_parquet(stage / "fills.parquet", fills)
        _write_parquet(stage / "trades.parquet", trades)
        _write_parquet(stage / "daily_equity.parquet", equity)
        _write_parquet(stage / "chronological_model_metrics.parquet", metrics)
        pd.DataFrame(metrics).to_csv(stage / "model_target_matrix.csv", index=False)
        _write_json(stage / "exit_time_comparison.json", comparison)
        _write_json(stage / "metrics.json", metrics)
        _write_report(stage / "report.md", run_id, dataset_manifest["dataset_id"], metrics)
        _write_checksums(stage)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _write_report(path: Path, run_id: str, dataset_id: str, metrics: list[dict[str, Any]]) -> None:
    base = [row for row in metrics if row["cost_scenario"] == "BASE"]
    lines = ["# MR-1 Overnight Morning-Pop Signal Validation", "", f"- Run ID: `{run_id}`", f"- Dataset ID: `{dataset_id}`", "- Authority: `EXPLORATORY`", "- 14:55 reference is a research mark, not fill proof.", "- DESCRIPTIVE ONLY — NO MODEL SELECTION.", "", "## Base-cost assessment", "", "| Model | Exit | Net cumulative | Max drawdown | Assessment |", "| --- | --- | ---: | ---: | --- |"]
    for row in sorted(base, key=lambda item: (item["exit_time"], item["model_id"])):
        lines.append(f"| {row['model_id']} | {row['exit_time']} | {row['net_cumulative_return']:.4%} | {row['maximum_drawdown']:.4%} | {row.get('exploratory_assessment', 'INCONCLUSIVE')} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verify_dataset(dataset: Path) -> None:
    expected = _read_json(dataset / "SHA256SUMS.json")
    for name, expected_hash in expected.items():
        if _file_hash(dataset / name) != expected_hash:
            raise ValueError(f"immutable Dataset checksum mismatch: {name}")


def _write_checksums(path: Path) -> None:
    _write_json(path / "SHA256SUMS.json", {item.name: _file_hash(item) for item in sorted(path.iterdir()) if item.name != "SHA256SUMS.json"})


def _write_parquet(path: Path, rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> None:
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


if __name__ == "__main__":
    raise SystemExit(main())
