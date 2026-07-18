"""Immutable blocked and invalid PIT replication evidence v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

from market_regime_alpha.research.pit_replication_preflight import (
    PITReplicationPreflight,
    PITReplicationPreflightStatus,
)
from market_regime_alpha.research.pit_replication_v2_protocol import (
    PITCandidateReplicationProtocolV2,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    ArtifactSchema,
    PIT_REPLICATION_BLOCKED_V2_SCHEMA,
    PIT_REPLICATION_INVALID_V2_SCHEMA,
    canonical_identity_hash,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PIT_REPLICATION_V2_IMPLEMENTATION_MODULES: tuple[str, ...] = (
    "pit_replication_v2_protocol.py",
    "pit_replication_v2_preflight.py",
    "pit_replication_v2_artifacts.py",
    "pit_replication_v2_reader.py",
    "pit_replication_v2_runner.py",
)
PIT_REPLICATION_V2_LIMITATIONS = (
    "REAL_XUNTOU_BUNDLE_NOT_AVAILABLE_OR_NOT_QUALIFIED",
    "HISTORICAL_PIT_VALIDATION_NOT_EXECUTED",
    "NO_FORMAL_OOS",
    "NO_MODEL_WINNER_SELECTION",
    "NO_ENTRY_PORTFOLIO_OR_EXECUTION_AUTHORITY",
)


@dataclass(frozen=True, slots=True)
class PITReplicationRunIdentityV2:
    protocol_id: str
    experiment_id: str
    git_commit_sha: str
    provider: str
    provider_preflight_schema: str
    provider_input_status: str
    provider_source_content_hash: str | None
    provider_artifact_id: str | None
    validation_partition_id: str
    implementation_module_hashes: Mapping[str, str]
    authority_ceiling: str

    def __post_init__(self) -> None:
        if self.provider != "XUNTOU":
            raise ValueError("PIT replication v2 identity must be Xuntou-bound")
        if set(self.implementation_module_hashes) != set(PIT_REPLICATION_V2_IMPLEMENTATION_MODULES):
            raise ValueError("PIT replication v2 implementation module set mismatch")
        if any(not value.startswith("sha256:") for value in self.implementation_module_hashes.values()):
            raise ValueError("PIT replication v2 implementation hash is invalid")
        if len(self.git_commit_sha) != 40 or any(character not in "0123456789abcdef" for character in self.git_commit_sha):
            raise ValueError("PIT replication v2 Git revision must be a full lowercase SHA")
        if self.authority_ceiling != "REHEARSAL_NOT_FORMAL_OOS":
            raise ValueError("PIT replication v2 authority ceiling is invalid")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["implementation_module_hashes"] = dict(sorted(self.implementation_module_hashes.items()))
        return payload

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PITReplicationRunIdentityV2:
        if set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("PIT replication v2 identity fields mismatch")
        values = dict(payload)
        hashes = values.get("implementation_module_hashes")
        if not isinstance(hashes, Mapping):
            raise ValueError("PIT replication v2 implementation hashes are invalid")
        values["implementation_module_hashes"] = {str(key): str(value) for key, value in hashes.items()}
        return cls(**values)

    def run_id(self) -> str:
        digest = canonical_identity_hash(self.to_canonical_dict()).split(":", 1)[1]
        return f"pit-replication-v2-{digest[:20]}"


def build_pit_replication_v2_identity(
    *,
    protocol: PITCandidateReplicationProtocolV2,
    preflight: PITReplicationPreflight,
) -> PITReplicationRunIdentityV2:
    module_root = Path(__file__).resolve().parent
    return PITReplicationRunIdentityV2(
        protocol_id=protocol.protocol_id,
        experiment_id=protocol.experiment_id,
        git_commit_sha=_git_revision(),
        provider=preflight.provider,
        provider_preflight_schema=preflight.schema_version,
        provider_input_status=preflight.status.value,
        provider_source_content_hash=preflight.bundle_content_hash,
        provider_artifact_id=preflight.provider_artifact_id,
        validation_partition_id=protocol.validation_partition_id,
        implementation_module_hashes={
            name: _content_hash(module_root / name)
            for name in PIT_REPLICATION_V2_IMPLEMENTATION_MODULES
        },
        authority_ceiling=protocol.authority_ceiling,
    )


def publish_pit_replication_v2(
    *,
    output_root: Path,
    protocol: PITCandidateReplicationProtocolV2,
    preflight: PITReplicationPreflight,
) -> Path:
    if preflight.status is PITReplicationPreflightStatus.AVAILABLE:
        raise ValueError("PIT replication success publication belongs to the qualified success pipeline")
    schema = (
        PIT_REPLICATION_BLOCKED_V2_SCHEMA
        if preflight.status is PITReplicationPreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT
        else PIT_REPLICATION_INVALID_V2_SCHEMA
    )
    identity = build_pit_replication_v2_identity(protocol=protocol, preflight=preflight)
    run_id = identity.run_id()
    final = output_root / run_id
    stage = output_root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError("PIT replication v2 Artifact is immutable")
    output_root.mkdir(parents=True, exist_ok=True)
    stage.mkdir()
    try:
        status = preflight.status.value
        manifest = {
            "schema_version": schema.schema_version,
            "run_id": run_id,
            "status": status,
            "data_eligibility": "UNQUALIFIED",
            "authority": "NO_RESEARCH_RESULT",
            "required_artifacts": sorted(schema.required_files),
            "run_identity": identity.to_canonical_dict(),
            "protocol_id": protocol.protocol_id,
            "provider": "XUNTOU",
        }
        _write_json(stage / "manifest.json", manifest)
        _write_json(stage / "protocol.json", {**protocol.to_canonical_dict(), "protocol_id": protocol.protocol_id})
        _write_json(stage / "preflight.json", preflight.to_public_dict())
        if schema is PIT_REPLICATION_BLOCKED_V2_SCHEMA:
            _write_json(
                stage / "blocker.json",
                {
                    "schema_version": "pit-replication-blocker-v2",
                    "status": status,
                    "required_provider": "XUNTOU",
                    "required_bundle_schema": preflight.required_bundle_schema,
                    "expected_source_files": list(preflight.expected_source_files),
                    "missing_input_reasons": list(preflight.reasons),
                    "no_research_result_produced": True,
                    "tencent_fallback_used": False,
                },
            )
        else:
            _write_json(
                stage / "source_identity.json",
                {
                    "provider": preflight.provider,
                    "bundle_schema": preflight.required_bundle_schema,
                    "source_content_hash": preflight.bundle_content_hash,
                    "provider_artifact_id": preflight.provider_artifact_id,
                    "preflight_schema": preflight.schema_version,
                },
            )
            _write_json(
                stage / "validation_errors.json",
                {
                    "schema_version": "pit-replication-validation-errors-v2",
                    "status": status,
                    "rejection_reasons": list(preflight.reasons),
                    "no_research_result_produced": True,
                },
            )
        _write_json(stage / "limitations.json", list(PIT_REPLICATION_V2_LIMITATIONS))
        (stage / "report.md").write_text(
            f"# PIT Candidate Replication v2\n\n## Status\n\n`{status}`\n\n"
            "No research result, Tencent fallback, model winner, Formal OOS claim, or trading authority was produced.\n",
            encoding="utf-8",
        )
        _write_checksums(stage)
        _validate_exact_set(stage, schema)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _git_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _validate_exact_set(root: Path, schema: ArtifactSchema) -> None:
    if frozenset(item.name for item in root.iterdir() if item.is_file()) != schema.required_files:
        raise ValueError("PIT replication v2 exact file set mismatch")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")


def _write_checksums(root: Path) -> None:
    _write_json(
        root / "SHA256SUMS.json",
        {
            item.name: _content_hash(item)
            for item in sorted(root.iterdir())
            if item.is_file() and item.name != "SHA256SUMS.json"
        },
    )


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
