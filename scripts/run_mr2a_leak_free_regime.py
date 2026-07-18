#!/usr/bin/env python3
"""Publish MR-2A leak-free regime diagnostics from immutable Dataset/MR-1 evidence."""

from __future__ import annotations
import argparse
import json
import sys
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]
from market_regime_alpha.research.mr2_failure_decomposition import feature_target_diagnostics, target_coverage, decompose_model_failures
from market_regime_alpha.research.prr_artifact_reader import load_verified_mr1_run, load_verified_prr_dataset
from market_regime_alpha.research.mr2a_regime import (
    build_decision_time_context,
    controlled_heterogeneity_gate,
    registry_hash,
    MR2A_SCHEMA_VERSION,
    MR2A_CONTEXT_SCHEMA_VERSION,
    MR2A_CONTEXT_DEFINITION,
)


def h(p: Path) -> str:
    return "sha256:" + sha256(p.read_bytes()).hexdigest()


def wj(p: Path, x: Any) -> None:
    p.write_text(json.dumps(x, sort_keys=True, indent=2, default=str) + "\n")


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--dataset", type=Path, required=True)
    a.add_argument("--mr1-run", type=Path, required=True)
    a.add_argument("--output-root", type=Path, default=ROOT / "data/processed/mr2a_leak_free_regime_runs")
    x = a.parse_args()
    ds = x.dataset.resolve()
    m = x.mr1_run.resolve()
    verified_dataset = load_verified_prr_dataset(ds)
    verified_mr1 = load_verified_mr1_run(m, expected_dataset_id=verified_dataset.dataset_id)
    dm = dict(verified_dataset.manifest)
    mm = dict(verified_mr1.manifest)
    prepared = verified_dataset.prepared
    bars = verified_dataset.bars
    rankings = tuple(dict(row) for row in verified_dataset.ranking_rows)
    dates = verified_dataset.decision_dates
    targets = [dict(row) for row in verified_mr1.morning_targets]
    metrics = [dict(row) for row in verified_mr1.metrics]
    context = build_decision_time_context(prepared=prepared, bars=bars, decision_dates=dates)
    ic, spreads = feature_target_diagnostics(ranking_rows=rankings, target_rows=targets)
    coverage = target_coverage(targets)
    failures = list(decompose_model_failures(mr1_metrics=metrics, target_coverage=coverage))
    identity = {
        "dataset_id": dm["dataset_id"],
        "dataset_checksums_hash": h(ds / "SHA256SUMS.json"),
        "mr1_run_id": mm["run_id"],
        "mr1_manifest_hash": h(m / "manifest.json"),
        "git_commit_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        "mr2_core_module_hash": h(ROOT / "src/market_regime_alpha/research/mr2a_regime.py"),
        "mr2_runner_hash": h(Path(__file__)),
        "market_context_schema_version": MR2A_CONTEXT_SCHEMA_VERSION,
        "market_context_definition_ids": [MR2A_CONTEXT_DEFINITION],
        "regime_threshold_config": {"volatility": "median_split", "effect_size": 0.001},
        "feature_direction_registry_hash": registry_hash(),
        "bootstrap_config": {"draws": 500},
        "permutation_config": {"draws": 500},
        "summary_rule_id": "mr2a-controlled-heterogeneity-v1",
        "random_seed": 17,
    }
    rid = "mr2a-" + sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    final = x.output_root / rid
    stage = x.output_root / f".{rid}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError(final)
    eq = pd.DataFrame(verified_mr1.daily_equity)
    ctx = {r["decision_date"]: r for r in context if r["data_status"] == "AVAILABLE"}
    uncertainty = []
    slices = []
    for (model, exit), g in eq[eq.cost_scenario.eq("BASE")].groupby(["model_id", "exit_time"]):
        up = [float(r.net_return) for r in g.itertuples() if ctx.get(str(r.session_date), {}).get("market_direction") == "UP"]
        down = [float(r.net_return) for r in g.itertuples() if ctx.get(str(r.session_date), {}).get("market_direction") == "DOWN"]
        gate = controlled_heterogeneity_gate(up, down, seed=17)
        uncertainty.append({"model_id": model, "exit_time": exit, "dimension": "market_direction", **gate})
        slices.extend(
            [
                {
                    "model_id": model,
                    "exit_time": exit,
                    "dimension": "market_direction",
                    "slice": "UP",
                    "session_count": len(up),
                    "model_net_return": sum(up),
                    "candidate_net_return": None,
                    "net_candidate_excess": None,
                    "data_status": "AVAILABLE",
                },
                {
                    "model_id": model,
                    "exit_time": exit,
                    "dimension": "market_direction",
                    "slice": "DOWN",
                    "session_count": len(down),
                    "model_net_return": sum(down),
                    "candidate_net_return": None,
                    "net_candidate_excess": None,
                    "data_status": "AVAILABLE",
                },
            ]
        )
    assessment = (
        "C1. REGIME_HETEROGENEITY_HYPOTHESIS"
        if any(r.get("assessment", "").startswith("C1") for r in uncertainty)
        else "C0. REGIME_HETEROGENEITY_NOT_SUPPORTED"
    )
    summary = {
        "schema_version": MR2A_SCHEMA_VERSION,
        "assessment": assessment,
        "previous_mr2_conclusion": "SUPERSEDED",
        "multiple_comparisons_disclosed": len(uncertainty),
        "data_eligibility": "EXPLORATORY",
    }
    stage.mkdir(parents=True)
    wj(
        stage / "manifest.json",
        {"schema_version": MR2A_SCHEMA_VERSION, "run_id": rid, "data_eligibility": "EXPLORATORY", "run_identity": identity},
    )
    for name, data in [
        ("decision_time_market_context.parquet", context),
        ("feature_target_ic.parquet", ic),
        ("feature_target_spreads.parquet", spreads),
        ("model_failure_decomposition.parquet", failures),
        ("regime_slice_metrics.parquet", slices),
        ("regime_effect_uncertainty.parquet", uncertainty),
        ("permutation_diagnostics.parquet", uncertainty),
    ]:
        pd.DataFrame(data).to_parquet(stage / name, index=False)
    wj(stage / "target_coverage.json", coverage)
    wj(
        stage / "multiple_testing_inventory.json",
        {
            "number_of_models": 9,
            "number_of_exit_times": 4,
            "number_of_regime_dimensions": 1,
            "number_of_slice_comparisons": len(uncertainty),
            "total_hypotheses_examined": len(uncertainty),
        },
    )
    wj(stage / "failure_summary.json", summary)
    wj(
        stage / "limitations.json",
        ["EXPLORATORY", "ETF_SECTOR_CONTEXT_UNAVAILABLE", "HISTORICAL_PIT_NOT_VERIFIED", "FORMAL_OOS_NOT_ESTABLISHED"],
    )
    (stage / "report.md").write_text(f"# MR-2A\n\nAssessment: `{assessment}`\n\nNo Formal OOS, winner, or production regime gate.\n")
    wj(stage / "SHA256SUMS.json", {p.name: h(p) for p in stage.iterdir() if p.name != "SHA256SUMS.json"})
    stage.rename(final)
    print(final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
