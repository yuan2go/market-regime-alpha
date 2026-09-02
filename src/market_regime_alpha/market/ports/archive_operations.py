"""Narrow read and resource ports for archive operation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from market_regime_alpha.market.domain import CaptureStatus


@dataclass(frozen=True, slots=True)
class ArchiveSliceOperatingContract:
    market_archive_id: UUID
    market_archive_slice_id: UUID
    provider_product_id: UUID
    request_sha256: str
    reserved_free_bytes: int
    maximum_slice_bytes: int
    terminal_status: str | None

    @property
    def required_free_bytes(self) -> int:
        return self.reserved_free_bytes + self.maximum_slice_bytes


@dataclass(frozen=True, slots=True)
class ArchiveCaptureDisposition:
    capture_id: UUID
    status: CaptureStatus
    source_gap_ids: tuple[UUID, ...]


class ArchiveOperationsReadPort(Protocol):
    def load_slice_contract(
        self,
        market_archive_id: UUID,
        market_archive_slice_id: UUID,
    ) -> ArchiveSliceOperatingContract: ...

    def capture_disposition(self, capture_id: UUID) -> ArchiveCaptureDisposition: ...


class ArchiveResourceInspector(Protocol):
    def available_bytes(self) -> int: ...


__all__ = [
    "ArchiveCaptureDisposition",
    "ArchiveOperationsReadPort",
    "ArchiveResourceInspector",
    "ArchiveSliceOperatingContract",
]
