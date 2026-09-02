"""Read-only Market archive inspection contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ArchiveSliceInspection:
    market_archive_slice_id: UUID
    ordinal: int
    scope_key: str
    expected_fact_kind: str
    event_window_start: datetime
    event_window_end: datetime
    status: str
    observation_count: int
    latest_relation: str | None
    latest_timeliness: str | None
    latest_known_at: datetime | None
    gap_id: UUID | None
    gap_reason_code: str | None


@dataclass(frozen=True, slots=True)
class ArchiveInspection:
    market_archive_id: UUID
    archive_code: str
    lane: str
    evidence_class: str
    archive_start_at: datetime
    event_window_start: datetime
    event_window_end: datetime
    slice_count: int
    captured_slice_count: int
    gap_slice_count: int
    resource_stop_count: int
    pending_slice_count: int
    observation_count: int
    changed_observation_count: int
    on_time_observation_count: int
    late_observation_count: int
    artifact_count: int
    artifact_bytes: int
    normalized_revision_count: int
    market_revision_successor_count: int
    seal_id: UUID | None
    sealed_at: datetime | None
    seal_disposition: str | None
    slices: tuple[ArchiveSliceInspection, ...]


class ArchiveInspectionPort(Protocol):
    def inspect(self, market_archive_id: UUID) -> ArchiveInspection: ...


__all__ = [
    "ArchiveInspection",
    "ArchiveInspectionPort",
    "ArchiveSliceInspection",
]
