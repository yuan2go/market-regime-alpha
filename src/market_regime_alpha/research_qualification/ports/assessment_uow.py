"""Narrow ResearchAssessment Authority UoW."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.research_qualification.domain.assessment import (
    ResearchAssessmentPlan,
)
from market_regime_alpha.research_qualification.ports.target_artifacts import (
    TargetArtifactRepository,
)
from market_regime_alpha.runtime.ports import (
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


@dataclass(frozen=True, slots=True)
class ResearchAssessmentRecord:
    research_assessment_id: UUID
    experiment_id: UUID
    revision: int
    assessment_status: str
    evaluation_count: int
    evaluation_roster_sha256: str
    evidence_count: int
    evidence_roster_sha256: str
    content_sha256: str
    recorded_at: datetime


class AssessmentRepository(Protocol):
    def lock_identity(self, assessment_code: str) -> None: ...

    def assess(
        self,
        plan: ResearchAssessmentPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ResearchAssessmentRecord: ...

    def record(
        self, research_assessment_id: UUID, *, lock: bool
    ) -> ResearchAssessmentRecord: ...


class AssessmentUnitOfWork(Protocol):
    @property
    def assessments(self) -> AssessmentRepository: ...

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


class AssessmentUnitOfWorkProvider(Protocol):
    def __call__(self) -> AssessmentUnitOfWork: ...


__all__ = [
    "AssessmentRepository",
    "AssessmentUnitOfWork",
    "AssessmentUnitOfWorkProvider",
    "ResearchAssessmentRecord",
]
