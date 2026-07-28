"""Canonical field-level SourceManifest for the Phase D daily loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import (
    DataEligibility,
    SourceArtifactReference,
)


class CriticalSourceFact(str, Enum):
    """Facts whose absence can make a daily decision unusable."""

    PRICE = "PRICE"
    DECISION_TIME = "DECISION_TIME"
    AVAILABLE_TIME = "AVAILABLE_TIME"
    TRADING_STATUS = "TRADING_STATUS"
    HISTORY_WINDOW = "HISTORY_WINDOW"
    UNIVERSE_MEMBERSHIP = "UNIVERSE_MEMBERSHIP"
    ELIGIBILITY = "ELIGIBILITY"


class SourceFieldFinality(str, Enum):
    PRELIMINARY = "PRELIMINARY"
    FINAL = "FINAL"
    UNKNOWN = "UNKNOWN"


class SourceFieldQualityStatus(str, Enum):
    COMPLETE = "COMPLETE"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


def _require_text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_aware(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class SourceManifestField:
    """Lineage and temporal semantics for one normalized decision input."""

    field_id: str
    symbol: str | None
    critical_fact: CriticalSourceFact | None
    provider_id: ProviderId
    source_artifact_id: ArtifactId
    event_time: datetime | None
    available_time: AvailabilityTime | None
    retrieved_time: RetrievedAt
    decision_time: DecisionTime
    unit: str
    adjustment_basis: str
    finality: SourceFieldFinality
    data_eligibility: DataEligibility
    quality_status: SourceFieldQualityStatus
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text("field_id", self.field_id)
        if self.symbol is not None:
            _require_text("symbol", self.symbol)
        if self.event_time is not None:
            _require_aware("event_time", self.event_time)
        if not isinstance(self.retrieved_time, RetrievedAt):
            raise TypeError("retrieved_time must be a RetrievedAt")
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        _require_text("unit", self.unit)
        _require_text("adjustment_basis", self.adjustment_basis)
        if not isinstance(self.finality, SourceFieldFinality):
            raise TypeError("finality must be a SourceFieldFinality")
        if not isinstance(self.data_eligibility, DataEligibility):
            raise TypeError("data_eligibility must be a DataEligibility")
        if not isinstance(self.quality_status, SourceFieldQualityStatus):
            raise TypeError("quality_status must be a SourceFieldQualityStatus")
        for reason in self.reason_codes:
            _require_text("reason_code", reason)
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes must be unique")
        if (
            self.quality_status is SourceFieldQualityStatus.COMPLETE
            and self.reason_codes
        ):
            raise ValueError("COMPLETE field cannot carry reason_codes")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "symbol": self.symbol,
            "critical_fact": (
                self.critical_fact.value if self.critical_fact is not None else None
            ),
            "provider_id": str(self.provider_id),
            "source_artifact_id": str(self.source_artifact_id),
            "event_time": (
                self.event_time.isoformat() if self.event_time is not None else None
            ),
            "available_time": (
                self.available_time.isoformat()
                if self.available_time is not None
                else None
            ),
            "retrieved_time": self.retrieved_time.isoformat(),
            "decision_time": self.decision_time.isoformat(),
            "unit": self.unit,
            "adjustment_basis": self.adjustment_basis,
            "finality": self.finality.value,
            "data_eligibility": self.data_eligibility.value,
            "quality_status": self.quality_status.value,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> SourceManifestField:
        expected = {
            "field_id",
            "symbol",
            "critical_fact",
            "provider_id",
            "source_artifact_id",
            "event_time",
            "available_time",
            "retrieved_time",
            "decision_time",
            "unit",
            "adjustment_basis",
            "finality",
            "data_eligibility",
            "quality_status",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("SourceManifestField fields mismatch")
        event_time = payload["event_time"]
        available_time = payload["available_time"]
        critical_fact = payload["critical_fact"]
        return cls(
            field_id=str(payload["field_id"]),
            symbol=(
                str(payload["symbol"]) if payload["symbol"] is not None else None
            ),
            critical_fact=(
                CriticalSourceFact(str(critical_fact))
                if critical_fact is not None
                else None
            ),
            provider_id=ProviderId(str(payload["provider_id"])),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            event_time=(
                datetime.fromisoformat(str(event_time))
                if event_time is not None
                else None
            ),
            available_time=(
                AvailabilityTime(datetime.fromisoformat(str(available_time)))
                if available_time is not None
                else None
            ),
            retrieved_time=RetrievedAt(
                datetime.fromisoformat(str(payload["retrieved_time"]))
            ),
            decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["decision_time"]))
            ),
            unit=str(payload["unit"]),
            adjustment_basis=str(payload["adjustment_basis"]),
            finality=SourceFieldFinality(str(payload["finality"])),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            quality_status=SourceFieldQualityStatus(str(payload["quality_status"])),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class SourceManifest:
    """Content-addressed Source Freeze evidence."""

    SCHEMA_VERSION = "phase-d-source-manifest-v1"

    provider_profile_id: str
    decision_time: DecisionTime
    source_artifacts: tuple[SourceArtifactReference, ...]
    fields: tuple[SourceManifestField, ...]
    source_conflicts: tuple[str, ...]
    limitations: tuple[str, ...]
    data_eligibility: DataEligibility
    content_hash: str = field(init=False)
    source_manifest_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        _require_text("provider_profile_id", self.provider_profile_id)
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        if not self.source_artifacts:
            raise ValueError("source_artifacts must not be empty")
        artifact_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("source_artifacts must be unique")
        artifact_scope = {
            (item.provider_id, item.artifact_id) for item in self.source_artifacts
        }
        field_keys: list[tuple[str | None, str]] = []
        for item in self.fields:
            if item.decision_time != self.decision_time:
                raise ValueError("field Decision Time does not match SourceManifest")
            if (item.provider_id, item.source_artifact_id) not in artifact_scope:
                raise ValueError("field references an unlisted source artifact")
            if item.data_eligibility is not DataEligibility.EXPLORATORY:
                raise ValueError("Phase D public SourceManifest is EXPLORATORY-only")
            field_keys.append((item.symbol, item.field_id))
        if len(field_keys) != len(set(field_keys)):
            raise ValueError("field_id must be unique within symbol")
        for values in (self.source_conflicts, self.limitations):
            for value in values:
                _require_text("manifest declaration", value)
            if len(values) != len(set(values)):
                raise ValueError("manifest declarations must be unique")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Phase D public SourceManifest is EXPLORATORY-only")
        content_hash = _canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "source_manifest_id",
            ArtifactId(f"source-manifest-{content_hash.split(':', 1)[1][:24]}"),
        )

    @property
    def source_hashes(self) -> tuple[str, ...]:
        return tuple(item.content_hash for item in self.source_artifacts)

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "provider_profile_id": self.provider_profile_id,
            "decision_time": self.decision_time.isoformat(),
            "source_artifacts": [
                {
                    "artifact_id": str(item.artifact_id),
                    "provider_id": str(item.provider_id),
                    "retrieved_time": item.retrieved_at.isoformat(),
                    "content_hash": item.content_hash,
                    "locator": item.locator,
                }
                for item in self.source_artifacts
            ],
            "fields": [item.to_canonical_dict() for item in self.fields],
            "source_conflicts": list(self.source_conflicts),
            "limitations": list(self.limitations),
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "source_manifest_id": str(self.source_manifest_id),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SourceManifest:
        expected = {
            "schema_version",
            "provider_profile_id",
            "decision_time",
            "source_artifacts",
            "fields",
            "source_conflicts",
            "limitations",
            "data_eligibility",
            "content_hash",
            "source_manifest_id",
        }
        if set(payload) != expected:
            raise ValueError("SourceManifest fields mismatch")
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported SourceManifest schema")
        artifacts = tuple(
            SourceArtifactReference(
                artifact_id=ArtifactId(str(item["artifact_id"])),
                provider_id=ProviderId(str(item["provider_id"])),
                retrieved_at=RetrievedAt(
                    datetime.fromisoformat(str(item["retrieved_time"]))
                ),
                content_hash=str(item["content_hash"]),
                locator=str(item["locator"]),
            )
            for item in payload["source_artifacts"]
        )
        manifest = cls(
            provider_profile_id=str(payload["provider_profile_id"]),
            decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["decision_time"]))
            ),
            source_artifacts=artifacts,
            fields=tuple(
                SourceManifestField.from_canonical_dict(item)
                for item in payload["fields"]
            ),
            source_conflicts=tuple(
                str(item) for item in payload["source_conflicts"]
            ),
            limitations=tuple(str(item) for item in payload["limitations"]),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if (
            manifest.content_hash != payload["content_hash"]
            or str(manifest.source_manifest_id) != payload["source_manifest_id"]
        ):
            raise ValueError("SourceManifest identity mismatch")
        return manifest
