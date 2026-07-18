"""Application facade for PIT replication v2 blocked/invalid/success outcomes."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.research.pit_replication_preflight import (
    PITReplicationPreflight,
    PITReplicationPreflightStatus,
)
from market_regime_alpha.research.pit_replication_success_v2 import (
    PITReplicationSuccessInputs,
    build_pit_replication_success_results,
)
from market_regime_alpha.research.pit_replication_success_v2_artifacts import (
    build_success_identity,
    publish_pit_replication_success_v2,
)
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    frozen_pit_replication_success_v2_protocol,
)
from market_regime_alpha.research.pit_replication_success_v2_reader import (
    load_verified_pit_replication_success_v2,
)
from market_regime_alpha.research.pit_partition_v2 import (
    PartitionOpenReceipt,
    ValidationPartitionSpecification,
    seal_validation_partition,
)
from market_regime_alpha.research.pit_replication_v2_artifacts import publish_pit_replication_v2
from market_regime_alpha.research.pit_replication_v2_protocol import frozen_pit_replication_v2_protocol
from market_regime_alpha.research.xuntou_pit_v4_preflight import (
    XuntouPITV4PreflightStatus,
    preflight_xuntou_pit_v4,
)


def run_pit_replication_success_v2(
    *,
    xuntou_bundle: Path | None,
    output_root: Path,
    success_inputs: PITReplicationSuccessInputs | None = None,
    partition_id: str | None = None,
    partition_start: date | None = None,
    partition_end: date | None = None,
) -> Path:
    if success_inputs is not None and success_inputs.test_only:
        protocol = frozen_pit_replication_success_v2_protocol(test_only=True)
        provisional = build_pit_replication_success_results(success_inputs, protocol=protocol)
        run_id = build_success_identity(provisional).run_id()
        opened = replace(success_inputs.partition_open_receipt, run_id=run_id)
        finalized_inputs = replace(success_inputs, partition_open_receipt=opened)
        results = build_pit_replication_success_results(finalized_inputs, protocol=protocol)
        final = publish_pit_replication_success_v2(output_root=output_root, results=results)
        load_verified_pit_replication_success_v2(final)
        return final
    preflight = preflight_xuntou_pit_v4(xuntou_bundle)
    if preflight.status is XuntouPITV4PreflightStatus.AVAILABLE:
        if success_inputs is None:
            if partition_id is None or partition_start is None or partition_end is None:
                raise ValueError("PARTITION_SPEC_REQUIRED")
            assert xuntou_bundle is not None
            success_inputs = _materialize_available_inputs(
                xuntou_bundle,
                preflight=preflight,
                output_root=output_root,
                partition_id=partition_id,
                partition_start=partition_start,
                partition_end=partition_end,
            )
        if success_inputs.test_only:
            raise ValueError("formal V4 preflight cannot consume test-only inputs")
        protocol = frozen_pit_replication_success_v2_protocol()
        provisional = build_pit_replication_success_results(success_inputs, protocol=protocol)
        run_id = build_success_identity(provisional).run_id()
        finalized_inputs = replace(
            success_inputs,
            partition_open_receipt=replace(success_inputs.partition_open_receipt, run_id=run_id),
        )
        results = build_pit_replication_success_results(finalized_inputs, protocol=protocol)
        final = publish_pit_replication_success_v2(output_root=output_root, results=results)
        load_verified_pit_replication_success_v2(final)
        return final
    legacy_status = (
        PITReplicationPreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT
        if preflight.status is XuntouPITV4PreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT
        else PITReplicationPreflightStatus.INVALID_PIT_EVIDENCE
    )
    projected = PITReplicationPreflight(
        schema_version="pit-replication-provider-preflight-v2",
        status=legacy_status,
        provider="XUNTOU",
        required_bundle_schema=preflight.required_bundle_schema,
        required_product="XTQUANT",
        expected_source_files=("xuntou_pit_validation_bundle_v4.json",),
        bundle_content_hash=preflight.bundle_content_hash,
        provider_artifact_id=None,
        provider_dataset_id=None,
        membership_source=None,
        reasons=preflight.reasons,
        tencent_fallback_allowed=False,
        prepared=None,
    )
    final = publish_pit_replication_v2(
        output_root=output_root,
        protocol=frozen_pit_replication_v2_protocol(),
        preflight=projected,
    )
    return final


def _materialize_available_inputs(
    bundle: Path,
    *,
    preflight: Any,
    output_root: Path,
    partition_id: str,
    partition_start: date,
    partition_end: date,
) -> PITReplicationSuccessInputs:
    root = json.loads(bundle.read_text(encoding="utf-8"))
    payload = _mapping(root.get("replication_payload"), "replication_payload")
    protocol = frozen_pit_replication_success_v2_protocol()
    now = datetime.now(timezone.utc)
    specification = ValidationPartitionSpecification(
        "pit-validation-partition-specification-v1",
        partition_id,
        "XUNTOU",
        "EXPLICIT_DATE_RANGE_V1",
        partition_start,
        partition_end,
        protocol.minimum_decision_dates,
        "NO_RESULT_DRIVEN_EXCLUSIONS_V1",
        protocol.protocol_id,
        protocol.ranking_model_spec_hash,
        now,
        "SPECIFIED_NOT_OPENED",
    )
    included = tuple(date.fromisoformat(str(value)) for value in _sequence(payload, "included_sessions"))
    excluded = tuple(
        (date.fromisoformat(str(value[0])), str(value[1]))
        for value in _sequence(payload, "excluded_sessions")
    )
    development = tuple(
        date.fromisoformat(str(value)) for value in _sequence(payload, "development_sessions")
    )
    content_hash = preflight.bundle_content_hash
    if not isinstance(content_hash, str):
        raise ValueError("qualified v4 bundle content hash is missing")
    provider_artifact_id = str(payload.get("provider_artifact_id", ""))
    if not provider_artifact_id:
        raise ValueError("qualified provider Artifact identity is missing")
    seal = seal_validation_partition(
        specification,
        included_sessions=included,
        excluded_sessions=excluded,
        development_sessions=development,
        calendar_identity=_text(payload, "calendar_identity"),
        provider_source_hashes=(content_hash,),
        universe_identity=_text(payload, "universe_identity"),
        sealed_at=now,
        existing_partition_ids=_existing_partition_ids(output_root),
    )
    receipt = PartitionOpenReceipt(
        "pit-validation-partition-open-receipt-v1",
        partition_id,
        now,
        "PENDING",
        "pit-replication-success-v2-semantic-reader-v1",
        seal.partition_content_hash,
    )
    qualification = preflight.qualification
    if qualification is None or not qualification.pit_correct_for_scope:
        raise ValueError("qualified v4 evidence receipt is missing")
    return PITReplicationSuccessInputs(
        provider_artifact_id=provider_artifact_id,
        provider_source_hashes=(content_hash,),
        pit_qualification=qualification.to_canonical_dict(),
        partition_specification=specification,
        partition_seal=seal,
        partition_open_receipt=receipt,
        amount_unit_contract=_mapping(payload.get("amount_unit_contract"), "amount_unit_contract"),
        universe_rows=_row_sequence(payload, "universe_rows"),
        eligibility_rows=_row_sequence(payload, "eligibility_rows"),
        orderability_rows=_row_sequence(payload, "orderability_rows"),
        population_rows=_row_sequence(payload, "population_rows"),
        feature_rows=_row_sequence(payload, "feature_rows"),
        evaluation_mark_rows=_row_sequence(payload, "evaluation_mark_rows"),
        path_rows=_row_sequence(payload, "path_rows", required=False),
        test_only=False,
    )


def _existing_partition_ids(output_root: Path) -> frozenset[str]:
    values: set[str] = set()
    if not output_root.exists():
        return frozenset()
    for manifest in output_root.glob("*/manifest.json"):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            partition = payload.get("partition_id")
            if isinstance(partition, str):
                values.add(partition)
        except (OSError, json.JSONDecodeError):
            continue
    return frozenset(values)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"qualified v4 {field} must be an object")
    return value


def _sequence(payload: Mapping[str, Any], field: str) -> tuple[Any, ...]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ValueError(f"qualified v4 {field} must be an array")
    return tuple(value)


def _row_sequence(
    payload: Mapping[str, Any], field: str, *, required: bool = True
) -> tuple[Mapping[str, Any], ...]:
    value = payload.get(field)
    if value is None and not required:
        return ()
    rows = _sequence(payload, field)
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError(f"qualified v4 {field} contains a non-object row")
    return tuple(row for row in rows if isinstance(row, Mapping))


def _text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"qualified v4 {field} must be non-empty")
    return value
