"""Narrow Research Qualification Policy and Decision UoW."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.research_qualification.domain.qualification import (
    ResearchQualificationDecisionPlan,
    ResearchQualificationPolicyPlan,
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
class ResearchQualificationPolicyRecord:
    research_qualification_policy_id: UUID
    version: int
    target_definition_id: UUID
    qualification_purpose: str
    floor_count: int
    floor_roster_sha256: str
    content_sha256: str
    frozen_at: datetime


@dataclass(frozen=True, slots=True)
class ResearchQualificationDecisionRecord:
    research_qualification_decision_id: UUID
    revision: int
    research_assessment_id: UUID
    research_qualification_policy_id: UUID
    decision_status: str
    floor_count: int
    floor_result_roster_sha256: str
    content_sha256: str
    effective_at: datetime
    known_at: datetime
    recorded_at: datetime


class QualificationRepository(Protocol):
    def lock_policy_identity(self, policy_code: str) -> None: ...

    def register_policy(
        self,
        plan: ResearchQualificationPolicyPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ResearchQualificationPolicyRecord: ...

    def policy_record(
        self, research_qualification_policy_id: UUID, *, lock: bool
    ) -> ResearchQualificationPolicyRecord: ...

    def lock_decision_identity(self, decision_code: str) -> None: ...

    def decide(
        self,
        plan: ResearchQualificationDecisionPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ResearchQualificationDecisionRecord: ...

    def decision_record(
        self, research_qualification_decision_id: UUID, *, lock: bool
    ) -> ResearchQualificationDecisionRecord: ...


class QualificationUnitOfWork(Protocol):
    @property
    def qualifications(self) -> QualificationRepository: ...

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


class QualificationUnitOfWorkProvider(Protocol):
    def __call__(self) -> QualificationUnitOfWork: ...


__all__ = [
    "QualificationRepository",
    "QualificationUnitOfWork",
    "QualificationUnitOfWorkProvider",
    "ResearchQualificationDecisionRecord",
    "ResearchQualificationPolicyRecord",
]
