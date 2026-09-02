"""Controlled WP-17P FIT, Model, and VALIDATION campaign orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from market_regime_alpha.bootstrap import TargetApplication
from market_regime_alpha.interfaces.wp17p_authorities import Wp17pAuthorityCatalog
from market_regime_alpha.interfaces.wp17p_decisions import (
    Wp17pDecisionExecution,
    Wp17pDecisionOperations,
)
from market_regime_alpha.interfaces.wp17p_evaluation import (
    Wp17pCompletedEvaluation,
    Wp17pEvaluationOperations,
    Wp17pOpenEvaluation,
    Wp17pPreparedEvaluation,
)
from market_regime_alpha.interfaces.wp17p_models import (
    Wp17pModelExecution,
    Wp17pModelOperations,
)
from market_regime_alpha.interfaces.wp17p_operations import (
    Wp17pDatasetAuthority,
    Wp17pResearchOperations,
)
from market_regime_alpha.interfaces.wp17p_outcomes import (
    Wp17pOutcomeExecution,
    Wp17pOutcomeOperations,
)
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestArmKind,
    BacktestSessionRole,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.shared.identity import InstrumentId


class _ResearchOperations(Protocol):
    def register_catalog(self, catalog: Wp17pAuthorityCatalog) -> None: ...

    def materialize_dataset(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        pilot_instrument_ids: tuple[InstrumentId, ...],
        exploratory_backtest_arm_id: UUID,
        exploratory_backtest_fold_id: UUID,
        exploratory_backtest_fold_session_id: UUID,
    ) -> Wp17pDatasetAuthority: ...


class _DecisionOperations(Protocol):
    def execute(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        dataset: Wp17pDatasetAuthority,
        complete_decision_support: bool,
        model_version_id: UUID | None = None,
    ) -> Wp17pDecisionExecution: ...


class _EvaluationOperations(Protocol):
    def predeclare(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        datasets: tuple[Wp17pDatasetAuthority, ...],
        decisions: tuple[Wp17pDecisionExecution, ...],
    ) -> Wp17pPreparedEvaluation: ...

    def open(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        prepared: Wp17pPreparedEvaluation,
        outcomes: tuple[Wp17pOutcomeExecution, ...],
    ) -> Wp17pOpenEvaluation: ...

    def complete(
        self,
        *,
        opened: Wp17pOpenEvaluation,
        outcomes: tuple[Wp17pOutcomeExecution, ...],
    ) -> Wp17pCompletedEvaluation: ...


class _OutcomeOperations(Protocol):
    def settle(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        dataset: Wp17pDatasetAuthority,
        decision: Wp17pDecisionExecution,
    ) -> Wp17pOutcomeExecution: ...


class _ModelOperations(Protocol):
    def train(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        fit_evaluation: Wp17pCompletedEvaluation,
    ) -> Wp17pModelExecution: ...


@dataclass(frozen=True, slots=True)
class Wp17pCampaignExecution:
    fit_dataset_id: UUID
    fit_evaluation_run_id: UUID
    model_version_id: UUID
    validation_dataset_ids: tuple[UUID, ...]
    validation_decision_run_ids: tuple[UUID, ...]
    validation_evaluation_run_id: UUID


class Wp17pCampaignOperations:
    """Coordinate owners without becoming a second research truth chain."""

    def __init__(
        self,
        application: TargetApplication,
        *,
        code_sha: str,
        research: _ResearchOperations | None = None,
        decisions: _DecisionOperations | None = None,
        evaluations: _EvaluationOperations | None = None,
        outcomes: _OutcomeOperations | None = None,
        models: _ModelOperations | None = None,
    ) -> None:
        self._research = research or Wp17pResearchOperations(application)
        self._decisions = decisions or Wp17pDecisionOperations(
            application,
            code_sha=code_sha,
        )
        self._evaluations = evaluations or Wp17pEvaluationOperations(application)
        self._outcomes = outcomes or Wp17pOutcomeOperations(
            application,
            code_sha=code_sha,
        )
        self._models = models or Wp17pModelOperations(application)

    def run(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        pilot_instrument_ids: tuple[InstrumentId, ...],
    ) -> Wp17pCampaignExecution:
        self._research.register_catalog(catalog)
        baseline = _one_arm(catalog, BacktestArmKind.RULE_BASELINE)
        challenger = _one_arm(catalog, BacktestArmKind.MODEL_CHALLENGER)
        fit_fold = _one_fold(catalog, PartitionPurpose.FIT)
        validation_fold = _one_fold(catalog, PartitionPurpose.VALIDATION)
        fit_session = _one_session(fit_fold, BacktestSessionRole.FIT_INPUT)
        validation_session = _one_session(
            validation_fold,
            BacktestSessionRole.EVALUATION,
        )

        fit_dataset = self._research.materialize_dataset(
            catalog=catalog,
            pilot_instrument_ids=pilot_instrument_ids,
            exploratory_backtest_arm_id=challenger.exploratory_backtest_arm_id,
            exploratory_backtest_fold_id=fit_fold.exploratory_backtest_fold_id,
            exploratory_backtest_fold_session_id=(fit_session.exploratory_backtest_fold_session_id),
        )
        fit_decision = self._decisions.execute(
            catalog=catalog,
            dataset=fit_dataset,
            complete_decision_support=False,
        )
        fit_predeclared = self._evaluations.predeclare(
            catalog=catalog,
            datasets=(fit_dataset,),
            decisions=(fit_decision,),
        )
        fit_outcome = self._outcomes.settle(
            catalog=catalog,
            dataset=fit_dataset,
            decision=fit_decision,
        )
        fit_open = self._evaluations.open(
            catalog=catalog,
            prepared=fit_predeclared,
            outcomes=(fit_outcome,),
        )
        fit_evaluation = self._evaluations.complete(
            opened=fit_open,
            outcomes=(fit_outcome,),
        )
        model = self._models.train(
            catalog=catalog,
            fit_evaluation=fit_evaluation,
        )

        validation_datasets = tuple(
            self._research.materialize_dataset(
                catalog=catalog,
                pilot_instrument_ids=pilot_instrument_ids,
                exploratory_backtest_arm_id=arm.exploratory_backtest_arm_id,
                exploratory_backtest_fold_id=(validation_fold.exploratory_backtest_fold_id),
                exploratory_backtest_fold_session_id=(validation_session.exploratory_backtest_fold_session_id),
            )
            for arm in (baseline, challenger)
        )
        validation_decisions = tuple(
            self._decisions.execute(
                catalog=catalog,
                dataset=dataset,
                complete_decision_support=True,
                model_version_id=(None if arm.kind is BacktestArmKind.RULE_BASELINE else model.model_version_id),
            )
            for arm, dataset in zip(
                (baseline, challenger),
                validation_datasets,
                strict=True,
            )
        )
        validation_predeclared = self._evaluations.predeclare(
            catalog=catalog,
            datasets=validation_datasets,
            decisions=validation_decisions,
        )
        validation_outcomes = tuple(
            self._outcomes.settle(
                catalog=catalog,
                dataset=dataset,
                decision=decision,
            )
            for dataset, decision in zip(
                validation_datasets,
                validation_decisions,
                strict=True,
            )
        )
        validation_open = self._evaluations.open(
            catalog=catalog,
            prepared=validation_predeclared,
            outcomes=validation_outcomes,
        )
        validation_evaluation = self._evaluations.complete(
            opened=validation_open,
            outcomes=validation_outcomes,
        )
        return Wp17pCampaignExecution(
            fit_dataset.dataset_id,
            fit_evaluation.evaluation_run_id,
            model.model_version_id,
            tuple(item.dataset_id for item in validation_datasets),
            tuple(item.decision_run_id for item in validation_decisions),
            validation_evaluation.evaluation_run_id,
        )


def _one_arm(catalog: Wp17pAuthorityCatalog, kind: BacktestArmKind):
    matches = tuple(item for item in catalog.backtest.arms if item.kind is kind)
    if len(matches) != 1:
        raise ValueError(f"WP-17P requires exactly one {kind.value} arm")
    return matches[0]


def _one_fold(catalog: Wp17pAuthorityCatalog, purpose: PartitionPurpose):
    matches = tuple(item for item in catalog.backtest.folds if item.purpose is purpose)
    if len(matches) != 1:
        raise ValueError(f"WP-17P requires exactly one {purpose.value} fold")
    return matches[0]


def _one_session(fold, role: BacktestSessionRole):
    matches = tuple(item for item in fold.sessions if item.role is role)
    if len(matches) != 1:
        raise ValueError(f"WP-17P fold requires exactly one {role.value} session")
    return matches[0]


__all__ = ["Wp17pCampaignExecution", "Wp17pCampaignOperations"]
