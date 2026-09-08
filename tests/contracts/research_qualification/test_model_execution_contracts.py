from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.infrastructure.models import (
    DeterministicRidgePredictor,
    DeterministicRidgeTrainer,
    ExplicitModelPredictorComposition,
    ExplicitModelTrainerComposition,
)
from market_regime_alpha.research_qualification.domain.research_models import (
    LinearTrainingRow,
)
from market_regime_alpha.research_qualification.ports.model_execution import (
    FrozenModelTrainingInput,
    FrozenModelVersionPayload,
    ModelPredictionBatch,
    ModelPrediction,
    ModelPredictionRow,
    ModelScalarParameter,
    ModelScalarType,
)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _training() -> FrozenModelTrainingInput:
    return FrozenModelTrainingInput(
        algorithm_code="deterministic_ridge",
        algorithm_version="1.0",
        implementation_sha256="a" * 64,
        feature_definition_ids=(_id(1), _id(2)),
        hyperparameters=(
            ModelScalarParameter(
                "ridge_alpha",
                ModelScalarType.DECIMAL,
                decimal_value=Decimal("0.01"),
            ),
        ),
        seed=17,
        rows=(
            LinearTrainingRow(_id(10), (Decimal("1"), Decimal("3")), Decimal("2")),
            LinearTrainingRow(_id(11), (Decimal("2"), Decimal("2")), Decimal("4")),
            LinearTrainingRow(_id(12), (Decimal("3"), Decimal("1")), Decimal("6")),
        ),
    )


def test_explicit_ridge_adapter_is_deterministic_across_fit_and_predict() -> None:
    training = _training()
    trainer = DeterministicRidgeTrainer()
    fitted = trainer.fit(training)

    assert trainer.fit(training) == fitted

    model = FrozenModelVersionPayload(
        algorithm_code=training.algorithm_code,
        algorithm_version=training.algorithm_version,
        implementation_sha256=training.implementation_sha256,
        fitted_content=fitted.content,
        fitted_content_sha256=fitted.content_sha256,
        feature_definition_ids=training.feature_definition_ids,
        hyperparameters=training.hyperparameters,
        seed=training.seed,
        coefficient_count=fitted.coefficient_count,
    )
    batch = ModelPredictionBatch(
        (
            ModelPredictionRow(_id(20), (Decimal("4"), Decimal("0"))),
            ModelPredictionRow(_id(21), (Decimal("2.5"), Decimal("1.5"))),
        )
    )
    predictor = DeterministicRidgePredictor()

    first = predictor.predict(model, batch)
    second = predictor.predict(model, batch)

    assert first == second
    assert tuple(item.row_id for item in first) == (_id(20), _id(21))
    assert all(item.point_estimate.is_finite() for item in first)


def test_model_adapter_fails_closed_for_wrong_family_or_frozen_contract() -> None:
    training = _training()
    trainer = DeterministicRidgeTrainer()

    with pytest.raises(ValueError, match="cannot execute"):
        trainer.fit(replace(training, algorithm_code="unregistered_family"))

    fitted = trainer.fit(training)
    model = FrozenModelVersionPayload(
        algorithm_code=training.algorithm_code,
        algorithm_version=training.algorithm_version,
        implementation_sha256=training.implementation_sha256,
        fitted_content=fitted.content,
        fitted_content_sha256=fitted.content_sha256,
        feature_definition_ids=training.feature_definition_ids,
        hyperparameters=training.hyperparameters,
        seed=training.seed,
        coefficient_count=fitted.coefficient_count,
    )
    with pytest.raises(ValueError, match="differ"):
        DeterministicRidgePredictor().predict(
            replace(model, coefficient_count=model.coefficient_count + 1),
            ModelPredictionBatch((ModelPredictionRow(_id(20), (Decimal("1"), Decimal("2"))),)),
        )


