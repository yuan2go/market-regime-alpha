"""Semantic Reader for PIT Candidate replication success v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from pandas.testing import assert_frame_equal

from market_regime_alpha.research.pit_partition_v2 import (
    PartitionOpenReceipt,
    PartitionSealArtifact,
    ValidationPartitionSpecification,
)
from market_regime_alpha.research.pit_replication_success_v2 import (
    PITReplicationSuccessInputs,
    assessment_payload,
    build_pit_replication_success_results,
)
from market_regime_alpha.research.pit_replication_success_v2_artifacts import (
    PIT_SUCCESS_V2_IMPLEMENTATION_MODULES,
    PIT_SUCCESS_V2_LIMITATIONS,
    PITReplicationSuccessIdentityV2,
    _chronological,
    _data_quality,
    _row_counts,
)
from market_regime_alpha.research.pit_replication_success_v2_features import (
    feature_set_payload,
    model_spec_payload,
)
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    PITCandidateReplicationProtocolV2,
)
from market_regime_alpha.research.mr1_research_runner import mr1_cost_scenarios
from market_regime_alpha.research.prr_artifact_schemas import (
    PIT_REPLICATION_SUCCESS_V2_SCHEMA,
    canonical_identity_hash,
)


@dataclass(frozen=True, slots=True)
class VerifiedPITReplicationSuccessV2:
    root: Path
    run_id: str
    status: str
    authority: str
    checksums_hash: str
    decision_date_count: int
    path_status: str
    test_only: bool


def load_verified_pit_replication_success_v2(
    path: Path,
) -> VerifiedPITReplicationSuccessV2:
    root = path.resolve()
    _verify_files(root)
    manifest = _object(root / "manifest.json")
    if manifest.get("schema_version") != PIT_REPLICATION_SUCCESS_V2_SCHEMA.schema_version:
        raise ValueError("PIT success v2 schema mismatch")
    if manifest.get("required_artifacts") != sorted(PIT_REPLICATION_SUCCESS_V2_SCHEMA.required_files):
        raise ValueError("PIT success v2 required file set mismatch")
    identity = PITReplicationSuccessIdentityV2.from_canonical_dict(_mapping(manifest.get("run_identity")))
    run_id = str(manifest.get("run_id", ""))
    if identity.run_id() != run_id or root.name != run_id:
        raise ValueError("PIT success v2 Run ID mismatch")
    module_root = Path(__file__).resolve().parent
    expected_hashes = {name: _hash(module_root / name) for name in PIT_SUCCESS_V2_IMPLEMENTATION_MODULES}
    if dict(identity.implementation_module_hashes) != expected_hashes:
        raise ValueError("PIT success v2 implementation identity is stale")
    protocol_payload = _object(root / "protocol.json")
    protocol_id = protocol_payload.pop("protocol_id", None)
    protocol_payload["path_target_ids"] = tuple(protocol_payload["path_target_ids"])
    protocol_payload["matched_k_seed_set"] = tuple(protocol_payload["matched_k_seed_set"])
    protocol_payload["cost_robustness_scenarios"] = tuple(
        protocol_payload["cost_robustness_scenarios"]
    )
    protocol = PITCandidateReplicationProtocolV2(**protocol_payload)
    if protocol_id != protocol.protocol_id or identity.protocol_id != protocol.protocol_id:
        raise ValueError("PIT success v2 Protocol identity mismatch")
    specification = _specification(_object(root / "partition_specification.json"))
    seal = _seal(_object(root / "partition_seal.json"))
    receipt = _receipt(_object(root / "partition_open_receipt.json"))
    if receipt.run_id != run_id or seal.partition_content_hash != receipt.partition_hash:
        raise ValueError("PIT success v2 partition open receipt mismatch")
    if manifest.get("partition_id") != specification.partition_id:
        raise ValueError("PIT success v2 partition identity mismatch")
    _verify_seal(specification, seal)
    source = _object(root / "source_artifacts.json")
    qualification = _object(root / "pit_qualification.json")
    amount = _object(root / "amount_unit_contract.json")
    if _object(root / "provider_selection.json") != {
        "provider": "XUNTOU",
        "tencent_fallback_used": False,
    }:
        raise ValueError("PIT success v2 provider selection mismatch")
    if not _amount_contract_qualified(amount):
        raise ValueError("PIT success v2 amount unit contract is not qualified")
    cost_model = _object(root / "cost_model.json")
    expected_cost = {
        scenario: asdict(mr1_cost_scenarios()[scenario])
        for scenario in protocol.cost_robustness_scenarios
    }
    if cost_model != {
        "cost_model_id": protocol.cost_model_id,
        "primary_cost_scenario": protocol.cost_scenario,
        "robustness_scenarios": list(protocol.cost_robustness_scenarios),
        "configs": expected_cost,
        "cost_model_hash": canonical_identity_hash(expected_cost),
    }:
        raise ValueError("PIT success v2 cost model mismatch")
    if identity.cost_model_hash != canonical_identity_hash(expected_cost):
        raise ValueError("PIT success v2 cost identity mismatch")
    inputs = PITReplicationSuccessInputs(
        provider_artifact_id=str(source["provider_artifact_id"]),
        provider_source_hashes=tuple(str(value) for value in source["source_hashes"]),
        pit_qualification=qualification,
        partition_specification=specification,
        partition_seal=seal,
        partition_open_receipt=receipt,
        amount_unit_contract=amount,
        universe_rows=_rows(root / "universe_snapshots.parquet"),
        eligibility_rows=_rows(root / "eligibility_snapshots.parquet"),
        orderability_rows=_rows(root / "orderability_snapshots.parquet"),
        population_rows=_rows(root / "candidate_populations.parquet"),
        feature_rows=_rows(root / "candidate_feature_evidence.parquet"),
        evaluation_mark_rows=_rows(root / "evaluation_marks.parquet"),
        path_rows=_rows(root / "path_diagnostics.parquet"),
        test_only=identity.test_only,
    )
    if not identity.test_only and qualification.get("pit_correct_for_scope") is not True:
        raise ValueError("formal PIT success requires qualified evidence")
    expected = build_pit_replication_success_results(inputs, protocol=protocol)
    _assert_rows(root / "candidate_model_scores.parquet", expected.model_score_rows, ("decision_date", "symbol"))
    _assert_rows(root / "candidate_rankings.parquet", expected.ranking_rows, ("decision_date", "symbol"))
    _assert_rows(root / "matched_k_selections.parquet", expected.selection_rows, ("decision_date", "seed", "slot_index"))
    _assert_rows(
        root / "matched_k_returns.parquet",
        expected.matched_k_return_rows,
        ("decision_date", "cost_scenario", "seed"),
    )
    _assert_rows(root / "daily_replication_metrics.parquet", expected.daily_metric_rows, ("decision_date",))
    if _object(root / "feature_set.json") != feature_set_payload():
        raise ValueError("PIT success v2 Feature set mismatch")
    if _object(root / "model_spec.json") != model_spec_payload(protocol):
        raise ValueError("PIT success v2 model specification mismatch")
    if _object(root / "primary_assessment.json") != assessment_payload(expected.assessment):
        raise ValueError("PIT success v2 assessment is not reconstructible")
    if _object(root / "chronological_replication_summary.json") != _chronological(expected):
        raise ValueError("PIT success v2 chronological summary mismatch")
    if _object(root / "data_quality.json") != _data_quality(expected):
        raise ValueError("PIT success v2 data quality mismatch")
    if manifest.get("row_counts") != _row_counts(expected):
        raise ValueError("PIT success v2 row counts mismatch")
    if _array(root / "limitations.json") != list(PIT_SUCCESS_V2_LIMITATIONS):
        raise ValueError("PIT success v2 limitations mismatch")
    if identity.provider_artifact_id != inputs.provider_artifact_id:
        raise ValueError("PIT success v2 provider identity mismatch")
    if identity.partition_hash != seal.partition_content_hash:
        raise ValueError("PIT success v2 partition identity mismatch")
    return VerifiedPITReplicationSuccessV2(
        root=root,
        run_id=run_id,
        status=expected.assessment.status,
        authority=protocol.authority_ceiling,
        checksums_hash=_hash(root / "SHA256SUMS.json"),
        decision_date_count=len(expected.daily_metric_rows),
        path_status=expected.path_status,
        test_only=identity.test_only,
    )


def _amount_contract_qualified(payload: Mapping[str, Any]) -> bool:
    return payload == {
        "currency": "CNY",
        "unit": "YUAN",
        "scale": 1.0,
        "aggregation": "SUM_NATIVE_PERIOD_AMOUNT",
        "adjustment_basis": "NONE",
        "provider_field": "amount",
        "evidence_source": payload.get("evidence_source"),
    } and isinstance(payload.get("evidence_source"), str) and bool(payload["evidence_source"])


def _verify_seal(specification: ValidationPartitionSpecification, seal: PartitionSealArtifact) -> None:
    payload = {
        "schema_version": "pit-validation-partition-seal-v1",
        "partition_id": specification.partition_id,
        "specification_hash": specification.specification_hash,
        "included_sessions": [value.isoformat() for value in seal.included_sessions],
        "excluded_sessions": [[value.isoformat(), reason] for value, reason in seal.excluded_sessions],
        "calendar_identity": seal.calendar_identity,
        "provider_source_hashes": list(seal.provider_source_hashes),
        "universe_identity": seal.universe_identity,
        "protocol_id": seal.protocol_id,
        "model_spec_hash": seal.model_spec_hash,
    }
    if seal.specification_hash != specification.specification_hash or seal.partition_content_hash != canonical_identity_hash(payload):
        raise ValueError("PIT success v2 partition seal is not reconstructible")


def _specification(payload: Mapping[str, Any]) -> ValidationPartitionSpecification:
    values = dict(payload)
    values["requested_start_date"] = date.fromisoformat(values["requested_start_date"])
    values["requested_end_date"] = date.fromisoformat(values["requested_end_date"])
    values["created_at"] = datetime.fromisoformat(values["created_at"])
    return ValidationPartitionSpecification(**values)


def _seal(payload: Mapping[str, Any]) -> PartitionSealArtifact:
    values = dict(payload)
    values["included_sessions"] = tuple(date.fromisoformat(value) for value in values["included_sessions"])
    values["excluded_sessions"] = tuple((date.fromisoformat(value), reason) for value, reason in values["excluded_sessions"])
    values["provider_source_hashes"] = tuple(values["provider_source_hashes"])
    values["sealed_at"] = datetime.fromisoformat(values["sealed_at"])
    return PartitionSealArtifact(**values)


def _receipt(payload: Mapping[str, Any]) -> PartitionOpenReceipt:
    values = dict(payload)
    values["opened_at"] = datetime.fromisoformat(values["opened_at"])
    return PartitionOpenReceipt(**values)


def _assert_rows(path: Path, expected_rows: Any, keys: tuple[str, ...]) -> None:
    actual = pd.read_parquet(path)
    expected = pd.DataFrame.from_records(expected_rows)
    columns = sorted(expected.columns)
    if set(actual.columns) != set(columns):
        raise ValueError(f"PIT success v2 columns mismatch: {path.name}")
    try:
        assert_frame_equal(
            actual.sort_values(list(keys)).reset_index(drop=True)[columns],
            expected.sort_values(list(keys)).reset_index(drop=True)[columns],
            check_dtype=False,
            check_exact=False,
            rtol=0,
            atol=1e-15,
        )
    except AssertionError as exc:
        raise ValueError(f"PIT success v2 table is not reconstructible: {path.name}") from exc


def _rows(path: Path) -> tuple[dict[str, Any], ...]:
    return tuple(pd.read_parquet(path).to_dict(orient="records"))


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("PIT success v2 Artifact is missing")
    files = frozenset(item.name for item in root.iterdir() if item.is_file())
    if files != PIT_REPLICATION_SUCCESS_V2_SCHEMA.required_files:
        raise ValueError("PIT success v2 exact file set mismatch")
    checksums = _object(root / "SHA256SUMS.json")
    if set(checksums) != set(files - {"SHA256SUMS.json"}):
        raise ValueError("PIT success v2 checksum coverage mismatch")
    for name, digest in checksums.items():
        if _hash(root / name) != digest:
            raise ValueError(f"PIT success v2 checksum mismatch: {name}")


def _object(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _array(path: Path) -> list[Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path.name} must contain an array")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("PIT success v2 identity must be an object")
    return value


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
