"""Immutable publisher for PIT Candidate replication success v2 evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
from statistics import mean, median
import subprocess
from typing import Any, Mapping

import pandas as pd

from market_regime_alpha.research.mr1_research_runner import mr1_cost_scenarios
from market_regime_alpha.research.pit_replication_success_v2 import (
    PITReplicationSuccessInputs,
    PITReplicationSuccessResults,
    assessment_payload,
)
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    PITCandidateReplicationProtocolV2,
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
PIT_SUCCESS_V2_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "status",
        "data_eligibility",
        "authority",
        "required_artifacts",
        "run_identity",
        "protocol_id",
        "provider",
        "partition_id",
        "row_counts",
    }
)
PIT_SUCCESS_V2_INPUT_EVIDENCE_KEYS: tuple[str, ...] = (
    "pit_qualification",
    "amount_unit_contract",
    "universe_snapshots",
    "eligibility_snapshots",
    "orderability_snapshots",
    "candidate_populations",
    "candidate_feature_evidence",
    "evaluation_marks",
    "path_diagnostics",
)


@dataclass(frozen=True, slots=True)
class PITReplicationSuccessIdentityV2:
    protocol_id: str
    provider_artifact_id: str
    provider_source_hashes: tuple[str, ...]
    provider_source_content_hash: str
    partition_hash: str
    model_spec_hash: str
    cost_model_hash: str
    input_evidence_hashes: Mapping[str, str]
    git_commit_sha: str
    implementation_module_hashes: Mapping[str, str]
    test_only: bool

    def __post_init__(self) -> None:
        hashes = (
            self.provider_source_hashes
            + (
                self.provider_source_content_hash,
                self.partition_hash,
                self.cost_model_hash,
            )
        )
        if any(not value.startswith("sha256:") for value in hashes):
            raise ValueError("PIT success v2 content identity is invalid")
        if (
            len(self.model_spec_hash) != 64
            or any(character not in "0123456789abcdef" for character in self.model_spec_hash)
        ):
            raise ValueError("PIT success v2 model specification hash is invalid")
        if (
            len(self.git_commit_sha) != 40
            or any(character not in "0123456789abcdef" for character in self.git_commit_sha)
        ):
            raise ValueError("PIT success v2 Git revision is invalid")
        if set(self.implementation_module_hashes) != set(PIT_SUCCESS_V2_IMPLEMENTATION_MODULES):
            raise ValueError("PIT success v2 implementation module set mismatch")
        if set(self.input_evidence_hashes) != set(PIT_SUCCESS_V2_INPUT_EVIDENCE_KEYS):
            raise ValueError("PIT success v2 input evidence set mismatch")
        if any(not value.startswith("sha256:") for value in self.input_evidence_hashes.values()):
            raise ValueError("PIT success v2 input evidence hash is invalid")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["provider_source_hashes"] = list(self.provider_source_hashes)
        payload["input_evidence_hashes"] = dict(sorted(self.input_evidence_hashes.items()))
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
        input_hashes = values["input_evidence_hashes"]
        if not isinstance(input_hashes, Mapping):
            raise ValueError("PIT success v2 input evidence hashes are invalid")
        values["input_evidence_hashes"] = dict(input_hashes)
        hashes = values["implementation_module_hashes"]
        if not isinstance(hashes, Mapping):
            raise ValueError("PIT success v2 implementation hashes are invalid")
        values["implementation_module_hashes"] = dict(hashes)
        return cls(**values)


def build_success_identity(results: PITReplicationSuccessResults) -> PITReplicationSuccessIdentityV2:
    return build_success_identity_from_inputs(results.inputs, protocol=results.protocol)


def build_success_identity_from_inputs(
    inputs: PITReplicationSuccessInputs,
    *,
    protocol: PITCandidateReplicationProtocolV2,
) -> PITReplicationSuccessIdentityV2:
    module_root = Path(__file__).resolve().parent
    cost_payload = _cost_payload_for_protocol(protocol)
    return PITReplicationSuccessIdentityV2(
        protocol.protocol_id,
        inputs.provider_artifact_id,
        inputs.provider_source_hashes,
        inputs.provider_source_content_hash,
        inputs.partition_seal.partition_content_hash,
        protocol.ranking_model_spec_hash,
        canonical_identity_hash(cost_payload),
        build_input_evidence_hashes(inputs),
        _revision(),
        {name: _hash(module_root / name) for name in PIT_SUCCESS_V2_IMPLEMENTATION_MODULES},
        inputs.test_only,
    )


def build_input_evidence_hashes(
    inputs: PITReplicationSuccessInputs,
) -> dict[str, str]:
    payloads: dict[str, object] = {
        "pit_qualification": dict(inputs.pit_qualification),
        "amount_unit_contract": dict(inputs.amount_unit_contract),
        "universe_snapshots": list(inputs.universe_rows),
        "eligibility_snapshots": list(inputs.eligibility_rows),
        "orderability_snapshots": list(inputs.orderability_rows),
        "candidate_populations": list(inputs.population_rows),
        "candidate_feature_evidence": list(inputs.feature_rows),
        "evaluation_marks": list(inputs.evaluation_mark_rows),
        "path_diagnostics": list(inputs.path_rows),
    }
    return {
        key: canonical_identity_hash(_canonical_value(payloads[key]))
        for key in PIT_SUCCESS_V2_INPUT_EVIDENCE_KEYS
    }


def success_reader_implementation_identity() -> str:
    module_root = Path(__file__).resolve().parent
    return canonical_identity_hash(
        {
            name: _hash(module_root / name)
            for name in PIT_SUCCESS_V2_IMPLEMENTATION_MODULES
        }
    )


def publish_pit_replication_success_v2(
    *, output_root: Path, results: PITReplicationSuccessResults
) -> Path:
    identity = build_success_identity(results)
    run_id = identity.run_id()
    receipt = results.inputs.partition_open_receipt
    seal = results.inputs.partition_seal
    if (
        receipt.run_id != run_id
        or receipt.partition_id != seal.partition_id
        or receipt.partition_hash != seal.partition_content_hash
        or receipt.reader_implementation_identity != success_reader_implementation_identity()
        or receipt.opened_at < seal.sealed_at
    ):
        raise ValueError("PIT success v2 publisher requires a valid first-open receipt")
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
        _json(
            stage / "source_artifacts.json",
            {
                "provider_artifact_id": results.inputs.provider_artifact_id,
                "source_hashes": list(results.inputs.provider_source_hashes),
                "source_content_hash": results.inputs.provider_source_content_hash,
            },
        )
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
    daily_rows = tuple(
        sorted(results.daily_metric_rows, key=lambda row: str(row["decision_date"]))
    )
    values = [float(row["net_lift_vs_multiseed_median"]) for row in daily_rows]
    split = len(values) // 2
    population_sizes = [int(row["population_size"]) for row in daily_rows]
    population_median = median(population_sizes)
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
        "monthly_slices": _temporal_slices(daily_rows, period="month"),
        "quarterly_slices": _temporal_slices(daily_rows, period="quarter"),
        "population_size_slices": _population_slices(
            daily_rows,
            threshold=population_median,
        ),
        "liquidity_slices": _liquidity_slices(results),
        "feature_completeness": _feature_completeness(results),
        "turnover": _turnover(results),
    }


def _temporal_slices(
    rows: tuple[Mapping[str, Any], ...],
    *,
    period: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        decision_date = str(row["decision_date"])
        key = (
            decision_date[:7]
            if period == "month"
            else f"{decision_date[:4]}-Q{(int(decision_date[5:7]) - 1) // 3 + 1}"
        )
        grouped.setdefault(key, []).append(float(row["net_lift_vs_multiseed_median"]))
    return [
        {
            "period": key,
            "date_count": len(slice_values),
            "mean_net_lift": mean(slice_values),
            "status": (
                "SUFFICIENT_FOR_DESCRIPTION"
                if len(slice_values) >= 5
                else "INSUFFICIENT_SLICE_COUNT"
            ),
        }
        for key, slice_values in sorted(grouped.items())
    ]


def _population_slices(
    rows: tuple[Mapping[str, Any], ...],
    *,
    threshold: float,
) -> dict[str, Any]:
    grouped = {
        "AT_OR_BELOW_MEDIAN": [
            float(row["net_lift_vs_multiseed_median"])
            for row in rows
            if int(row["population_size"]) <= threshold
        ],
        "ABOVE_MEDIAN": [
            float(row["net_lift_vs_multiseed_median"])
            for row in rows
            if int(row["population_size"]) > threshold
        ],
    }
    return {
        "median_population_size": threshold,
        "slices": [
            {
                "label": label,
                "date_count": len(slice_values),
                "mean_net_lift": mean(slice_values) if slice_values else None,
            }
            for label, slice_values in grouped.items()
        ],
    }


def _liquidity_slices(results: PITReplicationSuccessResults) -> dict[str, Any]:
    field = "liquidity_amount"
    if not results.inputs.population_rows or any(
        not isinstance(row.get(field), (int, float))
        for row in results.inputs.population_rows
    ):
        return {
            "status": "UNAVAILABLE",
            "reason": "CANDIDATE_LIQUIDITY_EVIDENCE_NOT_PERSISTED",
            "slices": [],
        }
    values_by_date: dict[str, list[float]] = {}
    for row in results.inputs.population_rows:
        values_by_date.setdefault(str(row["decision_date"]), []).append(float(row[field]))
    date_liquidity = {
        decision_date: median(values)
        for decision_date, values in values_by_date.items()
    }
    threshold = median(date_liquidity.values())
    effect_by_date = {
        str(row["decision_date"]): float(row["net_lift_vs_multiseed_median"])
        for row in results.daily_metric_rows
    }
    groups = {
        "AT_OR_BELOW_MEDIAN": [
            effect_by_date[key]
            for key, value in date_liquidity.items()
            if value <= threshold and key in effect_by_date
        ],
        "ABOVE_MEDIAN": [
            effect_by_date[key]
            for key, value in date_liquidity.items()
            if value > threshold and key in effect_by_date
        ],
    }
    return {
        "status": "AVAILABLE_DESCRIPTIVE_ONLY",
        "median_daily_candidate_liquidity": threshold,
        "slices": [
            {
                "label": label,
                "date_count": len(slice_values),
                "mean_net_lift": mean(slice_values) if slice_values else None,
            }
            for label, slice_values in groups.items()
        ],
    }


def _feature_completeness(results: PITReplicationSuccessResults) -> dict[str, Any]:
    totals: dict[str, int] = {}
    available: dict[str, int] = {}
    for row in results.inputs.feature_rows:
        decision_date = str(row["decision_date"])
        totals[decision_date] = totals.get(decision_date, 0) + 1
        if row.get("feature_status") == "AVAILABLE":
            available[decision_date] = available.get(decision_date, 0) + 1
    by_date = {
        key: available.get(key, 0) / value
        for key, value in sorted(totals.items())
    }
    total = sum(totals.values())
    return {
        "overall_ratio": sum(available.values()) / total,
        "by_date": by_date,
    }


def _turnover(results: PITReplicationSuccessResults) -> dict[str, Any]:
    top_by_date: dict[str, set[str]] = {}
    for row in results.ranking_rows:
        rank = row.get("rank")
        if row.get("eligible_for_ranking") is True and isinstance(rank, int) and rank <= results.protocol.top_k:
            top_by_date.setdefault(str(row["decision_date"]), set()).add(str(row["symbol"]))
    previous: set[str] | None = None
    by_date: dict[str, float | None] = {}
    observed: list[float] = []
    for decision_date, symbols in sorted(top_by_date.items()):
        if previous is None:
            by_date[decision_date] = None
        else:
            value = 1.0 - len(previous & symbols) / results.protocol.top_k
            by_date[decision_date] = value
            observed.append(value)
        previous = symbols
    return {
        "definition_id": "top5-one-minus-overlap-v1",
        "mean": mean(observed) if observed else None,
        "by_date": by_date,
    }


def _cost_payload(results: PITReplicationSuccessResults) -> dict[str, Any]:
    return _cost_payload_for_protocol(results.protocol)


def _cost_payload_for_protocol(
    protocol: PITCandidateReplicationProtocolV2,
) -> dict[str, Any]:
    costs = mr1_cost_scenarios()
    return {
        scenario: asdict(costs[scenario])
        for scenario in protocol.cost_robustness_scenarios
    }


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if hasattr(value, "tolist"):
        return _canonical_value(value.tolist())
    return value


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
