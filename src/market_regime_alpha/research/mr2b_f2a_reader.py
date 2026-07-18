"""Verified network-free reader for immutable MR-2B F2A Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import pandas as pd

from market_regime_alpha.research.prr_artifact_schemas import (
    MR2B_CONTEXT_PRIMARY_KEY,
    MR2B_DAILY_EXCESS_PRIMARY_KEY,
    MR2B_F2A_RUN_SCHEMA,
    MR2B_MULTISEED_RETURN_PRIMARY_KEY,
    MR2B_MULTISEED_SELECTION_PRIMARY_KEY,
    MR2B_NULL_SUMMARY_PRIMARY_KEY,
)


@dataclass(frozen=True, slots=True)
class VerifiedF2ARun:
    root: Path
    run_id: str
    dataset_id: str
    mr1_run_id: str
    manifest: Mapping[str, Any]
    primary_comparison_input: Mapping[str, Any]
    checksums_hash: str


def load_verified_f2a_run(
    path: Path,
    *,
    expected_dataset_id: str | None = None,
    expected_mr1_run_id: str | None = None,
) -> VerifiedF2ARun:
    root = path.resolve()
    _verify_files(root)
    manifest = _read_json(root / "manifest.json")
    missing = MR2B_F2A_RUN_SCHEMA.required_manifest_keys - manifest.keys()
    if missing or manifest.get("schema_version") != MR2B_F2A_RUN_SCHEMA.schema_version:
        raise ValueError("MR-2B F2A manifest schema is invalid")
    if manifest.get("data_eligibility") != "EXPLORATORY":
        raise ValueError("MR-2B F2A authority must remain EXPLORATORY")
    run_id = _text(manifest.get("run_id"), "run_id")
    dataset_id = _text(manifest.get("dataset_id"), "dataset_id")
    mr1_run_id = _text(manifest.get("mr1_run_id"), "mr1_run_id")
    if run_id != root.name:
        raise ValueError("MR-2B F2A run ID must match immutable directory")
    if expected_dataset_id is not None and dataset_id != expected_dataset_id:
        raise ValueError("MR-2B F2A Dataset identity mismatch")
    if expected_mr1_run_id is not None and mr1_run_id != expected_mr1_run_id:
        raise ValueError("MR-2B F2A MR-1 identity mismatch")
    if frozenset(manifest.get("required_artifacts", ())) != MR2B_F2A_RUN_SCHEMA.required_files:
        raise ValueError("MR-2B F2A required artifacts mismatch")
    contexts = pd.read_parquet(root / "auxiliary_watchlist_context.parquet")
    selections = pd.read_parquet(root / "multi_seed_matched_k_selections.parquet")
    returns = pd.read_parquet(root / "multi_seed_matched_k_returns.parquet")
    summaries = pd.read_parquet(root / "multi_seed_null_summary.parquet")
    daily = pd.read_parquet(root / "daily_candidate_excess.parquet")
    _unique(contexts, MR2B_CONTEXT_PRIMARY_KEY, "Context")
    _unique(selections, MR2B_MULTISEED_SELECTION_PRIMARY_KEY, "multi-seed selection")
    _unique(returns, MR2B_MULTISEED_RETURN_PRIMARY_KEY, "multi-seed return")
    _unique(summaries, MR2B_NULL_SUMMARY_PRIMARY_KEY, "null summary")
    _unique(daily, MR2B_DAILY_EXCESS_PRIMARY_KEY, "daily excess")
    _validate_semantics(manifest, contexts, selections, returns, summaries, daily)
    reconciliation = _read_json(root / "primary_seed_reconciliation.json")
    if reconciliation.get("status") != "EXACT_MATCH" or reconciliation.get("mismatch_rows") != 0:
        raise ValueError("MR-2B F2A primary seed did not reconcile")
    primary = _read_json(root / "primary_comparison_input.json")
    if primary.get("authority") != "DESCRIPTIVE_INPUT_ONLY":
        raise ValueError("MR-2B F2A primary input authority is invalid")
    return VerifiedF2ARun(
        root=root,
        run_id=run_id,
        dataset_id=dataset_id,
        mr1_run_id=mr1_run_id,
        manifest=MappingProxyType(manifest),
        primary_comparison_input=MappingProxyType(primary),
        checksums_hash=_content_hash(root / "SHA256SUMS.json"),
    )


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("MR-2B F2A Artifact directory is missing")
    files = frozenset(item.name for item in root.iterdir() if item.is_file())
    if files != MR2B_F2A_RUN_SCHEMA.required_files:
        raise ValueError("MR-2B F2A Artifact file set is invalid")
    checksums = _read_json(root / "SHA256SUMS.json")
    expected_files = MR2B_F2A_RUN_SCHEMA.required_files - {"SHA256SUMS.json"}
    if frozenset(checksums) != expected_files:
        raise ValueError("MR-2B F2A checksum coverage is invalid")
    for filename in sorted(expected_files):
        if checksums.get(filename) != _content_hash(root / filename):
            raise ValueError(f"artifact checksum mismatch: {filename}")


def _validate_semantics(manifest: Mapping[str, Any], contexts: pd.DataFrame, selections: pd.DataFrame, returns: pd.DataFrame, summaries: pd.DataFrame, daily: pd.DataFrame) -> None:
    dataset_id = str(manifest["dataset_id"])
    mr1_run_id = str(manifest["mr1_run_id"])
    for label, frame in (("selection", selections), ("return", returns), ("daily excess", daily)):
        if set(frame["dataset_id"].astype(str)) != {dataset_id} or set(frame["mr1_run_id"].astype(str)) != {mr1_run_id}:
            raise ValueError(f"MR-2B F2A {label} input identity mismatch")
    if set(contexts["dataset_id"].astype(str)) != {dataset_id}:
        raise ValueError("MR-2B F2A Context Dataset identity mismatch")
    row_counts = manifest.get("row_counts")
    expected_counts = {
        "auxiliary_watchlist_context": len(contexts),
        "multi_seed_matched_k_selections": len(selections),
        "multi_seed_matched_k_returns": len(returns),
        "multi_seed_null_summary": len(summaries),
        "daily_candidate_excess": len(daily),
    }
    if not isinstance(row_counts, Mapping) or dict(row_counts) != expected_counts:
        raise ValueError("MR-2B F2A manifest row counts mismatch")
    context_ids = dict(zip(contexts["decision_date"].astype(str), contexts["context_id"].astype(str), strict=True))
    if any(context_ids.get(str(row.decision_date)) != str(row.context_id) for row in daily.itertuples()):
        raise ValueError("MR-2B F2A daily Context identity mismatch")
    return_groups = returns.groupby(["decision_date", "model_id", "exit_time", "cost_scenario"], sort=False)
    if set(return_groups.groups) != set(summaries.set_index(list(MR2B_NULL_SUMMARY_PRIMARY_KEY)).index):
        raise ValueError("MR-2B F2A null summary keys mismatch returns")
    seed_count = int(manifest["seed_count"])
    for key, group in return_groups:
        if len(group) != seed_count or group["seed"].nunique() != seed_count:
            raise ValueError(f"MR-2B F2A return seed cardinality mismatch: {key}")
    if set(daily.set_index(list(MR2B_DAILY_EXCESS_PRIMARY_KEY)).index) != set(summaries.set_index(list(MR2B_NULL_SUMMARY_PRIMARY_KEY)).index):
        raise ValueError("MR-2B F2A daily excess keys mismatch null summaries")


def _unique(frame: pd.DataFrame, fields: tuple[str, ...], label: str) -> None:
    if frame.empty or any(field not in frame for field in fields):
        raise ValueError(f"MR-2B F2A {label} schema is incomplete")
    if frame.duplicated(list(fields)).any():
        raise ValueError(f"MR-2B F2A {label} primary keys must be unique")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"MR-2B F2A {label} must be non-empty")
    return value
