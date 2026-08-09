"""Immutable contracts for free-data preparation without another Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.providers.public_composite import (
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
)
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data import AssetType
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact


FREE_DATA_PREPARED_MANIFEST_SCHEMA = "free-data-prepared-input-manifest-v1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class FreeDataOperationScale(Enum):
    SMOKE = 20
    STANDARD = 100
    STRESS = 300

    @classmethod
    def from_symbol_count(cls, count: int) -> FreeDataOperationScale:
        if isinstance(count, bool):
            raise TypeError("symbol count must be an integer")
        try:
            return cls(count)
        except ValueError as exc:
            raise ValueError("free-data symbol count must be exactly 20, 100, or 300") from exc


@dataclass(frozen=True, slots=True)
class FreeDataInstrument:
    symbol: str
    asset_type: AssetType

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if not self.symbol.endswith((".SH", ".SZ", ".BJ")):
            raise ValueError("instrument symbol must use canonical SH/SZ/BJ identity")
        if not isinstance(self.asset_type, AssetType):
            raise TypeError("asset_type must be an AssetType")

    def to_canonical_dict(self) -> dict[str, str]:
        return {"symbol": self.symbol, "asset_type": self.asset_type.value}


@dataclass(frozen=True, slots=True)
class FreeDataPreparationRequest:
    scale: FreeDataOperationScale
    provider_profile_id: str
    decision_time: DecisionTime
    created_at: datetime
    code_revision: str
    instruments: tuple[FreeDataInstrument, ...]
    membership_source: str
    minimum_history_sessions: int
    liquidity_lookback_sessions: int
    minimum_median_daily_amount: Decimal
    configuration_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.scale, FreeDataOperationScale):
            raise TypeError("scale must be a FreeDataOperationScale")
        if self.provider_profile_id != TENCENT_FREE_OPERATIONAL_PROFILE_ID:
            raise ValueError("free-data preparation requires TENCENT_FREE_OPERATIONAL_V1")
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if (
            self.created_at.astimezone(_SHANGHAI).date()
            != self.decision_time.value.astimezone(_SHANGHAI).date()
        ):
            raise ValueError("created_at must share the Decision Time trading date")
        require_text("code_revision", self.code_revision)
        symbols = tuple(item.symbol for item in self.instruments)
        if len(symbols) != self.scale.value or symbols != tuple(sorted(set(symbols))):
            raise ValueError("instrument scope must be ordered, unique, and match scale")
        require_text("membership_source", self.membership_source)
        for label, value in (
            ("minimum_history_sessions", self.minimum_history_sessions),
            ("liquidity_lookback_sessions", self.liquidity_lookback_sessions),
        ):
            if isinstance(value, bool) or value <= 0:
                raise ValueError(f"{label} must be a positive integer")
        if self.liquidity_lookback_sessions < self.minimum_history_sessions:
            raise ValueError("liquidity lookback cannot be shorter than required history")
        if not isinstance(self.minimum_median_daily_amount, Decimal):
            raise TypeError("minimum_median_daily_amount must be Decimal")
        if self.minimum_median_daily_amount < 0:
            raise ValueError("minimum_median_daily_amount must be non-negative")
        require_sha256("configuration_hash", self.configuration_hash)

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(item.symbol for item in self.instruments)

    @property
    def asset_types(self) -> dict[str, AssetType]:
        return {item.symbol: item.asset_type for item in self.instruments}

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "scale": self.scale.name,
            "provider_profile_id": self.provider_profile_id,
            "decision_time": self.decision_time.isoformat(),
            "code_revision": self.code_revision,
            "instruments": [item.to_canonical_dict() for item in self.instruments],
            "membership_source": self.membership_source,
            "minimum_history_sessions": self.minimum_history_sessions,
            "liquidity_lookback_sessions": self.liquidity_lookback_sessions,
            "minimum_median_daily_amount": format(
                self.minimum_median_daily_amount, "f"
            ),
            "configuration_hash": self.configuration_hash,
        }

    @property
    def command_hash(self) -> str:
        return canonical_hash(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class PreparedArtifactReference:
    kind: str
    artifact_id: ArtifactId
    content_hash: str
    relative_locator: str

    def __post_init__(self) -> None:
        require_text("kind", self.kind)
        require_sha256("content_hash", self.content_hash)
        require_text("relative_locator", self.relative_locator)
        locator = Path(self.relative_locator)
        if locator.is_absolute() or ".." in locator.parts:
            raise ValueError("relative_locator must remain under the operation root")

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            "relative_locator": self.relative_locator,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> PreparedArtifactReference:
        if set(payload) != {
            "kind",
            "artifact_id",
            "content_hash",
            "relative_locator",
        }:
            raise ValueError("PreparedArtifactReference fields mismatch")
        return cls(
            kind=str(payload["kind"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            relative_locator=str(payload["relative_locator"]),
        )


@dataclass(frozen=True, slots=True)
class FreeDataPreparedManifest:
    schema_version: str
    manifest_id: ArtifactId
    content_hash: str
    command_hash: str
    configuration_hash: str
    provider_profile_id: str
    decision_time: datetime
    scale: FreeDataOperationScale
    artifacts: tuple[PreparedArtifactReference, ...]
    limitations: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        request: FreeDataPreparationRequest,
        artifacts: tuple[PreparedArtifactReference, ...],
        limitations: tuple[str, ...],
    ) -> FreeDataPreparedManifest:
        ordered = tuple(sorted(artifacts, key=lambda item: item.kind))
        ordered_limitations = tuple(sorted(set(limitations)))
        semantic = _prepared_payload(
            command_hash=request.command_hash,
            configuration_hash=request.configuration_hash,
            provider_profile_id=request.provider_profile_id,
            decision_time=request.decision_time.value,
            scale=request.scale,
            artifacts=ordered,
            limitations=ordered_limitations,
        )
        digest = canonical_hash(semantic)
        return cls(
            schema_version=FREE_DATA_PREPARED_MANIFEST_SCHEMA,
            manifest_id=ArtifactId(
                f"free-data-prepared-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            command_hash=request.command_hash,
            configuration_hash=request.configuration_hash,
            provider_profile_id=request.provider_profile_id,
            decision_time=request.decision_time.value,
            scale=request.scale,
            artifacts=ordered,
            limitations=ordered_limitations,
        )

    def __post_init__(self) -> None:
        if self.schema_version != FREE_DATA_PREPARED_MANIFEST_SCHEMA:
            raise ValueError("unsupported free-data prepared manifest")
        require_sha256("content_hash", self.content_hash)
        require_sha256("command_hash", self.command_hash)
        require_sha256("configuration_hash", self.configuration_hash)
        if self.provider_profile_id != TENCENT_FREE_OPERATIONAL_PROFILE_ID:
            raise ValueError("prepared manifest provider profile mismatch")
        if self.decision_time.tzinfo is None or self.decision_time.utcoffset() is None:
            raise ValueError("prepared Decision Time must be timezone-aware")
        kinds = tuple(item.kind for item in self.artifacts)
        if not kinds or kinds != tuple(sorted(set(kinds))):
            raise ValueError("prepared artifact kinds must be non-empty and ordered")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("prepared limitations must be unique and ordered")
        for required in (
            "EXPLORATORY",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ):
            if required not in self.limitations:
                raise ValueError("prepared authority ceiling is incomplete")
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("prepared manifest content hash mismatch")
        expected = f"free-data-prepared-{self.content_hash.split(':', 1)[1][:24]}"
        if str(self.manifest_id) != expected:
            raise ValueError("prepared manifest identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return _prepared_payload(
            command_hash=self.command_hash,
            configuration_hash=self.configuration_hash,
            provider_profile_id=self.provider_profile_id,
            decision_time=self.decision_time,
            scale=self.scale,
            artifacts=self.artifacts,
            limitations=self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": str(self.manifest_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FreeDataPreparedManifest:
        expected = {
            "schema_version",
            "manifest_id",
            "content_hash",
            "command_hash",
            "configuration_hash",
            "provider_profile_id",
            "decision_time",
            "scale",
            "artifacts",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("FreeDataPreparedManifest fields mismatch")
        raw_artifacts = payload["artifacts"]
        if not isinstance(raw_artifacts, list) or any(
            not isinstance(item, Mapping) for item in raw_artifacts
        ):
            raise ValueError("prepared artifacts must be an object array")
        return cls(
            schema_version=str(payload["schema_version"]),
            manifest_id=ArtifactId(str(payload["manifest_id"])),
            content_hash=str(payload["content_hash"]),
            command_hash=str(payload["command_hash"]),
            configuration_hash=str(payload["configuration_hash"]),
            provider_profile_id=str(payload["provider_profile_id"]),
            decision_time=datetime.fromisoformat(str(payload["decision_time"])),
            scale=FreeDataOperationScale[str(payload["scale"])],
            artifacts=tuple(
                PreparedArtifactReference.from_canonical_dict(item)
                for item in raw_artifacts
            ),
            limitations=tuple(str(item) for item in payload["limitations"]),
        )


@dataclass(frozen=True, slots=True)
class FreeDataPreparedPaths:
    history_source_stage: Path
    daily_source_manifest: Path
    full_source_manifest: Path
    daily_market_data: Path
    trading_calendar: Path
    operational_universe: Path
    supplemental_research_evidence: Path
    runtime_configuration: Path | None = None


@dataclass(frozen=True, slots=True)
class FreeDataPreparedInputs:
    manifest: FreeDataPreparedManifest
    manifest_path: Path
    paths: FreeDataPreparedPaths
    calendar: TradingCalendarArtifact


def publish_free_data_prepared_manifest(
    *, root: Path, manifest: FreeDataPreparedManifest
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    destination = root / str(manifest.manifest_id)
    if destination.exists():
        if load_free_data_prepared_manifest(destination) != manifest:
            raise ValueError("free-data prepared manifest identity conflict")
        return destination
    staging = Path(tempfile.mkdtemp(prefix=f".{manifest.manifest_id}.", dir=root))
    installed = False
    try:
        raw = (canonical_json(manifest.to_canonical_dict()) + "\n").encode()
        (staging / "artifact.json").write_bytes(raw)
        checksums = {"artifact.json": f"sha256:{sha256(raw).hexdigest()}"}
        (staging / "SHA256SUMS.json").write_text(
            canonical_json(checksums) + "\n", encoding="utf-8"
        )
        _fsync_directory(staging)
        os.replace(staging, destination)
        installed = True
        _fsync_directory(root)
    finally:
        if not installed and staging.exists():
            shutil.rmtree(staging)
    if load_free_data_prepared_manifest(destination) != manifest:
        raise ValueError("published free-data manifest mismatch")
    return destination


def load_free_data_prepared_manifest(path: Path) -> FreeDataPreparedManifest:
    root = path.resolve()
    if not root.is_dir() or {item.name for item in root.iterdir()} != {
        "SHA256SUMS.json",
        "artifact.json",
    }:
        raise ValueError("free-data prepared manifest exact file set mismatch")
    raw = (root / "artifact.json").read_bytes()
    checksums = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    if checksums != {"artifact.json": f"sha256:{sha256(raw).hexdigest()}"}:
        raise ValueError("free-data prepared manifest checksum mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != (canonical_json(payload) + "\n").encode():
        raise ValueError("free-data prepared manifest is not canonical")
    manifest = FreeDataPreparedManifest.from_canonical_dict(payload)
    if root.name != str(manifest.manifest_id):
        raise ValueError("free-data prepared manifest directory mismatch")
    return manifest


def _prepared_payload(
    *,
    command_hash: str,
    configuration_hash: str,
    provider_profile_id: str,
    decision_time: datetime,
    scale: FreeDataOperationScale,
    artifacts: tuple[PreparedArtifactReference, ...],
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": FREE_DATA_PREPARED_MANIFEST_SCHEMA,
        "command_hash": command_hash,
        "configuration_hash": configuration_hash,
        "provider_profile_id": provider_profile_id,
        "decision_time": decision_time.isoformat(),
        "scale": scale.name,
        "artifacts": [item.to_canonical_dict() for item in artifacts],
        "limitations": list(limitations),
    }


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "FREE_DATA_PREPARED_MANIFEST_SCHEMA",
    "FreeDataInstrument",
    "FreeDataOperationScale",
    "FreeDataPreparationRequest",
    "FreeDataPreparedInputs",
    "FreeDataPreparedManifest",
    "FreeDataPreparedPaths",
    "PreparedArtifactReference",
    "load_free_data_prepared_manifest",
    "publish_free_data_prepared_manifest",
]
