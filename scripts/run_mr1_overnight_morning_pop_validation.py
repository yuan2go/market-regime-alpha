#!/usr/bin/env python3
"""Run MR-1 from one immutable EXPLORATORY PRR Dataset without provider access."""

from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_regime_alpha.research.mr1_morning_pop import (  # noqa: E402
    MR1ExitTime,
    MR1TargetId,
    MR1_MORNING_TARGET_SCHEMA_VERSION,
    build_mr1_targets,
    replay_mr1_fixed_portfolios,
)
from market_regime_alpha.research.prr_artifact_reader import (  # noqa: E402
    MR1_RUN_FILENAMES,
    MR1_RUN_SCHEMA_VERSION,
    VerifiedPRRDataset,
    load_verified_prr_dataset,
)
from market_regime_alpha.research.prr_mvp_1 import ExploratoryExecutionCostConfig  # noqa: E402


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
    verified_dataset = load_verified_prr_dataset(dataset)
    manifest = dict(verified_dataset.manifest)
    prepared, bars, rankings, decision_dates = _dataset_inputs(verified_dataset)
    targets = build_mr1_targets(prepared=prepared, bars=bars, decision_dates=decision_dates)
    all_orders: list[dict[str, Any]] = []
    all_fills: list[dict[str, Any]] = []
    all_trades: list[dict[str, Any]] = []
    all_equity: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    comparison: dict[str, Any] = {"schema_version": "mr-1-exit-time-comparison-v1", "descriptive_only": True, "results": []}
    cost_scenarios = _cost_scenarios()
    baseline_rows = _candidate_daily_baselines(targets, cost_scenarios)
    baselines = _compound_daily_baselines(baseline_rows)
    for scenario, costs in cost_scenarios.items():
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
                    "candidate_baseline_gross_cumulative_return": baselines[scenario][exit_time.value]["gross"],
                    "candidate_baseline_net_cumulative_return": baselines[scenario][exit_time.value]["net"],
                    "candidate_baseline_kind": "NON_TRADABLE_CROSS_SECTIONAL_DIAGNOSTIC_WITH_SAME_COST_MECHANICS",
                }
                metric_rows.append(row)
                comparison["results"].append(row)
    _add_chronological_diagnostics(metric_rows, all_equity)
    _apply_failure_labels(metric_rows, all_equity)
    run_identity = _run_identity(dataset, args.top_k, rankings)
    run_id = f"mr1-{_canonical_hash(run_identity)[:20]}"
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
        run_identity=run_identity,
        baseline_rows=baseline_rows,
    )
    print(f"MR-1 completed: {final}")
    return 0


def _dataset_inputs(
    verified: VerifiedPRRDataset,
) -> tuple[Any, tuple[Any, ...], tuple[dict[str, Any], ...], tuple[date, ...]]:
    """Adapt a frozen reader result to MR-1's existing calculation interface."""

    return (
        verified.prepared,
        verified.bars,
        tuple(dict(row) for row in verified.ranking_rows),
        verified.decision_dates,
    )


# Historical MR-2 script compatibility only. New consumers use prr_artifact_reader.
def _load_dataset(
    dataset: Path,
) -> tuple[Any, tuple[Any, ...], tuple[dict[str, Any], ...], tuple[date, ...]]:
    return _dataset_inputs(load_verified_prr_dataset(dataset))


def _cost_scenarios() -> dict[str, ExploratoryExecutionCostConfig]:
    return {
        "LOW": ExploratoryExecutionCostConfig(buy_commission_bps=1.0, sell_commission_bps=1.0, minimum_commission=1.0, sell_stamp_duty_bps=2.5, entry_slippage_bps=1.0, exit_slippage_bps=1.0),
        "BASE": ExploratoryExecutionCostConfig(),
        "HIGH": ExploratoryExecutionCostConfig(buy_commission_bps=10.0, sell_commission_bps=10.0, minimum_commission=10.0, sell_stamp_duty_bps=10.0, entry_slippage_bps=15.0, exit_slippage_bps=15.0),
    }


