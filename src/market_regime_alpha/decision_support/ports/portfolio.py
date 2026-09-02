"""Narrow Portfolio Authority ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    PortfolioPolicyPlan,
    PortfolioProposalAuthority,
    PreparedPortfolioInputs,
)
from market_regime_alpha.runtime.ports import ArtifactRecord, AttemptClaim, AuditRepository, CommandReceiptRepository


@dataclass(frozen=True, slots=True)
class PortfolioPolicyRecord:
    portfolio_policy_id: UUID
    policy_code: str
    version: int
    content_sha256: str
    request_identity: str
    request_sha256: str
    frozen_at: datetime
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class PortfolioProposalRecord:
    portfolio_proposal_id: UUID
    decision_run_id: UUID
    strategy_version_id: UUID
    portfolio_policy_id: UUID
    status: str
    line_count: int
    included_count: int
    content_sha256: str
    request_identity: str
    request_sha256: str
    recorded_at: datetime
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class PortfolioReconciliation:
    portfolio_proposal_id: UUID
    line_count: int
    line_roster_sha256: str
    gross_weight: str
    matched: bool


class PortfolioInputPreparationProvider(Protocol):
    def prepare(self, opportunity_set_id: UUID, portfolio_policy_id: UUID) -> tuple[PreparedPortfolioInputs, PortfolioPolicyPlan]: ...


class PortfolioQueryProvider(Protocol):
    def find_policy_request(self, policy_code: str, request_identity: str) -> PortfolioPolicyRecord | None: ...
    def find_proposal_request(
        self, opportunity_set_id: UUID, portfolio_policy_id: UUID, request_identity: str
    ) -> PortfolioProposalRecord | None: ...


class PortfolioDependencyRepository(Protocol):
    def lock_and_revalidate(self, prepared: PreparedPortfolioInputs, policy: PortfolioPolicyPlan) -> None: ...


class PortfolioArtifactRepository(Protocol):
    def require_exact(self, binding: DecisionArtifactBinding, *, lock: bool) -> ArtifactRecord: ...


class PortfolioRepository(Protocol):
    def lock_policy_identity(self, policy_code: str) -> None: ...
    def lock_proposal_identity(self, decision_run_id: UUID, strategy_version_id: UUID, portfolio_policy_id: UUID) -> None: ...
    def authoritative_time(self) -> datetime: ...
    def register_policy(self, plan: PortfolioPolicyPlan, *, request_identity: str, request_sha256: str) -> PortfolioPolicyRecord: ...
    def insert_proposal(self, authority: PortfolioProposalAuthority) -> PortfolioProposalRecord: ...
    def policy_record(self, portfolio_policy_id: UUID, *, lock: bool) -> PortfolioPolicyRecord: ...
    def proposal_record(self, portfolio_proposal_id: UUID, *, lock: bool) -> PortfolioProposalRecord: ...
    def reconcile(self, portfolio_proposal_id: UUID, *, lock: bool) -> PortfolioReconciliation: ...


class PortfolioRuntimeFence(Protocol):
    def lock_live_for_step(self, claim: AttemptClaim, *, expected_step_kind: str) -> None: ...


class PortfolioUnitOfWork(Protocol):
    @property
    def portfolios(self) -> PortfolioRepository: ...
    @property
    def dependencies(self) -> PortfolioDependencyRepository: ...
    @property
    def artifacts(self) -> PortfolioArtifactRepository: ...
    @property
    def receipts(self) -> CommandReceiptRepository: ...
    @property
    def audit(self) -> AuditRepository: ...
    @property
    def runtime_finalization(self) -> PortfolioRuntimeFence: ...
    def __enter__(self) -> Self: ...
    def __exit__(
        self, exception_type: type[BaseException] | None, exception: BaseException | None, traceback: TracebackType | None
    ) -> None: ...
    def commit(self) -> None: ...


class PortfolioUnitOfWorkProvider(Protocol):
    def __call__(self) -> PortfolioUnitOfWork: ...


__all__ = [
    "PortfolioArtifactRepository",
    "PortfolioDependencyRepository",
    "PortfolioInputPreparationProvider",
    "PortfolioPolicyRecord",
    "PortfolioProposalRecord",
    "PortfolioQueryProvider",
    "PortfolioReconciliation",
    "PortfolioRepository",
    "PortfolioRuntimeFence",
    "PortfolioUnitOfWork",
    "PortfolioUnitOfWorkProvider",
]
