"""Semantic reader for immutable MR-2B F2B statistical evidence."""

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
from market_regime_alpha.research.mr2b_f2b import build_f2b_results
from market_regime_alpha.research.mr2b_f2b_artifacts import (
    F2B_LIMITATIONS,
    F2BRunIdentity,
    PROJECT_ROOT,
)
from market_regime_alpha.research.mr2b_f2b_protocol import F2BProtocol, frozen_f2b_protocol
from market_regime_alpha.research.prr_artifact_reader import VerifiedMR1Run, VerifiedPRRDataset
from market_regime_alpha.research.prr_artifact_schemas import MR2B_F2B_RUN_SCHEMA


@dataclass(frozen=True, slots=True)
class VerifiedF2BRun:
    root: Path
    run_id: str
    dataset_id: str
    mr1_run_id: str
    f2a_run_id: str
    manifest: Mapping[str, Any]
    protocol: F2BProtocol
    primary_observations: tuple[Mapping[str, Any], ...]
    bootstrap_distribution: tuple[Mapping[str, Any], ...]
    circular_shift_distribution: tuple[Mapping[str, Any], ...]
    random_permutation_distribution: tuple[Mapping[str, Any], ...]
    temporal_stability: tuple[Mapping[str, Any], ...]
    seed_panel_robustness: tuple[Mapping[str, Any], ...]
    primary_concentration: Mapping[str, Any]
    primary_assessment: Mapping[str, Any]
    secondary_comparisons: tuple[Mapping[str, Any], ...]
    multiple_testing_disclosure: Mapping[str, Any]
    competing_event_diagnostics: tuple[Mapping[str, Any], ...]
    competing_event_status: Mapping[str, Any]
    checksums_hash: str


