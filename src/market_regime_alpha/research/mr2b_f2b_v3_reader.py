"""Semantic reader for immutable MR-2B F2B v3 evidence."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import pandas as pd
from pandas.testing import assert_frame_equal

from market_regime_alpha.research.mr2b_f2a_reader import VerifiedF2ARun
from market_regime_alpha.research.mr2b_f2b_v3 import F2BResultsV3, build_f2b_v3_results
from market_regime_alpha.research.mr2b_f2b_v3_artifacts import (
    F2B_V3_IMPLEMENTATION_MODULES,
    F2B_V3_LIMITATIONS,
    F2BRunIdentityV3,
    PROJECT_ROOT,
    build_v2_v3_semantic_diff,
    f2b_v3_semantic_projection,
)
from market_regime_alpha.research.mr2b_f2b_v3_protocol import F2BProtocolV3, frozen_f2b_v3_protocol
from market_regime_alpha.research.prr_artifact_reader import VerifiedMR1Run, VerifiedPRRDataset
from market_regime_alpha.research.prr_artifact_schemas import MR2B_F2B_V3_RUN_SCHEMA


@dataclass(frozen=True, slots=True)
class VerifiedF2BRunV3:
    root: Path
    run_id: str
    dataset_id: str
    mr1_run_id: str
    f2a_run_id: str
    manifest: Mapping[str, Any]
    protocol: F2BProtocolV3
    primary_assessment: Mapping[str, Any]
    competing_event_status: Mapping[str, Any]
    statistics_executed: bool
    artifact_verification_status: str
    checksums_hash: str


def load_verified_f2b_v3_run(
    path: Path, *, dataset: VerifiedPRRDataset, mr1: VerifiedMR1Run, f2a: VerifiedF2ARun
) -> VerifiedF2BRunV3:
    root = path.resolve()
    _verify_files(root)
    manifest = _json(root / "manifest.json")
    if manifest.get("schema_version") != MR2B_F2B_V3_RUN_SCHEMA.schema_version:
        raise ValueError("F2B v3 schema mismatch")
    if frozenset(manifest.get("required_artifacts", ())) != MR2B_F2B_V3_RUN_SCHEMA.required_files:
        raise ValueError("F2B v3 required file contract mismatch")
    if MR2B_F2B_V3_RUN_SCHEMA.required_manifest_keys - manifest.keys():
        raise ValueError("F2B v3 manifest required fields are missing")
    identity = F2BRunIdentityV3.from_canonical_dict(_mapping(manifest.get("run_identity")))
    run_id = str(manifest.get("run_id"))
    if identity.run_id() != run_id or root.name != run_id:
        raise ValueError("F2B v3 Run ID mismatch")
    _verify_identity(identity, dataset=dataset, mr1=mr1, f2a=f2a)
    protocol_payload = _json(root / "protocol.json")
    protocol_id = protocol_payload.pop("protocol_id", None)
    protocol_payload["eligible_context_labels"] = tuple(protocol_payload["eligible_context_labels"])
    protocol_payload["bootstrap_sensitivity_block_lengths"] = tuple(
        protocol_payload["bootstrap_sensitivity_block_lengths"]
    )
    protocol = F2BProtocolV3(**protocol_payload)
    if protocol_id != protocol.protocol_id or protocol.to_canonical_dict() != frozen_f2b_v3_protocol().to_canonical_dict():
        raise ValueError("F2B v3 Protocol is not the frozen contract")
    if manifest.get("protocol_id") != protocol.protocol_id or identity.protocol_hash != protocol.protocol_id:
        raise ValueError("F2B v3 Protocol identity mismatch")
    expected = build_f2b_v3_results(dataset=dataset, mr1=mr1, f2a=f2a, protocol=protocol)
    actual_frames = _frames(root)
    expected_frames = _expected_frames(expected)
    keys = {
        "primary": ("decision_date",), "bootstrap": ("block_length", "draw_index"),
        "circular": ("shift",), "permutation": ("draw_index",),
        "temporal": ("diagnostic_type", "start_date", "end_date"),
        "panels": ("panel",), "secondary": ("model_id", "exit_time", "cost_scenario"),
        "competing": ("scope",),
    }
    for label, actual in actual_frames.items():
        _assert_table(actual, expected_frames[label], keys[label], label)
    actual_json = {
        "concentration": _json(root / "primary_concentration.json"),
        "assessment": _json(root / "primary_assessment.json"),
        "multiple": _json(root / "multiple_testing_disclosure.json"),
        "competing": _json(root / "competing_event_status.json"),
    }
    expected_json = {
        "concentration": expected.concentration_payload,
        "assessment": expected.primary_assessment_payload,
        "multiple": expected.multiple_testing,
        "competing": _competing_status(expected),
    }
    for label in actual_json:
        if not _canonical_equal(actual_json[label], expected_json[label]):
            raise ValueError(f"F2B v3 {label} is not reconstructible")
    semantic_diff = _json(root / "v2_vs_v3_semantic_diff.json")
    expected_diff = build_v2_v3_semantic_diff(
        v2_projection=semantic_diff.get("v2") if isinstance(semantic_diff.get("v2"), Mapping) else None,
        v3_projection=f2b_v3_semantic_projection(expected),
    )
    if not _canonical_equal(semantic_diff, expected_diff):
        raise ValueError("F2B v3 semantic diff is not reconstructible")
    if tuple(_json_value(root / "limitations.json")) != F2B_V3_LIMITATIONS:
        raise ValueError("F2B v3 limitations mismatch")
    if manifest.get("row_counts") != _row_counts(actual_frames):
        raise ValueError("F2B v3 row counts mismatch")
    if manifest.get("statistics_executed") is not expected.statistics_executed:
        raise ValueError("F2B v3 coverage decision mismatch")
    if manifest.get("primary_assessment") != expected.primary_gate.assessment.value:
        raise ValueError("F2B v3 Primary assessment mismatch")
    if (
        manifest.get("dataset_id") != dataset.dataset_id
        or manifest.get("mr1_run_id") != mr1.run_id
        or manifest.get("f2a_run_id") != f2a.run_id
    ):
        raise ValueError("F2B v3 input identity mismatch")
    return VerifiedF2BRunV3(
        root=root, run_id=run_id, dataset_id=dataset.dataset_id, mr1_run_id=mr1.run_id,
        f2a_run_id=f2a.run_id, manifest=_freeze(manifest), protocol=protocol,
        primary_assessment=_freeze(actual_json["assessment"]),
        competing_event_status=_freeze(actual_json["competing"]),
        statistics_executed=expected.statistics_executed,
        artifact_verification_status="VERIFIED_EXPLORATORY_STATISTICAL_ASSESSMENT",
        checksums_hash=_hash(root / "SHA256SUMS.json"),
    )


def _verify_identity(
    identity: F2BRunIdentityV3, *, dataset: VerifiedPRRDataset, mr1: VerifiedMR1Run, f2a: VerifiedF2ARun
) -> None:
    if (
        identity.dataset_id != dataset.dataset_id
        or identity.dataset_checksums_hash != dataset.checksums_hash
        or identity.mr1_run_id != mr1.run_id
        or identity.mr1_checksums_hash != mr1.checksums_hash
        or identity.f2a_run_id != f2a.run_id
        or identity.f2a_checksums_hash != f2a.checksums_hash
    ):
        raise ValueError("F2B v3 typed identity does not bind inputs")
    module_root = PROJECT_ROOT / "src" / "market_regime_alpha" / "research"
    if set(identity.implementation_module_hashes) != set(F2B_V3_IMPLEMENTATION_MODULES):
        raise ValueError("F2B v3 implementation module set mismatch")
    expected = {name: _hash(module_root / name) for name in F2B_V3_IMPLEMENTATION_MODULES}
    if dict(identity.implementation_module_hashes) != expected:
        raise ValueError("F2B v3 implementation identity is stale")


def _frames(root: Path) -> dict[str, pd.DataFrame]:
    return {
        "primary": pd.read_parquet(root / "primary_observations.parquet"),
        "bootstrap": pd.read_parquet(root / "primary_bootstrap_distribution.parquet"),
        "circular": pd.read_parquet(root / "primary_circular_shift_distribution.parquet"),
        "permutation": pd.read_parquet(root / "primary_random_permutation_distribution.parquet"),
        "temporal": pd.read_parquet(root / "primary_temporal_stability.parquet"),
        "panels": pd.read_parquet(root / "primary_seed_panel_robustness.parquet"),
        "secondary": pd.read_parquet(root / "secondary_comparison_inventory.parquet"),
        "competing": pd.read_parquet(root / "competing_event_diagnostics.parquet"),
    }


def _expected_frames(results: F2BResultsV3) -> dict[str, pd.DataFrame]:
    empty = {
        "primary": ("decision_date",),
        "bootstrap": ("method_id", "block_length", "draw_index", "effect", "valid"),
        "circular": ("method_id", "shift", "effect"),
        "permutation": ("method_id", "draw_index", "effect"),
        "temporal": ("diagnostic_type",),
        "panels": ("panel", "effect", "date_count"),
        "secondary": ("model_id", "exit_time", "cost_scenario"),
        "competing": ("scope", "target_id", "diagnostic_role"),
    }
    rows = {
        "primary": results.primary_observation_rows,
        "bootstrap": results.bootstrap_distribution_rows,
        "circular": results.circular_shift_rows,
        "permutation": results.random_permutation_rows,
        "temporal": results.temporal_rows,
        "panels": results.seed_panel_rows,
        "secondary": results.secondary_rows,
        "competing": results.competing_events.rows,
    }
    return {
        label: pd.DataFrame.from_records(value) if value else pd.DataFrame(columns=list(empty[label]))
        for label, value in rows.items()
    }


def _competing_status(results: F2BResultsV3) -> dict[str, Any]:
    from dataclasses import asdict

    return {
        "status": results.competing_events.status,
        "target_contract_id": results.competing_events.target_contract_id,
        **asdict(results.competing_events.coverage),
        "interpretation": results.competing_events.interpretation,
        "changes_primary_assessment": False,
    }


def _row_counts(frames: Mapping[str, pd.DataFrame]) -> dict[str, int]:
    return {
        "primary_observations": len(frames["primary"]),
        "primary_bootstrap_distribution": len(frames["bootstrap"]),
        "primary_circular_shift_distribution": len(frames["circular"]),
        "primary_random_permutation_distribution": len(frames["permutation"]),
        "primary_temporal_stability": len(frames["temporal"]),
        "primary_seed_panel_robustness": len(frames["panels"]),
        "secondary_comparison_inventory": len(frames["secondary"]),
        "competing_event_diagnostics": len(frames["competing"]),
    }


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("F2B v3 Artifact is missing")
    files = frozenset(item.name for item in root.iterdir() if item.is_file())
    if files != MR2B_F2B_V3_RUN_SCHEMA.required_files:
        raise ValueError("F2B v3 exact file set mismatch")
    checksums = _json(root / "SHA256SUMS.json")
    payloads = files - {"SHA256SUMS.json"}
    if frozenset(checksums) != payloads:
        raise ValueError("F2B v3 checksum coverage mismatch")
    for name in payloads:
        if checksums[name] != _hash(root / name):
            raise ValueError(f"F2B v3 checksum mismatch: {name}")


def _assert_table(actual: pd.DataFrame, expected: pd.DataFrame, keys: tuple[str, ...], label: str) -> None:
    if set(actual.columns) != set(expected.columns):
        raise ValueError(f"F2B v3 {label} columns mismatch")
    columns = sorted(expected.columns)
    usable = [key for key in keys if key in columns]
    actual_ordered = actual.sort_values(usable, na_position="last").reset_index(drop=True)[columns] if usable else actual[columns]
    expected_ordered = expected.sort_values(usable, na_position="last").reset_index(drop=True)[columns] if usable else expected[columns]
    try:
        assert_frame_equal(actual_ordered, expected_ordered, check_dtype=False, check_exact=False, rtol=0, atol=1e-15)
    except AssertionError as exc:
        raise ValueError(f"F2B v3 {label} is not reconstructible") from exc


def _json(path: Path) -> dict[str, Any]:
    value = _json_value(path)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _json_value(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("F2B v3 run_identity must be a mapping")
    return value


def _canonical_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
