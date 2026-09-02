"""Narrow persistence boundary for FormalResearchCampaign Authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.research_qualification.domain.formal_campaign import (
    FormalResearchCampaignDefinition,
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
class FormalCampaignRecord:
    formal_research_campaign_id: UUID
    campaign_code: str
    revision: int
    campaign_class: str
    target_definition_id: UUID
    partition_plan_count: int
    partition_plan_roster_sha256: str
    evaluation_protocol_count: int
    evaluation_protocol_roster_sha256: str
    cost_assumption_count: int
    cost_assumption_roster_sha256: str
    content_sha256: str
    predeclared_at: datetime


@dataclass(frozen=True, slots=True)
class FormalCampaignBindingRecord:
    formal_research_campaign_id: UUID
    binding_kind: str
    aggregate_id: UUID
    binding_count: int
    content_sha256: str
    bound_at: datetime


class FormalCampaignRepository(Protocol):
    def lock_identity(self, campaign_code: str) -> None: ...

    def predeclare(
        self,
        definition: FormalResearchCampaignDefinition,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> FormalCampaignRecord: ...

    def record(
        self, formal_research_campaign_id: UUID, *, lock: bool
    ) -> FormalCampaignRecord: ...

    def reconcile(self, formal_research_campaign_id: UUID) -> bool: ...

    def bind_provider_decision(
        self,
        formal_research_campaign_id: UUID,
        provider_qualification_decision_id: UUID,
    ) -> FormalCampaignBindingRecord: ...

    def bind_partition_roster(
        self, formal_research_campaign_id: UUID
    ) -> FormalCampaignBindingRecord: ...

    def bind_experiment(
        self, formal_research_campaign_id: UUID, experiment_id: UUID
    ) -> FormalCampaignBindingRecord: ...

    def open_protected(
        self,
        formal_research_campaign_id: UUID,
        *,
        purpose: str,
        experiment_run_id: UUID,
        evaluation_run_id: UUID,
    ) -> FormalCampaignBindingRecord: ...

    def bind_runtime_run(
        self,
        formal_research_campaign_id: UUID,
        *,
        runtime_profile: str,
        runtime_run_id: UUID,
    ) -> FormalCampaignBindingRecord: ...

    def binding_matches(
        self,
        formal_research_campaign_id: UUID,
        *,
        binding_kind: str,
        aggregate_id: UUID,
        content_sha256: str,
    ) -> bool: ...


class FormalCampaignUnitOfWork(Protocol):
    @property
    def campaigns(self) -> FormalCampaignRepository: ...

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


class FormalCampaignUnitOfWorkProvider(Protocol):
    def __call__(self) -> FormalCampaignUnitOfWork: ...


__all__ = [
    "FormalCampaignBindingRecord",
    "FormalCampaignRecord",
    "FormalCampaignRepository",
    "FormalCampaignUnitOfWork",
    "FormalCampaignUnitOfWorkProvider",
]
