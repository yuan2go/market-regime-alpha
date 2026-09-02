"""Narrow Decision-Support Risk Authority ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    PreparedRiskInputs,
    RiskDecisionAuthority,
    RiskPolicyPlan,
)
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    AttemptClaim,
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


@dataclass(frozen=True, slots=True)
class RiskPolicyRecord:
    risk_policy_id: UUID
    policy_code: str
    version: int
    rule_count: int
    content_sha256: str
    request_identity: str
    request_sha256: str
    frozen_at: datetime
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class RiskDecisionRecord:
    risk_decision_id: UUID
    portfolio_proposal_id: UUID
    risk_policy_id: UUID
    status: str
    reason_count: int
    content_sha256: str
    request_identity: str
    request_sha256: str
    decided_at: datetime
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class RiskReconciliation:
    risk_decision_id: UUID
    reason_count: int
    reason_roster_sha256: str
    matched: bool


class RiskInputPreparationProvider(Protocol):
    def prepare(self, portfolio_proposal_id: UUID, risk_policy_id: UUID) -> tuple[PreparedRiskInputs, RiskPolicyPlan]: ...


class RiskQueryProvider(Protocol):
    def find_policy_request(self, policy_code: str, request_identity: str) -> RiskPolicyRecord | None: ...
    def find_decision_request(
        self, portfolio_proposal_id: UUID, risk_policy_id: UUID, request_identity: str
    ) -> RiskDecisionRecord | None: ...


class RiskDependencyRepository(Protocol):
    def lock_and_revalidate(self, prepared: PreparedRiskInputs, policy: RiskPolicyPlan) -> None: ...


class RiskArtifactRepository(Protocol):
    def require_exact(self, binding: DecisionArtifactBinding, *, lock: bool) -> ArtifactRecord: ...


class RiskRepository(Protocol):
    def lock_policy_identity(self, policy_code: str) -> None: ...
    def lock_decision_identity(self, portfolio_proposal_id: UUID, risk_policy_id: UUID) -> None: ...
    def authoritative_time(self) -> datetime: ...
    def register_policy(self, plan: RiskPolicyPlan, *, request_identity: str, request_sha256: str) -> RiskPolicyRecord: ...
    def insert_decision(self, authority: RiskDecisionAuthority) -> RiskDecisionRecord: ...
    def policy_record(self, risk_policy_id: UUID, *, lock: bool) -> RiskPolicyRecord: ...
    def decision_record(self, risk_decision_id: UUID, *, lock: bool) -> RiskDecisionRecord: ...
    def reconcile(self, risk_decision_id: UUID, *, lock: bool) -> RiskReconciliation: ...


class RiskRuntimeFinalization(RuntimeCommandFinalization, Protocol):
    def lock_live_for_step(self, claim: AttemptClaim, *, expected_step_kind: str) -> None: ...


class RiskUnitOfWork(Protocol):
    @property
    def risks(self) -> RiskRepository: ...
    @property
    def dependencies(self) -> RiskDependencyRepository: ...
    @property
    def artifacts(self) -> RiskArtifactRepository: ...
    @property
    def receipts(self) -> CommandReceiptRepository: ...
    @property
    def audit(self) -> AuditRepository: ...
    @property
    def runtime_finalization(self) -> RiskRuntimeFinalization: ...
    def __enter__(self) -> Self: ...
    def __exit__(
        self, exception_type: type[BaseException] | None, exception: BaseException | None, traceback: TracebackType | None
    ) -> None: ...
    def commit(self) -> None: ...


class RiskUnitOfWorkProvider(Protocol):
    def __call__(self) -> RiskUnitOfWork: ...


__all__ = [
    "RiskArtifactRepository",
    "RiskDecisionRecord",
    "RiskDependencyRepository",
    "RiskInputPreparationProvider",
    "RiskPolicyRecord",
    "RiskQueryProvider",
    "RiskReconciliation",
    "RiskRepository",
    "RiskRuntimeFinalization",
    "RiskUnitOfWork",
    "RiskUnitOfWorkProvider",
]
