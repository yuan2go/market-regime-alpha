"""Narrow persistence contracts for Market archive commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.market.domain import (
    ArchiveCaptureObservation,
    ArchiveSealDisposition,
    MarketArchive,
    MarketArchiveSeal,
    ProspectiveArchiveGenerationPlan,
)


@dataclass(frozen=True, slots=True)
class ArchiveSliceGapRecord:
    market_archive_slice_gap_id: UUID
    market_archive_id: UUID
    market_archive_slice_id: UUID
    gap_id: UUID
    terminal_status: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ArchiveResourceStopRecord:
    market_archive_resource_stop_id: UUID
    market_archive_id: UUID
    market_archive_slice_id: UUID
    observed_free_bytes: int
    required_free_bytes: int
    reason_code: str
    content_sha256: str
from market_regime_alpha.runtime.ports import (
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


class ArchiveRepository(Protocol):
    def database_now(self) -> datetime: ...

    def insert_archive(
        self,
        archive: MarketArchive,
        *,
        archive_code: str,
        request_identity: str,
        request_sha256: str,
    ) -> None: ...

    def insert_prospective_generation(
        self,
        plan: ProspectiveArchiveGenerationPlan,
    ) -> None: ...

    def get_archive(self, market_archive_id: UUID, *, lock: bool = False) -> MarketArchive: ...

    def record_capture_observation(
        self,
        *,
        observation_id: UUID,
        market_archive_id: UUID,
        market_archive_slice_id: UUID,
        capture_id: UUID,
        schedule_slot: str,
        requested_at: datetime,
    ) -> ArchiveCaptureObservation: ...

    def get_capture_observation(
        self, observation_id: UUID
    ) -> ArchiveCaptureObservation: ...

    def record_slice_gap(
        self,
        *,
        binding_id: UUID,
        market_archive_id: UUID,
        market_archive_slice_id: UUID,
        gap_id: UUID,
        terminal_status: str,
    ) -> ArchiveSliceGapRecord: ...

    def get_slice_gap(self, binding_id: UUID) -> ArchiveSliceGapRecord: ...

    def record_resource_stop(
        self,
        *,
        resource_stop_id: UUID,
        market_archive_id: UUID,
        market_archive_slice_id: UUID,
        observed_free_bytes: int,
    ) -> ArchiveResourceStopRecord: ...

    def get_resource_stop(self, resource_stop_id: UUID) -> ArchiveResourceStopRecord: ...

    def finalize_overdue(
        self,
        market_archive_id: UUID,
    ) -> tuple[UUID, ...]: ...

    def seal_retrospective(
        self,
        *,
        seal_id: UUID,
        market_archive_id: UUID,
        disposition: ArchiveSealDisposition,
    ) -> MarketArchiveSeal: ...

    def get_seal(self, seal_id: UUID) -> MarketArchiveSeal: ...


class ArchiveUnitOfWork(Protocol):
    @property
    def archives(self) -> ArchiveRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> RuntimeCommandFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class ArchiveUnitOfWorkProvider(Protocol):
    def __call__(self) -> ArchiveUnitOfWork: ...


__all__ = [
    "ArchiveRepository",
    "ArchiveResourceStopRecord",
    "ArchiveSliceGapRecord",
    "ArchiveUnitOfWork",
    "ArchiveUnitOfWorkProvider",
]
