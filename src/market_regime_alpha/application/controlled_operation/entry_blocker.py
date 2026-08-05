"""Immutable fail-closed Entry blocker for Controlled operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
)
from market_regime_alpha.forecasting.artifact import VerifiedPathForecastArtifact
from market_regime_alpha.forecasting.contracts import CalibrationStatus, PathForecastStatus
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second
from market_regime_alpha.signals.contracts import SignalState
from market_regime_alpha.signals.v3 import VerifiedSignalRunArtifactV3


CONTROLLED_ENTRY_BLOCKER_SCHEMA = "controlled-entry-assessment-blocker-v1"


@dataclass(frozen=True, slots=True)
class ControlledEntryAssessmentBlocker:
    schema_version: str
    artifact_id: ArtifactId
    content_hash: str
    signal_artifact_id: ArtifactId
    signal_artifact_hash: str
    forecast_references: tuple[tuple[ArtifactId, str], ...]
    assessment_state: str
    reason_codes: tuple[str, ...]
    created_at: datetime
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTROLLED_ENTRY_BLOCKER_SCHEMA:
            raise ValueError("unsupported Controlled Entry blocker schema")
        require_sha256("content_hash", self.content_hash)
        require_sha256("signal_artifact_hash", self.signal_artifact_hash)
        require_utc_second("created_at", self.created_at)
        if self.assessment_state != "BLOCKED":
            raise ValueError("Controlled Entry assessment must remain BLOCKED")
        keys = tuple((str(item), digest) for item, digest in self.forecast_references)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("Entry forecast references must be unique and sorted")
        for _, digest in self.forecast_references:
            require_sha256("forecast hash", digest)
        if not self.reason_codes or self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Entry blocker reason codes must be non-empty and sorted")
        if "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE" not in self.reason_codes:
            raise ValueError("Entry validation blocker is missing")
        for required in ("NO_ORDER_CREATED", "NO_BROKER_INVOKED", "NO_FILL_CREATED"):
            if required not in self.limitations:
                raise ValueError("Entry execution authority ceiling is incomplete")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        signal: VerifiedSignalRunArtifactV3,
        forecasts: tuple[VerifiedPathForecastArtifact, ...],
        created_at: datetime,
    ) -> ControlledEntryAssessmentBlocker:
        snapshots = signal.artifact.snapshots
        by_signal = {
            item.artifact.signal_snapshot.envelope.artifact_id: item
            for item in forecasts
        }
        expected = {item.envelope.artifact_id for item in snapshots}
        if set(by_signal) != expected:
            raise ValueError("Entry blocker requires one PathForecast per Signal snapshot")
        if any(
            by_signal[item.envelope.artifact_id].artifact.signal_snapshot != item
            for item in snapshots
        ):
            raise ValueError("Entry blocker PathForecast Signal binding mismatch")
        reasons = {"ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE"}
        if not snapshots or any(item.signal_state is SignalState.DATA_INSUFFICIENT for item in snapshots):
            reasons.add("SIGNAL_DATA_INSUFFICIENT")
        if not forecasts or any(
            item.artifact.forecast.forecast_status is PathForecastStatus.DATA_INSUFFICIENT
            for item in forecasts
        ):
            reasons.add("PATH_FORECAST_DATA_INSUFFICIENT")
        if not forecasts or any(
            item.artifact.forecast.calibration_status
            is not CalibrationStatus.CALIBRATED_EXPLORATORY
            for item in forecasts
        ):
            reasons.add("PATH_FORECAST_NOT_CALIBRATED")
        references = tuple(
            sorted(
                (
                    (
                        item.artifact.artifact_id,
                        item.artifact.forecast.envelope.content_hash,
                    )
                    for item in forecasts
                ),
                key=lambda value: str(value[0]),
            )
        )
        values = {
            "signal_artifact_id": signal.artifact.artifact_id,
            "signal_artifact_hash": signal.artifact.envelope.content_hash,
            "forecast_references": references,
            "assessment_state": "BLOCKED",
            "reason_codes": tuple(sorted(reasons)),
            "created_at": created_at,
            "limitations": (
                "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                "NO_BROKER_INVOKED",
                "NO_FILL_CREATED",
                "NO_ORDER_CREATED",
                "TRADING_AUTHORITY_NOT_GRANTED",
            ),
        }
        digest = canonical_hash(_payload(**values))
        return cls(
            schema_version=CONTROLLED_ENTRY_BLOCKER_SCHEMA,
            artifact_id=ArtifactId(f"entry-blocker-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(**_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Controlled Entry blocker hash mismatch")
        if str(self.artifact_id) != f"entry-blocker-{digest.split(':', 1)[1][:24]}":
            raise ValueError("Controlled Entry blocker identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ControlledEntryAssessmentBlocker:
        expected = {
            "schema_version", "artifact_id", "content_hash", "signal_artifact_id",
            "signal_artifact_hash", "forecast_references", "assessment_state",
            "reason_codes", "created_at", "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Controlled Entry blocker fields mismatch")
        refs = payload["forecast_references"]
        if not isinstance(refs, list) or any(not isinstance(item, dict) for item in refs):
            raise ValueError("forecast_references must be an object array")
        return cls(
            schema_version=str(payload["schema_version"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            signal_artifact_id=ArtifactId(str(payload["signal_artifact_id"])),
            signal_artifact_hash=str(payload["signal_artifact_hash"]),
            forecast_references=tuple(
                (ArtifactId(str(item["artifact_id"])), str(item["content_hash"]))
                for item in refs
            ),
            assessment_state=str(payload["assessment_state"]),
            reason_codes=_strings(payload["reason_codes"], "reason codes"),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            limitations=_strings(payload["limitations"], "limitations"),
        )


def publish_controlled_entry_blocker(
    *, root: Path, artifact: ControlledEntryAssessmentBlocker
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.artifact_id)
    if final.exists():
        if load_controlled_entry_blocker(final) != artifact:
            raise FileExistsError("conflicting Controlled Entry blocker exists")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        encoded = (canonical_json(artifact.to_canonical_dict()) + "\n").encode()
        (stage / "artifact.json").write_bytes(encoded)
        _write_json(stage / "SHA256SUMS.json", {"artifact.json": f"sha256:{sha256(encoded).hexdigest()}"})
        _load(stage, enforce_directory_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_controlled_entry_blocker(path: Path) -> ControlledEntryAssessmentBlocker:
    return _load(path, enforce_directory_identity=True)


def _load(path: Path, *, enforce_directory_identity: bool) -> ControlledEntryAssessmentBlocker:
    root = path.resolve()
    if not root.is_dir() or {item.name for item in root.iterdir()} != {
        "artifact.json", "SHA256SUMS.json"
    }:
        raise ValueError("Controlled Entry blocker exact file set mismatch")
    raw = (root / "artifact.json").read_bytes()
    checksums = _read_json(root / "SHA256SUMS.json")
    if checksums != {"artifact.json": f"sha256:{sha256(raw).hexdigest()}"}:
        raise ValueError("Controlled Entry blocker checksum mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != (canonical_json(payload) + "\n").encode():
        raise ValueError("Controlled Entry blocker JSON is not canonical")
    artifact = ControlledEntryAssessmentBlocker.from_canonical_dict(payload)
    if enforce_directory_identity and root.name != str(artifact.artifact_id):
        raise ValueError("Controlled Entry blocker directory identity mismatch")
    return artifact


def _values(item: ControlledEntryAssessmentBlocker) -> dict[str, Any]:
    return {
        "signal_artifact_id": item.signal_artifact_id,
        "signal_artifact_hash": item.signal_artifact_hash,
        "forecast_references": item.forecast_references,
        "assessment_state": item.assessment_state,
        "reason_codes": item.reason_codes,
        "created_at": item.created_at,
        "limitations": item.limitations,
    }


def _payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTROLLED_ENTRY_BLOCKER_SCHEMA,
        "signal_artifact_id": str(values["signal_artifact_id"]),
        "signal_artifact_hash": values["signal_artifact_hash"],
        "forecast_references": [
            {"artifact_id": str(item), "content_hash": digest}
            for item, digest in values["forecast_references"]
        ],
        "assessment_state": values["assessment_state"],
        "reason_codes": list(values["reason_codes"]),
        "created_at": canonical_datetime(values["created_at"]),
        "limitations": list(values["limitations"]),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("Controlled Entry blocker checksum file must be an object")
    return payload


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _fsync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "ControlledEntryAssessmentBlocker",
    "load_controlled_entry_blocker",
    "publish_controlled_entry_blocker",
]
