"""Narrow ports owned by the Market/PIT bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.market.domain import (
    BarTimeframe,
    CorporateActionRevision,
    ClassificationMembersResult,
    DecisionReference,
    EvidenceScope,
    GapFactKind,
    InstrumentFactRevision,
    InstrumentFactKind,
    ListingStatus,
    MarketBarRevision,
    NumericInstrumentFactKind,
    NormalizationBatch,
    Provider,
    ProviderCapture,
    ProviderProduct,
    PriceBasis,
    SourceAvailabilityStatus,
    require_capture_key,
    SourceGap,
    SecurityStatus,
    SpecialTreatmentStatus,
    TradingSession,
)
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    ArtifactVerificationRecord,
    AttemptClaim,
    AuditRepository,
    CommandReceiptRepository,
    PublishedArtifact,
    ByteVerification,
)
from market_regime_alpha.shared.identity import (
    ContentHash,
    InstrumentId,
    TradingSessionId,
)
from market_regime_alpha.shared.time import DecisionTime


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
            self.request_headers_hash
            if isinstance(self.request_headers_hash, ContentHash)
            else ContentHash(self.request_headers_hash),
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
            self.implementation_sha256
            if isinstance(self.implementation_sha256, ContentHash)
            else ContentHash(self.implementation_sha256),
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


class MarketQueries(Protocol):
    def exact_bar_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        timeframe: BarTimeframe,
        price_basis: PriceBasis,
        event_start: datetime,
        event_end: datetime,
        decision_time: DecisionTime,
    ) -> MarketBarRevision | None: ...

    def trading_session_as_of(
        self,
        *,
        exchange: str,
        session_date: date,
        decision_time: DecisionTime,
    ) -> TradingSession | None: ...

    def instrument_for_identifier_as_of(
        self,
        *,
        identifier_scheme: str,
        identifier_value: str,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> InstrumentId | None: ...

    def classification_members_as_of(
        self,
        *,
        classification_scheme: str,
        classification_code: str,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> ClassificationMembersResult: ...

    def security_status_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        evidence_scope: EvidenceScope,
        decision_time: DecisionTime,
    ) -> SecurityStatus | None: ...

    def instrument_fact_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        fact_kind: NumericInstrumentFactKind,
        evidence_scope: EvidenceScope,
        event_time: datetime,
        decision_time: DecisionTime,
        session_id: TradingSessionId | None = None,
    ) -> InstrumentFactRevision | None: ...

    def listing_status_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> ListingStatus | None: ...

    def special_treatment_status_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> SpecialTreatmentStatus | None: ...

    def corporate_actions_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        ex_session_id: TradingSessionId,
        decision_time: DecisionTime,
    ) -> tuple[CorporateActionRevision, ...]: ...

    def source_gaps_as_of(
        self,
        *,
        decision_time: DecisionTime,
        capture_id: UUID | None = None,
        fact_kind: GapFactKind | None = None,
        instrument_id: InstrumentId | None = None,
        session_id: TradingSessionId | None = None,
        instrument_code: str | None = None,
        identifier_scheme: str | None = None,
        identifier_value: str | None = None,
        exchange: str | None = None,
        session_date: date | None = None,
        classification_scheme: str | None = None,
        classification_code: str | None = None,
        instrument_fact_kind: InstrumentFactKind | None = None,
        evidence_scope: EvidenceScope | None = None,
        action_key: str | None = None,
    ) -> tuple[SourceGap, ...]: ...

    def decision_reference_1455(
        self,
        *,
        instrument_id: InstrumentId,
        exchange: str,
        session_date: date,
        decision_time: DecisionTime,
    ) -> DecisionReference: ...


class MarketQueryProvider(Protocol):
    def for_provider_product(self, provider_product_id: UUID) -> MarketQueries: ...


class MarketRuntimeFinalization(Protocol):
    def lock_live(self, claim: AttemptClaim) -> None: ...

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

    def get(self, artifact_id: UUID) -> ArtifactRecord: ...

    def record_verification(
        self,
        *,
        verification_id: UUID,
        receipt_id: UUID,
        artifact: ArtifactRecord,
        verifier_id: str,
        policy: str,
        verification: ByteVerification,
    ) -> ArtifactVerificationRecord: ...


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
    "MarketDatabaseClock",
    "MarketNormalizer",
    "NormalizerContract",
    "MarketProvider",
    "MarketProviderError",
    "MarketQueries",
    "MarketQueryProvider",
    "MarketRepository",
    "MarketRuntimeFinalization",
    "MarketUnitOfWork",
    "MarketUnitOfWorkProvider",
    "ProviderResponse",
]
