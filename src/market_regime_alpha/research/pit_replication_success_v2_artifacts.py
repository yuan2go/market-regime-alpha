"""Immutable publisher for PIT Candidate replication success v2 evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

import pandas as pd

from market_regime_alpha.research.mr1_research_runner import mr1_cost_scenarios
from market_regime_alpha.research.pit_replication_success_v2 import (
    PITReplicationSuccessResults,
    assessment_payload,
)
from market_regime_alpha.research.pit_replication_success_v2_features import (
    feature_set_payload,
    model_spec_payload,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    PIT_REPLICATION_SUCCESS_V2_SCHEMA,
    canonical_identity_hash,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PIT_SUCCESS_V2_IMPLEMENTATION_MODULES: tuple[str, ...] = (
    "pit_replication_success_v2_protocol.py",
    "pit_partition_v2.py",
    "pit_replication_success_v2_features.py",
    "pit_replication_success_v2_statistics.py",
    "pit_replication_success_v2.py",
    "pit_replication_success_v2_artifacts.py",
    "pit_replication_success_v2_reader.py",
    "pit_replication_success_v2_runner.py",
)
PIT_SUCCESS_V2_LIMITATIONS = (
    "CONTROLLED_REPLICATION_INPUT_NOT_PRODUCTION_DATA",
    "NO_FORMAL_OOS_ALPHA",
    "NO_MODEL_WINNER_SELECTION",
    "REFERENCE_MARK_NOT_FILL_PROOF",
    "FEE_ASSUMPTIONS_REQUIRE_CURRENT_VERIFICATION",
    "NO_ENTRY_PORTFOLIO_OR_EXECUTION_AUTHORITY",
)


@dataclass(frozen=True, slots=True)
class PITReplicationSuccessIdentityV2:
    protocol_id: str
    provider_artifact_id: str
    provider_source_hashes: tuple[str, ...]
    partition_hash: str
    model_spec_hash: str
    cost_model_hash: str
    git_commit_sha: str
    implementation_module_hashes: Mapping[str, str]
    test_only: bool

    def __post_init__(self) -> None:
        if set(self.implementation_module_hashes) != set(PIT_SUCCESS_V2_IMPLEMENTATION_MODULES):
            raise ValueError("PIT success v2 implementation module set mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["provider_source_hashes"] = list(self.provider_source_hashes)
        payload["implementation_module_hashes"] = dict(sorted(self.implementation_module_hashes.items()))
        return payload

    def run_id(self) -> str:
        digest = canonical_identity_hash(self.to_canonical_dict()).split(":", 1)[1][:20]
        prefix = "test-only-pit-replication-v2" if self.test_only else "pit-replication-success-v2"
        return f"{prefix}-{digest}"

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PITReplicationSuccessIdentityV2:
        if set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("PIT success v2 identity fields mismatch")
        values = dict(payload)
        values["provider_source_hashes"] = tuple(values["provider_source_hashes"])
        hashes = values["implementation_module_hashes"]
        if not isinstance(hashes, Mapping):
            raise ValueError("PIT success v2 implementation hashes are invalid")
        values["implementation_module_hashes"] = dict(hashes)
        return cls(**values)


def build_success_identity(results: PITReplicationSuccessResults) -> PITReplicationSuccessIdentityV2:
    module_root = Path(__file__).resolve().parent
    cost_payload = _cost_payload(results)
    return PITReplicationSuccessIdentityV2(
        results.protocol.protocol_id,
        results.inputs.provider_artifact_id,
        results.inputs.provider_source_hashes,
        results.inputs.partition_seal.partition_content_hash,
        results.protocol.ranking_model_spec_hash,
        canonical_identity_hash(cost_payload),
        _revision(),
        {name: _hash(module_root / name) for name in PIT_SUCCESS_V2_IMPLEMENTATION_MODULES},
        results.inputs.test_only,
    )


def publish_pit_replication_success_v2(
    *, output_root: Path, results: PITReplicationSuccessResults
) -> Path:
    identity = build_success_identity(results)
    run_id = identity.run_id()
    final = output_root / run_id
    stage = output_root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError("PIT success v2 Artifact is immutable")
    output_root.mkdir(parents=True, exist_ok=True)
    stage.mkdir()
    try:
        manifest = {
            "schema_version": PIT_REPLICATION_SUCCESS_V2_SCHEMA.schema_version,
            "run_id": run_id,
            "status": results.assessment.status,
            "data_eligibility": (
                "TEST_ONLY_NOT_RESEARCH_EVIDENCE" if results.inputs.test_only else "CONTROLLED_REPLICATION_INPUT"
            ),
            "authority": results.protocol.authority_ceiling,
            "required_artifacts": sorted(PIT_REPLICATION_SUCCESS_V2_SCHEMA.required_files),
            "run_identity": identity.to_canonical_dict(),
            "protocol_id": results.protocol.protocol_id,
            "provider": "XUNTOU",
            "partition_id": results.inputs.partition_specification.partition_id,
            "row_counts": _row_counts(results),
        }
        _json(stage / "manifest.json", manifest)
        _json(stage / "protocol.json", {**results.protocol.to_canonical_dict(), "protocol_id": results.protocol.protocol_id})
        _json(stage / "provider_selection.json", {"provider": "XUNTOU", "tencent_fallback_used": False})
        _json(stage / "source_artifacts.json", {"provider_artifact_id": results.inputs.provider_artifact_id, "source_hashes": list(results.inputs.provider_source_hashes)})
        _json(stage / "pit_qualification.json", dict(results.inputs.pit_qualification))
        _json(stage / "partition_specification.json", results.inputs.partition_specification.to_canonical_dict())
        _json(stage / "partition_seal.json", asdict(results.inputs.partition_seal))
        _json(stage / "partition_open_receipt.json", asdict(results.inputs.partition_open_receipt))
        _json(stage / "data_quality.json", _data_quality(results))
        _json(stage / "amount_unit_contract.json", dict(results.inputs.amount_unit_contract))
        cost_payload = _cost_payload(results)
        _json(stage / "cost_model.json", {"cost_model_id": results.protocol.cost_model_id, "primary_cost_scenario": results.protocol.cost_scenario, "robustness_scenarios": list(results.protocol.cost_robustness_scenarios), "configs": cost_payload, "cost_model_hash": canonical_identity_hash(cost_payload)})
        _parquet(stage / "universe_snapshots.parquet", results.inputs.universe_rows)
        _parquet(stage / "eligibility_snapshots.parquet", results.inputs.eligibility_rows)
        _parquet(stage / "orderability_snapshots.parquet", results.inputs.orderability_rows)
        _parquet(stage / "candidate_populations.parquet", results.inputs.population_rows)
        _json(stage / "feature_set.json", feature_set_payload())
        _parquet(stage / "candidate_feature_evidence.parquet", results.inputs.feature_rows)
        _json(stage / "model_spec.json", model_spec_payload(results.protocol))
        _parquet(stage / "candidate_model_scores.parquet", results.model_score_rows)
        _parquet(stage / "candidate_rankings.parquet", results.ranking_rows)
        _parquet(stage / "matched_k_selections.parquet", results.selection_rows)
        _parquet(stage / "matched_k_returns.parquet", results.matched_k_return_rows)
        _parquet(stage / "evaluation_marks.parquet", results.inputs.evaluation_mark_rows)
        _parquet(stage / "daily_replication_metrics.parquet", results.daily_metric_rows)
        _parquet(stage / "path_diagnostics.parquet", results.path_diagnostic_rows, empty=("decision_date", "symbol", "status"))
        _json(stage / "chronological_replication_summary.json", _chronological(results))
        _json(stage / "primary_assessment.json", assessment_payload(results.assessment))
        _json(stage / "limitations.json", list(PIT_SUCCESS_V2_LIMITATIONS))
        (stage / "report.md").write_text(_report(run_id, results), encoding="utf-8")
        _checksums(stage)
        if frozenset(item.name for item in stage.iterdir() if item.is_file()) != PIT_REPLICATION_SUCCESS_V2_SCHEMA.required_files:
            raise ValueError("PIT success v2 exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _row_counts(results: PITReplicationSuccessResults) -> dict[str, int]:
    return {
        "decision_dates": len(results.daily_metric_rows),
        "universe": len(results.inputs.universe_rows),
        "eligibility": len(results.inputs.eligibility_rows),
        "orderability": len(results.inputs.orderability_rows),
        "candidate_populations": len(results.inputs.population_rows),
        "feature_evidence": len(results.inputs.feature_rows),
        "model_scores": len(results.model_score_rows),
        "rankings": len(results.ranking_rows),
        "matched_k_selections": len(results.selection_rows),
        "matched_k_returns": len(results.matched_k_return_rows),
        "daily_metrics": len(results.daily_metric_rows),
        "path_diagnostics": len(results.path_diagnostic_rows),
    }


def _data_quality(results: PITReplicationSuccessResults) -> dict[str, Any]:
    populations: dict[str, int] = {}
    for row in results.inputs.population_rows:
        key = str(row["decision_date"])
        populations[key] = populations.get(key, 0) + 1
    return {
        "schema_version": "pit-replication-data-quality-v2",
        "decision_date_count": len(populations),
        "population_size_by_date": populations,
        "average_population_size": sum(populations.values()) / len(populations),
        "unknown_orderability_count": sum(row.get("orderability_status") == "UNKNOWN" for row in results.inputs.orderability_rows),
        "feature_missing_count": sum(row.get("feature_status") != "AVAILABLE" for row in results.inputs.feature_rows),
    }


def _chronological(results: PITReplicationSuccessResults) -> dict[str, Any]:
    values = [float(row["net_lift_vs_multiseed_median"]) for row in results.daily_metric_rows]
    split = len(values) // 2
    return {
        "schema_version": "pit-chronological-replication-summary-v2",
        "date_count": len(values),
        "overall_effect": results.assessment.observed_effect,
        "first_half_effect": results.assessment.first_half_effect,
        "second_half_effect": results.assessment.second_half_effect,
        "seed_panel_effects": list(results.assessment.seed_panel_effects),
        "cost_robustness_effects": dict(results.assessment.cost_robustness_effects),
        "rolling_window": results.protocol.rolling_window,
        "rolling_positive_window_count": results.assessment.rolling_positive_window_count,
        "rolling_window_count": results.assessment.rolling_window_count,
        "leave_one_out_minimum": results.assessment.leave_one_out_minimum,
        "leave_one_out_maximum": results.assessment.leave_one_out_maximum,
        "largest_absolute_contribution_share": results.assessment.largest_absolute_contribution_share,
        "top_3_absolute_contribution_share": results.assessment.top_3_absolute_contribution_share,
        "path_status": results.path_status,
        "first_half_date_count": split,
        "second_half_date_count": len(values) - split,
    }


def _cost_payload(results: PITReplicationSuccessResults) -> dict[str, Any]:
    costs = mr1_cost_scenarios()
    return {
        scenario: asdict(costs[scenario])
        for scenario in results.protocol.cost_robustness_scenarios
    }


def _report(run_id: str, results: PITReplicationSuccessResults) -> str:
    return (
        "# PIT Candidate Replication Success V2\n\n"
        f"- Run ID: `{run_id}`\n"
        f"- Status: `{results.assessment.status}`\n"
        f"- Authority: `{results.protocol.authority_ceiling}`\n"
        f"- Path diagnostics: `{results.path_status}`\n\n"
        "No Formal OOS Alpha, model winner, production Candidate, or trading authority is established.\n"
    )


def _parquet(path: Path, rows: Any, *, empty: tuple[str, ...] = ()) -> None:
    frame = pd.DataFrame.from_records(rows)
    if frame.empty:
        frame = pd.DataFrame(columns=list(empty))
    frame.to_parquet(path, index=False)


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")


def _checksums(root: Path) -> None:
    _json(root / "SHA256SUMS.json", {item.name: _hash(item) for item in sorted(root.iterdir()) if item.is_file() and item.name != "SHA256SUMS.json"})


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _revision() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True).stdout.strip()
