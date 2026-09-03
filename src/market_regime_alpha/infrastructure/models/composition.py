"""Fail-closed startup composition of explicit Model family adapters."""

from __future__ import annotations

from typing import TypeVar

from market_regime_alpha.research_qualification.ports.model_execution import (
    FittedModelPayload,
    FrozenModelTrainingInput,
    FrozenModelVersionPayload,
    ModelPrediction,
    ModelPredictionBatch,
    ModelPredictor,
    ModelTrainer,
)


class ExplicitModelTrainerComposition:
    """Routes to one statically wired trainer; it is not business Authority."""

    def __init__(self, trainers: tuple[ModelTrainer, ...]) -> None:
        self._trainers = trainers

    def supports(self, algorithm_code: str, algorithm_version: str) -> bool:
        return (
            len(self._matching(algorithm_code, algorithm_version)) == 1
        )

    def fit(self, training: FrozenModelTrainingInput) -> FittedModelPayload:
        trainer = _require_one(
            self._matching(training.algorithm_code, training.algorithm_version),
            adapter_kind="ModelTrainer",
            algorithm_code=training.algorithm_code,
            algorithm_version=training.algorithm_version,
        )
        return trainer.fit(training)

    def _matching(
        self,
        algorithm_code: str,
        algorithm_version: str,
    ) -> tuple[ModelTrainer, ...]:
        return tuple(
            item
            for item in self._trainers
            if item.supports(algorithm_code, algorithm_version)
        )


class ExplicitModelPredictorComposition:
    """Routes to one statically wired predictor; it is not a model registry."""

    def __init__(self, predictors: tuple[ModelPredictor, ...]) -> None:
        self._predictors = predictors

    def supports(self, algorithm_code: str, algorithm_version: str) -> bool:
        return (
            len(self._matching(algorithm_code, algorithm_version)) == 1
        )

    def predict(
        self,
        model: FrozenModelVersionPayload,
        batch: ModelPredictionBatch,
    ) -> tuple[ModelPrediction, ...]:
        predictor = _require_one(
            self._matching(model.algorithm_code, model.algorithm_version),
            adapter_kind="ModelPredictor",
            algorithm_code=model.algorithm_code,
            algorithm_version=model.algorithm_version,
        )
        return predictor.predict(model, batch)

    def _matching(
        self,
        algorithm_code: str,
        algorithm_version: str,
    ) -> tuple[ModelPredictor, ...]:
        return tuple(
            item
            for item in self._predictors
            if item.supports(algorithm_code, algorithm_version)
        )


_Adapter = TypeVar("_Adapter", ModelTrainer, ModelPredictor)


def _require_one(
    adapters: tuple[_Adapter, ...],
    *,
    adapter_kind: str,
    algorithm_code: str,
    algorithm_version: str,
) -> _Adapter:
    if len(adapters) != 1:
        raise ValueError(
            f"{algorithm_code}@{algorithm_version} requires exactly one explicit "
            f"{adapter_kind}; found {len(adapters)}"
        )
    return adapters[0]


__all__ = [
    "ExplicitModelPredictorComposition",
    "ExplicitModelTrainerComposition",
]
