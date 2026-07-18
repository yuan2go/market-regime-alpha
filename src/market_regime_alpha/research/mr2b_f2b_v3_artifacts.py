"""Immutable publisher and typed identity for MR-2B F2B v3."""

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
from market_regime_alpha.research.mr2b_f2b_v3 import F2BResultsV3, build_f2b_v3_results
from market_regime_alpha.research.mr2b_f2b_v3_protocol import F2BProtocolV3, frozen_f2b_v3_protocol
from market_regime_alpha.research.prr_artifact_reader import (
    load_verified_mr1_run,
    load_verified_prr_dataset,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    MR2B_F2B_V3_RUN_SCHEMA,
    canonical_identity_hash,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_F2B_V3_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "mr2b_f2b_statistical_closure"
F2B_V3_LIMITATIONS = (
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
F2B_V3_IMPLEMENTATION_MODULES: tuple[str, ...] = (
    "mr2b_f2b_v3_protocol.py",
    "mr2b_f2b_v3_statistics.py",
    "mr2b_f2b_v3_primary.py",
    "mr2b_f2b_v3_competing_events.py",
    "mr2b_f2b_v3.py",
    "mr2b_f2b_v3_artifacts.py",
    "mr2b_f2b_v3_reader.py",
)


@dataclass(frozen=True, slots=True)
class F2BRunIdentityV3:
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
            raise ValueError("F2B v3 authority must remain EXPLORATORY")
        if self.alternative != "UP_GREATER_THAN_DOWN":
            raise ValueError("F2B v3 direction must remain frozen")
        if set(self.implementation_module_hashes) != set(F2B_V3_IMPLEMENTATION_MODULES):
            raise ValueError("F2B v3 implementation module set mismatch")
        if any(
            not isinstance(value, str) or not value.startswith("sha256:")
            for value in self.implementation_module_hashes.values()
        ):
            raise ValueError("F2B v3 implementation module hash is invalid")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["implementation_module_hashes"] = dict(sorted(self.implementation_module_hashes.items()))
        return payload

    def run_id(self) -> str:
        digest = canonical_identity_hash(self.to_canonical_dict()).split(":", 1)[1]
        return f"mr2b-f2b-v3-{digest[:20]}"

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> F2BRunIdentityV3:
        if set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("F2B v3 identity fields mismatch")
        values = dict(payload)
        hashes = values.get("implementation_module_hashes")
        if not isinstance(hashes, Mapping):
            raise ValueError("F2B v3 module hashes are invalid")
        values["implementation_module_hashes"] = dict(hashes)
        return cls(**values)


def build_f2b_v3_run_identity(
    *, dataset_root: Path, mr1_root: Path, f2a_root: Path,
    dataset_id: str, mr1_run_id: str, f2a_run_id: str,
    protocol: F2BProtocolV3, runner_path: Path,
) -> F2BRunIdentityV3:
    module_root = PROJECT_ROOT / "src" / "market_regime_alpha" / "research"
    return F2BRunIdentityV3(
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
        implementation_module_hashes={
            name: _hash(module_root / name) for name in F2B_V3_IMPLEMENTATION_MODULES
        },
        runner_hash=_hash(runner_path),
        data_eligibility="EXPLORATORY",
        authority_ceiling="EXPLORATORY",
    )


def publish_f2b_v3_artifact(
    *,
    output_root: Path,
    identity: F2BRunIdentityV3,
    results: F2BResultsV3,
    v2_semantic_projection: Mapping[str, Any] | None = None,
) -> Path:
    if identity.protocol_hash != results.protocol.protocol_id:
        raise ValueError("F2B v3 identity and Protocol mismatch")
    run_id = identity.run_id()
    final = output_root / run_id
    stage = output_root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError("F2B v3 Artifact is immutable")
    output_root.mkdir(parents=True, exist_ok=True)
    stage.mkdir()
    try:
        assessment = results.primary_assessment_payload
        manifest = {
            "schema_version": MR2B_F2B_V3_RUN_SCHEMA.schema_version,
            "run_id": run_id,
            "dataset_id": identity.dataset_id,
            "mr1_run_id": identity.mr1_run_id,
            "f2a_run_id": identity.f2a_run_id,
            "data_eligibility": "EXPLORATORY",
            "authority": "EXPLORATORY_STATISTICAL_ASSESSMENT",
            "required_artifacts": sorted(MR2B_F2B_V3_RUN_SCHEMA.required_files),
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
        _write_json(stage / "limitations.json", list(F2B_V3_LIMITATIONS))
        _write_json(
            stage / "v2_vs_v3_semantic_diff.json",
            build_v2_v3_semantic_diff(
                v2_projection=v2_semantic_projection,
                v3_projection=f2b_v3_semantic_projection(results),
            ),
        )
        _write_report(stage / "report.md", run_id, results)
        _write_checksums(stage)
        _validate_file_set(stage)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def f2b_v3_semantic_projection(results: F2BResultsV3) -> dict[str, Any]:
    assessment = results.primary_assessment_payload
    primary = results.primary_set
    bootstrap = assessment.get("bootstrap", {})
    circular = assessment.get("circular_shift", {})
    temporal = assessment.get("temporal", {})
    up_count = sum(row.context_label.value == "UP" for row in primary.observations)
    down_count = sum(row.context_label.value == "DOWN" for row in primary.observations)
    return {
        "up_count": up_count,
        "down_count": down_count,
        "observed_effect": assessment.get("observed_effect"),
        "bootstrap_ci_lower": bootstrap.get("ci_lower_95"),
        "bootstrap_ci_upper": bootstrap.get("ci_upper_95"),
        "circular_shift_p_value": circular.get("one_sided_p_value"),
        "first_half_effect": temporal.get("first_half_effect"),
        "second_half_effect": temporal.get("second_half_effect"),
        "seed_panel_effects": [row.get("effect") for row in results.seed_panel_rows],
        "primary_assessment": assessment.get("assessment"),
        "minimum_secondary_q_value": results.multiple_testing.get("minimum_bh_q_value"),
        "competing_event_status": results.competing_events.status,
    }


def f2b_v2_semantic_projection(
    *,
    primary_assessment: Mapping[str, Any],
    multiple_testing: Mapping[str, Any],
    competing_event_status: Mapping[str, Any],
) -> dict[str, Any]:
    bootstrap = _mapping_or_empty(primary_assessment.get("bootstrap"))
    circular = _mapping_or_empty(primary_assessment.get("circular_shift"))
    temporal = _mapping_or_empty(primary_assessment.get("temporal"))
    panel = _mapping_or_empty(primary_assessment.get("seed_panel_robustness"))
    coverage = _mapping_or_empty(primary_assessment.get("coverage"))
    return {
        "up_count": coverage.get("up_count"),
        "down_count": coverage.get("down_count"),
        "observed_effect": primary_assessment.get("observed_effect"),
        "bootstrap_ci_lower": bootstrap.get("ci_lower_95"),
        "bootstrap_ci_upper": bootstrap.get("ci_upper_95"),
        "circular_shift_p_value": circular.get("one_sided_p_value"),
        "first_half_effect": temporal.get("first_half_effect"),
        "second_half_effect": temporal.get("second_half_effect"),
        "seed_panel_effects": [
            panel.get("panel_A_effect"),
            panel.get("panel_B_effect"),
            panel.get("panel_C_effect"),
            panel.get("panel_D_effect"),
        ],
        "primary_assessment": primary_assessment.get("assessment"),
        "minimum_secondary_q_value": multiple_testing.get("minimum_bh_q_value"),
        "competing_event_status": competing_event_status.get("status"),
    }


def build_v2_v3_semantic_diff(
    *, v2_projection: Mapping[str, Any] | None, v3_projection: Mapping[str, Any]
) -> dict[str, Any]:
    if v2_projection is None:
        return {
            "schema_version": "mr-2b-f2b-v2-v3-semantic-diff-v1",
            "status": "V2_REFERENCE_NOT_SUPPLIED",
            "v2": None,
            "v3": dict(v3_projection),
            "differences": [],
        }
    keys = sorted(set(v2_projection) | set(v3_projection))
    differences = [
        {"field": key, "v2": v2_projection.get(key), "v3": v3_projection.get(key)}
        for key in keys
        if not _semantic_value_equal(v2_projection.get(key), v3_projection.get(key))
    ]
    return {
        "schema_version": "mr-2b-f2b-v2-v3-semantic-diff-v1",
        "status": "EXACT_MATCH" if not differences else "DIFFERENT",
        "v2": dict(v2_projection),
        "v3": dict(v3_projection),
        "differences": differences,
    }


def _semantic_value_equal(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-15
    return left == right


def _mapping_or_empty(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def run_f2b_v3_research(
    *, dataset_path: Path, mr1_run_path: Path, f2a_run_path: Path,
    f2b_v2_run_path: Path | None = None,
    runner_path: Path, output_root: Path = DEFAULT_F2B_V3_OUTPUT_ROOT,
) -> Path:
    dataset = load_verified_prr_dataset(dataset_path)
    mr1 = load_verified_mr1_run(mr1_run_path, dataset=dataset, expected_dataset_id=dataset.dataset_id)
    f2a = load_verified_f2a_run(
        f2a_run_path, dataset=dataset, mr1=mr1,
        expected_dataset_id=dataset.dataset_id, expected_mr1_run_id=mr1.run_id,
    )
    protocol = frozen_f2b_v3_protocol()
    results = build_f2b_v3_results(dataset=dataset, mr1=mr1, f2a=f2a, protocol=protocol)
    v2_projection: Mapping[str, Any] | None = None
    if f2b_v2_run_path is not None:
        from market_regime_alpha.research.mr2b_f2b_v2_reader import load_verified_f2b_v2_run

        verified_v2 = load_verified_f2b_v2_run(
            f2b_v2_run_path, dataset=dataset, mr1=mr1, f2a=f2a
        )
        v2_projection = f2b_v2_semantic_projection(
            primary_assessment=verified_v2.primary_assessment,
            multiple_testing=json.loads(
                (verified_v2.root / "multiple_testing_disclosure.json").read_text(encoding="utf-8")
            ),
            competing_event_status=verified_v2.competing_event_status,
        )
    identity = build_f2b_v3_run_identity(
        dataset_root=dataset.root, mr1_root=mr1.root, f2a_root=f2a.root,
        dataset_id=dataset.dataset_id, mr1_run_id=mr1.run_id, f2a_run_id=f2a.run_id,
        protocol=protocol, runner_path=runner_path,
    )
    final = publish_f2b_v3_artifact(
        output_root=output_root,
        identity=identity,
        results=results,
        v2_semantic_projection=v2_projection,
    )
    from market_regime_alpha.research.mr2b_f2b_v3_reader import load_verified_f2b_v3_run

    load_verified_f2b_v3_run(final, dataset=dataset, mr1=mr1, f2a=f2a)
    return final


def _row_counts(results: F2BResultsV3) -> dict[str, int]:
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


def _competing_status(results: F2BResultsV3) -> dict[str, Any]:
    coverage = asdict(results.competing_events.coverage)
    return {
        "status": results.competing_events.status,
        "target_contract_id": results.competing_events.target_contract_id,
        **coverage,
        "interpretation": results.competing_events.interpretation,
        "changes_primary_assessment": False,
    }


def _write_report(path: Path, run_id: str, results: F2BResultsV3) -> None:
    assessment = results.primary_assessment_payload
    lines = [
        "# MR-2B F2B v3 Post-Merge Hardening", "", "## Facts", "",
        f"- Run ID: `{run_id}`", f"- Statistics executed: `{results.statistics_executed}`",
        f"- Primary assessment: `{assessment['assessment']}`",
        f"- Insufficiency reasons: `{assessment['insufficiency_reasons']}`", "",
        "## Authority", "", "- EXPLORATORY only", "- NO FORMAL OOS ALPHA",
        "- NO MODEL WINNER", "- NO PRODUCTION MARKET REGIME GATE", "",
        "## Limitations", "", *(f"- `{item}`" for item in F2B_V3_LIMITATIONS),
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
    if files != MR2B_F2B_V3_RUN_SCHEMA.required_files:
        raise ValueError("F2B v3 exact file set is invalid")


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
