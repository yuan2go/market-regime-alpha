"""Narrow Evidence Authority UoW."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.research_qualification.domain.evidence import EvidenceItemPlan
from market_regime_alpha.research_qualification.ports.target_artifacts import (
    TargetArtifactRepository,
)
from market_regime_alpha.runtime.ports import (
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


@dataclass(frozen=True, slots=True)
class EvidenceItemRecord:
    evidence_item_id: UUID
    evaluation_run_id: UUID
    dependency_count: int
    dependency_roster_sha256: str
    content_sha256: str
    recorded_at: datetime


class EvidenceRepository(Protocol):
    def lock_identity(self, evaluation_run_id: UUID, evidence_code: str) -> None: ...

    def record(
        self,
        plan: EvidenceItemPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> EvidenceItemRecord: ...

    def item_record(
        self, evidence_item_id: UUID, *, lock: bool
    ) -> EvidenceItemRecord: ...


class EvidenceUnitOfWork(Protocol):
    @property
    def evidence(self) -> EvidenceRepository: ...

    @property
    def artifacts(self) -> TargetArtifactRepository: ...

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


class EvidenceUnitOfWorkProvider(Protocol):
    def __call__(self) -> EvidenceUnitOfWork: ...


__all__ = [
    "EvidenceItemRecord",
    "EvidenceRepository",
    "EvidenceUnitOfWork",
    "EvidenceUnitOfWorkProvider",
]
