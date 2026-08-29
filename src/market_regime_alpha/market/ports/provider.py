"""Provider, normalizer, byte-store, and database-clock ports."""

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Protocol
from uuid import UUID

from market_regime_alpha.market.domain import (
    NormalizationBatch,
    ProviderCapture,
    SourceAvailabilityStatus,
    require_capture_key,
)
from market_regime_alpha.runtime.ports import ByteVerification, PublishedArtifact
from market_regime_alpha.shared.identity import ContentHash


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    provider_product_id: UUID
    capture_key: str
    resource: str
    request_headers_hash: ContentHash

    def __post_init__(self) -> None:
        require_capture_key(self.capture_key)
        if not self.resource:
            raise ValueError("resource is required")
        object.__setattr__(
            self,
            "request_headers_hash",
            self.request_headers_hash if isinstance(self.request_headers_hash, ContentHash) else ContentHash(self.request_headers_hash),
        )


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    content: bytes
    media_type: str
    payload_encoding: str
    provider_time: datetime | None
    source_availability_status: SourceAvailabilityStatus
    source_available_at: datetime | None
    limitation_code: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise TypeError("Provider content must be exact bytes")
        if not self.media_type or not self.payload_encoding:
            raise ValueError("Provider media type and payload encoding are required")
        if self.source_availability_status is SourceAvailabilityStatus.UNKNOWN:
            if self.source_available_at is not None:
                raise ValueError("UNKNOWN availability cannot carry a timestamp")
        elif self.source_available_at is None:
            raise ValueError("reported availability requires a timestamp")


class MarketProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MarketProvider(Protocol):
    def capture(self, request: CaptureRequest) -> ProviderResponse: ...


@dataclass(frozen=True, slots=True)
class NormalizerContract:
    """Stable deterministic algorithm identity bound into normalization input."""

    implementation: str
    version: str
    implementation_sha256: ContentHash | str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", self.implementation):
            raise ValueError("normalizer implementation has an invalid format")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,99}", self.version):
            raise ValueError("normalizer version has an invalid format")
        object.__setattr__(
            self,
            "implementation_sha256",
            self.implementation_sha256 if isinstance(self.implementation_sha256, ContentHash) else ContentHash(self.implementation_sha256),
        )


class MarketArtifactByteStore(Protocol):
    def publish_bytes(
        self,
        content: bytes,
        *,
        media_type: str,
        expected_sha256: ContentHash | None = None,
    ) -> PublishedArtifact: ...

    def verify(
        self,
        content_sha256: ContentHash,
        *,
        expected_size: int,
    ) -> ByteVerification: ...

    def read_bytes(self, content_sha256: ContentHash, *, expected_size: int) -> bytes: ...


class MarketNormalizer(Protocol):
    @property
    def contract(self) -> NormalizerContract: ...

    def normalize(self, capture: ProviderCapture, content: bytes) -> NormalizationBatch: ...


class MarketDatabaseClock(Protocol):
    """PostgreSQL-backed acquisition time authority used outside provider I/O."""

    def now(self) -> datetime: ...