def _candidate_daily_baselines(targets: tuple[dict[str, Any], ...], costs_by_scenario: dict[str, ExploratoryExecutionCostConfig]) -> list[dict[str, Any]]:
    exit_targets = {
        "09:35": "NEXT_SESSION_0935_RETURN",
        "10:00": "NEXT_SESSION_1000_RETURN",
        "10:30": "NEXT_SESSION_1030_RETURN",
        "CLOSE": "NEXT_SESSION_CLOSE_RETURN",
    }
    rows: list[dict[str, Any]] = []
    for exit_time, target_id in exit_targets.items():
        dates = sorted({str(row["decision_date"]) for row in targets if row["target_id"] == target_id})
        for scenario, costs in costs_by_scenario.items():
            for decision_date in dates:
                all_rows = [row for row in targets if row["target_id"] == target_id and row["decision_date"] == decision_date]
                observed = [row for row in all_rows if row["status"] == "AVAILABLE"]
                weight = 1.0 / len(all_rows) if all_rows else 0.0
                observed_weight = len(observed) * weight
                missing_weight = (len(all_rows) - len(observed)) * weight
                if all_rows and abs((observed_weight + missing_weight) - 1.0) > 1e-12:
                    raise ValueError("Candidate daily baseline weights must reconcile to one")
                rows.append(
                    {
                        "schema_version": "mr-1-candidate-daily-baseline-v1",
                        "decision_date": decision_date,
                        "exit_time": exit_time,
                        "cost_scenario": scenario,
                        "candidate_gross_return": sum(float(row["value"]) * weight for row in observed),
                        "candidate_net_return": sum(
                            weight * _candidate_slot_net_return(row, weight, costs)
                            for row in observed
                        ),
                        "candidate_symbol_count": len(all_rows),
                        "candidate_observed_weight": observed_weight,
                        "candidate_missing_weight": missing_weight,
                        "baseline_kind": "NON_TRADABLE_CROSS_SECTIONAL_DIAGNOSTIC_WITH_SAME_COST_MECHANICS",
                        "data_eligibility": "EXPLORATORY",
                    }
                )
    return rows


