from __future__ import annotations

from decimal import Decimal
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid5

from market_regime_alpha.infrastructure.models import (
    DeterministicRidgeBacktestModelAdapter,
)
from market_regime_alpha.interfaces.backtest_actions import (
    BacktestCanonicalActionHandler,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestModelTrainingRecipe,
    BacktestModelTrainingRequirement,
    BacktestSpecification,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_models import (
    ModelDependencyVersion,
    ModelExecutionEnvironment,
    ModelScalarParameter,
    ModelScalarType,
)
from market_regime_alpha.research_qualification.ports.backtest_actions import (
    BacktestFitEvaluationExecution,
    BacktestModelExecutionResult,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestActionKind,
    BacktestExpectedAction,
)
from market_regime_alpha.runtime.ports import AttemptClaim


def _recipe() -> BacktestModelTrainingRecipe:
    return BacktestModelTrainingRecipe(
        algorithm_code="deterministic_ridge",
        algorithm_version="1.0.0",
        implementation_sha256="a" * 64,
        environment=ModelExecutionEnvironment(
            python_implementation="cpython",
            python_version="3.12.11",
            runtime_code="uv",
            runtime_version="0.8.13",
            uv_lock_sha256="b" * 64,
            dependencies=(ModelDependencyVersion(1, "numpy", "2.3.2", "c" * 64),),
        ),
        hyperparameters=(
            ModelScalarParameter(
                1,
                "ridge_alpha",
                ModelScalarType.DECIMAL,
                decimal_value=Decimal("0.01"),
            ),
        ),
    )


def test_ridge_adapter_translates_frozen_recipe_without_engine_defaults() -> None:
    recipe = _recipe()
    requirement = BacktestModelTrainingRequirement(
        requirement_id=UUID(int=1),
        ordinal=1,
        model_arm_id=UUID(int=2),
        fit_fold_id=UUID(int=3),
        validation_fold_id=UUID(int=4),
        model_definition=AuthorityBinding(UUID(int=5), "d" * 64),
        training_metric=AuthorityBinding(UUID(int=6), "e" * 64),
        planned_model_version=1,
        recipe=recipe,
    )
    artifact = ArtifactBinding(UUID(int=7), "f" * 64, 10)
    specification = cast(
        BacktestSpecification,
        SimpleNamespace(
            exploratory_backtest_run_id=UUID(int=8),
            random_seed=1729,
            code_artifact=artifact,
            config_artifact=artifact,
            provenance_sha256="1" * 64,
        ),
    )
    evaluation = BacktestFitEvaluationExecution(
        UUID(int=9),
        UUID(int=10),
        UUID(int=11),
    )

    adapter = DeterministicRidgeBacktestModelAdapter()
    request = adapter.training_request(
        specification=specification,
        requirement=requirement,
        fit_evaluation=evaluation,
        model_training_run_id=UUID(int=12),
    )

    assert adapter.supports(recipe) is True
    assert request.training.algorithm_code == recipe.algorithm_code
    assert request.training.algorithm_sha256 == recipe.implementation_sha256
    assert request.training.ridge_alpha == Decimal("0.01")
    assert request.training.evaluation_run_id == evaluation.evaluation_run_id
    assert request.environment == recipe.environment
    assert request.hyperparameters == recipe.hyperparameters


class _ModelApplication:
    def __init__(self) -> None:
        self.opened = None
        self.versioned = None

    def open_reproducible_training_run(self, request, context, *, runtime_claim=None) -> None:
        self.opened = (request, context, runtime_claim)

    def fit_and_register_reproducible_version(self, request, context, *, runtime_claim=None) -> None:
        self.versioned = (request, context, runtime_claim)


class _Reads:
    def __init__(self, evaluation, result) -> None:
        self.evaluation = evaluation
        self.result = result

    def fit_evaluation_execution(self, **kwargs):
        self.fit_scope = kwargs
        return self.evaluation

    def model_execution_result(self, **kwargs):
        self.model_scope = kwargs
        return self.result


class _Backtests:
    def bind_model_lineage(self, lineage, context, *, runtime_claim=None):
        self.bound = (lineage, context, runtime_claim)


def _claim(step_key: str) -> AttemptClaim:
    return AttemptClaim(
        attempt_id=UUID(int=21),
        run_id=UUID(int=22),
        step_id=UUID(int=23),
        step_key=step_key,
        attempt_no=1,
        fence_token=1,
        lease_owner="worker",
        lease_until=datetime.now(UTC) + timedelta(minutes=1),
    )


def test_model_action_delegates_each_mutation_to_canonical_owner() -> None:
    recipe = _recipe()
    requirement = BacktestModelTrainingRequirement(
        requirement_id=UUID(int=31),
        ordinal=1,
        model_arm_id=UUID(int=32),
        fit_fold_id=UUID(int=33),
        validation_fold_id=UUID(int=34),
        model_definition=AuthorityBinding(UUID(int=35), "d" * 64),
        training_metric=AuthorityBinding(UUID(int=36), "e" * 64),
        planned_model_version=7,
        recipe=recipe,
    )
    artifact = ArtifactBinding(UUID(int=37), "f" * 64, 10)
    specification = cast(
        BacktestSpecification,
        SimpleNamespace(
            exploratory_backtest_run_id=UUID(int=38),
            content_sha256="1" * 64,
            random_seed=1729,
            code_artifact=artifact,
            config_artifact=artifact,
            provenance_sha256="2" * 64,
            model_training_requirements=(requirement,),
        ),
    )
    action = BacktestExpectedAction(
        action_id=UUID(int=39),
        ordinal=1,
        kind=BacktestActionKind.TRAIN_MODEL,
        exploratory_backtest_run_id=specification.exploratory_backtest_run_id,
        arm_id=requirement.model_arm_id,
        fold_id=requirement.fit_fold_id,
        fold_session_id=None,
        model_training_requirement_id=requirement.requirement_id,
        dependency_action_ids=(),
    )
    evaluation = BacktestFitEvaluationExecution(UUID(int=40), UUID(int=41), UUID(int=42))
    model_training_run_id = uuid5(action.action_id, "model-training-run")
    model_version_id = uuid5(action.action_id, "model-version")
    result = BacktestModelExecutionResult(
        model_id=requirement.model_definition.authority_id,
        model_training_run_id=model_training_run_id,
        model_training_run_sha256="3" * 64,
        model_training_reproducibility_sha256="4" * 64,
        model_version_id=model_version_id,
        model_version_sha256="5" * 64,
    )
    models = _ModelApplication()
    reads = _Reads(evaluation, result)
    backtests = _Backtests()
    handler = BacktestCanonicalActionHandler(
        artifacts=cast(Any, SimpleNamespace()),
        selection=cast(Any, SimpleNamespace()),
        research_definitions=cast(Any, SimpleNamespace()),
        reads=cast(Any, reads),
        feature_materializers=(cast(Any, SimpleNamespace()),),
        worker_id="test-worker",
        research_models=cast(Any, models),
        model_adapters=(DeterministicRidgeBacktestModelAdapter(),),
        backtests=cast(Any, backtests),
    )

    for step_key in (
        "open-model-training",
        "register-model-version",
        "bind-model-lineage",
    ):
        handler.execute_step(specification, action, _claim(step_key))

    assert models.opened[0].training.model_training_run_id == model_training_run_id
    assert models.versioned[0].model_version_id == model_version_id
    lineage = backtests.bound[0]
    assert lineage.model_training_requirement_id == requirement.requirement_id
    assert lineage.backtest_evaluation_execution_id == (evaluation.backtest_evaluation_execution_id)
    assert lineage.model_training_run_sha256 == result.model_training_run_sha256
