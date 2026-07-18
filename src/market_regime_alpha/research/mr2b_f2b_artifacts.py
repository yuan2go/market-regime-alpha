"""Atomic immutable publication for MR-2B F2B statistical evidence."""

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
from market_regime_alpha.research.mr2b_f2b import F2BResults, build_f2b_results
from market_regime_alpha.research.mr2b_f2b_competing_events import COMPETING_EVENT_RULE_ID
from market_regime_alpha.research.mr2b_f2b_protocol import F2BProtocol, frozen_f2b_protocol
from market_regime_alpha.research.prr_artifact_reader import (
    load_verified_mr1_run,
    load_verified_prr_dataset,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    MR2B_F2B_RUN_SCHEMA,
    canonical_identity_hash,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_F2B_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "mr2b_f2b_statistical_closure"
F2B_LIMITATIONS = (
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
class F2BRunIdentity:
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
    bootstrap_method_id: str
    bootstrap_draws: int
    bootstrap_block_length: int
    bootstrap_seed: int
    randomization_method_id: str
    random_permutation_draws: int
    random_permutation_seed: int
    stability_rule_id: str
    concentration_rule_id: str
    seed_panel_rule_id: str
    secondary_family_id: str
    multiple_testing_method_id: str
    competing_event_contract_id: str
    implementation_module_hashes: Mapping[str, str]
    runner_hash: str
    data_eligibility: str
    authority_ceiling: str

    def __post_init__(self) -> None:
        if self.data_eligibility != "EXPLORATORY" or self.authority_ceiling != "EXPLORATORY":
            raise ValueError("F2B identity authority must remain EXPLORATORY")
        if self.alternative != "UP_GREATER_THAN_DOWN":
            raise ValueError("F2B identity alternative must remain directional")
        if not self.implementation_module_hashes:
            raise ValueError("F2B implementation hashes must not be empty")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["implementation_module_hashes"] = dict(sorted(self.implementation_module_hashes.items()))
        return payload

    def run_id(self) -> str:
        digest = canonical_identity_hash(self.to_canonical_dict()).split(":", 1)[1]
        return f"mr2b-f2b-{digest[:20]}"

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> F2BRunIdentity:
        if set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("F2B run identity fields do not match typed contract")
        values = dict(payload)
        hashes = values.get("implementation_module_hashes")
        if not isinstance(hashes, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in hashes.items()
        ):
            raise ValueError("F2B implementation module hashes are invalid")
        values["implementation_module_hashes"] = dict(hashes)
        return cls(**values)


def build_f2b_run_identity(
    *, dataset_root: Path, mr1_root: Path, f2a_root: Path, dataset_id: str,
    mr1_run_id: str, f2a_run_id: str, protocol: F2BProtocol, runner_path: Path,
) -> F2BRunIdentity:
    module_root = PROJECT_ROOT / "src" / "market_regime_alpha" / "research"
    names = (
        "mr2b_f2b_protocol.py", "mr2b_f2b_statistics.py", "mr2b_f2b_primary.py",
        "mr2b_f2b_secondary.py", "mr2b_f2b_competing_events.py", "mr2b_f2b.py",
        "mr2b_f2b_artifacts.py", "mr2b_f2b_reader.py",
    )
    hashes = {name: _content_hash(module_root / name) for name in names}
    return F2BRunIdentity(
        dataset_id=dataset_id,
        dataset_checksums_hash=_content_hash(dataset_root / "SHA256SUMS.json"),
        mr1_run_id=mr1_run_id,
        mr1_checksums_hash=_content_hash(mr1_root / "SHA256SUMS.json"),
        f2a_run_id=f2a_run_id,
        f2a_checksums_hash=_content_hash(f2a_root / "SHA256SUMS.json"),
        git_commit_sha=_revision(),
        protocol_schema_version=protocol.schema_version,
        protocol_hash=protocol.protocol_id,
        primary_hypothesis_id=protocol.primary_hypothesis_id,
        alternative=protocol.alternative,
        metric_id=protocol.metric_id,
        bootstrap_method_id=protocol.bootstrap_method_id,
        bootstrap_draws=protocol.bootstrap_draws,
        bootstrap_block_length=protocol.bootstrap_block_length,
        bootstrap_seed=protocol.bootstrap_seed,
        randomization_method_id=protocol.primary_randomization_method_id,
        random_permutation_draws=protocol.random_permutation_draws,
        random_permutation_seed=protocol.random_permutation_seed,
        stability_rule_id=protocol.first_second_half_rule_id,
        concentration_rule_id=protocol.concentration_rule_id,
        seed_panel_rule_id=protocol.seed_panel_rule_id,
        secondary_family_id=protocol.secondary_family_id,
        multiple_testing_method_id=protocol.multiple_testing_method_id,
        competing_event_contract_id=COMPETING_EVENT_RULE_ID,
        implementation_module_hashes=hashes,
        runner_hash=_content_hash(runner_path),
        data_eligibility="EXPLORATORY",
        authority_ceiling="EXPLORATORY",
    )


def publish_f2b_artifact(
    *, output_root: Path, identity: F2BRunIdentity, results: F2BResults
) -> Path:
    if identity.protocol_hash != results.protocol.protocol_id:
        raise ValueError("F2B identity and Protocol mismatch")
    run_id = identity.run_id()
    final = output_root / run_id
    stage = output_root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError("F2B Artifact is immutable and non-overwriting")
    output_root.mkdir(parents=True, exist_ok=True)
    stage.mkdir()
    try:
        protocol_payload = {**results.protocol.to_canonical_dict(), "protocol_id": results.protocol.protocol_id}
        assessment = results.primary_assessment_payload
        manifest = {
            "schema_version": MR2B_F2B_RUN_SCHEMA.schema_version,
            "run_id": run_id,
            "dataset_id": identity.dataset_id,
            "mr1_run_id": identity.mr1_run_id,
            "f2a_run_id": identity.f2a_run_id,
            "data_eligibility": "EXPLORATORY",
            "authority": "EXPLORATORY_STATISTICAL_ASSESSMENT",
            "required_artifacts": sorted(MR2B_F2B_RUN_SCHEMA.required_files),
            "run_identity": identity.to_canonical_dict(),
            "protocol_id": results.protocol.protocol_id,
            "row_counts": {
                "primary_observations": len(results.primary_observation_rows),
                "primary_bootstrap_distribution": len(results.bootstrap_distribution_rows),
                "primary_circular_shift_distribution": len(results.circular_shift_rows),
                "primary_random_permutation_distribution": len(results.random_permutation_rows),
                "primary_temporal_stability": len(results.temporal_rows),
                "primary_seed_panel_robustness": len(results.seed_panel_rows),
                "secondary_comparison_inventory": len(results.secondary_rows),
                "competing_event_diagnostics": len(results.competing_events.rows),
            },
            "primary_assessment": assessment["assessment"],
        }
        _write_json(stage / "manifest.json", manifest)
        _write_json(stage / "protocol.json", protocol_payload)
        _write_parquet(stage / "primary_observations.parquet", results.primary_observation_rows)
        _write_parquet(stage / "primary_bootstrap_distribution.parquet", results.bootstrap_distribution_rows)
        _write_parquet(stage / "primary_circular_shift_distribution.parquet", results.circular_shift_rows)
        _write_parquet(stage / "primary_random_permutation_distribution.parquet", results.random_permutation_rows)
        _write_parquet(stage / "primary_temporal_stability.parquet", results.temporal_rows)
        _write_parquet(stage / "primary_seed_panel_robustness.parquet", results.seed_panel_rows)
        _write_json(stage / "primary_concentration.json", results.concentration_payload)
        _write_json(stage / "primary_assessment.json", assessment)
        _write_parquet(stage / "secondary_comparison_inventory.parquet", results.secondary_rows)
        _write_json(stage / "multiple_testing_disclosure.json", results.multiple_testing)
        _write_parquet(
            stage / "competing_event_diagnostics.parquet",
            results.competing_events.rows,
            empty_columns=("scope", "target_id", "diagnostic_role"),
        )
        _write_json(
            stage / "competing_event_status.json",
            {
                "status": results.competing_events.status,
                "target_contract_id": results.competing_events.target_contract_id,
                "coverage": results.competing_events.coverage,
                "missing_target_count": results.competing_events.missing_target_count,
                "interpretation": results.competing_events.interpretation,
                "changes_primary_assessment": False,
            },
        )
        _write_json(stage / "limitations.json", list(F2B_LIMITATIONS))
        _write_report(stage / "report.md", run_id, identity, results)
        _write_checksums(stage)
        _validate_file_set(stage)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def run_f2b_research(
    *, dataset_path: Path, mr1_run_path: Path, f2a_run_path: Path,
    output_root: Path = DEFAULT_F2B_OUTPUT_ROOT, runner_path: Path,
) -> Path:
    dataset = load_verified_prr_dataset(dataset_path)
    mr1 = load_verified_mr1_run(mr1_run_path, dataset=dataset, expected_dataset_id=dataset.dataset_id)
    f2a = load_verified_f2a_run(
        f2a_run_path, dataset=dataset, mr1=mr1,
        expected_dataset_id=dataset.dataset_id, expected_mr1_run_id=mr1.run_id,
    )
    protocol = frozen_f2b_protocol()
    results = build_f2b_results(dataset=dataset, mr1=mr1, f2a=f2a, protocol=protocol)
    identity = build_f2b_run_identity(
        dataset_root=dataset.root, mr1_root=mr1.root, f2a_root=f2a.root,
        dataset_id=dataset.dataset_id, mr1_run_id=mr1.run_id, f2a_run_id=f2a.run_id,
        protocol=protocol, runner_path=runner_path,
    )
    final = publish_f2b_artifact(output_root=output_root, identity=identity, results=results)
    from market_regime_alpha.research.mr2b_f2b_reader import load_verified_f2b_run

    load_verified_f2b_run(final, dataset=dataset, mr1=mr1, f2a=f2a)
    return final


def _write_report(path: Path, run_id: str, identity: F2BRunIdentity, results: F2BResults) -> None:
    primary = results.primary_assessment_payload
    lines = [
        "# MR-2B F2B Directional Statistical Closure", "", "## Facts", "",
        f"- Run ID: `{run_id}`", f"- Dataset ID: `{identity.dataset_id}`",
        f"- MR-1 Run ID: `{identity.mr1_run_id}`", f"- F2A Run ID: `{identity.f2a_run_id}`",
        f"- Observed UP-minus-DOWN effect: `{primary['observed_effect']}`",
        f"- Circular-shift one-sided p-value: `{primary['circular_shift']['one_sided_p_value']}`",
        "", "## Statistical inference", "",
        f"- Frozen directional Primary assessment: `{primary['assessment']}`",
        f"- Failure reasons: `{primary['failure_reasons']}`",
        "- Secondary comparisons cannot replace the Primary conclusion.",
        "", "## Model assumptions", "",
        "- The 20-symbol watchlist is an auxiliary Context proxy, not the A-share market.",
        "- Multi-seed selections are same-date comparator evidence, not independent time observations.",
        "", "## Risks", "", *(f"- `{item}`" for item in F2B_LIMITATIONS),
        "", "## Invalidation conditions", "",
        "- F2A semantic verification failure", "- Protocol identity mismatch",
        "- Insufficient slice coverage", "- Bootstrap instability", "- Comparator panel instability",
        "- Result concentration", "- Future PIT replication failure", "- Independent OOS sign reversal",
        "", "## Trading authority", "",
        "- NO TRADING AUTHORITY", "- NO PRODUCTION REGIME GATE", "- NO MODEL WINNER",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_parquet(path: Path, rows: Any, *, empty_columns: tuple[str, ...] = ()) -> None:
    frame = pd.DataFrame.from_records(rows)
    if frame.empty and empty_columns:
        frame = pd.DataFrame(columns=list(empty_columns))
    frame.to_parquet(path, index=False)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")


def _write_checksums(root: Path) -> None:
    _write_json(root / "SHA256SUMS.json", {
        item.name: _content_hash(item) for item in sorted(root.iterdir())
        if item.is_file() and item.name != "SHA256SUMS.json"
    })


def _validate_file_set(root: Path) -> None:
    if frozenset(item.name for item in root.iterdir() if item.is_file()) != MR2B_F2B_RUN_SCHEMA.required_files:
        raise ValueError("F2B Artifact exact file set is invalid")


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _revision() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
    return result.stdout.strip()
