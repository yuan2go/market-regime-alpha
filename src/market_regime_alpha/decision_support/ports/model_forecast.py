"""Narrow ports for optional model-backed Forecast production."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    ForecastModelBindingPlan,
    ModelForecastPrediction,
    PreparedInferenceInputs,
)


@dataclass(frozen=True, slots=True)
class PreparedModelForecastInputs:
    inference: PreparedInferenceInputs
    dataset_id: UUID
    exploratory_backtest_run_id: UUID | None
    exploratory_backtest_arm_id: UUID | None
    exploratory_backtest_fold_id: UUID | None
    exploratory_backtest_fold_session_id: UUID | None
    inference_fold_ordinal: int | None
    model_version_id: UUID
    model_id: UUID
    model_training_run_id: UUID
    training_fold_id: UUID
    training_fold_ordinal: int
    model_version_sha256: str
    fitted_model_artifact: DecisionArtifactBinding
    model_registered_at: datetime
    target_metric_definition_id: UUID
    predictions: tuple[ModelForecastPrediction, ...]
    experimental_model_use_id: UUID | None = None

    def __post_init__(self) -> None:
        commitments = self.inference.commitments
        expected = {
            (item.candidate_id, item.commitment_id) for item in commitments
        }
        actual = {
            (item.candidate_id, item.commitment_id) for item in self.predictions
        }
        if len(actual) != len(self.predictions) or actual != expected:
            raise ValueError("Model Forecast requires a complete prediction roster")
        if any(item.dataset_id != self.dataset_id for item in self.predictions):
            raise ValueError("Model Forecast prediction Dataset binding differs")
        if self.experimental_model_use_id is None:
            if self.inference_fold_ordinal is None or self.inference_fold_ordinal <= self.training_fold_ordinal:
                raise ValueError("Model Forecast inference fold must follow training")
        else:
            if any(value is not None for value in (self.exploratory_backtest_run_id, self.exploratory_backtest_arm_id,
                    self.exploratory_backtest_fold_id, self.exploratory_backtest_fold_session_id, self.inference_fold_ordinal)):
                raise ValueError("experimental use cannot mix retrospective inference")
            if self.model_registered_at >= self.inference.signal_inputs.decision_time:
                raise ValueError("ModelVersion must precede the actual DecisionTime")


@dataclass(frozen=True, slots=True)
class ModelForecastReconciliation:
    forecast_group_id: UUID
    model_version_id: UUID
    forecast_count: int
    binding_count: int
    binding_roster_sha256: str
    matched: bool


@dataclass(frozen=True, slots=True)
class ModelForecastBindingSummary:
    forecast_group_id: UUID
    model_version_id: UUID
    binding_count: int
    binding_roster_sha256: str
    receipt_result_hash: str


class ModelForecastInputPreparationProvider(Protocol):
    def prepare(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
        model_version_id: UUID,
        *, experimental_model_use_id: UUID | None = None,
    ) -> PreparedModelForecastInputs: ...


class ModelForecastQueryProvider(Protocol):
    def summary(
        self,
        forecast_group_id: UUID,
    ) -> ModelForecastBindingSummary | None: ...


class ModelForecastRepository(Protocol):
    def lock_and_revalidate(self, prepared: PreparedModelForecastInputs) -> None: ...

    def insert(self, bindings: tuple[ForecastModelBindingPlan, ...]) -> None: ...

    def reconcile(
        self,
        forecast_group_id: UUID,
        model_version_id: UUID,
        *,
        lock: bool,
    ) -> ModelForecastReconciliation: ...


class ModelForecastArtifactRepository(Protocol):
    def require_exact(
        self,
        binding: DecisionArtifactBinding,
        *,
        lock: bool,
    ) -> object: ...


__all__ = [
    "ModelForecastInputPreparationProvider",
    "ModelForecastBindingSummary",
    "ModelForecastArtifactRepository",
    "ModelForecastQueryProvider",
    "ModelForecastReconciliation",
    "ModelForecastRepository",
    "PreparedModelForecastInputs",
]
