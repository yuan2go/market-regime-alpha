"""Immutable publication contracts for PIT Candidate replication evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from market_regime_alpha.research.pit_replication_preflight import (
    PITReplicationPreflight,
    PITReplicationPreflightStatus,
)
from market_regime_alpha.research.pit_replication_protocol import (
    PITCandidateReplicationProtocol,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    PIT_REPLICATION_BLOCKED_RUN_SCHEMA,
    canonical_identity_hash,
)


PIT_REPLICATION_LIMITATIONS = (
    "REAL_XUNTOU_BUNDLE_NOT_AVAILABLE",
    "HISTORICAL_PIT_VALIDATION_NOT_EXECUTED",
    "NO_FORMAL_OOS",
    "NO_MODEL_WINNER_SELECTION",
    "NO_ENTRY_PORTFOLIO_OR_EXECUTION_AUTHORITY",
)


@dataclass(frozen=True, slots=True)
class PITReplicationRunIdentity:
    protocol_id: str
    experiment_id: str
    code_revision: str
    provider: str
    provider_preflight_schema: str
    provider_input_status: str
    provider_source_content_hash: str | None
    provider_artifact_id: str | None
    validation_partition_id: str
    implementation_hashes: Mapping[str, str]
    authority_ceiling: str

    def __post_init__(self) -> None:
        if self.provider != "XUNTOU":
            raise ValueError("PIT replication identity must be bound to Xuntou")
        if not self.implementation_hashes:
            raise ValueError("PIT replication implementation hashes are required")
        if self.authority_ceiling != "REHEARSAL_NOT_FORMAL_OOS":
            raise ValueError("PIT replication authority ceiling is invalid")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["implementation_hashes"] = dict(sorted(self.implementation_hashes.items()))
        return payload

    def run_id(self) -> str:
        digest = canonical_identity_hash(self.to_canonical_dict()).split(":", 1)[1]
        return f"pit-replication-{digest[:20]}"

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PITReplicationRunIdentity:
        if set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("PIT replication identity fields do not match typed contract")
        values = dict(payload)
        hashes = values.get("implementation_hashes")
        if not isinstance(hashes, Mapping):
            raise ValueError("PIT replication implementation hashes are invalid")
        values["implementation_hashes"] = {str(key): str(value) for key, value in hashes.items()}
        return cls(**values)


def build_pit_replication_run_identity(
    *,
    protocol: PITCandidateReplicationProtocol,
    preflight: PITReplicationPreflight,
    code_revision: str,
) -> PITReplicationRunIdentity:
    root = Path(__file__).resolve().parent
    names = (
        "pit_replication_protocol.py",
        "pit_replication_preflight.py",
        "pit_replication_runner.py",
        "pit_replication_artifacts.py",
        "pit_replication_reader.py",
    )
    return PITReplicationRunIdentity(
        protocol_id=protocol.protocol_id,
        experiment_id=protocol.experiment_id,
        code_revision=code_revision,
        provider=preflight.provider,
        provider_preflight_schema=preflight.schema_version,
        provider_input_status=preflight.status.value,
        provider_source_content_hash=preflight.bundle_content_hash,
        provider_artifact_id=preflight.provider_artifact_id,
        validation_partition_id=protocol.validation_partition_id,
        implementation_hashes={name: _content_hash(root / name) for name in names},
        authority_ceiling=protocol.authority_ceiling,
    )


def publish_blocked_pit_replication(
    *,
    output_root: Path,
    protocol: PITCandidateReplicationProtocol,
    preflight: PITReplicationPreflight,
    code_revision: str,
) -> Path:
    if preflight.status is not PITReplicationPreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT:
        raise ValueError("blocked Artifact requires a missing external provider input")
    identity = build_pit_replication_run_identity(
        protocol=protocol, preflight=preflight, code_revision=code_revision
    )
    run_id = identity.run_id()
    final = output_root / run_id
    stage = output_root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError("PIT replication Artifact is immutable and non-overwriting")
    output_root.mkdir(parents=True, exist_ok=True)
    stage.mkdir()
    try:
        manifest = {
            "schema_version": PIT_REPLICATION_BLOCKED_RUN_SCHEMA.schema_version,
            "run_id": run_id,
            "status": "BLOCKED_EXTERNAL_PROVIDER_INPUT",
            "data_eligibility": "UNQUALIFIED",
            "authority": "NO_RESEARCH_RESULT",
            "required_artifacts": sorted(PIT_REPLICATION_BLOCKED_RUN_SCHEMA.required_files),
            "run_identity": identity.to_canonical_dict(),
            "protocol_id": protocol.protocol_id,
            "provider": "XUNTOU",
        }
        blocker = {
            "schema_version": "pit-replication-blocker-v1",
            "status": "BLOCKED_EXTERNAL_PROVIDER_INPUT",
            "required_provider": "XUNTOU",
            "required_bundle_schema": preflight.required_bundle_schema,
            "expected_source_files": list(preflight.expected_source_files),
            "missing_input_reasons": list(preflight.reasons),
            "no_research_result_produced": True,
            "tencent_fallback_used": False,
        }
        _write_json(stage / "manifest.json", manifest)
        _write_json(
            stage / "protocol.json",
            {**protocol.to_canonical_dict(), "protocol_id": protocol.protocol_id},
        )
        _write_json(stage / "preflight.json", preflight.to_public_dict())
        _write_json(stage / "blocker.json", blocker)
        _write_json(stage / "limitations.json", list(PIT_REPLICATION_LIMITATIONS))
        (stage / "report.md").write_text(
            "# PIT Candidate Replication\n\n"
            "## Status\n\n"
            "`BLOCKED_EXTERNAL_PROVIDER_INPUT`\n\n"
            "A real normalized Xuntou bundle is required. No Tencent fallback, simulated "
            "provider input, Candidate result, model winner, Formal OOS claim, or trading "
            "authority was produced.\n",
            encoding="utf-8",
        )
        _write_checksums(stage)
        _validate_exact_set(stage)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _validate_exact_set(root: Path) -> None:
    actual = frozenset(item.name for item in root.iterdir() if item.is_file())
    if actual != PIT_REPLICATION_BLOCKED_RUN_SCHEMA.required_files:
        raise ValueError("blocked PIT replication Artifact exact file set is invalid")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


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
