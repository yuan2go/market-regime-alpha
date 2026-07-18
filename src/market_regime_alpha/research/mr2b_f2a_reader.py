"""Full semantic reader for immutable MR-2B F2A v2 evidence."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import pandas as pd
from pandas.testing import assert_frame_equal

from market_regime_alpha.research.mr2b_context import (
    MR2B_CONTEXT_COVERAGE_POLICY_ID,
    MR2B_CONTEXT_DEFINITION_ID,
    MR2B_CONTEXT_GRID_DEFINITION_ID,
    MR2B_CONTEXT_SCHEMA_VERSION,
    MR2B_CONTEXT_SYMBOL_EVIDENCE_SCHEMA_VERSION,
    MR2B_DIRECTION_LABEL_POLICY_ID,
    context_record,
    context_symbol_evidence_record,
)
from market_regime_alpha.research.mr2b_f2a import (
    MR2B_DAILY_EXCESS_SCHEMA_VERSION,
    MR2B_F2A_SCHEMA_VERSION,
    MR2B_PRIMARY_INPUT_SCHEMA_VERSION,
    MR2B_PRIMARY_PROJECTION_RULE_ID,
    build_f2a_coverage,
    build_f2a_inputs,
    build_primary_comparison_input,
)
from market_regime_alpha.research.mr2b_f2a_artifacts import (
    F2A_CASH_LOCK_EMPTY_HASH_POLICY_ID,
    F2A_COLLISION_DIAGNOSTIC_RULE_ID,
    F2A_LIMITATIONS,
    F2A_SEMANTIC_READER_RULE_ID,
    F2A_SEMANTIC_TAMPER_RULE_ID,
    F2ARunIdentity,
    PROJECT_ROOT,
)
from market_regime_alpha.research.mr2b_multiseed import (
    MR2B_MULTISEED_SCHEMA_VERSION,
    MR2B_PERCENTILE_METHOD_ID,
    MR2B_QUANTILE_METHOD_ID,
)
from market_regime_alpha.research.prr_artifact_reader import (
    VerifiedMR1Run,
    VerifiedPRRDataset,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    MR2B_CONTEXT_PRIMARY_KEY,
    MR2B_CONTEXT_SYMBOL_EVIDENCE_PRIMARY_KEY,
    MR2B_DAILY_EXCESS_PRIMARY_KEY,
    MR2B_F2A_RUN_SCHEMA,
    MR2B_MULTISEED_RETURN_PRIMARY_KEY,
    MR2B_MULTISEED_SELECTION_PRIMARY_KEY,
    MR2B_NULL_SUMMARY_PRIMARY_KEY,
    MR1_CASH_LOCK_POLICY_ID,
    MR1_MATCHED_K_ALGORITHM_ID,
    MR1_MISSING_WEIGHT_POLICY_ID,
    canonical_identity_hash,
)


@dataclass(frozen=True, slots=True)
class VerifiedF2ARun:
    root: Path
    run_id: str
    dataset_id: str
    mr1_run_id: str
    manifest: Mapping[str, Any]
    contexts: tuple[Mapping[str, Any], ...]
    context_symbol_evidence: tuple[Mapping[str, Any], ...]
    multiseed_selections: tuple[Mapping[str, Any], ...]
    multiseed_returns: tuple[Mapping[str, Any], ...]
    null_summaries: tuple[Mapping[str, Any], ...]
    daily_candidate_excess: tuple[Mapping[str, Any], ...]
    primary_comparison_input: Mapping[str, Any]
    coverage: Mapping[str, Any]
    checksums_hash: str


def load_verified_f2a_run(
    path: Path,
    *,
    dataset: VerifiedPRRDataset,
    mr1: VerifiedMR1Run,
    expected_dataset_id: str | None = None,
    expected_mr1_run_id: str | None = None,
) -> VerifiedF2ARun:
    """Reconstruct every F2A table from verified immutable inputs before accepting it."""

    root = path.resolve()
    _verify_files(root)
    manifest = _read_json(root / "manifest.json")
    _verify_manifest(manifest, root=root, dataset=dataset, mr1=mr1)
    run_id = _text(manifest.get("run_id"), "run_id")
    dataset_id = _text(manifest.get("dataset_id"), "dataset_id")
    mr1_run_id = _text(manifest.get("mr1_run_id"), "mr1_run_id")
    if expected_dataset_id is not None and dataset_id != expected_dataset_id:
        raise ValueError("MR-2B F2A Dataset identity mismatch")
    if expected_mr1_run_id is not None and mr1_run_id != expected_mr1_run_id:
        raise ValueError("MR-2B F2A MR-1 identity mismatch")

    identity = F2ARunIdentity.from_canonical_dict(_mapping(manifest.get("run_identity")))
    if identity.run_id() != run_id or run_id != root.name:
        raise ValueError("MR-2B F2A run ID does not match typed identity and directory")
    _verify_identity_inputs(identity, dataset=dataset, mr1=mr1)
    _verify_identity_contract(identity)
    seed_config = _read_json(root / "seed_config.json")
    _verify_seed_config(seed_config, identity=identity, manifest=manifest)
    limitations = _read_json_value(root / "limitations.json")
    if not isinstance(limitations, list) or tuple(limitations) != F2A_LIMITATIONS:
        raise ValueError("MR-2B F2A limitations do not match the authority contract")

    frames = {
        "contexts": pd.read_parquet(root / "auxiliary_watchlist_context.parquet"),
        "symbol_evidence": pd.read_parquet(
            root / "auxiliary_watchlist_context_symbol_evidence.parquet"
        ),
        "selections": pd.read_parquet(root / "multi_seed_matched_k_selections.parquet"),
        "returns": pd.read_parquet(root / "multi_seed_matched_k_returns.parquet"),
        "summaries": pd.read_parquet(root / "multi_seed_null_summary.parquet"),
        "daily": pd.read_parquet(root / "daily_candidate_excess.parquet"),
    }
    _unique(frames["contexts"], MR2B_CONTEXT_PRIMARY_KEY, "Context")
    _unique(
        frames["symbol_evidence"],
        MR2B_CONTEXT_SYMBOL_EVIDENCE_PRIMARY_KEY,
        "symbol Context evidence",
    )
    _unique(frames["selections"], MR2B_MULTISEED_SELECTION_PRIMARY_KEY, "selection")
    _unique(frames["returns"], MR2B_MULTISEED_RETURN_PRIMARY_KEY, "return")
    _unique(frames["summaries"], MR2B_NULL_SUMMARY_PRIMARY_KEY, "null summary")
    _unique(frames["daily"], MR2B_DAILY_EXCESS_PRIMARY_KEY, "daily excess")

    expected = build_f2a_inputs(dataset=dataset, mr1=mr1, seeds=identity.seed_set)
    if manifest.get("seed_set_id") != expected.multiseed.seed_set_id:
        raise ValueError("MR-2B F2A seed-set evidence does not match immutable inputs")
    if (
        manifest.get("seed_count") != len(identity.seed_set)
        or manifest.get("primary_seed") != identity.primary_seed
        or manifest.get("top_k") != identity.top_k
        or manifest.get("model_count") != len({row.model_id for row in expected.populations})
        or manifest.get("decision_date_count")
        != len({row.decision_date for row in expected.populations})
    ):
        raise ValueError("MR-2B F2A manifest semantic cardinalities mismatch")
    expected_frames = {
        "contexts": pd.DataFrame.from_records(
            tuple(context_record(row) for row in expected.contexts)
        ),
        "symbol_evidence": pd.DataFrame.from_records(
            tuple(context_symbol_evidence_record(row) for row in expected.context_symbol_evidence)
        ),
        "selections": pd.DataFrame.from_records(expected.multiseed.selection_rows),
        "returns": pd.DataFrame.from_records(expected.multiseed.return_rows),
        "summaries": pd.DataFrame.from_records(expected.multiseed.null_summary_rows),
        "daily": pd.DataFrame.from_records(expected.daily_excess_rows),
    }
    keys = {
        "contexts": MR2B_CONTEXT_PRIMARY_KEY,
        "symbol_evidence": MR2B_CONTEXT_SYMBOL_EVIDENCE_PRIMARY_KEY,
        "selections": MR2B_MULTISEED_SELECTION_PRIMARY_KEY,
        "returns": MR2B_MULTISEED_RETURN_PRIMARY_KEY,
        "summaries": MR2B_NULL_SUMMARY_PRIMARY_KEY,
        "daily": MR2B_DAILY_EXCESS_PRIMARY_KEY,
    }
    for label in frames:
        _assert_semantic_table(
            frames[label], expected_frames[label], key=keys[label], label=label
        )

    reconciliation = _read_json(root / "primary_seed_reconciliation.json")
    if reconciliation != expected.multiseed.primary_seed_reconciliation:
        raise ValueError("MR-2B F2A primary-seed reconciliation is not reconstructible")
    primary = _read_json(root / "primary_comparison_input.json")
    expected_primary = build_primary_comparison_input(expected.daily_excess_rows)
    if not _canonical_equal(primary, expected_primary):
        raise ValueError("MR-2B F2A Primary Input is not derived from daily evidence")
    coverage = _read_json(root / "coverage.json")
    expected_coverage = build_f2a_coverage(expected.contexts, expected.daily_excess_rows)
    if coverage != expected_coverage:
        raise ValueError("MR-2B F2A coverage is not reconstructible")
    _verify_manifest_rows(manifest, frames)

    return VerifiedF2ARun(
        root=root,
        run_id=run_id,
        dataset_id=dataset_id,
        mr1_run_id=mr1_run_id,
        manifest=_freeze_mapping(manifest),
        contexts=_frozen_records(frames["contexts"]),
        context_symbol_evidence=_frozen_records(frames["symbol_evidence"]),
        multiseed_selections=_frozen_records(frames["selections"]),
        multiseed_returns=_frozen_records(frames["returns"]),
        null_summaries=_frozen_records(frames["summaries"]),
        daily_candidate_excess=_frozen_records(frames["daily"]),
        primary_comparison_input=_freeze_mapping(primary),
        coverage=_freeze_mapping(coverage),
        checksums_hash=_content_hash(root / "SHA256SUMS.json"),
    )


def _verify_manifest(
    manifest: Mapping[str, Any],
    *,
    root: Path,
    dataset: VerifiedPRRDataset,
    mr1: VerifiedMR1Run,
) -> None:
    missing = MR2B_F2A_RUN_SCHEMA.required_manifest_keys - manifest.keys()
    if missing or manifest.get("schema_version") != MR2B_F2A_RUN_SCHEMA.schema_version:
        raise ValueError("MR-2B F2A manifest schema is invalid")
    if manifest.get("data_eligibility") != "EXPLORATORY":
        raise ValueError("MR-2B F2A authority must remain EXPLORATORY")
    if manifest.get("authority") != "EXPLORATORY_CONDITIONALITY_INPUT_EVIDENCE":
        raise ValueError("MR-2B F2A evidence authority is invalid")
    if manifest.get("dataset_id") != dataset.dataset_id or manifest.get("mr1_run_id") != mr1.run_id:
        raise ValueError("MR-2B F2A upstream input identity mismatch")
    if manifest.get("run_id") != root.name:
        raise ValueError("MR-2B F2A run ID must match immutable directory")
    if frozenset(manifest.get("required_artifacts", ())) != MR2B_F2A_RUN_SCHEMA.required_files:
        raise ValueError("MR-2B F2A required artifacts mismatch")


def _verify_identity_inputs(
    identity: F2ARunIdentity,
    *,
    dataset: VerifiedPRRDataset,
    mr1: VerifiedMR1Run,
) -> None:
    expected = {
        "dataset_id": dataset.dataset_id,
        "dataset_manifest_hash": _content_hash(dataset.root / "dataset_manifest.json"),
        "dataset_checksums_hash": dataset.checksums_hash,
        "mr1_run_id": mr1.run_id,
        "mr1_manifest_hash": _content_hash(mr1.root / "manifest.json"),
        "mr1_checksums_hash": mr1.checksums_hash,
        "top_k": int(mr1.manifest["top_k"]),
    }
    payload = identity.to_canonical_dict()
    if any(payload[key] != value for key, value in expected.items()):
        raise ValueError("MR-2B F2A typed identity does not match immutable inputs")
    if identity.seed_set_hash != canonical_identity_hash({"seeds": identity.seed_set}):
        raise ValueError("MR-2B F2A seed-set identity mismatch")


def _verify_identity_contract(identity: F2ARunIdentity) -> None:
    expected = {
        "context_schema_version": MR2B_CONTEXT_SCHEMA_VERSION,
        "symbol_context_evidence_schema_version": MR2B_CONTEXT_SYMBOL_EVIDENCE_SCHEMA_VERSION,
        "context_definition_id": MR2B_CONTEXT_DEFINITION_ID,
        "grid_definition_id": MR2B_CONTEXT_GRID_DEFINITION_ID,
        "coverage_policy_id": MR2B_CONTEXT_COVERAGE_POLICY_ID,
        "direction_label_policy_id": MR2B_DIRECTION_LABEL_POLICY_ID,
        "selection_algorithm_id": MR1_MATCHED_K_ALGORITHM_ID,
        "multi_seed_schema_version": MR2B_MULTISEED_SCHEMA_VERSION,
        "daily_excess_schema_version": MR2B_DAILY_EXCESS_SCHEMA_VERSION,
        "primary_comparison_input_schema_version": MR2B_PRIMARY_INPUT_SCHEMA_VERSION,
        "quantile_method_id": MR2B_QUANTILE_METHOD_ID,
        "percentile_method_id": MR2B_PERCENTILE_METHOD_ID,
        "cash_lock_policy_id": MR1_CASH_LOCK_POLICY_ID,
        "missing_weight_policy_id": MR1_MISSING_WEIGHT_POLICY_ID,
        "f2a_schema_version": MR2B_F2A_SCHEMA_VERSION,
        "primary_projection_rule_id": MR2B_PRIMARY_PROJECTION_RULE_ID,
        "semantic_reader_rule_id": F2A_SEMANTIC_READER_RULE_ID,
        "collision_diagnostic_rule_id": F2A_COLLISION_DIAGNOSTIC_RULE_ID,
        "cash_lock_empty_selection_hash_policy_id": F2A_CASH_LOCK_EMPTY_HASH_POLICY_ID,
        "semantic_tamper_validation_rule_id": F2A_SEMANTIC_TAMPER_RULE_ID,
    }
    payload = identity.to_canonical_dict()
    if any(payload[key] != value for key, value in expected.items()):
        raise ValueError("MR-2B F2A typed identity contract is stale or unsupported")
    module_root = PROJECT_ROOT / "src" / "market_regime_alpha" / "research"
    module_hashes = {
        "f2a_context_module_hash": _content_hash(module_root / "mr2b_context.py"),
        "f2a_multiseed_module_hash": _content_hash(module_root / "mr2b_multiseed.py"),
        "f2a_core_module_hash": _content_hash(module_root / "mr2b_f2a.py"),
        "f2a_artifact_module_hash": _content_hash(module_root / "mr2b_f2a_artifacts.py"),
        "f2a_reader_module_hash": _content_hash(module_root / "mr2b_f2a_reader.py"),
        "f2a_runner_hash": _content_hash(
            PROJECT_ROOT / "scripts" / "run_mr2b_f2a_conditionality_inputs.py"
        ),
    }
    if any(payload[key] != value for key, value in module_hashes.items()):
        raise ValueError("MR-2B F2A implementation identity is stale")


def _verify_seed_config(
    config: Mapping[str, Any],
    *,
    identity: F2ARunIdentity,
    manifest: Mapping[str, Any],
) -> None:
    expected = {
        "schema_version": "mr-2b-f2a-seed-config-v1",
        "seed_set_id": manifest["seed_set_id"],
        "seeds": list(identity.seed_set),
        "primary_seed": identity.primary_seed,
        "seed_count": len(identity.seed_set),
    }
    if config != expected:
        raise ValueError("MR-2B F2A seed config does not match typed identity")


def _verify_manifest_rows(manifest: Mapping[str, Any], frames: Mapping[str, pd.DataFrame]) -> None:
    expected = {
        "auxiliary_watchlist_context": len(frames["contexts"]),
        "auxiliary_watchlist_context_symbol_evidence": len(frames["symbol_evidence"]),
        "multi_seed_matched_k_selections": len(frames["selections"]),
        "multi_seed_matched_k_returns": len(frames["returns"]),
        "multi_seed_null_summary": len(frames["summaries"]),
        "daily_candidate_excess": len(frames["daily"]),
    }
    if manifest.get("row_counts") != expected:
        raise ValueError("MR-2B F2A manifest row counts mismatch")


def _assert_semantic_table(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
    *,
    key: tuple[str, ...],
    label: str,
) -> None:
    if set(actual.columns) != set(expected.columns):
        raise ValueError(f"MR-2B F2A {label} columns do not match reconstructed evidence")
    columns = sorted(expected.columns)
    actual_ordered = actual.sort_values(list(key)).reset_index(drop=True)[columns]
    expected_ordered = expected.sort_values(list(key)).reset_index(drop=True)[columns]
    try:
        assert_frame_equal(
            actual_ordered,
            expected_ordered,
            check_dtype=False,
            check_exact=False,
            rtol=0.0,
            atol=1e-15,
        )
    except AssertionError as exc:
        raise ValueError(
            f"MR-2B F2A {label} is not reconstructible from immutable inputs"
        ) from exc


def _unique(frame: pd.DataFrame, fields: tuple[str, ...], label: str) -> None:
    if frame.empty or any(field not in frame for field in fields):
        raise ValueError(f"MR-2B F2A {label} schema is incomplete")
    if frame.duplicated(list(fields)).any():
        raise ValueError(f"MR-2B F2A {label} primary keys must be unique")


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


def _frozen_records(frame: pd.DataFrame) -> tuple[Mapping[str, Any], ...]:
    return tuple(_freeze_mapping(row) for row in frame.to_dict(orient="records"))


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = _read_json_value(path)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _read_json_value(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("F2A run_identity must be a mapping")
    return value


def _canonical_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"MR-2B F2A {label} must be non-empty")
    return value
