"""Application module for publishing one immutable MR-1 exploratory research run."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pandas as pd

from market_regime_alpha.research.mr1_candidate_baselines import (
    CandidateBaselineId,
    build_candidate_daily_baselines,
    build_model_candidate_populations,
    compound_candidate_baselines,
    selection_lifts,
)
from market_regime_alpha.research.mr1_morning_pop import (
    MR1ExitTime,
    MR1TargetId,
    MR1_MORNING_TARGET_SCHEMA_VERSION,
    build_mr1_targets,
    replay_mr1_fixed_portfolios,
)
from market_regime_alpha.research.prr_artifact_reader import load_verified_prr_dataset
from market_regime_alpha.research.prr_artifact_schemas import (
    MR1_BASELINE_PRIMARY_SEED,
    MR1_CANDIDATE_BASELINE_SCHEMA_VERSION,
    MR1_CASH_LOCK_POLICY_ID,
    MR1_MATCHED_K_ALGORITHM_ID,
    MR1_MATCHED_K_SELECTION_SCHEMA_VERSION,
    MR1_MISSING_WEIGHT_POLICY_ID,
    MR1_MODEL_POPULATION_DEFINITION_ID,
    MR1_MODEL_POPULATION_SCHEMA_VERSION,
    MR1_POPULATION_HASH_POLICY_ID,
    MR1_RANKING_POPULATION_VALIDATION_RULE_ID,
    MR1_RUN_SCHEMA,
    ModelCandidatePopulation,
)
from market_regime_alpha.research.prr_mvp_1 import ExploratoryExecutionCostConfig


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MR1_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "mr1_morning_pop_runs"


def run_mr1_research(
    *,
    dataset_path: Path,
    output_root: Path = DEFAULT_MR1_OUTPUT_ROOT,
    top_k: int = 5,
) -> Path:
    """Verify one Dataset, calculate MR-1, and atomically publish a v4 run."""

    verified = load_verified_prr_dataset(dataset_path)
    rankings = tuple(dict(row) for row in verified.ranking_rows)
    targets = build_mr1_targets(
        prepared=verified.prepared,
        bars=verified.bars,
        decision_dates=verified.decision_dates,
    )
    cost_configs = mr1_cost_scenarios()
    populations = build_model_candidate_populations(
        dataset_id=verified.dataset_id,
        ranking_rows=rankings,
    )
    baseline_result = build_candidate_daily_baselines(
        populations=populations,
        target_rows=targets,
        decision_dates=verified.decision_dates,
        cost_configs=cost_configs,
        top_k=top_k,
        baseline_seed=MR1_BASELINE_PRIMARY_SEED,
    )
    compounded_baselines = compound_candidate_baselines(baseline_result.baseline_rows)
    orders: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    equity: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    comparison: dict[str, Any] = {
        "schema_version": "mr-1-exit-time-comparison-v2",
        "descriptive_only": True,
        "results": [],
    }
    for scenario, costs in cost_configs.items():
        for exit_time in MR1ExitTime:
            replay = replay_mr1_fixed_portfolios(
                prepared=verified.prepared,
                ranking_rows=rankings,
                target_rows=targets,
                decision_dates=verified.decision_dates,
                top_k=top_k,
                exit_time=exit_time,
                cost_scenario=scenario,
                cost_config=costs,
            )
            orders.extend(replay.orders)
            fills.extend(replay.fills)
            trades.extend(replay.trades)
            equity.extend(replay.daily_equity)
            for model_id, metrics in replay.metrics["models"].items():
                baseline_values = _baseline_values(
                    compounded_baselines,
                    model_id=model_id,
                    scenario=scenario,
                    exit_time=exit_time.value,
                )
                increments = selection_lifts(
                    model_gross_return=float(metrics["gross_cumulative_return"]),
                    model_net_return=float(metrics["net_cumulative_return"]),
                    all_candidate_gross_return=baseline_values["all_candidate_gross_cumulative_return"],
                    matched_k_gross_return=baseline_values["matched_k_gross_cumulative_return"],
                    matched_k_net_return=baseline_values["matched_k_net_cumulative_return"],
                )
                row = {
                    "model_id": model_id,
                    "exit_time": exit_time.value,
                    "cost_scenario": scenario,
                    **metrics,
                    **baseline_values,
                    **increments,
                    "all_candidate_net_baseline_role": "NON_TRADABLE_DIAGNOSTIC_ONLY",
                    "matched_k_baseline_role": "PRIMARY_COMPARATOR_FOR_SELECTION_LIFT",
                }
                metric_rows.append(row)
                comparison["results"].append(row)
    _add_chronological_diagnostics(metric_rows, equity)
    _apply_failure_labels(metric_rows, equity)
    run_identity = build_mr1_run_identity(
        dataset_path=verified.root,
        top_k=top_k,
        rankings=rankings,
        populations=populations,
        cost_configs=cost_configs,
    )
    run_id = mr1_run_id(run_identity)
    return _write_run(
        root=output_root,
        run_id=run_id,
        dataset=verified.root,
        dataset_manifest=dict(verified.manifest),
        targets=targets,
        orders=orders,
        fills=fills,
        trades=trades,
        equity=equity,
        metrics=metric_rows,
        comparison=comparison,
        top_k=top_k,
        run_identity=run_identity,
        baseline_rows=baseline_result.baseline_rows,
        selection_rows=baseline_result.selection_rows,
    )


def mr1_cost_scenarios() -> dict[str, ExploratoryExecutionCostConfig]:
    """Return the predeclared LOW/BASE/HIGH research cost assumptions."""

    return {
        "LOW": ExploratoryExecutionCostConfig(
            buy_commission_bps=1.0,
            sell_commission_bps=1.0,
            minimum_commission=1.0,
            sell_stamp_duty_bps=2.5,
            entry_slippage_bps=1.0,
            exit_slippage_bps=1.0,
        ),
        "BASE": ExploratoryExecutionCostConfig(),
        "HIGH": ExploratoryExecutionCostConfig(
            buy_commission_bps=10.0,
            sell_commission_bps=10.0,
            minimum_commission=10.0,
            sell_stamp_duty_bps=10.0,
            entry_slippage_bps=15.0,
            exit_slippage_bps=15.0,
        ),
    }


def _baseline_values(
    compounded: Mapping[tuple[str, str, str, str], Mapping[str, float]],
    *,
    model_id: str,
    scenario: str,
    exit_time: str,
) -> dict[str, float]:
    all_gross = compounded[
        (model_id, CandidateBaselineId.ALL_CANDIDATE_GROSS_V1.value, scenario, exit_time)
    ]
    matched_gross = compounded[
        (model_id, CandidateBaselineId.MATCHED_K_HASH_GROSS_V1.value, scenario, exit_time)
    ]
    matched_net = compounded[
        (model_id, CandidateBaselineId.MATCHED_K_HASH_NET_V1.value, scenario, exit_time)
    ]
    all_net = compounded[
        (
            model_id,
            CandidateBaselineId.ALL_CANDIDATE_NET_DIAGNOSTIC_V1.value,
            scenario,
            exit_time,
        )
    ]
    return {
        "all_candidate_gross_cumulative_return": float(all_gross["gross"]),
        "matched_k_gross_cumulative_return": float(matched_gross["gross"]),
        "matched_k_net_cumulative_return": float(matched_net["net"]),
        "all_candidate_net_diagnostic_cumulative_return": float(all_net["net"]),
    }


def _add_chronological_diagnostics(
    metrics: list[dict[str, Any]],
    equity: list[dict[str, Any]],
) -> None:
    rows_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in equity:
        rows_by_key.setdefault(
            (str(row["model_id"]), str(row["exit_time"]), str(row["cost_scenario"])),
            [],
        ).append(row)
    for metric in metrics:
        rows = sorted(
            rows_by_key[(metric["model_id"], metric["exit_time"], metric["cost_scenario"])],
            key=lambda item: item["session_date"],
        )
        segments = [rows[:20], rows[20:40], rows[40:60]]
        segment_returns = [(_compound_model_returns(segment) if segment else None) for segment in segments]
        metric["first_20_return"], metric["middle_20_return"], metric["last_20_return"] = segment_returns
        metric["rolling_20_date_stability"] = [
            round(_compound_model_returns(rows[index : index + 20]), 12)
            for index in range(max(0, len(rows) - 19))
        ]
        metric["maximum_losing_streak"] = _maximum_losing_streak(rows)


def _apply_failure_labels(
    metrics: list[dict[str, Any]],
    equity: list[dict[str, Any]],
) -> None:
    scenario_index = {
        (row["model_id"], row["exit_time"], row["cost_scenario"]): row for row in metrics
    }
    for row in metrics:
        if row["cost_scenario"] != "BASE":
            continue
        scenarios = [
            scenario_index[(row["model_id"], row["exit_time"], scenario)]
            for scenario in ("LOW", "BASE", "HIGH")
        ]
        segments = [row["first_20_return"], row["middle_20_return"], row["last_20_return"]]
        daily = [
            item
            for item in equity
            if item["model_id"] == row["model_id"]
            and item["exit_time"] == row["exit_time"]
            and item["cost_scenario"] == "BASE"
        ]
        positive_sum = sum(max(float(item["net_return"]), 0.0) for item in daily)
        concentrated = (
            positive_sum > 0.0
            and max((max(float(item["net_return"]), 0.0) for item in daily), default=0.0)
            / positive_sum
            > 0.5
        )
        promising = (
            row["net_selection_lift_vs_matched_k"] > 0.0
            and all(value is not None and value > 0.0 for value in segments)
            and row["maximum_drawdown"] >= -0.15
            and all(item["net_cumulative_return"] > 0.0 for item in scenarios)
            and not concentrated
        )
        failed = (
            row["net_cumulative_return"] <= 0.0
            or scenarios[-1]["net_cumulative_return"] <= 0.0
            or row["maximum_drawdown"] < -0.25
        )
        label = (
            "PROMISING_EXPLORATORY"
            if promising
            else "FAILED_EXPLORATORY"
            if failed
            else "INCONCLUSIVE"
        )
        for scenario in scenarios:
            scenario["exploratory_assessment"] = label
            scenario["assessment_rule_version"] = "mr-1-matched-k-assessment-v2"
            scenario["assessment_notice"] = "DESCRIPTIVE ONLY — NO MODEL SELECTION"


def build_mr1_run_identity(
    *,
    dataset_path: Path,
    top_k: int,
    rankings: tuple[dict[str, Any], ...],
    populations: tuple[ModelCandidatePopulation, ...],
    cost_configs: Mapping[str, ExploratoryExecutionCostConfig],
) -> dict[str, Any]:
    model_ids = sorted({str(row["model_id"]) for row in rankings})
    module_root = PROJECT_ROOT / "src" / "market_regime_alpha" / "research"
    return {
        "dataset_id": _read_json(dataset_path / "dataset_manifest.json")["dataset_id"],
        "dataset_manifest_hash": _file_hash(dataset_path / "dataset_manifest.json"),
        "dataset_checksums_hash": _file_hash(dataset_path / "SHA256SUMS.json"),
        "git_commit_sha": _revision(),
        "mr1_morning_pop_module_hash": _file_hash(module_root / "mr1_morning_pop.py"),
        "mr1_candidate_baselines_module_hash": _file_hash(module_root / "mr1_candidate_baselines.py"),
        "mr1_research_runner_module_hash": _file_hash(Path(__file__)),
        "artifact_schema_module_hash": _file_hash(module_root / "prr_artifact_schemas.py"),
        "artifact_reader_module_hash": _file_hash(module_root / "prr_artifact_reader.py"),
        "target_schema_ids": [
            MR1_MORNING_TARGET_SCHEMA_VERSION,
            *(item.value for item in MR1TargetId),
        ],
        "candidate_daily_baseline_schema_version": MR1_CANDIDATE_BASELINE_SCHEMA_VERSION,
        "model_population_schema_version": MR1_MODEL_POPULATION_SCHEMA_VERSION,
        "population_definition_id": MR1_MODEL_POPULATION_DEFINITION_ID,
        "population_hash_policy_id": MR1_POPULATION_HASH_POLICY_ID,
        "matched_k_selection_schema_version": MR1_MATCHED_K_SELECTION_SCHEMA_VERSION,
        "selection_evidence_schema_version": MR1_MATCHED_K_SELECTION_SCHEMA_VERSION,
        "ranking_population_validation_rule_id": MR1_RANKING_POPULATION_VALIDATION_RULE_ID,
        "population_inventory_hash": _canonical_hash(
            [
                {
                    "decision_date": item.decision_date.isoformat(),
                    "model_id": item.model_id,
                    "target_id": item.target_id,
                    "population_hash": item.population_hash,
                }
                for item in populations
            ]
        ),
        "matched_k_algorithm_id": MR1_MATCHED_K_ALGORITHM_ID,
        "baseline_seed": MR1_BASELINE_PRIMARY_SEED,
        "cash_lock_policy_id": MR1_CASH_LOCK_POLICY_ID,
        "missing_weight_policy_id": MR1_MISSING_WEIGHT_POLICY_ID,
        "model_ids": model_ids,
        "top_k": top_k,
        "cost_scenario_config_hashes": {
            name: _canonical_hash(asdict(value)) for name, value in cost_configs.items()
        },
    }


def mr1_run_id(run_identity: Mapping[str, Any]) -> str:
    return f"mr1-{_canonical_hash(run_identity)[:20]}"


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
    baseline_rows: tuple[dict[str, Any], ...],
    selection_rows: tuple[dict[str, Any], ...],
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
                "schema_version": MR1_RUN_SCHEMA.schema_version,
                "run_id": run_id,
                "dataset_id": dataset_manifest["dataset_id"],
                "dataset_manifest_hash": _file_hash(dataset / "dataset_manifest.json"),
                "dataset_checksums_hash": _file_hash(dataset / "SHA256SUMS.json"),
                "dataset_locator_role": "EXTERNAL_IMMUTABLE_INPUT",
                "data_eligibility": "EXPLORATORY",
                "top_k": top_k,
                "model_count": len({str(row["model_id"]) for row in baseline_rows}),
                "exit_times": [item.value for item in MR1ExitTime],
                "cost_scenarios": ["LOW", "BASE", "HIGH"],
                "required_artifacts": sorted(MR1_RUN_SCHEMA.required_files),
                "candidate_daily_baseline_schema_version": MR1_CANDIDATE_BASELINE_SCHEMA_VERSION,
                "matched_k_selection_schema_version": MR1_MATCHED_K_SELECTION_SCHEMA_VERSION,
                "run_identity": run_identity,
            },
        )
        _write_json(
            stage / "limitations.json",
            [
                "CURRENT_WATCHLIST_BACKFILL_BIAS",
                "HISTORICAL_PIT_NOT_VERIFIED",
                "HISTORICAL_BUYABILITY_NOT_VERIFIED",
                "REFERENCE_MARK_NOT_FILL_PROOF",
                "NO_LEVEL2_OR_ORDER_BOOK",
                "FEE_ASSUMPTIONS_REQUIRE_CURRENT_VERIFICATION",
                "ALL_CANDIDATE_NET_DIAGNOSTIC_NOT_PRIMARY_COMPARATOR",
                "AUXILIARY_DATA_ONLY",
                "FORMAL_OOS_NOT_ESTABLISHED",
            ],
        )
        _write_parquet(stage / "morning_targets.parquet", targets)
        _write_parquet(stage / "orders.parquet", orders)
        _write_parquet(stage / "fills.parquet", fills)
        _write_parquet(stage / "trades.parquet", trades)
        _write_parquet(stage / "daily_equity.parquet", equity)
        _write_parquet(stage / "candidate_daily_baselines.parquet", baseline_rows)
        _write_parquet(stage / "matched_k_selections.parquet", selection_rows)
        _write_parquet(stage / "chronological_model_metrics.parquet", metrics)
        pd.DataFrame(metrics).to_csv(stage / "model_target_matrix.csv", index=False)
        _write_json(stage / "exit_time_comparison.json", comparison)
        _write_json(stage / "metrics.json", metrics)
        _write_report(stage / "report.md", run_id, str(dataset_manifest["dataset_id"]), metrics)
        _write_checksums(stage)
        _validate_file_set(stage, MR1_RUN_SCHEMA.required_files)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _write_report(
    path: Path,
    run_id: str,
    dataset_id: str,
    metrics: list[dict[str, Any]],
) -> None:
    base = [row for row in metrics if row["cost_scenario"] == "BASE"]
    lines = [
        "# MR-1 Overnight Morning-Pop Signal Validation",
        "",
        f"- Run ID: `{run_id}`",
        f"- Dataset ID: `{dataset_id}`",
        "- Authority: `EXPLORATORY`",
        "- Matched-K SHA-256 rank-blind baseline is the primary selection comparator.",
        "- All-Candidate net is a non-tradable diagnostic and not a primary Alpha comparator.",
        "- CLOSE comparator and baselines share the same overlapping-sleeve cash lock.",
        "- 14:55 reference is a research mark, not fill proof.",
        "- DESCRIPTIVE ONLY — NO MODEL SELECTION.",
        "",
        "## Base-cost assessment",
        "",
        "| Model | Exit | Net cumulative | Matched-K net lift | Max drawdown | Assessment |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in sorted(base, key=lambda item: (item["exit_time"], item["model_id"])):
        lines.append(
            f"| {row['model_id']} | {row['exit_time']} | {row['net_cumulative_return']:.4%} | "
            f"{row['net_selection_lift_vs_matched_k']:.4%} | {row['maximum_drawdown']:.4%} | "
            f"{row.get('exploratory_assessment', 'INCONCLUSIVE')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _compound_model_returns(rows: list[dict[str, Any]]) -> float:
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


def _validate_file_set(path: Path, expected: frozenset[str]) -> None:
    actual = frozenset(item.name for item in path.iterdir() if item.is_file())
    if actual != expected:
        raise ValueError("MR-1 artifact file set does not match its declared schema")


def _write_checksums(path: Path) -> None:
    _write_json(
        path / "SHA256SUMS.json",
        {
            item.name: _file_hash(item)
            for item in sorted(path.iterdir())
            if item.name != "SHA256SUMS.json"
        },
    )


def _write_parquet(
    path: Path,
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> None:
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _canonical_hash(value: Any) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
