"""Typed acquisition disposition, separate from normalized Market facts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from market_regime_alpha.market.domain import ProviderCapture
from market_regime_alpha.market.ports.provider import NormalizerContract


@dataclass(frozen=True, slots=True)
class ArchiveAcquisitionReadiness:
    capture_id: UUID
    state: str
    policy: NormalizerContract
    source_sha256: str
    requested_at: datetime
    first_mature_at: datetime
    expected_interval_count: int
    session_ids: tuple[UUID, ...]


@runtime_checkable
class ArchiveAcquisitionReadinessClassifier(Protocol):
    def acquisition_readiness(self, capture: ProviderCapture, content: bytes) -> ArchiveAcquisitionReadiness | None: ...