def load_verified_f2b_run(
    path: Path, *, dataset: VerifiedPRRDataset, mr1: VerifiedMR1Run, f2a: VerifiedF2ARun
) -> VerifiedF2BRun:
    root = path.resolve()
    _verify_files(root)
    manifest = _read_json(root / "manifest.json")
    _verify_manifest(manifest, root=root, dataset=dataset, mr1=mr1, f2a=f2a)
    identity = F2BRunIdentity.from_canonical_dict(_mapping(manifest.get("run_identity")))
    run_id = str(manifest["run_id"])
    if identity.run_id() != run_id or root.name != run_id:
        raise ValueError("F2B Run ID does not match typed identity and directory")
    _verify_identity(identity, dataset=dataset, mr1=mr1, f2a=f2a)
    protocol_payload = _read_json(root / "protocol.json")
    protocol_id = protocol_payload.pop("protocol_id", None)
    protocol_payload["eligible_context_labels"] = tuple(protocol_payload["eligible_context_labels"])
    protocol_payload["bootstrap_sensitivity_block_lengths"] = tuple(
        protocol_payload["bootstrap_sensitivity_block_lengths"]
    )
    protocol = F2BProtocol(**protocol_payload)
    if protocol_id != protocol.protocol_id or protocol.to_canonical_dict() != frozen_f2b_protocol().to_canonical_dict():
        raise ValueError("F2B Protocol is not the frozen directional protocol")
    if identity.protocol_hash != protocol.protocol_id or manifest.get("protocol_id") != protocol.protocol_id:
        raise ValueError("F2B Protocol identity mismatch")

    frames = {
        "primary": pd.read_parquet(root / "primary_observations.parquet"),
        "bootstrap": pd.read_parquet(root / "primary_bootstrap_distribution.parquet"),
        "circular": pd.read_parquet(root / "primary_circular_shift_distribution.parquet"),
        "permutation": pd.read_parquet(root / "primary_random_permutation_distribution.parquet"),
        "temporal": pd.read_parquet(root / "primary_temporal_stability.parquet"),
        "panels": pd.read_parquet(root / "primary_seed_panel_robustness.parquet"),
        "secondary": pd.read_parquet(root / "secondary_comparison_inventory.parquet"),
        "competing": pd.read_parquet(root / "competing_event_diagnostics.parquet"),
    }
    expected = build_f2b_results(dataset=dataset, mr1=mr1, f2a=f2a, protocol=protocol)
    expected_frames = {
        "primary": pd.DataFrame.from_records(expected.primary_observation_rows),
        "bootstrap": pd.DataFrame.from_records(expected.bootstrap_distribution_rows),
        "circular": pd.DataFrame.from_records(expected.circular_shift_rows),
        "permutation": pd.DataFrame.from_records(expected.random_permutation_rows),
        "temporal": pd.DataFrame.from_records(expected.temporal_rows),
        "panels": pd.DataFrame.from_records(expected.seed_panel_rows),
        "secondary": pd.DataFrame.from_records(expected.secondary_rows),
        "competing": (
            pd.DataFrame.from_records(expected.competing_events.rows)
            if expected.competing_events.rows
            else pd.DataFrame(columns=["scope", "target_id", "diagnostic_role"])
        ),
    }
    sort_keys = {
        "primary": ("decision_date",),
        "bootstrap": ("block_length", "draw_index"),
        "circular": ("shift",),
        "permutation": ("draw_index",),
        "temporal": ("diagnostic_type", "start_date", "end_date"),
        "panels": ("panel",),
        "secondary": ("model_id", "exit_time", "cost_scenario"),
        "competing": ("scope",),
    }
    for label in frames:
        _assert_table(frames[label], expected_frames[label], sort_keys[label], label)
    json_actual = {
        "concentration": _read_json(root / "primary_concentration.json"),
        "assessment": _read_json(root / "primary_assessment.json"),
        "multiple": _read_json(root / "multiple_testing_disclosure.json"),
        "competing_status": _read_json(root / "competing_event_status.json"),
    }
    json_expected = {
        "concentration": expected.concentration_payload,
        "assessment": expected.primary_assessment_payload,
        "multiple": expected.multiple_testing,
        "competing_status": {
            "status": expected.competing_events.status,
            "target_contract_id": expected.competing_events.target_contract_id,
            "coverage": expected.competing_events.coverage,
            "missing_target_count": expected.competing_events.missing_target_count,
            "interpretation": expected.competing_events.interpretation,
            "changes_primary_assessment": False,
        },
    }
    for label in json_actual:
        if not _canonical_equal(json_actual[label], json_expected[label]):
            raise ValueError(f"F2B {label} is not reconstructible from immutable evidence")
    limitations = _read_json_value(root / "limitations.json")
    if not isinstance(limitations, list) or tuple(limitations) != F2B_LIMITATIONS:
        raise ValueError("F2B limitations do not match authority contract")
    _verify_row_counts(manifest, frames)
    if manifest.get("primary_assessment") != expected.primary_gate.assessment.value:
        raise ValueError("F2B manifest Primary assessment mismatch")
    return VerifiedF2BRun(
        root=root, run_id=run_id, dataset_id=dataset.dataset_id, mr1_run_id=mr1.run_id,
        f2a_run_id=f2a.run_id, manifest=_freeze_mapping(manifest), protocol=protocol,
        primary_observations=_frozen_records(frames["primary"]),
        bootstrap_distribution=_frozen_records(frames["bootstrap"]),
        circular_shift_distribution=_frozen_records(frames["circular"]),
        random_permutation_distribution=_frozen_records(frames["permutation"]),
        temporal_stability=_frozen_records(frames["temporal"]),
        seed_panel_robustness=_frozen_records(frames["panels"]),
        primary_concentration=_freeze_mapping(json_actual["concentration"]),
        primary_assessment=_freeze_mapping(json_actual["assessment"]),
        secondary_comparisons=_frozen_records(frames["secondary"]),
        multiple_testing_disclosure=_freeze_mapping(json_actual["multiple"]),
        competing_event_diagnostics=_frozen_records(frames["competing"]),
        competing_event_status=_freeze_mapping(json_actual["competing_status"]),
        checksums_hash=_content_hash(root / "SHA256SUMS.json"),
    )


