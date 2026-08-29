"""Narrow Market transaction and cross-cutting ports."""

from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.market.ports.repository import MarketRepository
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    ArtifactVerificationRecord,
    AttemptClaim,
    AuditRepository,
    ByteVerification,
    CommandReceiptRepository,
    PublishedArtifact,
)


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
