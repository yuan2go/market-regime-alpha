"""Atomic immutable Artifact publication for MR-2B F2A descriptive inputs."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

import pandas as pd

from market_regime_alpha.research.mr2b_context import context_record
from market_regime_alpha.research.mr2b_context import (
    MR2B_CONTEXT_COVERAGE_POLICY_ID,
    MR2B_CONTEXT_DEFINITION_ID,
    MR2B_CONTEXT_GRID_DEFINITION_ID,
    MR2B_CONTEXT_SCHEMA_VERSION,
    MR2B_DIRECTION_LABEL_POLICY_ID,
)
from market_regime_alpha.research.mr2b_f2a import (
    MR2B_DAILY_EXCESS_SCHEMA_VERSION,
    MR2B_F2A_SCHEMA_VERSION,
    MR2B_PRIMARY_INPUT_SCHEMA_VERSION,
    F2AInputs,
    build_f2a_inputs,
)
from market_regime_alpha.research.mr2b_multiseed import (
    MR2B_F2A_SEEDS,
    MR2B_MULTISEED_SCHEMA_VERSION,
    MR2B_PERCENTILE_METHOD_ID,
    MR2B_QUANTILE_METHOD_ID,
)
from market_regime_alpha.research.prr_artifact_reader import (
    load_verified_mr1_run,
    load_verified_prr_dataset,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    MR1_BASELINE_PRIMARY_SEED,
    MR1_CASH_LOCK_POLICY_ID,
    MR1_MATCHED_K_ALGORITHM_ID,
    MR1_MISSING_WEIGHT_POLICY_ID,
    MR2B_F2A_RUN_SCHEMA,
    canonical_identity_hash,
)


F2A_LIMITATIONS = (
    "CURRENT_WATCHLIST_BACKFILL_BIAS",
    "HISTORICAL_PIT_NOT_VERIFIED",
    "WATCHLIST_CONTEXT_IS_NOT_FULL_MARKET_CONTEXT",
    "MULTI_SEED_REFERENCE_IS_NOT_INDEPENDENT_TIME_EVIDENCE",
    "SINGLE_DATASET_ONLY",
    "NO_FORMAL_OOS",
    "REFERENCE_MARK_NOT_FILL_PROOF",
    "FEE_ASSUMPTIONS_REQUIRE_CURRENT_VERIFICATION",
)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_F2A_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "mr2b_f2a_conditionality_inputs"


def run_f2a_research(
    *,
    dataset_path: Path,
    mr1_run_path: Path,
    output_root: Path = DEFAULT_F2A_OUTPUT_ROOT,
    runner_path: Path,
) -> Path:
    """Verify immutable inputs, build F2A tables, publish, and verify the result."""

    dataset = load_verified_prr_dataset(dataset_path)
    mr1 = load_verified_mr1_run(
        mr1_run_path,
        dataset=dataset,
        expected_dataset_id=dataset.dataset_id,
    )
    inputs = build_f2a_inputs(dataset=dataset, mr1=mr1, seeds=MR2B_F2A_SEEDS)
    identity = build_f2a_run_identity(
        dataset_root=dataset.root,
        mr1_root=mr1.root,
        dataset_id=dataset.dataset_id,
        mr1_run_id=mr1.run_id,
        watchlist_id=inputs.contexts[0].watchlist_id,
        top_k=int(mr1.manifest["top_k"]),
        runner_path=runner_path,
    )
    final = publish_f2a_artifact(output_root=output_root, run_identity=identity, inputs=inputs)
    from market_regime_alpha.research.mr2b_f2a_reader import load_verified_f2a_run

    load_verified_f2a_run(
        final,
        expected_dataset_id=dataset.dataset_id,
        expected_mr1_run_id=mr1.run_id,
    )
    return final


def build_f2a_run_identity(
    *,
    dataset_root: Path,
    mr1_root: Path,
    dataset_id: str,
    mr1_run_id: str,
    watchlist_id: str,
    top_k: int,
    runner_path: Path,
) -> dict[str, Any]:
    """Build a path-independent semantic identity for one F2A run."""

    module_root = PROJECT_ROOT / "src" / "market_regime_alpha" / "research"
    seed_set_hash = canonical_identity_hash({"seeds": MR2B_F2A_SEEDS})
    return {
        "dataset_id": dataset_id,
        "dataset_manifest_hash": _content_hash(dataset_root / "dataset_manifest.json"),
        "dataset_checksums_hash": _content_hash(dataset_root / "SHA256SUMS.json"),
        "mr1_run_id": mr1_run_id,
        "mr1_manifest_hash": _content_hash(mr1_root / "manifest.json"),
        "mr1_checksums_hash": _content_hash(mr1_root / "SHA256SUMS.json"),
        "git_commit_sha": _revision(),
        "f2a_context_module_hash": _content_hash(module_root / "mr2b_context.py"),
        "f2a_multiseed_module_hash": _content_hash(module_root / "mr2b_multiseed.py"),
        "f2a_core_module_hash": _content_hash(module_root / "mr2b_f2a.py"),
        "f2a_artifact_module_hash": _content_hash(Path(__file__)),
        "f2a_reader_module_hash": _content_hash(module_root / "mr2b_f2a_reader.py"),
        "f2a_runner_hash": _content_hash(runner_path),
        "context_schema_version": MR2B_CONTEXT_SCHEMA_VERSION,
        "context_definition_id": MR2B_CONTEXT_DEFINITION_ID,
        "watchlist_identity": watchlist_id,
        "grid_definition_id": MR2B_CONTEXT_GRID_DEFINITION_ID,
        "coverage_policy_id": MR2B_CONTEXT_COVERAGE_POLICY_ID,
        "direction_label_policy_id": MR2B_DIRECTION_LABEL_POLICY_ID,
        "selection_algorithm_id": MR1_MATCHED_K_ALGORITHM_ID,
        "seed_set": list(MR2B_F2A_SEEDS),
        "seed_set_hash": seed_set_hash,
        "primary_seed": MR1_BASELINE_PRIMARY_SEED,
        "top_k": top_k,
        "multi_seed_schema_version": MR2B_MULTISEED_SCHEMA_VERSION,
        "daily_excess_schema_version": MR2B_DAILY_EXCESS_SCHEMA_VERSION,
        "primary_comparison_input_schema_version": MR2B_PRIMARY_INPUT_SCHEMA_VERSION,
        "quantile_method_id": MR2B_QUANTILE_METHOD_ID,
        "percentile_method_id": MR2B_PERCENTILE_METHOD_ID,
        "cash_lock_policy_id": MR1_CASH_LOCK_POLICY_ID,
        "missing_weight_policy_id": MR1_MISSING_WEIGHT_POLICY_ID,
        "f2a_schema_version": MR2B_F2A_SCHEMA_VERSION,
        "data_eligibility": "EXPLORATORY",
    }


def f2a_run_id(run_identity: Mapping[str, Any]) -> str:
    return f"mr2b-f2a-{canonical_identity_hash(dict(run_identity)).split(':', 1)[1][:20]}"


def publish_f2a_artifact(
    *,
    output_root: Path,
    run_identity: Mapping[str, Any],
    inputs: F2AInputs,
) -> Path:
    """Publish one non-overwriting F2A Artifact after semantic inputs are complete."""

    run_id = f2a_run_id(run_identity)
    final = output_root / run_id
    stage = output_root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError(f"MR-2B F2A Artifact is immutable: {final}")
    contexts = tuple(context_record(item) for item in inputs.contexts)
    model_count = len({item.model_id for item in inputs.populations})
    date_count = len({item.decision_date for item in inputs.populations})
    seed_count = len(
        {int(row["seed"]) for row in inputs.multiseed.return_rows}
    )
    primary_seed = int(inputs.multiseed.primary_seed_reconciliation["primary_seed"])
    top_k_values = {int(row["top_k"]) for row in inputs.multiseed.selection_rows}
    if len(top_k_values) != 1:
        raise ValueError("F2A selection evidence must use one Top-K")
    stage.mkdir(parents=True)
    try:
        row_counts = {
            "auxiliary_watchlist_context": len(contexts),
            "multi_seed_matched_k_selections": len(inputs.multiseed.selection_rows),
            "multi_seed_matched_k_returns": len(inputs.multiseed.return_rows),
            "multi_seed_null_summary": len(inputs.multiseed.null_summary_rows),
            "daily_candidate_excess": len(inputs.daily_excess_rows),
        }
        _write_json(
            stage / "manifest.json",
            {
                "schema_version": MR2B_F2A_RUN_SCHEMA.schema_version,
                "run_id": run_id,
                "dataset_id": run_identity["dataset_id"],
                "mr1_run_id": run_identity["mr1_run_id"],
                "data_eligibility": "EXPLORATORY",
                "authority": "EXPLORATORY_CONDITIONALITY_INPUT_EVIDENCE",
                "required_artifacts": sorted(MR2B_F2A_RUN_SCHEMA.required_files),
                "run_identity": dict(run_identity),
                "seed_set_id": inputs.multiseed.seed_set_id,
                "seed_count": seed_count,
                "primary_seed": primary_seed,
                "top_k": next(iter(top_k_values)),
                "model_count": model_count,
                "decision_date_count": date_count,
                "row_counts": row_counts,
            },
        )
        _write_json(
            stage / "seed_config.json",
            {
                "schema_version": "mr-2b-f2a-seed-config-v1",
                "seed_set_id": inputs.multiseed.seed_set_id,
                "seeds": list(run_identity["seed_set"]),
                "primary_seed": primary_seed,
                "seed_count": seed_count,
            },
        )
        _write_parquet(stage / "auxiliary_watchlist_context.parquet", contexts)
        _write_parquet(
            stage / "multi_seed_matched_k_selections.parquet",
            inputs.multiseed.selection_rows,
        )
        _write_parquet(
            stage / "multi_seed_matched_k_returns.parquet",
            inputs.multiseed.return_rows,
        )
        _write_parquet(
            stage / "multi_seed_null_summary.parquet",
            inputs.multiseed.null_summary_rows,
        )
        _write_parquet(stage / "daily_candidate_excess.parquet", inputs.daily_excess_rows)
        _write_json(
            stage / "primary_seed_reconciliation.json",
            inputs.multiseed.primary_seed_reconciliation,
        )
        _write_json(stage / "primary_comparison_input.json", inputs.primary_comparison_input)
        _write_json(stage / "coverage.json", inputs.coverage)
        _write_json(stage / "limitations.json", list(F2A_LIMITATIONS))
        _write_report(stage / "report.md", run_id, run_identity, inputs)
        _write_checksums(stage)
        _validate_file_set(stage)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _write_report(path: Path, run_id: str, identity: Mapping[str, Any], inputs: F2AInputs) -> None:
    primary = inputs.primary_comparison_input
    lines = [
        "# MR-2B F2A Conditionality Inputs",
        "",
        "## Facts",
        "",
        f"- Run ID: `{run_id}`",
        f"- Dataset ID: `{identity['dataset_id']}`",
        f"- MR-1 Run ID: `{identity['mr1_run_id']}`",
        f"- Context dates evaluated: {len(inputs.contexts)}",
        f"- Seed 17 reconciliation: `{inputs.multiseed.primary_seed_reconciliation['status']}`",
        "",
        "## Descriptive evidence",
        "",
        f"- Frozen primary input mean UP-minus-DOWN daily net-lift difference: `{primary.get('descriptive_mean_difference')}`",
        "- This is a descriptive input only; no hypothesis is supported or rejected here.",
        "",
        "## Model assumptions",
        "",
        "- The accepted 20-symbol watchlist is auxiliary context, not the A-share market.",
        "- Multi-seed selections form a same-day comparator distribution; seeds are not independent dates.",
        "",
        "## Risks",
        "",
        *(f"- `{item}`" for item in F2A_LIMITATIONS),
        "",
        "## Invalidation",
        "",
        "- Seed 17 reconciliation failure",
        "- Context grid incompleteness",
        "- Dataset/MR-1 identity mismatch",
        "- Daily excess join mismatch",
        "",
        "No model winner, Formal OOS Alpha, production Regime Gate, or execution authority is established.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_parquet(path: Path, rows: Any) -> None:
    pd.DataFrame.from_records(rows).to_parquet(path, index=False)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _write_checksums(root: Path) -> None:
    checksums = {
        item.name: _content_hash(item)
        for item in sorted(root.iterdir())
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    _write_json(root / "SHA256SUMS.json", checksums)


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _validate_file_set(root: Path) -> None:
    files = frozenset(item.name for item in root.iterdir() if item.is_file())
    if files != MR2B_F2A_RUN_SCHEMA.required_files:
        raise ValueError("MR-2B F2A Artifact file set is invalid")
