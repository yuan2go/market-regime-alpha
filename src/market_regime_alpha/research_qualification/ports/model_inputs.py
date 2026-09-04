"""Typed resolver contract for complete post-Evaluation Model training inputs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_models import (
    LinearTrainingRow,
    ModelExecutionEnvironment,
    ModelScalarParameter,
    ModelTrainingReproducibility,
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
    ridge_alpha: Decimal | None
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
class ReproducibleModelTrainingRunRequest:
    """Permanent current-run request with no nullable reproducibility fallback."""

    training: OpenModelTrainingRunRequest
    environment: ModelExecutionEnvironment
    hyperparameters: tuple[ModelScalarParameter, ...]

    def __post_init__(self) -> None:
        if tuple(item.ordinal for item in self.hyperparameters) != tuple(range(1, len(self.hyperparameters) + 1)):
            raise ValueError("Model hyperparameters must use contiguous ordinals")
        if self.training.algorithm_code == "deterministic_ridge":
            alpha = tuple(
                item
                for item in self.hyperparameters
                if item.parameter_code == "ridge_alpha"
                and item.value_type.value == "DECIMAL"
            )
            if len(alpha) != 1 or alpha[0].decimal_value != self.training.ridge_alpha:
                raise ValueError("deterministic ridge typed alpha differs from training contract")


@dataclass(frozen=True, slots=True)
class PreparedReproducibleModelTrainingInputs:
    training: PreparedModelTrainingInputs
    reproducibility: ModelTrainingReproducibility

    def __post_init__(self) -> None:
        if self.training.request.model_training_run_id != self.reproducibility.model_training_run_id:
            raise ValueError("prepared reproducibility identity differs")


@dataclass(frozen=True, slots=True)
class RegisteredModelTrainingInputs:
    model_training_run_id: UUID
    model_id: UUID
    algorithm_code: str
    algorithm_version: str
    implementation_sha256: ContentHash | str
    training_input_artifact: ArtifactBinding
    feature_definition_ids: tuple[UUID, ...]
    linear_rows: tuple[LinearTrainingRow, ...]
    ridge_alpha: Decimal | None
    random_seed: int
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "implementation_sha256",
            ContentHash(str(self.implementation_sha256)),
        )


@dataclass(frozen=True, slots=True)
class RegisteredReproducibleModelTrainingInputs:
    training: RegisteredModelTrainingInputs
    reproducibility: ModelTrainingReproducibility

    def __post_init__(self) -> None:
        if (
            self.training.model_training_run_id != self.reproducibility.model_training_run_id
            or self.training.implementation_sha256 != self.reproducibility.implementation_sha256
        ):
            raise ValueError("registered reproducibility lineage differs")


class ModelTrainingInputProvider(Protocol):
    def prepare(
        self,
        request: OpenModelTrainingRunRequest,
    ) -> PreparedModelTrainingInputs: ...

    def load_registered(
        self,
        model_training_run_id: UUID,
    ) -> RegisteredModelTrainingInputs: ...

    def prepare_reproducible(
        self,
        request: ReproducibleModelTrainingRunRequest,
    ) -> PreparedReproducibleModelTrainingInputs: ...

    def load_registered_reproducible(
        self,
        model_training_run_id: UUID,
    ) -> RegisteredReproducibleModelTrainingInputs: ...


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
    "PreparedReproducibleModelTrainingInputs",
    "RegisteredModelTrainingInputs",
    "RegisteredReproducibleModelTrainingInputs",
    "ReproducibleModelTrainingRunRequest",
]
