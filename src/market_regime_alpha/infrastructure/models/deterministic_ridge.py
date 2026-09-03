"""Concrete deterministic ridge adapter for the generic Model seam."""

from __future__ import annotations

from market_regime_alpha.research_qualification.application.deterministic_linear import (
    fit_deterministic_ridge,
    load_deterministic_ridge_artifact,
    predict_deterministic_ridge,
)
from market_regime_alpha.research_qualification.ports.model_execution import (
    FittedModelPayload,
    FrozenModelTrainingInput,
    FrozenModelVersionPayload,
    ModelPrediction,
    ModelPredictionBatch,
    ModelScalarType,
)


class DeterministicRidgeTrainer:
    def supports(self, algorithm_code: str, algorithm_version: str) -> bool:
        return _supports_algorithm(algorithm_code, algorithm_version)

    def fit(self, training: FrozenModelTrainingInput) -> FittedModelPayload:
        _require_algorithm(training.algorithm_code, training.algorithm_version)
        alpha = tuple(
            item
            for item in training.hyperparameters
            if item.parameter_code == "ridge_alpha"
            and item.value_type is ModelScalarType.DECIMAL
        )
        if len(alpha) != 1 or alpha[0].decimal_value is None:
            raise ValueError("deterministic ridge requires one decimal ridge_alpha")
        fitted = fit_deterministic_ridge(
            training.rows,
            feature_definition_ids=training.feature_definition_ids,
            alpha=alpha[0].decimal_value,
            seed=training.seed,
        )
        return FittedModelPayload(
            fitted.content,
            fitted.content_sha256,
            len(fitted.coefficients) + 1,
        )


class DeterministicRidgePredictor:
    def supports(self, algorithm_code: str, algorithm_version: str) -> bool:
        return _supports_algorithm(algorithm_code, algorithm_version)

    def predict(
        self,
        model: FrozenModelVersionPayload,
        batch: ModelPredictionBatch,
    ) -> tuple[ModelPrediction, ...]:
        _require_algorithm(model.algorithm_code, model.algorithm_version)
        alpha = tuple(
            item
            for item in model.hyperparameters
            if item.parameter_code == "ridge_alpha"
            and item.value_type is ModelScalarType.DECIMAL
        )
        if len(alpha) != 1 or alpha[0].decimal_value is None:
            raise ValueError("deterministic ridge requires one decimal ridge_alpha")
        fitted = load_deterministic_ridge_artifact(model.fitted_content)
        if (
            str(model.fitted_content_sha256) != fitted.content_sha256
            or fitted.feature_definition_ids != model.feature_definition_ids
            or fitted.alpha != alpha[0].decimal_value
            or fitted.seed != model.seed
            or len(fitted.coefficients) + 1 != model.coefficient_count
        ):
            raise ValueError("fitted ridge bytes differ from frozen ModelVersion")
        return tuple(
            ModelPrediction(
                row.row_id,
                predict_deterministic_ridge(fitted, row.features),
            )
            for row in batch.rows
        )


def _require_algorithm(code: str, version: str) -> None:
    if not _supports_algorithm(code, version):
        raise ValueError("deterministic ridge adapter cannot execute this algorithm")


def _supports_algorithm(code: str, version: str) -> bool:
    return code == "deterministic_ridge" and version in {"1.0", "1.0.0"}


__all__ = ["DeterministicRidgePredictor", "DeterministicRidgeTrainer"]
