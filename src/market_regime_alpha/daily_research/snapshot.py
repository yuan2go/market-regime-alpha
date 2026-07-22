"""Immutable Decision-Time root snapshot and source-lineage contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, ClassVar, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    ModelId,
    ProviderId,
    UniverseId,
)
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.daily_research._contract_support import (
    DailyDataAuthority,
    canonical_content_hash,
    datetime_value,
    exact_fields,
    hash_value,
    identity,
    object_value,
    required_date,
    required_string,
)


DAILY_RESEARCH_SNAPSHOT_SCHEMA_VERSION = "daily-research-snapshot-v1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class DecisionSourceArtifact:
    """One exact source or upstream Artifact visible at the daily Decision Time."""

    artifact_id: ArtifactId
    provider_id: ProviderId
    content_hash: str
    observed_at: AsOfTime
    available_at: AvailabilityTime
    data_authority: DailyDataAuthority

    def __post_init__(self) -> None:
        hash_value("source content_hash", self.content_hash)
        if not isinstance(self.data_authority, DailyDataAuthority):
            raise TypeError("data_authority must be a DailyDataAuthority")
        if self.available_at.value < self.observed_at.value:
            raise ValueError("source available_at must not precede observed_at")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "provider_id": str(self.provider_id),
            "content_hash": self.content_hash,
            "observed_at": self.observed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "data_authority": self.data_authority.value,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DecisionSourceArtifact:
        exact_fields(
            payload,
            {"artifact_id", "provider_id", "content_hash", "observed_at", "available_at", "data_authority"},
            "Decision Source Artifact",
        )
        return cls(
            artifact_id=ArtifactId(required_string(payload["artifact_id"], "artifact_id")),
            provider_id=ProviderId(required_string(payload["provider_id"], "provider_id")),
            content_hash=required_string(payload["content_hash"], "content_hash"),
            observed_at=AsOfTime(datetime_value(payload["observed_at"], "observed_at")),
            available_at=AvailabilityTime(datetime_value(payload["available_at"], "available_at")),
            data_authority=DailyDataAuthority(required_string(payload["data_authority"], "data_authority")),
        )


@dataclass(frozen=True, slots=True)
class DailyResearchSnapshot:
    """Root information-state identity for one daily research decision."""

    schema_version: ClassVar[str] = DAILY_RESEARCH_SNAPSHOT_SCHEMA_VERSION

    decision_date: date
    decision_time: DecisionTime
    timezone: str
    universe_identity: UniverseId
    market_data_identity: DatasetId
    feature_registry_identity: ArtifactId
    registered_component_identities: tuple[ArtifactId, ...]
    model_identity: ModelId
    configuration_identity: ArtifactId
    market_context_identity: ArtifactId
    etf_snapshot_identity: ArtifactId
    theme_snapshot_identity: ArtifactId
    holdings_identity: ArtifactId
    source_artifacts: tuple[DecisionSourceArtifact, ...]
    data_authority: DailyDataAuthority
    created_at: AsOfTime
    snapshot_id: ArtifactId = field(init=False)
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.timezone != "Asia/Shanghai":
            raise ValueError("Daily Research Snapshot timezone must be Asia/Shanghai")
        if self.decision_time.value.utcoffset() != timedelta(hours=8):
            raise ValueError("Daily Research Snapshot Decision Time must use Asia/Shanghai offset")
        if self.decision_date != self.decision_time.value.astimezone(_SHANGHAI).date():
            raise ValueError("decision_date must equal the Asia/Shanghai Decision Time date")
        if self.created_at.value < self.decision_time.value:
            raise ValueError("created_at must not precede Decision Time")
        if not isinstance(self.data_authority, DailyDataAuthority):
            raise TypeError("data_authority must be a DailyDataAuthority")
        if not self.source_artifacts:
            raise ValueError("Daily Research Snapshot requires source_artifacts")
        source_ids = tuple(str(item.artifact_id) for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_artifacts must have unique Artifact IDs")
        if tuple(sorted(source_ids)) != source_ids:
            raise ValueError("source_artifacts must be sorted by Artifact ID")
        registered_ids = tuple(str(item) for item in self.registered_component_identities)
        if not registered_ids:
            raise ValueError("registered_component_identities must not be empty")
        if len(registered_ids) != len(set(registered_ids)):
            raise ValueError("registered_component_identities must be unique")
        if tuple(sorted(registered_ids)) != registered_ids:
            raise ValueError("registered_component_identities must be sorted")
        missing_lineage = self._upstream_identities() - set(source_ids)
        if missing_lineage:
            raise ValueError(
                "Daily Research Snapshot upstream identities must have source Artifact lineage: "
                + ", ".join(sorted(missing_lineage))
            )
        for source in self.source_artifacts:
            if source.data_authority is not self.data_authority:
                raise ValueError("source Artifact authority must match snapshot authority")
            if source.observed_at.value > self.decision_time.value:
                raise ValueError("source observed_at is after Decision Time")
            if source.available_at.value > self.decision_time.value:
                raise ValueError("source available_at is after Decision Time")
        digest = canonical_content_hash(self._identity_payload())
        prefix = (
            "test-only-daily-snapshot"
            if self.data_authority is DailyDataAuthority.TEST_ONLY_NOT_RESEARCH_EVIDENCE
            else "daily-snapshot"
        )
        object.__setattr__(self, "content_hash", digest)
        object.__setattr__(self, "snapshot_id", identity(prefix, digest))

    def _upstream_identities(self) -> set[str]:
        return {
            str(self.universe_identity),
            str(self.market_data_identity),
            str(self.feature_registry_identity),
            str(self.model_identity),
            str(self.configuration_identity),
            str(self.market_context_identity),
            str(self.etf_snapshot_identity),
            str(self.theme_snapshot_identity),
            str(self.holdings_identity),
            *(str(item) for item in self.registered_component_identities),
        }

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_date": self.decision_date.isoformat(),
            "decision_time": self.decision_time.isoformat(),
            "timezone": self.timezone,
            "universe_identity": str(self.universe_identity),
            "market_data_identity": str(self.market_data_identity),
            "feature_registry_identity": str(self.feature_registry_identity),
            "registered_component_identities": [
                str(item) for item in self.registered_component_identities
            ],
            "model_identity": str(self.model_identity),
            "configuration_identity": str(self.configuration_identity),
            "market_context_identity": str(self.market_context_identity),
            "etf_snapshot_identity": str(self.etf_snapshot_identity),
            "theme_snapshot_identity": str(self.theme_snapshot_identity),
            "holdings_identity": str(self.holdings_identity),
            "source_artifacts": [item.to_canonical_dict() for item in self.source_artifacts],
            "data_authority": self.data_authority.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self._identity_payload(),
            "snapshot_id": str(self.snapshot_id),
            "created_at": self.created_at.isoformat(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DailyResearchSnapshot:
        expected = {
            "schema_version", "snapshot_id", "decision_date", "decision_time", "timezone",
            "universe_identity", "market_data_identity", "feature_registry_identity",
            "registered_component_identities",
            "model_identity", "configuration_identity", "market_context_identity",
            "etf_snapshot_identity", "theme_snapshot_identity", "holdings_identity",
            "source_artifacts", "data_authority", "created_at", "content_hash",
        }
        exact_fields(payload, expected, "Daily Research Snapshot")
        if payload["schema_version"] != cls.schema_version:
            raise ValueError("Daily Research Snapshot Schema mismatch")
        raw_sources = payload["source_artifacts"]
        if not isinstance(raw_sources, list):
            raise ValueError("source_artifacts must be an array")
        raw_registered = payload["registered_component_identities"]
        if not isinstance(raw_registered, list):
            raise ValueError("registered_component_identities must be an array")
        snapshot = cls(
            decision_date=required_date(payload["decision_date"], "decision_date"),
            decision_time=DecisionTime(datetime_value(payload["decision_time"], "decision_time")),
            timezone=required_string(payload["timezone"], "timezone"),
            universe_identity=UniverseId(required_string(payload["universe_identity"], "universe_identity")),
            market_data_identity=DatasetId(required_string(payload["market_data_identity"], "market_data_identity")),
            feature_registry_identity=ArtifactId(required_string(payload["feature_registry_identity"], "feature_registry_identity")),
            registered_component_identities=tuple(
                ArtifactId(required_string(item, "registered component identity"))
                for item in raw_registered
            ),
            model_identity=ModelId(required_string(payload["model_identity"], "model_identity")),
            configuration_identity=ArtifactId(required_string(payload["configuration_identity"], "configuration_identity")),
            market_context_identity=ArtifactId(required_string(payload["market_context_identity"], "market_context_identity")),
            etf_snapshot_identity=ArtifactId(required_string(payload["etf_snapshot_identity"], "etf_snapshot_identity")),
            theme_snapshot_identity=ArtifactId(required_string(payload["theme_snapshot_identity"], "theme_snapshot_identity")),
            holdings_identity=ArtifactId(required_string(payload["holdings_identity"], "holdings_identity")),
            source_artifacts=tuple(
                DecisionSourceArtifact.from_canonical_dict(object_value(item, "source Artifact"))
                for item in raw_sources
            ),
            data_authority=DailyDataAuthority(required_string(payload["data_authority"], "data_authority")),
            created_at=AsOfTime(datetime_value(payload["created_at"], "created_at")),
        )
        if str(snapshot.snapshot_id) != payload["snapshot_id"] or snapshot.content_hash != payload["content_hash"]:
            raise ValueError("Daily Research Snapshot identity mismatch")
        return snapshot
