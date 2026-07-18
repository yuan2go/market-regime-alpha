"""Semantic reader for immutable PIT Candidate replication artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.research.pit_replication_artifacts import (
    PIT_REPLICATION_LIMITATIONS,
    PITReplicationRunIdentity,
)
from market_regime_alpha.research.pit_replication_preflight import (
    PITReplicationPreflightStatus,
    preflight_xuntou_replication,
)
from market_regime_alpha.research.pit_replication_protocol import (
    PITCandidateReplicationProtocol,
    frozen_pit_replication_protocol,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    PIT_REPLICATION_BLOCKED_RUN_SCHEMA,
)


@dataclass(frozen=True, slots=True)
class VerifiedPITReplicationRun:
    root: Path
    run_id: str
    status: str
    manifest: Mapping[str, Any]
    protocol: PITCandidateReplicationProtocol
    preflight: Mapping[str, Any]
    blocker: Mapping[str, Any]
    checksums_hash: str


def load_verified_pit_replication_run(path: Path) -> VerifiedPITReplicationRun:
    root = path.resolve()
    if not root.is_dir():
        raise ValueError("PIT replication Artifact directory does not exist")
    actual_files = frozenset(item.name for item in root.iterdir() if item.is_file())
    if actual_files != PIT_REPLICATION_BLOCKED_RUN_SCHEMA.required_files:
        raise ValueError("PIT replication Artifact exact file set is invalid")
    _verify_checksums(root)
    manifest = _read_object(root / "manifest.json")
    if set(PIT_REPLICATION_BLOCKED_RUN_SCHEMA.required_manifest_keys) - set(manifest):
        raise ValueError("PIT replication manifest is missing required fields")
    if manifest.get("schema_version") != PIT_REPLICATION_BLOCKED_RUN_SCHEMA.schema_version:
        raise ValueError("unsupported PIT replication Artifact schema")
    if manifest.get("required_artifacts") != sorted(PIT_REPLICATION_BLOCKED_RUN_SCHEMA.required_files):
        raise ValueError("PIT replication manifest required Artifact set mismatch")
    if manifest.get("status") != "BLOCKED_EXTERNAL_PROVIDER_INPUT":
        raise ValueError("blocker manifest status is invalid")
    if manifest.get("data_eligibility") != "UNQUALIFIED" or manifest.get("authority") != "NO_RESEARCH_RESULT":
        raise ValueError("blocked PIT replication authority is invalid")

    identity = PITReplicationRunIdentity.from_canonical_dict(_mapping(manifest.get("run_identity")))
    run_id = str(manifest.get("run_id", ""))
    if identity.run_id() != run_id or root.name != run_id:
        raise ValueError("PIT replication Run ID does not match typed identity")
    protocol_payload = _read_object(root / "protocol.json")
    protocol_id = protocol_payload.pop("protocol_id", None)
    protocol_payload["comparator_model_ids"] = tuple(protocol_payload["comparator_model_ids"])
    protocol_payload["matched_k_seed_set"] = tuple(protocol_payload["matched_k_seed_set"])
    protocol = PITCandidateReplicationProtocol(**protocol_payload)
    frozen = frozen_pit_replication_protocol()
    if protocol.to_canonical_dict() != frozen.to_canonical_dict():
        raise ValueError("PIT replication Protocol differs from frozen contract")
    if protocol_id != protocol.protocol_id or manifest.get("protocol_id") != protocol.protocol_id:
        raise ValueError("PIT replication Protocol identity mismatch")
    if identity.protocol_id != protocol.protocol_id or identity.experiment_id != protocol.experiment_id:
        raise ValueError("PIT replication run identity does not bind the Protocol")

    preflight = _read_object(root / "preflight.json")
    expected_preflight = preflight_xuntou_replication(None).to_public_dict()
    if preflight != expected_preflight:
        raise ValueError("blocked PIT replication preflight cannot be semantically reconstructed")
    if identity.provider_input_status != PITReplicationPreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT.value:
        raise ValueError("PIT replication identity preflight status mismatch")
    if identity.provider_source_content_hash is not None or identity.provider_artifact_id is not None:
        raise ValueError("blocked PIT replication identity cannot claim provider evidence")

    blocker = _read_object(root / "blocker.json")
    expected_blocker = {
        "schema_version": "pit-replication-blocker-v1",
        "status": "BLOCKED_EXTERNAL_PROVIDER_INPUT",
        "required_provider": "XUNTOU",
        "required_bundle_schema": expected_preflight["required_bundle_schema"],
        "expected_source_files": expected_preflight["expected_source_files"],
        "missing_input_reasons": expected_preflight["reasons"],
        "no_research_result_produced": True,
        "tencent_fallback_used": False,
    }
    if blocker != expected_blocker:
        raise ValueError("PIT replication blocker semantics are invalid")
    limitations = _read_list(root / "limitations.json")
    if limitations != list(PIT_REPLICATION_LIMITATIONS):
        raise ValueError("PIT replication limitations were changed")
    return VerifiedPITReplicationRun(
        root=root,
        run_id=run_id,
        status="BLOCKED_EXTERNAL_PROVIDER_INPUT",
        manifest=MappingProxyType(manifest),
        protocol=protocol,
        preflight=MappingProxyType(preflight),
        blocker=MappingProxyType(blocker),
        checksums_hash=_content_hash(root / "SHA256SUMS.json"),
    )


def _verify_checksums(root: Path) -> None:
    checksums = _read_object(root / "SHA256SUMS.json")
    expected_names = set(PIT_REPLICATION_BLOCKED_RUN_SCHEMA.required_files) - {"SHA256SUMS.json"}
    if set(checksums) != expected_names:
        raise ValueError("PIT replication checksum file set mismatch")
    for name, expected in checksums.items():
        if _content_hash(root / name) != expected:
            raise ValueError(f"PIT replication checksum mismatch for {name}")


def _read_object(path: Path) -> dict[str, Any]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return {str(key): value for key, value in payload.items()}


def _read_list(path: Path) -> list[Any]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path.name} must contain a JSON array")
    return payload


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected JSON object")
    return value


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
