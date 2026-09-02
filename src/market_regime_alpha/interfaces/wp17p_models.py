"""Deterministic optional Model training for the WP-17P pilot."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid5

from market_regime_alpha.bootstrap import TargetApplication
from market_regime_alpha.interfaces.wp17p_authorities import Wp17pAuthorityCatalog
from market_regime_alpha.interfaces.wp17p_evaluation import Wp17pCompletedEvaluation
from market_regime_alpha.research_qualification.application.research_models import (
    RegisterModelVersionRequest,
)
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestArmKind,
)
from market_regime_alpha.research_qualification.domain.research_models import (
    ResearchModelPlan,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    ExploratoryBacktestArmKind,
    PartitionPurpose,
)
from market_regime_alpha.research_qualification.ports.model_inputs import (
    OpenModelTrainingRunRequest,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.shared.hashing import canonical_json_sha256


_RIDGE_ALPHA = Decimal("0.01")
_ALGORITHM_CODE = "deterministic_ridge"
_ALGORITHM_VERSION = "1.0.0"
_ALGORITHM_SHA256 = canonical_json_sha256(
    {
        "algorithm": _ALGORITHM_CODE,
        "centering": "decimal_mean",
        "intercept": True,
        "linear_solver": "deterministic_gaussian_elimination",
        "ridge_alpha": str(_RIDGE_ALPHA),
        "scaling": "none",
        "version": _ALGORITHM_VERSION,
    }
)


@dataclass(frozen=True, slots=True)
class Wp17pModelExecution:
    model_id: UUID
    model_training_run_id: UUID
    model_version_id: UUID
    model_version_hash: str


class Wp17pModelOperations:
    """Train only from a completed, exact FIT Evaluation roster."""

    def __init__(self, application: TargetApplication) -> None:
        self._application = application

    def train(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        fit_evaluation: Wp17pCompletedEvaluation,
    ) -> Wp17pModelExecution:
        challenger = tuple(
            item
            for item in catalog.backtest.arms
            if item.kind is BacktestArmKind.MODEL_CHALLENGER
        )
        fit_folds = tuple(
            item
            for item in catalog.backtest.folds
            if item.purpose is PartitionPurpose.FIT
        )
        metrics = tuple(
            item
            for item in catalog.fit_evaluation_protocol.metrics
            if item.backtest_arm_kind
            is ExploratoryBacktestArmKind.MODEL_CHALLENGER
        )
        if len(challenger) != 1 or len(fit_folds) != 1 or len(metrics) != 1:
            raise ValueError("WP-17P Model training declarations are ambiguous")
        model = wp17p_model_plan(catalog)
        app = self._application
        app.research_models.register_model(
            model,
            _context("register-model"),
        )
        training_run_id = uuid5(model.model_id, "training:1")
        app.research_models.open_training_run(
            OpenModelTrainingRunRequest(
                training_run_id,
                model.model_id,
                fit_evaluation.evaluation_run_id,
                metrics[0].evaluation_protocol_metric_id,
                catalog.backtest.exploratory_backtest_run_id,
                challenger[0].exploratory_backtest_arm_id,
                fit_folds[0].exploratory_backtest_fold_id,
                _ALGORITHM_CODE,
                _ALGORITHM_VERSION,
                _ALGORITHM_SHA256,
                _RIDGE_ALPHA,
                catalog.backtest.random_seed,
                catalog.backtest.code_artifact,
                catalog.backtest.config_artifact,
                catalog.backtest.provenance_sha256,
            ),
            _context("open-model-training"),
        )
        model_version_id = uuid5(model.model_id, "version:1")
        version = app.research_models.fit_and_register_version(
            RegisterModelVersionRequest(
                model_version_id,
                model.model_id,
                1,
                training_run_id,
                str(catalog.backtest.provenance_sha256),
            ),
            _context("fit-model-version"),
        )
        return Wp17pModelExecution(
            model.model_id,
            training_run_id,
            model_version_id,
            version.result_hash,
        )


def wp17p_model_plan(catalog: Wp17pAuthorityCatalog) -> ResearchModelPlan:
    return ResearchModelPlan(
        uuid5(catalog.backtest.exploratory_backtest_run_id, "model:ridge"),
        "wp17p_deterministic_ridge",
        catalog.target.target_definition_id,
        catalog.target.version,
        catalog.target.content_sha256,
        (
            (
                catalog.feature.feature_definition_id,
                catalog.feature.content_sha256,
            ),
        ),
        catalog.backtest.code_artifact,
        catalog.backtest.config_artifact,
        catalog.backtest.provenance_sha256,
    )


def _context(suffix: str) -> CommandContext:
    return CommandContext(
        idempotency_key=f"wp17p:{suffix}",
        actor_type=ActorType.OPERATOR,
        actor_id="wp17p-pilot-operator",
        reason_code="WP17P_EXPLORATORY_PILOT",
    )


__all__ = [
    "Wp17pModelExecution",
    "Wp17pModelOperations",
    "wp17p_model_plan",
]