def test_model_parameters_are_closed_typed_scalars() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ModelScalarParameter("alpha", ModelScalarType.DECIMAL)
    with pytest.raises(ValueError, match="does not match"):
        ModelScalarParameter(
            "alpha",
            ModelScalarType.INTEGER,
            decimal_value=Decimal("1"),
        )


def test_explicit_model_composition_routes_without_engine_family_dispatch() -> None:
    training = _training()
    ridge_trainer = DeterministicRidgeTrainer()
    ridge_predictor = DeterministicRidgePredictor()
    trainers = ExplicitModelTrainerComposition((ridge_trainer,))
    predictors = ExplicitModelPredictorComposition((ridge_predictor,))

    fitted = trainers.fit(training)
    model = FrozenModelVersionPayload(
        algorithm_code=training.algorithm_code,
        algorithm_version=training.algorithm_version,
        implementation_sha256=training.implementation_sha256,
        fitted_content=fitted.content,
        fitted_content_sha256=fitted.content_sha256,
        feature_definition_ids=training.feature_definition_ids,
        hyperparameters=training.hyperparameters,
        seed=training.seed,
        coefficient_count=fitted.coefficient_count,
    )
    batch = ModelPredictionBatch(
        (ModelPredictionRow(_id(20), (Decimal("4"), Decimal("0"))),)
    )

    assert trainers.supports("deterministic_ridge", "1.0") is True
    assert predictors.supports("deterministic_ridge", "1.0") is True
    assert predictors.predict(model, batch) == ridge_predictor.predict(model, batch)


def test_explicit_model_composition_fails_closed_for_missing_or_ambiguous_family() -> None:
    class DuplicateTrainer:
        def supports(self, algorithm_code: str, algorithm_version: str) -> bool:
            return algorithm_code == "deterministic_ridge" and algorithm_version == "1.0"

        def fit(self, training: FrozenModelTrainingInput):
            return DeterministicRidgeTrainer().fit(training)

    class DuplicatePredictor:
        def supports(self, algorithm_code: str, algorithm_version: str) -> bool:
            return algorithm_code == "deterministic_ridge" and algorithm_version == "1.0"

        def predict(
            self,
            model: FrozenModelVersionPayload,
            batch: ModelPredictionBatch,
        ) -> tuple[ModelPrediction, ...]:
            return DeterministicRidgePredictor().predict(model, batch)

    training = _training()
    with pytest.raises(ValueError, match="exactly one explicit ModelTrainer"):
        ExplicitModelTrainerComposition(()).fit(training)
    with pytest.raises(ValueError, match="exactly one explicit ModelTrainer"):
        ExplicitModelTrainerComposition(
            (DeterministicRidgeTrainer(), DuplicateTrainer())
        ).fit(training)

    fitted = DeterministicRidgeTrainer().fit(training)
    model = FrozenModelVersionPayload(
        algorithm_code=training.algorithm_code,
        algorithm_version=training.algorithm_version,
        implementation_sha256=training.implementation_sha256,
        fitted_content=fitted.content,
        fitted_content_sha256=fitted.content_sha256,
        feature_definition_ids=training.feature_definition_ids,
        hyperparameters=training.hyperparameters,
        seed=training.seed,
        coefficient_count=fitted.coefficient_count,
    )
    batch = ModelPredictionBatch(
        (ModelPredictionRow(_id(20), (Decimal("4"), Decimal("0"))),)
    )
    with pytest.raises(ValueError, match="exactly one explicit ModelPredictor"):
        ExplicitModelPredictorComposition(
            (DeterministicRidgePredictor(), DuplicatePredictor())
        ).predict(model, batch)
    with pytest.raises(ValueError, match="duplicates"):
        replace(
            _training(),
            hyperparameters=(
                ModelScalarParameter(
                    "ridge_alpha",
                    ModelScalarType.DECIMAL,
                    decimal_value=Decimal("0.01"),
                ),
                ModelScalarParameter(
                    "ridge_alpha",
                    ModelScalarType.DECIMAL,
                    decimal_value=Decimal("0.02"),
                ),
            ),
        )
