"""Narrow Evaluation UoW owning Protocol, Run, access, and all outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationProtocolPlan,
    EvaluationRunPlan,
)
from market_regime_alpha.research_qualification.ports.evaluation_inputs import (
    OutcomeAcquisitionResult,
    TransactionalOutcomeAcquisition,
)
from market_regime_alpha.research_qualification.ports.target_artifacts import TargetArtifactRepository
from market_regime_alpha.runtime.ports import AuditRepository, CommandReceiptRepository, RuntimeCommandFinalization


@dataclass(frozen=True, slots=True)
class EvaluationProtocolRecord:
    evaluation_protocol_id: UUID
    target_definition_id: UUID
    applicable_purpose: str
    metric_count: int
    metric_roster_sha256: str
    frozen_at: datetime


@dataclass(frozen=True, slots=True)
class EvaluationRunRecord:
    evaluation_run_id: UUID
    experiment_run_id: UUID
    research_partition_id: UUID
    evaluation_protocol_id: UUID
    status: str
    opened_at: datetime
    content_sha256: str
    version: int


@dataclass(frozen=True, slots=True)
class EvaluationCompletionResult:
    evaluation_run_id: UUID
    metric_count: int
    metric_observation_count: int
    metric_roster_sha256: str


class EvaluationRepository(Protocol):
    def lock_protocol_identity(self, protocol_code: str) -> None: ...

    def register_protocol(
        self,
        plan: EvaluationProtocolPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> EvaluationProtocolRecord: ...

    def open_run(
        self, plan: EvaluationRunPlan, *, request_sha256: str
    ) -> EvaluationRunRecord: ...

    def complete(self, evaluation_run_id: UUID) -> EvaluationCompletionResult: ...

    def fail(self, evaluation_run_id: UUID, reason_code: str) -> EvaluationRunRecord: ...

    def protocol_record(self, evaluation_protocol_id: UUID, *, lock: bool) -> EvaluationProtocolRecord: ...

    def run_record(self, evaluation_run_id: UUID, *, lock: bool) -> EvaluationRunRecord: ...


class EvaluationUnitOfWork(Protocol):
    @property
    def evaluations(self) -> EvaluationRepository: ...

    @property
    def outcome_acquisition(self) -> TransactionalOutcomeAcquisition: ...

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


class EvaluationUnitOfWorkProvider(Protocol):
    def __call__(self) -> EvaluationUnitOfWork: ...


__all__ = [
    "EvaluationCompletionResult",
    "EvaluationProtocolRecord",
    "EvaluationRepository",
    "EvaluationRunRecord",
    "EvaluationUnitOfWork",
    "EvaluationUnitOfWorkProvider",
    "OutcomeAcquisitionResult",
]
