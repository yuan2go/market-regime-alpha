"""Shared lineage and validation, without a generic domain state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    normalize_canonical_datetime,
    require_sha256,
    require_text,
)


def _artifact_ids(label: str, values: tuple[ArtifactId, ...]) -> None:
    if not values:
        raise ValueError(f"{label} must not be empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    if tuple(sorted(values, key=str)) != values:
        raise ValueError(f"{label} must be sorted")


def parse_canonical_datetime(label: str, value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an RFC3339 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an RFC3339 string") from exc
    return normalize_canonical_datetime(parsed)


@dataclass(frozen=True, slots=True)
class StateLineage:
    """Exact upstream/runtime/model binding carried by every STATE artifact."""

    continuous_operation_id: ArtifactId
    runtime_tick_id: ArtifactId
    provider_attempt_ids: tuple[ArtifactId, ...]
    evidence_ids: tuple[ArtifactId, ...]
    dataset_id: DatasetId
    feature_id: ArtifactId
    source_artifact_ids: tuple[ArtifactId, ...]
    model_id: ModelId
    model_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    as_of_time: datetime
    available_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        _artifact_ids("provider_attempt_ids", self.provider_attempt_ids)
        _artifact_ids("evidence_ids", self.evidence_ids)
        _artifact_ids("source_artifact_ids", self.source_artifact_ids)
        require_text("model_version", self.model_version)
        require_sha256("configuration_hash", self.configuration_hash)
        as_of = normalize_canonical_datetime(self.as_of_time)
        available = normalize_canonical_datetime(self.available_at)
        created = normalize_canonical_datetime(self.created_at)
        if self.as_of_time != as_of or self.available_at != available:
            raise ValueError("State lineage times must use canonical whole-second UTC")
        if self.created_at != created:
            raise ValueError("created_at must use canonical whole-second UTC")
        if available > as_of:
            raise ValueError("available_at must not exceed as_of_time")

    def identity_payload(self) -> dict[str, Any]:
        """CreatedAt is audit metadata and deliberately excluded from identity."""

        return {
            "continuous_operation_id": str(self.continuous_operation_id),
            "runtime_tick_id": str(self.runtime_tick_id),
            "provider_attempt_ids": [str(value) for value in self.provider_attempt_ids],
            "evidence_ids": [str(value) for value in self.evidence_ids],
            "dataset_id": str(self.dataset_id),
            "feature_id": str(self.feature_id),
            "source_artifact_ids": [str(value) for value in self.source_artifact_ids],
            "model_id": str(self.model_id),
            "model_version": self.model_version,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "as_of_time": canonical_datetime(self.as_of_time),
            "available_at": canonical_datetime(self.available_at),
        }

    @property
    def lineage_hash(self) -> str:
        return canonical_hash(self.identity_payload())

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "created_at": canonical_datetime(self.created_at),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StateLineage:
        expected = {
            "continuous_operation_id",
            "runtime_tick_id",
            "provider_attempt_ids",
            "evidence_ids",
            "dataset_id",
            "feature_id",
            "source_artifact_ids",
            "model_id",
            "model_version",
            "configuration_id",
            "configuration_hash",
            "as_of_time",
            "available_at",
            "created_at",
        }
        if set(payload) != expected:
            raise ValueError("StateLineage fields mismatch")
        return cls(
            continuous_operation_id=ArtifactId(str(payload["continuous_operation_id"])),
            runtime_tick_id=ArtifactId(str(payload["runtime_tick_id"])),
            provider_attempt_ids=_read_ids("provider_attempt_ids", payload),
            evidence_ids=_read_ids("evidence_ids", payload),
            dataset_id=DatasetId(str(payload["dataset_id"])),
            feature_id=ArtifactId(str(payload["feature_id"])),
            source_artifact_ids=_read_ids("source_artifact_ids", payload),
            model_id=ModelId(str(payload["model_id"])),
            model_version=str(payload["model_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            as_of_time=parse_canonical_datetime("as_of_time", payload["as_of_time"]),
            available_at=parse_canonical_datetime("available_at", payload["available_at"]),
            created_at=parse_canonical_datetime("created_at", payload["created_at"]),
        )


def _read_ids(label: str, payload: Mapping[str, Any]) -> tuple[ArtifactId, ...]:
    value = payload[label]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(ArtifactId(item) for item in value)