def _compound_daily_baselines(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    result: dict[str, dict[str, dict[str, float]]] = {}
    for row in rows:
        scenario = str(row["cost_scenario"])
        exit_time = str(row["exit_time"])
        result.setdefault(scenario, {}).setdefault(exit_time, {"gross": 1.0, "net": 1.0})
        result[scenario][exit_time]["gross"] *= 1.0 + float(row["candidate_gross_return"])
        result[scenario][exit_time]["net"] *= 1.0 + float(row["candidate_net_return"])
    for scenario_values in result.values():
        for values in scenario_values.values():
            values["gross"] -= 1.0
            values["net"] -= 1.0
    return result


def _candidate_slot_net_return(row: dict[str, Any], weight: float, costs: ExploratoryExecutionCostConfig) -> float:
    reference_price = float(row["reference_price"])
    exit_price = float(row["exit_price"])
    entry_price = reference_price * (1.0 + costs.entry_slippage_bps / 10_000.0)
    realized_exit = exit_price * (1.0 - costs.exit_slippage_bps / 10_000.0)
    entry_notional = costs.normalized_trade_notional * weight
    quantity = entry_notional / entry_price
    exit_notional = quantity * realized_exit
    buy = max(entry_notional * costs.buy_commission_bps / 10_000.0, costs.minimum_commission)
    sell = max(exit_notional * costs.sell_commission_bps / 10_000.0, costs.minimum_commission)
    stamp = exit_notional * costs.sell_stamp_duty_bps / 10_000.0
    transfer = (entry_notional + exit_notional) * costs.transfer_fee_bps / 10_000.0
    return (exit_notional - buy - sell - stamp - transfer - entry_notional) / entry_notional


def _add_chronological_diagnostics(metrics: list[dict[str, Any]], equity: list[dict[str, Any]]) -> None:
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
        metric["top5_gross_minus_candidate_gross"] = metric["gross_cumulative_return"] - metric["candidate_baseline_gross_cumulative_return"]
        metric["top5_net_minus_candidate_net"] = metric["net_cumulative_return"] - metric["candidate_baseline_net_cumulative_return"]


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
            row["top5_net_minus_candidate_net"] > 0.0
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


def _run_identity(dataset: Path, top_k: int, rankings: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    module = PROJECT_ROOT / "src" / "market_regime_alpha" / "research" / "mr1_morning_pop.py"
    model_ids = sorted({str(row["model_id"]) for row in rankings})
    costs = _cost_scenarios()
    return {
        "dataset_id": _read_json(dataset / "dataset_manifest.json")["dataset_id"],
        "dataset_checksums_hash": _file_hash(dataset / "SHA256SUMS.json"),
        "git_commit_sha": _revision(),
        "mr1_morning_pop_module_hash": _file_hash(module),
        "runner_hash": _file_hash(Path(__file__)),
        "target_schema_ids": [MR1_MORNING_TARGET_SCHEMA_VERSION, *(item.value for item in MR1TargetId)],
        "candidate_daily_baseline_schema_version": "mr-1-candidate-daily-baseline-v1",
        "model_ids": model_ids,
        "top_k": top_k,
        "cost_scenario_config_hashes": {name: _canonical_hash(repr(value)) for name, value in costs.items()},
    }


def _write_run(
    *,
    root: Path,
    run_id: str,
    dataset: Path,
    dataset_manifest: dict[str, Any],
    targets: tuple[dict[str, Any], ...],
    orders: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    equity: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    comparison: dict[str, Any],
    top_k: int,
    run_identity: dict[str, Any],
    baseline_rows: list[dict[str, Any]],
) -> Path:
    final = root / run_id
    stage = root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError(f"MR-1 run is immutable: {final}")
    stage.mkdir(parents=True)
    try:
        _write_json(
            stage / "manifest.json",
            {
                "schema_version": MR1_RUN_SCHEMA_VERSION,
                "run_id": run_id,
                "dataset_id": dataset_manifest["dataset_id"],
                "dataset_path": str(dataset),
                "dataset_manifest_hash": _file_hash(dataset / "dataset_manifest.json"),
                "data_eligibility": "EXPLORATORY",
                "top_k": top_k,
                "exit_times": [item.value for item in MR1ExitTime],
                "cost_scenarios": ["LOW", "BASE", "HIGH"],
                "required_artifacts": sorted(MR1_RUN_FILENAMES),
                "candidate_daily_baseline_schema_version": "mr-1-candidate-daily-baseline-v1",
                "run_identity": run_identity,
            },
        )
        _write_json(stage / "limitations.json", ["CURRENT_WATCHLIST_BACKFILL_BIAS", "HISTORICAL_PIT_NOT_VERIFIED", "HISTORICAL_BUYABILITY_NOT_VERIFIED", "REFERENCE_MARK_NOT_FILL_PROOF", "NO_LEVEL2_OR_ORDER_BOOK", "FEE_ASSUMPTIONS_REQUIRE_CURRENT_VERIFICATION", "AUXILIARY_DATA_ONLY", "FORMAL_OOS_NOT_ESTABLISHED"])
        _write_parquet(stage / "morning_targets.parquet", targets)
        _write_parquet(stage / "orders.parquet", orders)
        _write_parquet(stage / "fills.parquet", fills)
        _write_parquet(stage / "trades.parquet", trades)
        _write_parquet(stage / "daily_equity.parquet", equity)
        _write_parquet(stage / "candidate_daily_baseline.parquet", baseline_rows)
        _write_parquet(stage / "chronological_model_metrics.parquet", metrics)
        pd.DataFrame(metrics).to_csv(stage / "model_target_matrix.csv", index=False)
        _write_json(stage / "exit_time_comparison.json", comparison)
        _write_json(stage / "metrics.json", metrics)
        _write_report(stage / "report.md", run_id, dataset_manifest["dataset_id"], metrics)
        _write_checksums(stage)
        _validate_file_set(stage, MR1_RUN_FILENAMES)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _write_report(path: Path, run_id: str, dataset_id: str, metrics: list[dict[str, Any]]) -> None:
    base = [row for row in metrics if row["cost_scenario"] == "BASE"]
    lines = ["# MR-1 Overnight Morning-Pop Signal Validation", "", f"- Run ID: `{run_id}`", f"- Dataset ID: `{dataset_id}`", "- Authority: `EXPLORATORY`", "- 14:55 reference is a research mark, not fill proof.", "- `candidate_daily_baseline.parquet` is a non-tradable cross-sectional diagnostic with the same cost mechanics and fixed missing-slot cash weight.", "- DESCRIPTIVE ONLY — NO MODEL SELECTION.", "", "## Base-cost assessment", "", "| Model | Exit | Net cumulative | Max drawdown | Assessment |", "| --- | --- | ---: | ---: | --- |"]
    for row in sorted(base, key=lambda item: (item["exit_time"], item["model_id"])):
        lines.append(f"| {row['model_id']} | {row['exit_time']} | {row['net_cumulative_return']:.4%} | {row['maximum_drawdown']:.4%} | {row.get('exploratory_assessment', 'INCONCLUSIVE')} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verify_dataset(dataset: Path) -> None:
    load_verified_prr_dataset(dataset)


def _validate_file_set(path: Path, expected: frozenset[str]) -> None:
    actual = frozenset(item.name for item in path.iterdir() if item.is_file())
    if actual != expected:
        raise ValueError("MR-1 artifact file set does not match its declared schema")


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


def _canonical_hash(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _revision() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
