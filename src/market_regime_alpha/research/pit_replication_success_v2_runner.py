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
    build_success_identity_from_inputs,
    publish_pit_replication_success_v2,
    success_reader_implementation_identity,
)
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    frozen_pit_replication_success_v2_protocol,
)
from market_regime_alpha.research.pit_partition_v2 import (
    PartitionOpenReceipt,
    ValidationPartitionSpecification,
    open_partition,
    open_persisted_partition,
    persist_partition_seal,
    seal_validation_partition,
)
from market_regime_alpha.research.pit_replication_v2_artifacts import publish_pit_replication_v2
from market_regime_alpha.research.pit_replication_v2_protocol import frozen_pit_replication_v2_protocol
from market_regime_alpha.research.pit_replication_v2_reader import (
    load_verified_pit_replication_artifact_v2,
)
from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash
from market_regime_alpha.research.xuntou_pit_v4_evidence import (
    PIT_V4_EVIDENCE_SECTIONS,
)
from market_regime_alpha.research.xuntou_pit_v4_contract import AmountUnitContract
from market_regime_alpha.research.xuntou_pit_v4_preflight import (
    XuntouPITV4Preflight,
    XuntouPITV4PreflightStatus,
    preflight_xuntou_pit_v4,
)


PIT_REPLICATION_INPUT_PROJECTION_V2 = "pit-replication-input-projection-v2"
PIT_REPLICATION_INPUT_PROJECTION_FIELDS = frozenset(
    {
        "schema_version",
        "provider_artifact_id",
        "source_content_hash",
        "raw_source_hashes",
        "evidence_section_hashes",
        "included_sessions",
        "excluded_sessions",
        "development_sessions",
        "calendar_identity",
        "universe_identity",
        "amount_unit_contract",
        "universe_rows",
        "eligibility_rows",
        "orderability_rows",
        "population_rows",
        "feature_rows",
        "evaluation_mark_rows",
        "path_rows",
        "projection_content_hash",
    }
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
        run_id = build_success_identity_from_inputs(success_inputs, protocol=protocol).run_id()
        opened = open_partition(
            success_inputs.partition_seal,
            opened_at=datetime.now(timezone.utc),
            run_id=run_id,
            reader_implementation_identity=success_reader_implementation_identity(),
        )
        finalized_inputs = replace(success_inputs, partition_open_receipt=opened)
        results = build_pit_replication_success_results(finalized_inputs, protocol=protocol)
        final = publish_pit_replication_success_v2(output_root=output_root, results=results)
        load_verified_pit_replication_artifact_v2(final)
        return final
    if success_inputs is not None:
        raise ValueError("formal success inputs must be materialized from qualified Xuntou v4")
    preflight = preflight_xuntou_pit_v4(xuntou_bundle)
    if preflight.status is XuntouPITV4PreflightStatus.AVAILABLE:
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
        protocol = frozen_pit_replication_success_v2_protocol()
        run_id = build_success_identity_from_inputs(success_inputs, protocol=protocol).run_id()
        receipt = open_persisted_partition(
            output_root=output_root,
            seal=success_inputs.partition_seal,
            opened_at=datetime.now(timezone.utc),
            run_id=run_id,
            reader_implementation_identity=success_reader_implementation_identity(),
        )
        finalized_inputs = replace(
            success_inputs,
            partition_open_receipt=receipt,
        )
        results = build_pit_replication_success_results(finalized_inputs, protocol=protocol)
        final = publish_pit_replication_success_v2(output_root=output_root, results=results)
        load_verified_pit_replication_artifact_v2(final)
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
    load_verified_pit_replication_artifact_v2(final)
    return final


def _materialize_available_inputs(
    bundle: Path,
    *,
    preflight: XuntouPITV4Preflight,
    output_root: Path,
    partition_id: str,
    partition_start: date,
    partition_end: date,
) -> PITReplicationSuccessInputs:
    root = json.loads(bundle.read_text(encoding="utf-8"))
    if not isinstance(root, Mapping):
        raise ValueError("qualified v4 bundle root must be an object")
    payload = _validated_replication_payload(root, preflight=preflight)
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
    source_content_hash = preflight.source_content_hash
    if not isinstance(source_content_hash, str):
        raise ValueError("qualified v4 source content hash is missing")
    provider_artifact_id = preflight.provider_artifact_id
    if not isinstance(provider_artifact_id, str) or not provider_artifact_id:
        raise ValueError("qualified provider Artifact identity is missing")
    declared_provider_id = payload.get("provider_artifact_id")
    if declared_provider_id is not None and declared_provider_id != provider_artifact_id:
        raise ValueError("bundle-declared provider Artifact identity conflicts with preflight")
    amount_unit_contract = _mapping(
        payload.get("amount_unit_contract"),
        "amount_unit_contract",
    )
    if set(amount_unit_contract) != set(AmountUnitContract.__dataclass_fields__):
        raise ValueError("qualified amount-unit contract fields mismatch")
    try:
        parsed_amount_unit_contract = AmountUnitContract(**amount_unit_contract)
    except (TypeError, ValueError) as exc:
        raise ValueError("qualified amount-unit contract is invalid") from exc
    if not parsed_amount_unit_contract.absolute_threshold_qualified:
        raise ValueError("ABSOLUTE_LIQUIDITY_THRESHOLD_NOT_QUALIFIED")
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
    persist_partition_seal(
        output_root=output_root,
        specification=specification,
        seal=seal,
    )
    receipt = PartitionOpenReceipt(
        "pit-validation-partition-open-receipt-v1",
        partition_id,
        now,
        "PENDING",
        success_reader_implementation_identity(),
        seal.partition_content_hash,
    )
    qualification = preflight.qualification
    if qualification is None or not qualification.pit_correct_for_scope:
        raise ValueError("qualified v4 evidence receipt is missing")
    return PITReplicationSuccessInputs(
        provider_artifact_id=provider_artifact_id,
        provider_source_hashes=(content_hash,),
        provider_source_content_hash=source_content_hash,
        pit_qualification=qualification.to_canonical_dict(),
        partition_specification=specification,
        partition_seal=seal,
        partition_open_receipt=receipt,
        amount_unit_contract=amount_unit_contract,
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


def _validated_replication_payload(
    root: Mapping[str, Any],
    *,
    preflight: XuntouPITV4Preflight,
) -> Mapping[str, Any]:
    payload = _mapping(root.get("replication_payload"), "replication_payload")
    if set(payload) != PIT_REPLICATION_INPUT_PROJECTION_FIELDS:
        raise ValueError("qualified v4 replication projection fields mismatch")
    if payload.get("schema_version") != PIT_REPLICATION_INPUT_PROJECTION_V2:
        raise ValueError("qualified v4 replication projection schema mismatch")
    if payload.get("provider_artifact_id") != preflight.provider_artifact_id:
        raise ValueError("bundle-declared provider Artifact identity conflicts with preflight")
    if payload.get("source_content_hash") != preflight.source_content_hash:
        raise ValueError("replication projection source identity conflicts with preflight")
    raw_hashes = root.get("raw_source_hashes")
    if not isinstance(raw_hashes, Mapping) or payload.get("raw_source_hashes") != raw_hashes:
        raise ValueError("replication projection raw-source identity mismatch")
    sections = root.get("evidence_sections")
    if not isinstance(sections, Mapping) or set(sections) != set(PIT_V4_EVIDENCE_SECTIONS):
        raise ValueError("replication projection evidence section set mismatch")
    section_hashes: dict[str, object] = {}
    for name in PIT_V4_EVIDENCE_SECTIONS:
        section = sections.get(name)
        if not isinstance(section, Mapping):
            raise ValueError("replication projection evidence section is invalid")
        section_hashes[name] = section.get("content_hash")
    if payload.get("evidence_section_hashes") != section_hashes:
        raise ValueError("replication projection evidence section identity mismatch")
    projection = dict(payload)
    projection_hash = projection.pop("projection_content_hash")
    if projection_hash != canonical_identity_hash(projection):
        raise ValueError("replication projection content hash mismatch")
    return payload


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
