"""Immutable acquisition-substage Artifact for recoverable LIVE source fetches."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.providers.public_composite.contracts import (
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeBatch,
    PublicQuote,
    PublicSecurityStatusObservation,
)


class PublicSourceAcquisitionStage(str, Enum):
    HISTORY_SOURCE_FROZEN = "HISTORY_SOURCE_FROZEN"
    SECURITY_STATUS_SOURCE_FROZEN = "SECURITY_STATUS_SOURCE_FROZEN"
    SUPPLEMENTAL_SOURCE_FROZEN = "SUPPLEMENTAL_SOURCE_FROZEN"
    DECISION_QUOTE_SOURCE_FROZEN = "DECISION_QUOTE_SOURCE_FROZEN"


SOURCE_STAGE_ARTIFACT_SCHEMA_V1 = "public-source-acquisition-stage-v1"
SOURCE_STAGE_ARTIFACT_SCHEMA_V2 = "public-source-acquisition-stage-v2"
SOURCE_STAGE_ARTIFACT_SCHEMA_V3 = "public-source-acquisition-stage-v3"
SOURCE_STAGE_ARTIFACT_SCHEMA = SOURCE_STAGE_ARTIFACT_SCHEMA_V3
SOURCE_STAGE_ARTIFACT_FILES = (
    "SHA256SUMS.json",
    "batch.json",
    "manifest.json",
)


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _batch_payload(
    batch: PublicCompositeBatch,
    *,
    include_security_status: bool = False,
) -> dict[str, Any]:
    payload = {
        "raw_payloads": [
            item.to_canonical_dict(include_payload=True)
            for item in batch.raw_payloads
        ],
        "bars": [item.to_canonical_dict() for item in batch.bars],
        "quotes": [item.to_canonical_dict() for item in batch.quotes],
        "source_conflicts": list(batch.source_conflicts),
        "limitations": list(batch.limitations),
    }
    if include_security_status:
        payload["security_status_observations"] = [
            item.to_canonical_dict()
            for item in batch.security_status_observations
        ]
    return payload


def _batch_from_payload(
    payload: Mapping[str, Any],
    *,
    include_security_status: bool,
) -> PublicCompositeBatch:
    expected = {
        "raw_payloads",
        "bars",
        "quotes",
        "source_conflicts",
        "limitations",
        *(("security_status_observations",) if include_security_status else ()),
    }
    if set(payload) != expected:
        raise ValueError("source stage batch fields mismatch")
    batch = PublicCompositeBatch(
        raw_payloads=tuple(
            AcquiredSourcePayload.from_canonical_dict(item)
            for item in payload["raw_payloads"]
        ),
        bars=tuple(PublicBar.from_canonical_dict(item) for item in payload["bars"]),
        quotes=tuple(
            PublicQuote.from_canonical_dict(item) for item in payload["quotes"]
        ),
        source_conflicts=tuple(str(item) for item in payload["source_conflicts"]),
        limitations=tuple(str(item) for item in payload["limitations"]),
        security_status_observations=(
            tuple(
                PublicSecurityStatusObservation.from_canonical_dict(item)
                for item in payload["security_status_observations"]
            )
            if include_security_status
            else ()
        ),
    )
    known = {item.source_artifact_id for item in batch.raw_payloads}
    if any(item.source_artifact_id not in known for item in batch.bars):
        raise ValueError("source stage bar references unarchived bytes")
    if any(item.source_artifact_id not in known for item in batch.quotes):
        raise ValueError("source stage quote references unarchived bytes")
    if any(
        item.source_artifact_id not in known
        for item in batch.security_status_observations
    ):
        raise ValueError("source stage status references unarchived bytes")
    return batch


@dataclass(frozen=True, slots=True)
class PublicSourceStageScope:
    """All request semantics that make one frozen acquisition stage reusable."""

    run_request_id: str
    decision_date: date
    decision_time: DecisionTime
    provider_profile_id: str
    universe_policy_id: str
    acquisition_stage: PublicSourceAcquisitionStage

    def __post_init__(self) -> None:
        _require_acquisition_key(self.run_request_id)
        if not isinstance(self.decision_date, date):
            raise TypeError("decision_date must be a date")
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        if self.decision_time.value.date() != self.decision_date:
            raise ValueError("decision_date must match decision_time")
        _require_acquisition_key(self.provider_profile_id)
        _require_acquisition_key(self.universe_policy_id)
        if not isinstance(
            self.acquisition_stage,
            PublicSourceAcquisitionStage,
        ):
            raise TypeError(
                "acquisition_stage must be a PublicSourceAcquisitionStage"
            )

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "run_request_id": self.run_request_id,
            "decision_date": self.decision_date.isoformat(),
            "decision_time": self.decision_time.isoformat(),
            "provider_profile_id": self.provider_profile_id,
            "universe_policy_id": self.universe_policy_id,
            "acquisition_stage": self.acquisition_stage.value,
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> PublicSourceStageScope:
        expected = {
            "run_request_id",
            "decision_date",
            "decision_time",
            "provider_profile_id",
            "universe_policy_id",
            "acquisition_stage",
        }
        if set(payload) != expected:
            raise ValueError("source stage scope fields mismatch")
        return cls(
            run_request_id=str(payload["run_request_id"]),
            decision_date=date.fromisoformat(str(payload["decision_date"])),
            decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["decision_time"]))
            ),
            provider_profile_id=str(payload["provider_profile_id"]),
            universe_policy_id=str(payload["universe_policy_id"]),
            acquisition_stage=PublicSourceAcquisitionStage(
                str(payload["acquisition_stage"])
            ),
        )


def source_stage_artifact_id(
    *,
    stage: PublicSourceAcquisitionStage,
    batch: PublicCompositeBatch,
    acquisition_key: str | None = None,
    scope: PublicSourceStageScope | None = None,
) -> tuple[ArtifactId, str]:
    if acquisition_key is not None and scope is not None:
        raise ValueError("source stage accepts acquisition_key or scope, not both")
    if scope is not None and scope.acquisition_stage is not stage:
        raise ValueError("source stage scope does not match stage")
    schema_version = (
        SOURCE_STAGE_ARTIFACT_SCHEMA_V3
        if scope is not None
        else
        SOURCE_STAGE_ARTIFACT_SCHEMA_V2
        if acquisition_key is not None
        else SOURCE_STAGE_ARTIFACT_SCHEMA_V1
    )
    semantic: dict[str, Any] = {
        "schema_version": schema_version,
        "stage": stage.value,
        "batch": _batch_payload(
            batch,
            include_security_status=scope is not None,
        ),
    }
    if acquisition_key is not None:
        _require_acquisition_key(acquisition_key)
        semantic["acquisition_key"] = acquisition_key
    if scope is not None:
        semantic["scope"] = scope.to_canonical_dict()
        semantic["raw_payload_hashes"] = _raw_payload_hashes(batch)
    content_hash = _canonical_hash(semantic)
    return (
        ArtifactId(
            f"source-stage-{stage.value.lower().replace('_', '-')}-"
            f"{content_hash.split(':', 1)[1][:24]}"
        ),
        content_hash,
    )


@dataclass(frozen=True, slots=True)
class VerifiedPublicSourceStageArtifact:
    root: Path
    artifact_id: ArtifactId
    stage: PublicSourceAcquisitionStage
    batch: PublicCompositeBatch
    content_hash: str
    checksums_hash: str
    acquisition_key: str | None
    scope: PublicSourceStageScope | None


def publish_public_source_stage_artifact(
    *,
    root: Path,
    stage: PublicSourceAcquisitionStage,
    batch: PublicCompositeBatch,
    acquisition_key: str | None = None,
    scope: PublicSourceStageScope | None = None,
) -> Path:
    artifact_id, content_hash = source_stage_artifact_id(
        stage=stage,
        batch=batch,
        acquisition_key=acquisition_key,
        scope=scope,
    )
    schema_version = (
        SOURCE_STAGE_ARTIFACT_SCHEMA_V3
        if scope is not None
        else
        SOURCE_STAGE_ARTIFACT_SCHEMA_V2
        if acquisition_key is not None
        else SOURCE_STAGE_ARTIFACT_SCHEMA_V1
    )
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact_id)
    if final.exists():
        raise FileExistsError(f"source stage Artifact exists: {final}")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{artifact_id}.", dir=root)
    )
    try:
        _write_json(
            staging / "batch.json",
            _batch_payload(
                batch,
                include_security_status=scope is not None,
            ),
        )
        manifest: dict[str, Any] = {
            "schema_version": schema_version,
            "artifact_id": str(artifact_id),
            "stage": stage.value,
            "content_hash": content_hash,
            "required_artifacts": sorted(SOURCE_STAGE_ARTIFACT_FILES),
        }
        if acquisition_key is not None:
            manifest["acquisition_key"] = acquisition_key
        if scope is not None:
            manifest["scope"] = scope.to_canonical_dict()
            manifest["raw_payload_hashes"] = _raw_payload_hashes(batch)
        _write_json(staging / "manifest.json", manifest)
        _write_json(
            staging / "SHA256SUMS.json",
            {
                name: _file_hash(staging / name)
                for name in ("batch.json", "manifest.json")
            },
        )
        if {item.name for item in staging.iterdir()} != set(
            SOURCE_STAGE_ARTIFACT_FILES
        ):
            raise RuntimeError("source stage exact file set mismatch")
        staging.rename(final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final


def load_verified_public_source_stage_artifact(
    path: Path,
) -> VerifiedPublicSourceStageArtifact:
    if not path.is_dir():
        raise ValueError("source stage Artifact path is not a directory")
    if {item.name for item in path.iterdir()} != set(
        SOURCE_STAGE_ARTIFACT_FILES
    ):
        raise ValueError("source stage exact file set mismatch")
    checksums = _read_json(path / "SHA256SUMS.json")
    if set(checksums) != {"batch.json", "manifest.json"}:
        raise ValueError("source stage checksum index mismatch")
    for name, expected in checksums.items():
        if _file_hash(path / name) != expected:
            raise ValueError(f"source stage checksum mismatch: {name}")
    manifest = _read_json(path / "manifest.json")
    schema_version = str(manifest.get("schema_version"))
    if schema_version not in {
        SOURCE_STAGE_ARTIFACT_SCHEMA_V1,
        SOURCE_STAGE_ARTIFACT_SCHEMA_V2,
        SOURCE_STAGE_ARTIFACT_SCHEMA_V3,
    } or manifest.get("required_artifacts") != sorted(
        SOURCE_STAGE_ARTIFACT_FILES
    ):
        raise ValueError("source stage manifest mismatch")
    raw_acquisition_key = manifest.get("acquisition_key")
    if (
        schema_version == SOURCE_STAGE_ARTIFACT_SCHEMA_V2
        and not isinstance(raw_acquisition_key, str)
    ):
        raise ValueError("source stage acquisition key mismatch")
    acquisition_key = (
        raw_acquisition_key
        if schema_version == SOURCE_STAGE_ARTIFACT_SCHEMA_V2
        else None
    )
    raw_scope = manifest.get("scope")
    if (
        schema_version == SOURCE_STAGE_ARTIFACT_SCHEMA_V3
        and not isinstance(raw_scope, dict)
    ):
        raise ValueError("source stage scope mismatch")
    if schema_version == SOURCE_STAGE_ARTIFACT_SCHEMA_V3:
        assert isinstance(raw_scope, dict)
        scope = PublicSourceStageScope.from_canonical_dict(raw_scope)
    else:
        scope = None
    expected_manifest_fields = {
        "schema_version",
        "artifact_id",
        "stage",
        "content_hash",
        "required_artifacts",
        *(
            ("acquisition_key",)
            if schema_version == SOURCE_STAGE_ARTIFACT_SCHEMA_V2
            else ()
        ),
        *(
            ("scope", "raw_payload_hashes")
            if schema_version == SOURCE_STAGE_ARTIFACT_SCHEMA_V3
            else ()
        ),
    }
    if set(manifest) != expected_manifest_fields:
        raise ValueError("source stage manifest fields mismatch")
    if acquisition_key is not None:
        _require_acquisition_key(acquisition_key)
    stage = PublicSourceAcquisitionStage(str(manifest["stage"]))
    if scope is not None and scope.acquisition_stage is not stage:
        raise ValueError("source stage scope does not match manifest stage")
    batch = _batch_from_payload(
        _read_json(path / "batch.json"),
        include_security_status=(
            schema_version == SOURCE_STAGE_ARTIFACT_SCHEMA_V3
        ),
    )
    if (
        schema_version == SOURCE_STAGE_ARTIFACT_SCHEMA_V3
        and manifest.get("raw_payload_hashes") != _raw_payload_hashes(batch)
    ):
        raise ValueError("source stage raw payload hash inventory mismatch")
    artifact_id, content_hash = source_stage_artifact_id(
        stage=stage,
        batch=batch,
        acquisition_key=acquisition_key,
        scope=scope,
    )
    if (
        manifest.get("artifact_id") != str(artifact_id)
        or manifest.get("content_hash") != content_hash
        or path.name != str(artifact_id)
    ):
        raise ValueError("source stage semantic identity mismatch")
    return VerifiedPublicSourceStageArtifact(
        root=path,
        artifact_id=artifact_id,
        stage=stage,
        batch=batch,
        content_hash=content_hash,
        checksums_hash=_canonical_hash(
            {str(key): value for key, value in sorted(checksums.items())}
        ),
        acquisition_key=acquisition_key,
        scope=scope,
    )


def find_verified_public_source_stage_artifact(
    *,
    root: Path,
    stage: PublicSourceAcquisitionStage,
    acquisition_key: str | None = None,
    scope: PublicSourceStageScope | None = None,
) -> VerifiedPublicSourceStageArtifact | None:
    """Find a v2/v3 Artifact published before its Runtime Journal receipt."""

    if (acquisition_key is None) == (scope is None):
        raise ValueError("exactly one recovery identity is required")
    if acquisition_key is not None:
        _require_acquisition_key(acquisition_key)
    if scope is not None and scope.acquisition_stage is not stage:
        raise ValueError("source stage scope does not match stage")
    if not root.exists():
        return None
    matches: list[VerifiedPublicSourceStageArtifact] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        verified = load_verified_public_source_stage_artifact(path)
        if (
            verified.stage is stage
            and (
                verified.acquisition_key == acquisition_key
                if acquisition_key is not None
                else verified.scope == scope
            )
        ):
            matches.append(verified)
    if len(matches) > 1:
        raise ValueError("multiple acquisition stage Artifacts bind one request")
    return matches[0] if matches else None


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid source stage JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"source stage JSON must be object: {path.name}")
    return payload


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _raw_payload_hashes(batch: PublicCompositeBatch) -> list[dict[str, str]]:
    return sorted(
        (
            {
                "source_artifact_id": str(item.source_artifact_id),
                "raw_hash": item.raw_hash,
            }
            for item in batch.raw_payloads
        ),
        key=lambda item: item["source_artifact_id"],
    )


def _require_acquisition_key(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("acquisition_key must be a non-empty trimmed string")
