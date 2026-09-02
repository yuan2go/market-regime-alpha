"""Typed resolver contract for complete post-Evaluation Model training inputs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_models import (
    LinearTrainingRow,
    ModelTrainingSamplePlan,
)
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.ports import ArtifactRecord


@dataclass(frozen=True, slots=True)
class OpenModelTrainingRunRequest:
    model_training_run_id: UUID
    model_id: UUID
    evaluation_run_id: UUID
    evaluation_protocol_metric_id: UUID
    exploratory_backtest_run_id: UUID
    exploratory_backtest_arm_id: UUID
    exploratory_backtest_fold_id: UUID
    algorithm_code: str
    algorithm_version: str
    algorithm_sha256: ContentHash | str
    ridge_alpha: Decimal
    random_seed: int
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str


@dataclass(frozen=True, slots=True)
class PreparedModelTrainingInputs:
    request: OpenModelTrainingRunRequest
    samples: tuple[ModelTrainingSamplePlan, ...]
    linear_rows: tuple[LinearTrainingRow, ...]
    training_input_content: bytes
    training_input_content_sha256: ContentHash | str


@dataclass(frozen=True, slots=True)
class RegisteredModelTrainingInputs:
    model_training_run_id: UUID
    model_id: UUID
    training_input_artifact: ArtifactBinding
    feature_definition_ids: tuple[UUID, ...]
    linear_rows: tuple[LinearTrainingRow, ...]
    ridge_alpha: Decimal
    random_seed: int
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding


class ModelTrainingInputProvider(Protocol):
    def prepare(
        self,
        request: OpenModelTrainingRunRequest,
    ) -> PreparedModelTrainingInputs: ...

    def load_registered(
        self,
        model_training_run_id: UUID,
    ) -> RegisteredModelTrainingInputs: ...


class ModelArtifactPublisher(Protocol):
    def publish(
        self,
        content: bytes,
        *,
        media_type: str,
        context: CommandContext,
        expected_sha256: str | None = None,
        pin_reason_code: str | None = None,
    ) -> ArtifactRecord: ...


__all__ = [
    "ModelTrainingInputProvider",
    "ModelArtifactPublisher",
    "OpenModelTrainingRunRequest",
    "PreparedModelTrainingInputs",
    "RegisteredModelTrainingInputs",
]
