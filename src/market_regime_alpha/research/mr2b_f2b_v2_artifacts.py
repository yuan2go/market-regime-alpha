"""Immutable publisher and typed identity for MR-2B F2B v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

import pandas as pd

from market_regime_alpha.research.mr2b_f2a_reader import load_verified_f2a_run
from market_regime_alpha.research.mr2b_f2b_v2 import F2BResultsV2, build_f2b_v2_results
from market_regime_alpha.research.mr2b_f2b_v2_protocol import F2BProtocolV2, frozen_f2b_v2_protocol
from market_regime_alpha.research.prr_artifact_reader import (
    load_verified_mr1_run,
    load_verified_prr_dataset,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    MR2B_F2B_V2_RUN_SCHEMA,
    canonical_identity_hash,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_F2B_V2_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "mr2b_f2b_statistical_closure"
F2B_V2_LIMITATIONS = (
    "CURRENT_WATCHLIST_BACKFILL_BIAS",
    "HISTORICAL_PIT_NOT_VERIFIED",
    "WATCHLIST_CONTEXT_IS_NOT_FULL_MARKET_CONTEXT",
    "MULTI_SEED_REFERENCE_IS_NOT_INDEPENDENT_TIME_EVIDENCE",
    "MULTISEED_MEDIAN_IS_MONTE_CARLO_APPROXIMATION",
    "SINGLE_DATASET_ONLY",
    "REPEATED_EXPLORATORY_SAMPLE_INSPECTION",
    "NO_FORMAL_OOS",
    "REFERENCE_MARK_NOT_FILL_PROOF",
    "FEE_ASSUMPTIONS_REQUIRE_CURRENT_VERIFICATION",
)


@dataclass(frozen=True, slots=True)
class F2BRunIdentityV2:
    dataset_id: str
    dataset_checksums_hash: str
    mr1_run_id: str
    mr1_checksums_hash: str
    f2a_run_id: str
    f2a_checksums_hash: str
    git_commit_sha: str
    protocol_schema_version: str
    protocol_hash: str
    primary_hypothesis_id: str
    alternative: str
    metric_id: str
    implementation_module_hashes: Mapping[str, str]
    runner_hash: str
    data_eligibility: str
    authority_ceiling: str

    def __post_init__(self) -> None:
        if self.data_eligibility != "EXPLORATORY" or self.authority_ceiling != "EXPLORATORY":
            raise ValueError("F2B v2 authority must remain EXPLORATORY")
        if self.alternative != "UP_GREATER_THAN_DOWN":
            raise ValueError("F2B v2 direction must remain frozen")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["implementation_module_hashes"] = dict(sorted(self.implementation_module_hashes.items()))
        return payload

    def run_id(self) -> str:
        digest = canonical_identity_hash(self.to_canonical_dict()).split(":", 1)[1]
        return f"mr2b-f2b-v2-{digest[:20]}"

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> F2BRunIdentityV2:
        if set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("F2B v2 identity fields mismatch")
        values = dict(payload)
        hashes = values.get("implementation_module_hashes")
        if not isinstance(hashes, Mapping):
            raise ValueError("F2B v2 module hashes are invalid")
        values["implementation_module_hashes"] = dict(hashes)
        return cls(**values)


def build_f2b_v2_run_identity(
    *, dataset_root: Path, mr1_root: Path, f2a_root: Path,
    dataset_id: str, mr1_run_id: str, f2a_run_id: str,
    protocol: F2BProtocolV2, runner_path: Path,
) -> F2BRunIdentityV2:
    module_root = PROJECT_ROOT / "src" / "market_regime_alpha" / "research"
    names = (
        "mr2b_f2b_v2_protocol.py", "mr2b_f2b_v2_statistics.py", "mr2b_f2b_v2_primary.py",
        "mr2b_f2b_v2_competing_events.py", "mr2b_f2b_v2.py", "mr2b_f2b_v2_artifacts.py",
        "mr2b_f2b_v2_reader.py", "mr2b_verifier_registry.py",
    )
    return F2BRunIdentityV2(
        dataset_id=dataset_id,
        dataset_checksums_hash=_hash(dataset_root / "SHA256SUMS.json"),
        mr1_run_id=mr1_run_id,
        mr1_checksums_hash=_hash(mr1_root / "SHA256SUMS.json"),
        f2a_run_id=f2a_run_id,
        f2a_checksums_hash=_hash(f2a_root / "SHA256SUMS.json"),
        git_commit_sha=_revision(),
        protocol_schema_version=protocol.schema_version,
        protocol_hash=protocol.protocol_id,
        primary_hypothesis_id=protocol.primary_hypothesis_id,
        alternative=protocol.alternative,
        metric_id=protocol.metric_id,
        implementation_module_hashes={name: _hash(module_root / name) for name in names},
        runner_hash=_hash(runner_path),
        data_eligibility="EXPLORATORY",
        authority_ceiling="EXPLORATORY",
    )


def publish_f2b_v2_artifact(
    *, output_root: Path, identity: F2BRunIdentityV2, results: F2BResultsV2
) -> Path:
    if identity.protocol_hash != results.protocol.protocol_id:
        raise ValueError("F2B v2 identity and Protocol mismatch")
    run_id = identity.run_id()
    final = output_root / run_id
    stage = output_root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError("F2B v2 Artifact is immutable")
    output_root.mkdir(parents=True, exist_ok=True)
    stage.mkdir()
    try:
        assessment = results.primary_assessment_payload
        manifest = {
            "schema_version": MR2B_F2B_V2_RUN_SCHEMA.schema_version,
            "run_id": run_id,
            "dataset_id": identity.dataset_id,
            "mr1_run_id": identity.mr1_run_id,
            "f2a_run_id": identity.f2a_run_id,
            "data_eligibility": "EXPLORATORY",
            "authority": "EXPLORATORY_STATISTICAL_ASSESSMENT",
            "required_artifacts": sorted(MR2B_F2B_V2_RUN_SCHEMA.required_files),
            "run_identity": identity.to_canonical_dict(),
            "protocol_id": results.protocol.protocol_id,
            "statistics_executed": results.statistics_executed,
            "artifact_verification_status": "PENDING_SEMANTIC_READER",
            "row_counts": _row_counts(results),
            "primary_assessment": assessment["assessment"],
        }
        _write_json(stage / "manifest.json", manifest)
        _write_json(stage / "protocol.json", {**results.protocol.to_canonical_dict(), "protocol_id": results.protocol.protocol_id})
        _write_parquet(stage / "primary_observations.parquet", results.primary_observation_rows, ("decision_date",))
        _write_parquet(stage / "primary_bootstrap_distribution.parquet", results.bootstrap_distribution_rows, ("method_id", "block_length", "draw_index", "effect", "valid"))
        _write_parquet(stage / "primary_circular_shift_distribution.parquet", results.circular_shift_rows, ("method_id", "shift", "effect"))
        _write_parquet(stage / "primary_random_permutation_distribution.parquet", results.random_permutation_rows, ("method_id", "draw_index", "effect"))
        _write_parquet(stage / "primary_temporal_stability.parquet", results.temporal_rows, ("diagnostic_type",))
        _write_parquet(stage / "primary_seed_panel_robustness.parquet", results.seed_panel_rows, ("panel", "effect", "date_count"))
        _write_json(stage / "primary_concentration.json", results.concentration_payload)
        _write_json(stage / "primary_assessment.json", assessment)
        _write_parquet(stage / "secondary_comparison_inventory.parquet", results.secondary_rows, ("model_id", "exit_time", "cost_scenario"))
        _write_json(stage / "multiple_testing_disclosure.json", results.multiple_testing)
        _write_parquet(stage / "competing_event_diagnostics.parquet", results.competing_events.rows, ("scope", "target_id", "diagnostic_role"))
        _write_json(stage / "competing_event_status.json", _competing_status(results))
        _write_json(stage / "limitations.json", list(F2B_V2_LIMITATIONS))
        _write_report(stage / "report.md", run_id, results)
        _write_checksums(stage)
        _validate_file_set(stage)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def run_f2b_v2_research(
    *, dataset_path: Path, mr1_run_path: Path, f2a_run_path: Path,
    runner_path: Path, output_root: Path = DEFAULT_F2B_V2_OUTPUT_ROOT,
) -> Path:
    dataset = load_verified_prr_dataset(dataset_path)
    mr1 = load_verified_mr1_run(mr1_run_path, dataset=dataset, expected_dataset_id=dataset.dataset_id)
    f2a = load_verified_f2a_run(
        f2a_run_path, dataset=dataset, mr1=mr1,
        expected_dataset_id=dataset.dataset_id, expected_mr1_run_id=mr1.run_id,
    )
    protocol = frozen_f2b_v2_protocol()
    results = build_f2b_v2_results(dataset=dataset, mr1=mr1, f2a=f2a, protocol=protocol)
    identity = build_f2b_v2_run_identity(
        dataset_root=dataset.root, mr1_root=mr1.root, f2a_root=f2a.root,
        dataset_id=dataset.dataset_id, mr1_run_id=mr1.run_id, f2a_run_id=f2a.run_id,
        protocol=protocol, runner_path=runner_path,
    )
    final = publish_f2b_v2_artifact(output_root=output_root, identity=identity, results=results)
    from market_regime_alpha.research.mr2b_f2b_v2_reader import load_verified_f2b_v2_run

    load_verified_f2b_v2_run(final, dataset=dataset, mr1=mr1, f2a=f2a)
    return final


def _row_counts(results: F2BResultsV2) -> dict[str, int]:
    return {
        "primary_observations": len(results.primary_observation_rows),
        "primary_bootstrap_distribution": len(results.bootstrap_distribution_rows),
        "primary_circular_shift_distribution": len(results.circular_shift_rows),
        "primary_random_permutation_distribution": len(results.random_permutation_rows),
        "primary_temporal_stability": len(results.temporal_rows),
        "primary_seed_panel_robustness": len(results.seed_panel_rows),
        "secondary_comparison_inventory": len(results.secondary_rows),
        "competing_event_diagnostics": len(results.competing_events.rows),
    }


def _competing_status(results: F2BResultsV2) -> dict[str, Any]:
    coverage = asdict(results.competing_events.coverage)
    return {
        "status": results.competing_events.status,
        "target_contract_id": results.competing_events.target_contract_id,
        **coverage,
        "interpretation": results.competing_events.interpretation,
        "changes_primary_assessment": False,
    }


def _write_report(path: Path, run_id: str, results: F2BResultsV2) -> None:
    assessment = results.primary_assessment_payload
    lines = [
        "# MR-2B F2B v2 Post-Merge Hardening", "", "## Facts", "",
        f"- Run ID: `{run_id}`", f"- Statistics executed: `{results.statistics_executed}`",
        f"- Primary assessment: `{assessment['assessment']}`",
        f"- Insufficiency reasons: `{assessment['insufficiency_reasons']}`", "",
        "## Authority", "", "- EXPLORATORY only", "- NO FORMAL OOS ALPHA",
        "- NO MODEL WINNER", "- NO PRODUCTION MARKET REGIME GATE", "",
        "## Limitations", "", *(f"- `{item}`" for item in F2B_V2_LIMITATIONS),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_parquet(path: Path, rows: Any, empty_columns: tuple[str, ...]) -> None:
    frame = pd.DataFrame.from_records(rows)
    if frame.empty:
        frame = pd.DataFrame(columns=list(empty_columns))
    frame.to_parquet(path, index=False)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")


def _write_checksums(root: Path) -> None:
    _write_json(root / "SHA256SUMS.json", {
        item.name: _hash(item) for item in sorted(root.iterdir())
        if item.is_file() and item.name != "SHA256SUMS.json"
    })


def _validate_file_set(root: Path) -> None:
    files = frozenset(item.name for item in root.iterdir() if item.is_file())
    if files != MR2B_F2B_V2_RUN_SCHEMA.required_files:
        raise ValueError("F2B v2 exact file set is invalid")


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
