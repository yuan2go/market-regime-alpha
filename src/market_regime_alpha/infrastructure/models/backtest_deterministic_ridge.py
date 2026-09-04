"""Backtest request adapter for the explicitly supported ridge family."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestModelTrainingRecipe,
    BacktestModelTrainingRequirement,
    BacktestSpecification,
)
from market_regime_alpha.research_qualification.domain.research_models import (
    ModelScalarType,
)
from market_regime_alpha.research_qualification.ports.backtest_actions import (
    BacktestFitEvaluationExecution,
)
from market_regime_alpha.research_qualification.ports.model_inputs import (
    OpenModelTrainingRunRequest,
    ReproducibleModelTrainingRunRequest,
)


class DeterministicRidgeBacktestModelAdapter:
    """Translate a frozen ridge recipe without leaking ridge into the engine."""

    def supports(self, recipe: BacktestModelTrainingRecipe) -> bool:
        return recipe.algorithm_code == "deterministic_ridge" and recipe.algorithm_version in {"1.0", "1.0.0"}

    def training_request(
        self,
        *,
        specification: BacktestSpecification,
        requirement: BacktestModelTrainingRequirement,
        fit_evaluation: BacktestFitEvaluationExecution,
        model_training_run_id: UUID,
    ) -> ReproducibleModelTrainingRunRequest:
        recipe = requirement.recipe
        if recipe is None or not self.supports(recipe):
            raise ValueError("ridge Backtest adapter cannot execute this recipe")
        alpha = tuple(
            item for item in recipe.hyperparameters if item.parameter_code == "ridge_alpha" and item.value_type is ModelScalarType.DECIMAL
        )
        if len(alpha) != 1 or alpha[0].decimal_value is None:
            raise ValueError("deterministic ridge requires one typed decimal ridge_alpha")
        return ReproducibleModelTrainingRunRequest(
            training=OpenModelTrainingRunRequest(
                model_training_run_id=model_training_run_id,
                model_id=requirement.model_definition.authority_id,
                evaluation_run_id=fit_evaluation.evaluation_run_id,
                evaluation_protocol_metric_id=(self._training_metric(requirement)),
                exploratory_backtest_run_id=(specification.exploratory_backtest_run_id),
                exploratory_backtest_arm_id=requirement.model_arm_id,
                exploratory_backtest_fold_id=requirement.fit_fold_id,
                algorithm_code=recipe.algorithm_code,
                algorithm_version=recipe.algorithm_version,
                algorithm_sha256=recipe.implementation_sha256,
                ridge_alpha=alpha[0].decimal_value,
                random_seed=specification.random_seed,
                code_artifact=specification.code_artifact,
                config_artifact=specification.config_artifact,
                provenance_sha256=specification.provenance_sha256,
            ),
            environment=recipe.environment,
            hyperparameters=recipe.hyperparameters,
        )

    @staticmethod
    def _training_metric(
        requirement: BacktestModelTrainingRequirement,
    ) -> UUID:
        if requirement.training_metric is None:
            raise ValueError("current Model requirement lacks training metric")
        return requirement.training_metric.authority_id


__all__ = ["DeterministicRidgeBacktestModelAdapter"]
