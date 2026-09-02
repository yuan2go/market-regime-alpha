"""Immutable two-lane Market archive and dual-clock contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.market.domain.vocabulary import BarTimeframe, PriceBasis
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


def _hash(value: ContentHash | str) -> ContentHash:
    return value if isinstance(value, ContentHash) else ContentHash(value)


class ArchiveLane(StrEnum):
    RETROSPECTIVE_BACKFILL = "RETROSPECTIVE_BACKFILL"
    PROSPECTIVE_CONTEMPORANEOUS = "PROSPECTIVE_CONTEMPORANEOUS"


class ArchiveEvidenceClass(StrEnum):
    EXPLORATORY_RETROSPECTIVE = "EXPLORATORY_RETROSPECTIVE"
    FIRST_PARTY_CONTEMPORANEOUS = "FIRST_PARTY_CONTEMPORANEOUS"


class ArchiveSliceStatus(StrEnum):
    PLANNED = "PLANNED"
    CAPTURED = "CAPTURED"
    GAP_RECORDED = "GAP_RECORDED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"

    @property
    def is_terminal(self) -> bool:
        return self is not ArchiveSliceStatus.PLANNED


class ArchiveSealDisposition(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL_WITH_GAPS = "PARTIAL_WITH_GAPS"
    PARTIAL_WITH_RESOURCE_LIMIT = "PARTIAL_WITH_RESOURCE_LIMIT"


class ArchiveObservationRelation(StrEnum):
    FIRST = "FIRST"
    IDENTICAL = "IDENTICAL"
    CHANGED = "CHANGED"
    FAILED = "FAILED"


class ArchiveObservationTimeliness(StrEnum):
    ON_TIME = "ON_TIME"
    LATE = "LATE"
    MISSED = "MISSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class MarketArchiveSlice:
    market_archive_slice_id: UUID
    market_archive_id: UUID
    ordinal: int
    scope_key: str
    event_window_start: datetime
    event_window_end: datetime
    request_sha256: ContentHash | str
    expected_fact_kind: str
    status: ArchiveSliceStatus
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("archive slice ordinal must be positive")
        if not self.scope_key or len(self.scope_key) > 200:
            raise ValueError("archive slice scope_key is required")
        start = require_utc(self.event_window_start, field="event_window_start")
        end = require_utc(self.event_window_end, field="event_window_end")
        if end < start:
            raise ValueError("archive slice event window is invalid")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.expected_fact_kind):
            raise ValueError("expected_fact_kind has an invalid format")
        if not isinstance(self.status, ArchiveSliceStatus):
            raise TypeError("status must be ArchiveSliceStatus")
        request_hash = _hash(self.request_sha256)
        object.__setattr__(self, "event_window_start", start)
        object.__setattr__(self, "event_window_end", end)
        object.__setattr__(self, "request_sha256", request_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "event_window_end": end,
                        "event_window_start": start,
                        "expected_fact_kind": self.expected_fact_kind,
                        "market_archive_id": self.market_archive_id,
                        "market_archive_slice_id": self.market_archive_slice_id,
                        "ordinal": self.ordinal,
                        "request_sha256": str(request_hash),
                        "scope_key": self.scope_key,
                        "status": self.status,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class MarketArchive:
    market_archive_id: UUID
    lane: ArchiveLane
    provider_product_id: UUID
    exchange_code: str
    timeframe: BarTimeframe
    price_basis: PriceBasis
    instrument_scope: str
    instrument_scope_sha256: ContentHash | str
    event_window_start: datetime
    event_window_end: datetime
    archive_start_at: datetime
    reserved_free_bytes: int
    maximum_archive_bytes: int
    maximum_slice_bytes: int
    code_artifact_id: UUID
    config_artifact_id: UUID
    provenance_sha256: ContentHash | str
    slices: tuple[MarketArchiveSlice, ...]
    evidence_class: ArchiveEvidenceClass = field(init=False)
    slice_count: int = field(init=False)
    slice_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.lane, ArchiveLane):
            raise TypeError("lane must be ArchiveLane")
        if not isinstance(self.timeframe, BarTimeframe):
            raise TypeError("timeframe must be BarTimeframe")
        if not isinstance(self.price_basis, PriceBasis):
            raise TypeError("price_basis must be PriceBasis")
        if not re.fullmatch(r"[A-Z][A-Z0-9]{1,15}", self.exchange_code):
            raise ValueError("exchange_code has an invalid format")
        if not self.instrument_scope or len(self.instrument_scope) > 200:
            raise ValueError("instrument_scope is required")
        window_start = require_utc(self.event_window_start, field="event_window_start")
        window_end = require_utc(self.event_window_end, field="event_window_end")
        archive_start = require_utc(self.archive_start_at, field="archive_start_at")
        if window_end < window_start:
            raise ValueError("archive event window is invalid")
        if (
            self.lane is ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS
            and window_start < archive_start
        ):
            raise ValueError("prospective event window cannot precede archive start")
        for name in (
            "reserved_free_bytes",
            "maximum_archive_bytes",
            "maximum_slice_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be positive")
        if self.maximum_slice_bytes > self.maximum_archive_bytes:
            raise ValueError("maximum_slice_bytes cannot exceed maximum_archive_bytes")
        if not self.slices:
            raise ValueError("archive slice roster must be non-empty")
        if any(item.market_archive_id != self.market_archive_id for item in self.slices):
            raise ValueError("archive slice belongs to another archive")
        if tuple(item.ordinal for item in self.slices) != tuple(
            range(1, len(self.slices) + 1)
        ):
            raise ValueError("archive slice ordinals must be contiguous")
        if any(
            item.event_window_start < window_start or item.event_window_end > window_end
            for item in self.slices
        ):
            raise ValueError("archive slice lies outside the archive event window")
        scope_hash = _hash(self.instrument_scope_sha256)
        provenance_hash = _hash(self.provenance_sha256)
        roster_hash = ContentHash(
            canonical_json_sha256(
                [
                    {
                        "content_sha256": str(item.content_sha256),
                        "ordinal": item.ordinal,
                    }
                    for item in self.slices
                ]
            )
        )
        evidence_class = (
            ArchiveEvidenceClass.EXPLORATORY_RETROSPECTIVE
            if self.lane is ArchiveLane.RETROSPECTIVE_BACKFILL
            else ArchiveEvidenceClass.FIRST_PARTY_CONTEMPORANEOUS
        )
        object.__setattr__(self, "event_window_start", window_start)
        object.__setattr__(self, "event_window_end", window_end)
        object.__setattr__(self, "archive_start_at", archive_start)
        object.__setattr__(self, "instrument_scope_sha256", scope_hash)
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(self, "evidence_class", evidence_class)
        object.__setattr__(self, "slice_count", len(self.slices))
        object.__setattr__(self, "slice_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "archive_start_at": archive_start,
                        "code_artifact_id": self.code_artifact_id,
                        "config_artifact_id": self.config_artifact_id,
                        "event_window_end": window_end,
                        "event_window_start": window_start,
                        "evidence_class": evidence_class,
                        "exchange_code": self.exchange_code,
                        "instrument_scope": self.instrument_scope,
                        "instrument_scope_sha256": str(scope_hash),
                        "lane": self.lane,
                        "market_archive_id": self.market_archive_id,
                        "maximum_archive_bytes": self.maximum_archive_bytes,
                        "maximum_slice_bytes": self.maximum_slice_bytes,
                        "price_basis": self.price_basis,
                        "provenance_sha256": str(provenance_hash),
                        "provider_product_id": self.provider_product_id,
                        "reserved_free_bytes": self.reserved_free_bytes,
                        "slice_count": len(self.slices),
                        "slice_roster_sha256": str(roster_hash),
                        "timeframe": self.timeframe,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ArchiveCaptureObservation:
    market_archive_capture_observation_id: UUID
    market_archive_id: UUID
    market_archive_slice_id: UUID
    capture_id: UUID
    observation_ordinal: int
    previous_observation_id: UUID | None
    schedule_slot: str
    requested_at: datetime
    capture_started_at: datetime
    capture_completed_at: datetime
    recorded_at: datetime
    known_at: datetime
    event_window_start: datetime
    event_window_end: datetime
    artifact_sha256: ContentHash | str
    artifact_size_bytes: int
    normalized_revision_count: int
    normalized_revision_roster_sha256: ContentHash | str
    relation: ArchiveObservationRelation
    timeliness: ArchiveObservationTimeliness
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.observation_ordinal, bool) or self.observation_ordinal < 1:
            raise ValueError("observation_ordinal must be positive")
        if (self.observation_ordinal == 1) != (self.previous_observation_id is None):
            raise ValueError("archive observation revision chain is invalid")
        if (self.observation_ordinal == 1) != (
            self.relation is ArchiveObservationRelation.FIRST
        ):
            raise ValueError("archive observation FIRST relation is invalid")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.schedule_slot):
            raise ValueError("schedule_slot has an invalid format")
        if not isinstance(self.relation, ArchiveObservationRelation):
            raise TypeError("relation must be ArchiveObservationRelation")
        if not isinstance(self.timeliness, ArchiveObservationTimeliness):
            raise TypeError("timeliness must be ArchiveObservationTimeliness")
        requested = require_utc(self.requested_at, field="requested_at")
        started = require_utc(self.capture_started_at, field="capture_started_at")
        completed = require_utc(self.capture_completed_at, field="capture_completed_at")
        recorded = require_utc(self.recorded_at, field="recorded_at")
        known = require_utc(self.known_at, field="known_at")
        event_start = require_utc(self.event_window_start, field="event_window_start")
        event_end = require_utc(self.event_window_end, field="event_window_end")
        if not requested <= started <= completed <= recorded:
            raise ValueError("archive observation capture times are out of order")
        if known != max(completed, recorded):
            raise ValueError("archive observation known_at must equal max capture-completed/recorded time")
        if event_end < event_start:
            raise ValueError("archive observation event window is invalid")
        for name in ("artifact_size_bytes", "normalized_revision_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be non-negative")
        artifact_hash = _hash(self.artifact_sha256)
        revision_hash = _hash(self.normalized_revision_roster_sha256)
        for name, value in (
            ("requested_at", requested),
            ("capture_started_at", started),
            ("capture_completed_at", completed),
            ("recorded_at", recorded),
            ("known_at", known),
            ("event_window_start", event_start),
            ("event_window_end", event_end),
            ("artifact_sha256", artifact_hash),
            ("normalized_revision_roster_sha256", revision_hash),
        ):
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        name: getattr(self, name)
                        for name in self.__dataclass_fields__
                        if name != "content_sha256"
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class MarketArchiveSeal:
    market_archive_seal_id: UUID
    market_archive_id: UUID
    sealed_at: datetime
    knowledge_cutoff: datetime
    disposition: ArchiveSealDisposition
    slice_count: int
    slice_roster_sha256: ContentHash
    capture_count: int
    capture_roster_sha256: ContentHash
    artifact_count: int
    artifact_roster_sha256: ContentHash
    normalized_revision_count: int
    normalized_revision_roster_sha256: ContentHash
    gap_count: int
    gap_roster_sha256: ContentHash
    content_sha256: ContentHash

    @classmethod
    def create(
        cls,
        *,
        market_archive_seal_id: UUID,
        archive: MarketArchive,
        terminal_slices: tuple[MarketArchiveSlice, ...],
        sealed_at: datetime,
        disposition: ArchiveSealDisposition,
        capture_count: int,
        capture_roster_sha256: ContentHash | str,
        artifact_count: int,
        artifact_roster_sha256: ContentHash | str,
        normalized_revision_count: int,
        normalized_revision_roster_sha256: ContentHash | str,
        gap_count: int,
        gap_roster_sha256: ContentHash | str,
    ) -> MarketArchiveSeal:
        if archive.lane is not ArchiveLane.RETROSPECTIVE_BACKFILL:
            raise ValueError("only a retrospective archive may be sealed")
        if not isinstance(disposition, ArchiveSealDisposition):
            raise TypeError("disposition must be ArchiveSealDisposition")
        if len(terminal_slices) != archive.slice_count or any(
            not item.status.is_terminal for item in terminal_slices
        ):
            raise ValueError("every archive slice must be terminal")
        if tuple((item.market_archive_slice_id, item.ordinal) for item in terminal_slices) != tuple(
            (item.market_archive_slice_id, item.ordinal) for item in archive.slices
        ):
            raise ValueError("terminal archive slice roster does not match the frozen roster")
        if disposition is ArchiveSealDisposition.COMPLETE and (
            gap_count != 0
            or any(item.status is not ArchiveSliceStatus.CAPTURED for item in terminal_slices)
        ):
            raise ValueError("COMPLETE seal requires every slice captured and zero gaps")
        if disposition is ArchiveSealDisposition.PARTIAL_WITH_GAPS and gap_count < 1:
            raise ValueError("PARTIAL_WITH_GAPS seal requires at least one gap")
        if disposition is ArchiveSealDisposition.PARTIAL_WITH_RESOURCE_LIMIT and not any(
            item.status is ArchiveSliceStatus.RESOURCE_LIMIT for item in terminal_slices
        ):
            raise ValueError("PARTIAL_WITH_RESOURCE_LIMIT requires a resource-limited slice")
        counts = {
            "capture_count": capture_count,
            "artifact_count": artifact_count,
            "normalized_revision_count": normalized_revision_count,
            "gap_count": gap_count,
        }
        if any(isinstance(value, bool) or value < 0 for value in counts.values()):
            raise ValueError("archive seal counts must be non-negative")
        sealed = require_utc(sealed_at, field="sealed_at")
        if sealed < archive.archive_start_at:
            raise ValueError("archive seal cannot precede archive start")
        hashes = {
            "capture_roster_sha256": _hash(capture_roster_sha256),
            "artifact_roster_sha256": _hash(artifact_roster_sha256),
            "normalized_revision_roster_sha256": _hash(normalized_revision_roster_sha256),
            "gap_roster_sha256": _hash(gap_roster_sha256),
        }
        content_hash = ContentHash(
            canonical_json_sha256(
                {
                    "archive_roster_sha256": str(archive.slice_roster_sha256),
                    "disposition": disposition,
                    "knowledge_cutoff": sealed,
                    "market_archive_id": archive.market_archive_id,
                    "market_archive_seal_id": market_archive_seal_id,
                    "sealed_at": sealed,
                    **counts,
                    **{name: str(value) for name, value in hashes.items()},
                }
            )
        )
        return cls(
            market_archive_seal_id=market_archive_seal_id,
            market_archive_id=archive.market_archive_id,
            sealed_at=sealed,
            knowledge_cutoff=sealed,
            disposition=disposition,
            slice_count=archive.slice_count,
            slice_roster_sha256=archive.slice_roster_sha256,
            capture_count=capture_count,
            capture_roster_sha256=hashes["capture_roster_sha256"],
            artifact_count=artifact_count,
            artifact_roster_sha256=hashes["artifact_roster_sha256"],
            normalized_revision_count=normalized_revision_count,
            normalized_revision_roster_sha256=hashes["normalized_revision_roster_sha256"],
            gap_count=gap_count,
            gap_roster_sha256=hashes["gap_roster_sha256"],
            content_sha256=content_hash,
        )


@dataclass(frozen=True, slots=True)
class RetrospectiveSimulationClock:
    market_archive_id: UUID
    market_archive_seal_id: UUID
    simulation_session_id: UUID
    knowledge_cutoff: datetime
    simulated_event_cutoff: datetime
    evidence_class: ArchiveEvidenceClass = field(
        default=ArchiveEvidenceClass.EXPLORATORY_RETROSPECTIVE,
        init=False,
    )
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        knowledge = require_utc(self.knowledge_cutoff, field="knowledge_cutoff")
        simulated = require_utc(
            self.simulated_event_cutoff,
            field="simulated_event_cutoff",
        )
        if simulated >= knowledge:
            raise ValueError("simulated event cutoff must precede knowledge cutoff")
        object.__setattr__(self, "knowledge_cutoff", knowledge)
        object.__setattr__(self, "simulated_event_cutoff", simulated)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "evidence_class": self.evidence_class,
                        "knowledge_cutoff": knowledge,
                        "market_archive_id": self.market_archive_id,
                        "market_archive_seal_id": self.market_archive_seal_id,
                        "simulated_event_cutoff": simulated,
                        "simulation_session_id": self.simulation_session_id,
                    }
                )
            ),
        )


__all__ = [
    "ArchiveCaptureObservation",
    "ArchiveEvidenceClass",
    "ArchiveLane",
    "ArchiveObservationRelation",
    "ArchiveObservationTimeliness",
    "ArchiveSealDisposition",
    "ArchiveSliceStatus",
    "MarketArchive",
    "MarketArchiveSeal",
    "MarketArchiveSlice",
    "RetrospectiveSimulationClock",
]
