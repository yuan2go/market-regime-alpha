"""Narrow ports owned by the Market/PIT bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.market.domain import (
    ClassificationMembershipRevision,
    ClassificationRevision,
    CorporateActionRevision,
    Instrument,
    InstrumentFactRevision,
    InstrumentIdentifier,
    MarketBarRevision,
    NormalizationBatch,
    Provider,
    ProviderCapture,
    ProviderProduct,
    SecurityStatusFactRevision,
    SourceAvailabilityStatus,
    SourceGap,
    TradingSession,
)
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    AttemptClaim,
    AuditRepository,
    CommandReceiptRepository,
    PublishedArtifact,
)
from market_regime_alpha.shared.identity import ContentHash


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    provider_product_id: UUID
    capture_key: str
    resource: str
    request_headers_hash: str

    def __post_init__(self) -> None:
        if not self.capture_key or len(self.capture_key) > 200:
            raise ValueError("capture_key is required and limited to 200 characters")
        if not self.resource:
            raise ValueError("resource is required")
        ContentHash(self.request_headers_hash)


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    content: bytes
    media_type: str
    payload_encoding: str
    provider_time: datetime | None
    source_availability_status: SourceAvailabilityStatus
    source_available_at: datetime | None
    limitation_code: str | None
    authority_ceiling: str = "EXPLORATORY_UNQUALIFIED"

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise TypeError("Provider content must be exact bytes")
        if not self.media_type or not self.payload_encoding:
            raise ValueError("Provider media type and payload encoding are required")
        if self.authority_ceiling != "EXPLORATORY_UNQUALIFIED":
            raise ValueError("WP-04 Providers cannot exceed exploratory/unqualified authority")
        if self.source_availability_status is SourceAvailabilityStatus.UNKNOWN:
            if self.source_available_at is not None:
                raise ValueError("UNKNOWN availability cannot carry a timestamp")
        elif self.source_available_at is None:
            raise ValueError("reported availability requires a timestamp")


class MarketProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class MarketProvider(Protocol):
    def capture(self, request: CaptureRequest) -> ProviderResponse: ...


class MarketArtifactByteStore(Protocol):
    def publish_bytes(
        self,
        content: bytes,
        *,
        media_type: str,
        expected_sha256: str | None = None,
    ) -> PublishedArtifact: ...

    def verify(self, content_sha256: str, *, expected_size: int): ...

    def read_bytes(self, content_sha256: str, *, expected_size: int) -> bytes: ...


class MarketNormalizer(Protocol):
    def normalize(self, capture: ProviderCapture, content: bytes) -> NormalizationBatch: ...


@dataclass(frozen=True, slots=True)
class CaptureSource:
    capture: ProviderCapture
    artifact: ArtifactRecord | None


class MarketRepository(Protocol):
    def register_provider(self, provider: Provider) -> int: ...

    def register_provider_product(self, product: ProviderProduct) -> int: ...

    def insert_capture(
        self,
        capture: ProviderCapture,
        published: PublishedArtifact | None,
    ) -> int: ...

    def get_capture(self, capture_id: UUID) -> ProviderCapture: ...

    def capture_source(self, capture_id: UUID, *, lock: bool = False) -> CaptureSource: ...

    def insert_instrument(self, instrument: Instrument) -> None: ...

    def insert_instrument_identifier(self, identifier: InstrumentIdentifier) -> None: ...

    def insert_trading_session(self, session: TradingSession) -> int: ...

    def insert_classification(self, item: ClassificationRevision) -> None: ...

    def insert_classification_membership(
        self, item: ClassificationMembershipRevision
    ) -> None: ...

    def insert_bar_revision(self, bar: MarketBarRevision) -> None: ...

    def insert_security_status_revision(
        self, fact: SecurityStatusFactRevision
    ) -> None: ...

    def insert_instrument_fact_revision(self, fact: InstrumentFactRevision) -> None: ...

    def insert_corporate_action(self, action: CorporateActionRevision) -> None: ...

    def insert_source_gap(self, gap: SourceGap) -> None: ...

    def lock_capture_source(self, capture_id: UUID) -> CaptureSource: ...


class MarketQueryRepository(Protocol):
    def capture_source(self, capture_id: UUID) -> CaptureSource: ...


class MarketRuntimeFinalization(Protocol):
    def succeed(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        result_hash: str,
    ) -> tuple[int, int]: ...

    def fail(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        error_class: str,
        error_code: str,
    ) -> tuple[str, int, int]: ...


class MarketArtifactRepository(Protocol):
    def register(
        self,
        *,
        artifact_id: UUID,
        published: PublishedArtifact,
        retention_until: datetime | None,
        pin_reason_code: str | None,
    ) -> ArtifactRecord: ...


class MarketUnitOfWork(Protocol):
    @property
    def market(self) -> MarketRepository: ...

    @property
    def artifacts(self) -> MarketArtifactRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> MarketRuntimeFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class MarketUnitOfWorkProvider(Protocol):
    def __call__(self) -> MarketUnitOfWork: ...


__all__ = [
    "CaptureRequest",
    "CaptureSource",
    "MarketArtifactByteStore",
    "MarketArtifactRepository",
    "MarketNormalizer",
    "MarketProvider",
    "MarketProviderError",
    "MarketQueryRepository",
    "MarketRepository",
    "MarketRuntimeFinalization",
    "MarketUnitOfWork",
    "MarketUnitOfWorkProvider",
    "ProviderResponse",
]
