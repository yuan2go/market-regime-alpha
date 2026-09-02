"""Exact optional ModelVersion binding for an uncalibrated Forecast."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.shared.financial import bounded_decimal
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")


class ModelPredictionState(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class ModelForecastPrediction:
    candidate_id: UUID
    commitment_id: UUID
    dataset_id: UUID
    feature_vector_sha256: ContentHash | str
    state: ModelPredictionState
    reason_code: str
    point_estimate: Decimal | None
    input_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        vector_hash = ContentHash(str(self.feature_vector_sha256))
        if not isinstance(self.state, ModelPredictionState):
            raise TypeError("state must be ModelPredictionState")
        if not _REASON.fullmatch(self.reason_code):
            raise ValueError("reason_code has an invalid format")
        point = (
            None
            if self.point_estimate is None
            else bounded_decimal(
                self.point_estimate,
                field="point_estimate",
                precision=48,
                scale=18,
            )
        )
        if (self.state is ModelPredictionState.AVAILABLE) != (point is not None):
            raise ValueError("AVAILABLE prediction requires exactly one finite value")
        object.__setattr__(self, "feature_vector_sha256", vector_hash)
        object.__setattr__(self, "point_estimate", point)
        object.__setattr__(
            self,
            "input_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "candidate_id": self.candidate_id,
                        "commitment_id": self.commitment_id,
                        "dataset_id": self.dataset_id,
                        "feature_vector_sha256": vector_hash,
                        "reason_code": self.reason_code,
                        "state": self.state,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ForecastModelBindingPlan:
    forecast_model_binding_id: UUID
    forecast_id: UUID
    forecast_group_id: UUID
    forecast_estimate_id: UUID
    decision_run_id: UUID
    strategy_version_id: UUID
    commitment_id: UUID
    target_metric_definition_id: UUID
    forecast_estimate_content_sha256: ContentHash | str
    dataset_id: UUID
    exploratory_backtest_run_id: UUID
    exploratory_backtest_arm_id: UUID
    exploratory_backtest_fold_id: UUID
    exploratory_backtest_fold_session_id: UUID
    inference_fold_ordinal: int
    model_version_id: UUID
    model_id: UUID
    model_training_run_id: UUID
    training_fold_id: UUID
    training_fold_ordinal: int
    model_version_sha256: ContentHash | str
    fitted_model_artifact_id: UUID
    fitted_model_content_sha256: ContentHash | str
    fitted_model_size_bytes: int
    feature_vector_sha256: ContentHash | str
    prediction_state: ModelPredictionState
    reason_code: str
    point_estimate: Decimal | None
    model_registered_at: datetime
    forecast_recorded_at: datetime
    inference_input_sha256: ContentHash = field(init=False)
    inference_output_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool) or value < 1
            for value in (self.inference_fold_ordinal, self.training_fold_ordinal)
        ):
            raise ValueError("fold ordinals must be positive")
        if self.inference_fold_ordinal <= self.training_fold_ordinal:
            raise ValueError("Model Forecast requires a later fold than training")
        if (
            isinstance(self.fitted_model_size_bytes, bool)
            or self.fitted_model_size_bytes < 0
        ):
            raise ValueError("fitted_model_size_bytes must be non-negative")
        registered = require_utc(
            self.model_registered_at,
            field="model_registered_at",
        )
        forecast_at = require_utc(
            self.forecast_recorded_at,
            field="forecast_recorded_at",
        )
        if registered >= forecast_at:
            raise ValueError("ModelVersion must be registered before Forecast")
        version_hash = ContentHash(str(self.model_version_sha256))
        estimate_hash = ContentHash(str(self.forecast_estimate_content_sha256))
        fitted_hash = ContentHash(str(self.fitted_model_content_sha256))
        vector_hash = ContentHash(str(self.feature_vector_sha256))
        if not isinstance(self.prediction_state, ModelPredictionState):
            raise TypeError("prediction_state must be ModelPredictionState")
        if not _REASON.fullmatch(self.reason_code):
            raise ValueError("reason_code has an invalid format")
        point = (
            None
            if self.point_estimate is None
            else bounded_decimal(
                self.point_estimate,
                field="point_estimate",
                precision=48,
                scale=18,
            )
        )
        if (self.prediction_state is ModelPredictionState.AVAILABLE) != (
            point is not None
        ):
            raise ValueError("AVAILABLE binding requires exactly one finite value")
        input_hash = ContentHash(
            canonical_json_sha256(
                {
                    "dataset_id": self.dataset_id,
                    "feature_vector_sha256": str(vector_hash),
                    "fitted_model_artifact_id": self.fitted_model_artifact_id,
                    "fitted_model_content_sha256": str(fitted_hash),
                    "fitted_model_size_bytes": self.fitted_model_size_bytes,
                    "model_version_id": self.model_version_id,
                    "model_version_sha256": str(version_hash),
                }
            )
        )
        output_hash = ContentHash(
            canonical_json_sha256(
                {
                    "forecast_estimate_id": self.forecast_estimate_id,
                    "point_estimate": point,
                    "reason_code": self.reason_code,
                    "state": self.prediction_state,
                }
            )
        )
        object.__setattr__(self, "model_registered_at", registered)
        object.__setattr__(self, "forecast_recorded_at", forecast_at)
        object.__setattr__(self, "model_version_sha256", version_hash)
        object.__setattr__(self, "forecast_estimate_content_sha256", estimate_hash)
        object.__setattr__(self, "fitted_model_content_sha256", fitted_hash)
        object.__setattr__(self, "feature_vector_sha256", vector_hash)
        object.__setattr__(self, "point_estimate", point)
        object.__setattr__(self, "inference_input_sha256", input_hash)
        object.__setattr__(self, "inference_output_sha256", output_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "commitment_id": self.commitment_id,
                        "dataset_id": self.dataset_id,
                        "decision_run_id": self.decision_run_id,
                        "exploratory_backtest_arm_id": self.exploratory_backtest_arm_id,
                        "exploratory_backtest_fold_id": self.exploratory_backtest_fold_id,
                        "exploratory_backtest_fold_session_id": self.exploratory_backtest_fold_session_id,
                        "exploratory_backtest_run_id": self.exploratory_backtest_run_id,
                        "forecast_group_id": self.forecast_group_id,
                        "forecast_id": self.forecast_id,
                        "forecast_estimate_content_sha256": str(estimate_hash),
                        "forecast_model_binding_id": self.forecast_model_binding_id,
                        "inference_fold_ordinal": self.inference_fold_ordinal,
                        "inference_input_sha256": str(input_hash),
                        "inference_output_sha256": str(output_hash),
                        "model_id": self.model_id,
                        "model_registered_at": registered,
                        "model_training_run_id": self.model_training_run_id,
                        "model_version_id": self.model_version_id,
                        "model_version_sha256": str(version_hash),
                        "prediction_state": self.prediction_state,
                        "reason_code": self.reason_code,
                        "training_fold_id": self.training_fold_id,
                        "training_fold_ordinal": self.training_fold_ordinal,
                        "target_metric_definition_id": self.target_metric_definition_id,
                    }
                )
            ),
        )


__all__ = [
    "ForecastModelBindingPlan",
    "ModelForecastPrediction",
    "ModelPredictionState",
]
