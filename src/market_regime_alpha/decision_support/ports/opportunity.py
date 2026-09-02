"""Narrow Opportunity/Thesis Authority ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    OpportunityAuthority,
    PreparedOpportunityInputs,
    ThesisPlan,
)
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    AttemptClaim,
    AuditRepository,
    CommandReceiptRepository,
)


@dataclass(frozen=True, slots=True)
class OpportunitySetRecord:
    opportunity_set_id: UUID
    decision_run_id: UUID
    strategy_version_id: UUID
    opportunity_count: int
    context_count: int
    content_sha256: str
    request_identity: str
    request_sha256: str
    recorded_at: datetime
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class ThesisRecord:
    thesis_id: UUID
    opportunity_id: UUID
    revision: int
    condition_count: int
    content_sha256: str
    request_identity: str
    request_sha256: str
    frozen_at: datetime
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class OpportunityReconciliation:
    opportunity_set_id: UUID
    opportunity_count: int
    context_count: int
    opportunity_roster_sha256: str
    matched: bool


class OpportunityInputPreparationProvider(Protocol):
    def prepare(self, decision_run_id: UUID, strategy_version_id: UUID) -> PreparedOpportunityInputs: ...


class OpportunityQueryProvider(Protocol):
    def find_set_request(self, decision_run_id: UUID, strategy_version_id: UUID, request_identity: str) -> OpportunitySetRecord | None: ...
    def find_thesis_request(self, opportunity_id: UUID, request_identity: str) -> ThesisRecord | None: ...


class OpportunityDependencyRepository(Protocol):
    def lock_and_revalidate(self, prepared: PreparedOpportunityInputs) -> None: ...
    def require_opportunity(self, opportunity_id: UUID, content_sha256: str, *, lock: bool) -> tuple[UUID, UUID, UUID]: ...


class OpportunityArtifactRepository(Protocol):
    def require_exact(self, binding: DecisionArtifactBinding, *, lock: bool) -> ArtifactRecord: ...


class OpportunityRepository(Protocol):
    def lock_set_identity(self, decision_run_id: UUID, strategy_version_id: UUID) -> None: ...
    def lock_thesis_identity(self, opportunity_id: UUID) -> None: ...
    def authoritative_time(self) -> datetime: ...
    def insert_set(self, authority: OpportunityAuthority) -> OpportunitySetRecord: ...
    def insert_thesis(
        self, plan: ThesisPlan, *, opportunity_scope: tuple[UUID, UUID, UUID], request_identity: str, request_sha256: str
    ) -> ThesisRecord: ...
    def set_record(self, opportunity_set_id: UUID, *, lock: bool) -> OpportunitySetRecord: ...
    def thesis_record(self, thesis_id: UUID, *, lock: bool) -> ThesisRecord: ...
    def reconcile(self, opportunity_set_id: UUID, *, lock: bool) -> OpportunityReconciliation: ...


class OpportunityRuntimeFence(Protocol):
    def lock_live_for_step(self, claim: AttemptClaim, *, expected_step_kind: str) -> None: ...


class OpportunityUnitOfWork(Protocol):
    @property
    def opportunities(self) -> OpportunityRepository: ...
    @property
    def dependencies(self) -> OpportunityDependencyRepository: ...
    @property
    def artifacts(self) -> OpportunityArtifactRepository: ...
    @property
    def receipts(self) -> CommandReceiptRepository: ...
    @property
    def audit(self) -> AuditRepository: ...
    @property
    def runtime_finalization(self) -> OpportunityRuntimeFence: ...
    def __enter__(self) -> Self: ...
    def __exit__(
        self, exception_type: type[BaseException] | None, exception: BaseException | None, traceback: TracebackType | None
    ) -> None: ...
    def commit(self) -> None: ...


class OpportunityUnitOfWorkProvider(Protocol):
    def __call__(self) -> OpportunityUnitOfWork: ...


__all__ = [
    "OpportunityArtifactRepository",
    "OpportunityDependencyRepository",
    "OpportunityInputPreparationProvider",
    "OpportunityQueryProvider",
    "OpportunityReconciliation",
    "OpportunityRepository",
    "OpportunityRuntimeFence",
    "OpportunitySetRecord",
    "OpportunityUnitOfWork",
    "OpportunityUnitOfWorkProvider",
    "ThesisRecord",
]
