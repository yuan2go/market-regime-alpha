"""Narrow Context Authority ports owned by Decision Support."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.decision_support.domain.context import (
    ContextAssessmentAuthority,
    ContextPolicyPlan,
    DecisionArtifactBinding,
    PreparedContextInputs,
)
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    AttemptClaim,
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


@dataclass(frozen=True, slots=True)
class ContextPolicyRecord:
    context_policy_id: UUID
    policy_code: str
    version: int
    metric_count: int
    kind_count: int
    content_sha256: str
    request_identity: str
    request_sha256: str
    frozen_at: datetime
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class ContextAssessmentRecord:
    assessment_group_id: UUID
    decision_run_id: UUID
    context_policy_id: UUID
    assessment_count: int
    metric_count: int
    source_count: int
    assessment_roster_sha256: str
    content_sha256: str
    request_identity: str
    request_sha256: str
    recorded_at: datetime
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class ContextReconciliation:
    assessment_group_id: UUID
    actual_assessment_count: int
    actual_metric_count: int
    actual_source_count: int
    assessment_roster_sha256: str
    matched: bool


class ContextInputPreparationProvider(Protocol):
    def prepare(
        self,
        decision_run_id: UUID,
        context_policy_id: UUID,
    ) -> PreparedContextInputs: ...


class ContextQueryProvider(Protocol):
    def authoritative_time(self) -> datetime: ...

    def find_policy_request(
        self,
        policy_code: str,
        request_identity: str,
    ) -> ContextPolicyRecord | None: ...

    def find_assessment_request(
        self,
        decision_run_id: UUID,
        context_policy_id: UUID,
        request_identity: str,
    ) -> ContextAssessmentRecord | None: ...


class ContextArtifactRepository(Protocol):
    def require_exact(
        self,
        binding: DecisionArtifactBinding,
        *,
        lock: bool,
    ) -> ArtifactRecord: ...


class ContextDependencyRepository(Protocol):
    def lock_and_revalidate(self, prepared: PreparedContextInputs) -> None: ...


class ContextRepository(Protocol):
    def lock_policy_identity(self, policy_code: str) -> None: ...

    def lock_assessment_identity(
        self,
        decision_run_id: UUID,
        context_policy_id: UUID,
    ) -> None: ...

    def authoritative_recorded_at(self) -> datetime: ...

    def register_policy(
        self,
        plan: ContextPolicyPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ContextPolicyRecord: ...

    def policy_record(
        self,
        context_policy_id: UUID,
        *,
        lock: bool,
    ) -> ContextPolicyRecord: ...

    def insert_assessment(
        self,
        authority: ContextAssessmentAuthority,
    ) -> ContextAssessmentRecord: ...

    def assessment_record(
        self,
        assessment_group_id: UUID,
        *,
        lock: bool,
    ) -> ContextAssessmentRecord: ...

    def reconcile(
        self,
        assessment_group_id: UUID,
        *,
        lock: bool,
    ) -> ContextReconciliation: ...


class ContextRuntimeFinalization(RuntimeCommandFinalization, Protocol):
    def lock_live_for_step(
        self,
        claim: AttemptClaim,
        *,
        expected_step_kind: str,
    ) -> None: ...


class ContextUnitOfWork(Protocol):
    @property
    def contexts(self) -> ContextRepository: ...

    @property
    def dependencies(self) -> ContextDependencyRepository: ...

    @property
    def artifacts(self) -> ContextArtifactRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> ContextRuntimeFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class ContextUnitOfWorkProvider(Protocol):
    def __call__(self) -> ContextUnitOfWork: ...


__all__ = [
    "ContextAssessmentRecord",
    "ContextArtifactRepository",
    "ContextDependencyRepository",
    "ContextInputPreparationProvider",
    "ContextPolicyRecord",
    "ContextQueryProvider",
    "ContextReconciliation",
    "ContextRepository",
    "ContextRuntimeFinalization",
    "ContextUnitOfWork",
    "ContextUnitOfWorkProvider",
]
