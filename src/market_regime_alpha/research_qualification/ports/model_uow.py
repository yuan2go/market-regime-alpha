"""Narrow UoW owned only by optional Model training/version Authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.research_qualification.domain.research_models import (
    ReproducibleModelTrainingRunPlan,
    ModelTrainingRunPlan,
    ModelVersionPlan,
    ResearchModelPlan,
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
class ResearchModelRecord:
    model_id: UUID
    model_code: str
    target_definition_id: UUID
    feature_count: int
    feature_roster_sha256: str
    content_sha256: str
    registered_at: datetime


@dataclass(frozen=True, slots=True)
class ModelTrainingRunRecord:
    model_training_run_id: UUID
    model_id: UUID
    evaluation_run_id: UUID
    exploratory_backtest_run_id: UUID
    exploratory_backtest_fold_id: UUID
    sample_count: int
    estimable_count: int
    sample_roster_sha256: str
    training_input_artifact_id: UUID
    content_sha256: str
    opened_at: datetime


@dataclass(frozen=True, slots=True)
class ModelVersionRecord:
    model_version_id: UUID
    model_id: UUID
    version: int
    model_training_run_id: UUID
    fitted_model_artifact_id: UUID
    content_sha256: str
    registered_at: datetime


@dataclass(frozen=True, slots=True)
class ReproducibleModelTrainingRunRecord:
    training_run: ModelTrainingRunRecord
    reproducibility_sha256: str


class ResearchModelRepository(Protocol):
    def lock_model_identity(self, model_code: str) -> None: ...

    def register_model(
        self,
        plan: ResearchModelPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ResearchModelRecord: ...

    def register_training_run(
        self,
        plan: ModelTrainingRunPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ModelTrainingRunRecord: ...

    def register_reproducible_training_run(
        self,
        plan: ReproducibleModelTrainingRunPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ReproducibleModelTrainingRunRecord: ...

    def register_version(
        self,
        plan: ModelVersionPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ModelVersionRecord: ...

    def model_record(self, model_id: UUID, *, lock: bool) -> ResearchModelRecord: ...

    def training_run_record(self, model_training_run_id: UUID, *, lock: bool) -> ModelTrainingRunRecord: ...

    def reproducible_training_run_record(
        self,
        model_training_run_id: UUID,
        *,
        lock: bool,
    ) -> ReproducibleModelTrainingRunRecord | None: ...

    def version_record(self, model_version_id: UUID, *, lock: bool) -> ModelVersionRecord: ...


class ResearchModelUnitOfWork(Protocol):
    @property
    def research_models(self) -> ResearchModelRepository: ...

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


class ResearchModelUnitOfWorkProvider(Protocol):
    def __call__(self) -> ResearchModelUnitOfWork: ...


__all__ = [
    "ModelTrainingRunRecord",
    "ModelVersionRecord",
    "ResearchModelRecord",
    "ReproducibleModelTrainingRunRecord",
    "ResearchModelRepository",
    "ResearchModelUnitOfWork",
    "ResearchModelUnitOfWorkProvider",
]
