"""Narrow Partition UoW; it owns only Partition and Member writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.research_qualification.domain.partition import ResearchPartitionPlan
from market_regime_alpha.research_qualification.ports.partition_inputs import (
    DerivedPartitionMember,
    PartitionCalendarBounds,
    PartitionInputQueries,
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
class ResearchPartitionRecord:
    research_partition_id: UUID
    exchange_code: str
    timezone_name: str
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: str
    purpose: str
    calendar_session_count: int
    calendar_roster_sha256: str
    member_count: int
    member_roster_sha256: str
    content_sha256: str
    frozen_at: datetime


class ResearchPartitionRepository(Protocol):
    def lock_identity(self, partition_code: str) -> None: ...

    def insert(
        self,
        plan: ResearchPartitionPlan,
        bounds: PartitionCalendarBounds,
        members: tuple[DerivedPartitionMember, ...],
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ResearchPartitionRecord: ...

    def record(self, research_partition_id: UUID, *, lock: bool) -> ResearchPartitionRecord: ...

    def reconcile(self, research_partition_id: UUID) -> bool: ...


class PartitionUnitOfWork(Protocol):
    @property
    def inputs(self) -> PartitionInputQueries: ...

    @property
    def partitions(self) -> ResearchPartitionRepository: ...

    @property
    def artifacts(self) -> TargetArtifactRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> RuntimeCommandFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, exception_type: type[BaseException] | None, exception: BaseException | None, traceback: TracebackType | None) -> None: ...

    def commit(self) -> None: ...


class PartitionUnitOfWorkProvider(Protocol):
    def __call__(self) -> PartitionUnitOfWork: ...


__all__ = [
    "PartitionUnitOfWork",
    "PartitionUnitOfWorkProvider",
    "ResearchPartitionRecord",
    "ResearchPartitionRepository",
]
