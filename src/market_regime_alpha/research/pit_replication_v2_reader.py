"""Semantic reader for blocked and invalid PIT replication evidence v2."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.research.pit_replication_preflight import PITReplicationPreflightStatus
from market_regime_alpha.research.pit_replication_v2_artifacts import (
    PIT_REPLICATION_V2_IMPLEMENTATION_MODULES,
    PIT_REPLICATION_V2_LIMITATIONS,
    PITReplicationRunIdentityV2,
)
from market_regime_alpha.research.pit_replication_v2_protocol import (
    PITCandidateReplicationProtocolV2,
    frozen_pit_replication_v2_protocol,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    ArtifactSchema,
    PIT_REPLICATION_BLOCKED_V2_SCHEMA,
    PIT_REPLICATION_INVALID_V2_SCHEMA,
)


@dataclass(frozen=True, slots=True)
class VerifiedPITReplicationRunV2:
    root: Path
    run_id: str
    schema_version: str
    status: str
    manifest: Mapping[str, Any]
    protocol: PITCandidateReplicationProtocolV2
    preflight: Mapping[str, Any]
    checksums_hash: str


def load_verified_pit_replication_v2(path: Path) -> VerifiedPITReplicationRunV2:
    root = path.resolve()
    manifest = _read_object(root / "manifest.json")
    schema = _schema(str(manifest.get("schema_version", "")))
    _verify_files(root, schema)
    if schema.required_manifest_keys - manifest.keys():
        raise ValueError("PIT replication v2 manifest fields are missing")
    if manifest.get("required_artifacts") != sorted(schema.required_files):
        raise ValueError("PIT replication v2 required file set mismatch")
    identity = PITReplicationRunIdentityV2.from_canonical_dict(_mapping(manifest.get("run_identity")))
    run_id = str(manifest.get("run_id", ""))
    if identity.run_id() != run_id or root.name != run_id:
        raise ValueError("PIT replication v2 Run ID mismatch")
    module_root = Path(__file__).resolve().parent
    expected_hashes = {
        name: _content_hash(module_root / name) for name in PIT_REPLICATION_V2_IMPLEMENTATION_MODULES
    }
    if dict(identity.implementation_module_hashes) != expected_hashes:
        raise ValueError("PIT replication v2 implementation identity is stale")
    protocol_payload = _read_object(root / "protocol.json")
    protocol_id = protocol_payload.pop("protocol_id", None)
    protocol_payload["comparator_model_ids"] = tuple(protocol_payload["comparator_model_ids"])
    protocol_payload["matched_k_seed_set"] = tuple(protocol_payload["matched_k_seed_set"])
    protocol = PITCandidateReplicationProtocolV2(**protocol_payload)
    frozen = frozen_pit_replication_v2_protocol()
    if protocol.to_canonical_dict() != frozen.to_canonical_dict():
        raise ValueError("PIT replication v2 Protocol is not frozen")
    if protocol_id != protocol.protocol_id or identity.protocol_id != protocol.protocol_id:
        raise ValueError("PIT replication v2 Protocol identity mismatch")
    preflight = _read_object(root / "preflight.json")
    if preflight.get("schema_version") != identity.provider_preflight_schema:
        raise ValueError("PIT replication v2 preflight identity mismatch")
    if preflight.get("status") != identity.provider_input_status:
        raise ValueError("PIT replication v2 preflight status mismatch")
    if preflight.get("bundle_content_hash") != identity.provider_source_content_hash:
        raise ValueError("PIT replication v2 source hash mismatch")
    status = str(manifest.get("status"))
    if status != identity.provider_input_status:
        raise ValueError("PIT replication v2 manifest status mismatch")
    if schema is PIT_REPLICATION_BLOCKED_V2_SCHEMA:
        _verify_blocker(root, preflight)
        if status != PITReplicationPreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT.value:
            raise ValueError("PIT replication blocked schema/status mismatch")
    else:
        _verify_invalid(root, preflight, identity)
        if status != PITReplicationPreflightStatus.INVALID_PIT_EVIDENCE.value:
            raise ValueError("PIT replication invalid schema/status mismatch")
    if _read_list(root / "limitations.json") != list(PIT_REPLICATION_V2_LIMITATIONS):
        raise ValueError("PIT replication v2 limitations mismatch")
    return VerifiedPITReplicationRunV2(
        root,
        run_id,
        schema.schema_version,
        status,
        MappingProxyType(manifest),
        protocol,
        MappingProxyType(preflight),
        _content_hash(root / "SHA256SUMS.json"),
    )


def _verify_blocker(root: Path, preflight: Mapping[str, Any]) -> None:
    expected = {
        "schema_version": "pit-replication-blocker-v2",
        "status": preflight["status"],
        "required_provider": "XUNTOU",
        "required_bundle_schema": preflight["required_bundle_schema"],
        "expected_source_files": preflight["expected_source_files"],
        "missing_input_reasons": preflight["reasons"],
        "no_research_result_produced": True,
        "tencent_fallback_used": False,
    }
    if _read_object(root / "blocker.json") != expected:
        raise ValueError("PIT replication v2 blocker is not reconstructible")


def _verify_invalid(
    root: Path, preflight: Mapping[str, Any], identity: PITReplicationRunIdentityV2
) -> None:
    expected_source = {
        "provider": identity.provider,
        "bundle_schema": preflight["required_bundle_schema"],
        "source_content_hash": identity.provider_source_content_hash,
        "provider_artifact_id": identity.provider_artifact_id,
        "preflight_schema": identity.provider_preflight_schema,
    }
    if _read_object(root / "source_identity.json") != expected_source:
        raise ValueError("PIT replication v2 invalid source identity mismatch")
    expected_errors = {
        "schema_version": "pit-replication-validation-errors-v2",
        "status": preflight["status"],
        "rejection_reasons": preflight["reasons"],
        "no_research_result_produced": True,
    }
    if _read_object(root / "validation_errors.json") != expected_errors:
        raise ValueError("PIT replication v2 rejection reasons are not reconstructible")


def _schema(version: str) -> ArtifactSchema:
    if version == PIT_REPLICATION_BLOCKED_V2_SCHEMA.schema_version:
        return PIT_REPLICATION_BLOCKED_V2_SCHEMA
    if version == PIT_REPLICATION_INVALID_V2_SCHEMA.schema_version:
        return PIT_REPLICATION_INVALID_V2_SCHEMA
    raise ValueError(f"unsupported PIT replication v2 schema: {version}")


def _verify_files(root: Path, schema: ArtifactSchema) -> None:
    if not root.is_dir():
        raise ValueError("PIT replication v2 Artifact is missing")
    files = frozenset(item.name for item in root.iterdir() if item.is_file())
    if files != schema.required_files:
        raise ValueError("PIT replication v2 exact file set mismatch")
    checksums = _read_object(root / "SHA256SUMS.json")
    if set(checksums) != set(files - {"SHA256SUMS.json"}):
        raise ValueError("PIT replication v2 checksum coverage mismatch")
    for name, expected in checksums.items():
        if _content_hash(root / name) != expected:
            raise ValueError(f"PIT replication v2 checksum mismatch: {name}")


def _read_object(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _read_list(path: Path) -> list[Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path.name} must contain an array")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("PIT replication v2 identity must be an object")
    return value


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