def _verify_manifest(
    manifest: Mapping[str, Any], *, root: Path, dataset: VerifiedPRRDataset,
    mr1: VerifiedMR1Run, f2a: VerifiedF2ARun,
) -> None:
    if MR2B_F2B_RUN_SCHEMA.required_manifest_keys - manifest.keys():
        raise ValueError("F2B manifest required fields are missing")
    if manifest.get("schema_version") != MR2B_F2B_RUN_SCHEMA.schema_version:
        raise ValueError("F2B manifest schema mismatch")
    if manifest.get("run_id") != root.name:
        raise ValueError("F2B manifest Run ID mismatch")
    if (
        manifest.get("dataset_id") != dataset.dataset_id
        or manifest.get("mr1_run_id") != mr1.run_id
        or manifest.get("f2a_run_id") != f2a.run_id
    ):
        raise ValueError("F2B immutable input identity mismatch")
    if manifest.get("data_eligibility") != "EXPLORATORY" or manifest.get("authority") != "EXPLORATORY_STATISTICAL_ASSESSMENT":
        raise ValueError("F2B authority mismatch")
    if frozenset(manifest.get("required_artifacts", ())) != MR2B_F2B_RUN_SCHEMA.required_files:
        raise ValueError("F2B required Artifact set mismatch")


def _verify_identity(
    identity: F2BRunIdentity, *, dataset: VerifiedPRRDataset, mr1: VerifiedMR1Run, f2a: VerifiedF2ARun
) -> None:
    if (
        identity.dataset_id != dataset.dataset_id
        or identity.mr1_run_id != mr1.run_id
        or identity.f2a_run_id != f2a.run_id
        or identity.dataset_checksums_hash != dataset.checksums_hash
        or identity.mr1_checksums_hash != mr1.checksums_hash
        or identity.f2a_checksums_hash != f2a.checksums_hash
    ):
        raise ValueError("F2B typed identity does not bind verified inputs")
    module_root = PROJECT_ROOT / "src" / "market_regime_alpha" / "research"
    expected = {name: _content_hash(module_root / name) for name in identity.implementation_module_hashes}
    if dict(identity.implementation_module_hashes) != expected:
        raise ValueError("F2B implementation module identity is stale")


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("F2B Artifact directory is missing")
    files = frozenset(item.name for item in root.iterdir() if item.is_file())
    if files != MR2B_F2B_RUN_SCHEMA.required_files:
        raise ValueError("F2B Artifact exact file set mismatch")
    checksums = _read_json(root / "SHA256SUMS.json")
    payloads = MR2B_F2B_RUN_SCHEMA.required_files - {"SHA256SUMS.json"}
    if frozenset(checksums) != payloads:
        raise ValueError("F2B checksum coverage mismatch")
    for filename in payloads:
        if checksums.get(filename) != _content_hash(root / filename):
            raise ValueError(f"F2B checksum mismatch: {filename}")


def _verify_row_counts(manifest: Mapping[str, Any], frames: Mapping[str, pd.DataFrame]) -> None:
    expected = {
        "primary_observations": len(frames["primary"]),
        "primary_bootstrap_distribution": len(frames["bootstrap"]),
        "primary_circular_shift_distribution": len(frames["circular"]),
        "primary_random_permutation_distribution": len(frames["permutation"]),
        "primary_temporal_stability": len(frames["temporal"]),
        "primary_seed_panel_robustness": len(frames["panels"]),
        "secondary_comparison_inventory": len(frames["secondary"]),
        "competing_event_diagnostics": len(frames["competing"]),
    }
    if manifest.get("row_counts") != expected:
        raise ValueError("F2B manifest row counts mismatch")


def _assert_table(actual: pd.DataFrame, expected: pd.DataFrame, keys: tuple[str, ...], label: str) -> None:
    if set(actual.columns) != set(expected.columns):
        raise ValueError(f"F2B {label} columns mismatch")
    columns = sorted(expected.columns)
    usable_keys = [key for key in keys if key in actual.columns]
    actual_ordered = actual.sort_values(usable_keys, na_position="last").reset_index(drop=True)[columns]
    expected_ordered = expected.sort_values(usable_keys, na_position="last").reset_index(drop=True)[columns]
    try:
        assert_frame_equal(actual_ordered, expected_ordered, check_dtype=False, check_exact=False, rtol=0.0, atol=1e-15)
    except AssertionError as exc:
        raise ValueError(f"F2B {label} is not reconstructible from immutable evidence") from exc


def _read_json(path: Path) -> dict[str, Any]:
    value = _read_json_value(path)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _read_json_value(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("F2B run_identity must be a mapping")
    return value


def _canonical_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


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


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
