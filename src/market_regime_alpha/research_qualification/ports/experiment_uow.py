"""Narrow Experiment UoW; EvaluationRun is deliberately absent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.research_qualification.domain.experiment import (
    ExperimentDefinition,
    ExperimentPartitionBinding,
    ExperimentRunPlan,
)
from market_regime_alpha.research_qualification.ports.target_artifacts import TargetArtifactRepository
from market_regime_alpha.runtime.ports import AuditRepository, CommandReceiptRepository, RuntimeCommandFinalization


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    experiment_id: UUID
    target_definition_id: UUID
    definition_sha256: str
    partition_count: int
    partition_roster_sha256: str
    content_sha256: str
    registered_at: datetime


@dataclass(frozen=True, slots=True)
class ExperimentRunRecord:
    experiment_run_id: UUID
    experiment_id: UUID
    experiment_partition_id: UUID
    research_partition_id: UUID
    opened_at: datetime


class ExperimentRepository(Protocol):
    def lock_identity(self, experiment_code: str) -> None: ...

    def register(
        self,
        definition: ExperimentDefinition,
        bindings: tuple[ExperimentPartitionBinding, ...],
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ExperimentRecord: ...

    def open_run(self, plan: ExperimentRunPlan) -> ExperimentRunRecord: ...

    def record(self, experiment_id: UUID, *, lock: bool) -> ExperimentRecord: ...

    def run_record(self, experiment_run_id: UUID, *, lock: bool) -> ExperimentRunRecord: ...


class ExperimentUnitOfWork(Protocol):
    @property
    def experiments(self) -> ExperimentRepository: ...

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


class ExperimentUnitOfWorkProvider(Protocol):
    def __call__(self) -> ExperimentUnitOfWork: ...


__all__ = [
    "ExperimentRecord",
    "ExperimentRepository",
    "ExperimentRunRecord",
    "ExperimentUnitOfWork",
    "ExperimentUnitOfWorkProvider",
]
