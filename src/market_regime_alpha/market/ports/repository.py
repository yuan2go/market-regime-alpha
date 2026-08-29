"""Aggregate persistence port for Market/PIT commands."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from market_regime_alpha.market.domain import (
    NormalizationBatch,
    Provider,
    ProviderCapture,
    ProviderProduct,
    SourceGap,
)
from market_regime_alpha.runtime.ports import ArtifactRecord, PublishedArtifact
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


@dataclass(frozen=True, slots=True)
class CaptureSource:
    capture: ProviderCapture
    artifact: ArtifactRecord | None


class MarketRepository(Protocol):
    def register_provider(self, provider: Provider) -> int: ...

    def register_provider_product(self, product: ProviderProduct) -> int: ...

    def record_capture(
        self,
        capture: ProviderCapture,
        published: PublishedArtifact | None,
    ) -> ProviderCapture: ...

    def record_capture_failure(
        self,
        capture: ProviderCapture,
        gap: SourceGap,
    ) -> tuple[ProviderCapture, DecisionTime]: ...

    def get_capture(self, capture_id: UUID) -> ProviderCapture: ...

    def capture_source(self, capture_id: UUID, *, lock: bool = False) -> CaptureSource: ...

    def insert_normalization(
        self,
        batch: NormalizationBatch,
        *,
        expected_artifact_sha256: ContentHash,
        expected_artifact_size: int,
    ) -> DecisionTime: ...

    def normalization_decision_visible_at(self, capture_id: UUID) -> DecisionTime: ...
