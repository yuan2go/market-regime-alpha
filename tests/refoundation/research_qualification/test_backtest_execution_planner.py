from __future__ import annotations

from datetime import date
from uuid import UUID

from market_regime_alpha.research_qualification.application.backtest_execution import (
    BacktestExecutionPlanner,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestArmFold,
    BacktestArmSpecification,
    BacktestComparisonRole,
    BacktestContextMode,
    BacktestExecutionKind,
    BacktestFoldDependency,
    BacktestFoldSession,
    BacktestFoldSpecification,
    BacktestModelTrainingRequirement,
    BacktestSessionRole,
    FrozenBacktestEvidence,
    FrozenBacktestRun,
    FrozenBacktestSource,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestActionKind,
    BacktestActionObservation,
    BacktestExecutionState,
    BacktestNextOperation,
    BacktestObservedState,
    BacktestResearchState,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _binding(value: int) -> AuthorityBinding:
    return AuthorityBinding(_id(value), f"{value:064x}")


def _run() -> FrozenBacktestRun:
    arms = (
        BacktestArmSpecification(
            exploratory_backtest_arm_id=_id(101),
            ordinal=1,
            arm_code="rule",
            execution_kind=BacktestExecutionKind.RULE,
            comparison_role=BacktestComparisonRole.BASELINE,
            context_mode=BacktestContextMode.CURRENT_GATE,
            candidate=_binding(11),
            context=_binding(12),
            strategy=_binding(13),
            model=None,
            portfolio=_binding(14),
            risk=_binding(15),
            effective_cost_roster_sha256="a" * 64,
        ),
        BacktestArmSpecification(
            exploratory_backtest_arm_id=_id(102),
            ordinal=2,
            arm_code="ridge",
            execution_kind=BacktestExecutionKind.MODEL,
            comparison_role=BacktestComparisonRole.CHALLENGER,
            context_mode=BacktestContextMode.CURRENT_GATE,
            candidate=_binding(11),
            context=_binding(12),
            strategy=_binding(13),
            model=_binding(16),
            portfolio=_binding(14),
            risk=_binding(15),
            effective_cost_roster_sha256="a" * 64,
        ),
    )
    purposes = (
        PartitionPurpose.FIT,
        PartitionPurpose.VALIDATION,
        PartitionPurpose.FIT,
        PartitionPurpose.VALIDATION,
    )
    folds = tuple(
        BacktestFoldSpecification(
            exploratory_backtest_fold_id=_id(200 + ordinal),
            ordinal=ordinal,
            purpose=purpose,
            exchange_code="XSHG",
            purge_sessions=0,
            embargo_sessions=0,
            evaluation_protocol=_binding(300 + ordinal),
            sessions=(
                BacktestFoldSession(
                    exploratory_backtest_fold_session_id=_id(400 + ordinal),
                    ordinal=1,
                    trading_session_id=_id(500 + ordinal),
                    session_date=date(2026, 1, ordinal + 1),
                    role=(
                        BacktestSessionRole.FIT_INPUT
                        if purpose is PartitionPurpose.FIT
                        else BacktestSessionRole.EVALUATION
                    ),
                ),
            ),
        )
        for ordinal, purpose in enumerate(purposes, start=1)
    )
    dependencies = (
        BacktestFoldDependency(
            _id(601),
            1,
            folds[0].exploratory_backtest_fold_id,
            folds[1].exploratory_backtest_fold_id,
        ),
        BacktestFoldDependency(
            _id(602),
            2,
            folds[2].exploratory_backtest_fold_id,
            folds[3].exploratory_backtest_fold_id,
        ),
    )
    arm_folds = tuple(
        BacktestArmFold(
            arm_fold_id=_id(700 + ordinal),
            ordinal=ordinal,
            arm_id=arm.exploratory_backtest_arm_id,
            fold_id=fold.exploratory_backtest_fold_id,
        )
        for ordinal, (fold, arm) in enumerate(
            ((fold, arm) for fold in folds for arm in arms), start=1
        )
    )
    model_definition = arms[1].model
    assert model_definition is not None
    requirements = tuple(
        BacktestModelTrainingRequirement(
            requirement_id=_id(800 + ordinal),
            ordinal=ordinal,
            model_arm_id=arms[1].exploratory_backtest_arm_id,
            fit_fold_id=dependency.fit_fold_id,
            validation_fold_id=dependency.validation_fold_id,
            model_definition=model_definition,
        )
        for ordinal, dependency in enumerate(dependencies, start=1)
    )
    return FrozenBacktestRun(
        exploratory_backtest_run_id=_id(1),
        run_code="generic",
        generation=99,
        definition_sha256="d" * 64,
        specification_sha256="e" * 64,
        source=FrozenBacktestSource.CURRENT_RELATIONAL,
        evidence=FrozenBacktestEvidence.CURRENT,
        arms=arms,
        folds=folds,
        fold_dependencies=dependencies,
        arm_folds=arm_folds,
        model_training_requirements=requirements,
        distinct_trading_session_count=4,
        fold_session_binding_count=4,
    )


def test_planner_compiles_arbitrary_fold_dag_without_ordinal_inference() -> None:
    plan = BacktestExecutionPlanner().compile(_run())

    assert len(plan.expected_actions) == 30
    assert {item.action.kind for item in plan.ready_actions} == {
        BacktestActionKind.MATERIALIZE_DATASET
    }
    assert len(plan.ready_actions) == 8
    assert plan.execution_state is BacktestExecutionState.PLANNED
    assert plan.research_state is BacktestResearchState.NOT_APPLICABLE

    training = {
        action.model_training_requirement_id: action
        for action in plan.expected_actions
        if action.kind is BacktestActionKind.TRAIN_MODEL
    }
    assert set(training) == {_id(801), _id(802)}
    validation_model_decisions = tuple(
        action
        for action in plan.expected_actions
        if action.kind is BacktestActionKind.GENERATE_DECISION_SUPPORT
        and action.arm_id == _id(102)
        and action.fold_id in {_id(202), _id(204)}
    )
    assert len(validation_model_decisions) == 2
    assert training[_id(801)].action_id in validation_model_decisions[0].dependency_action_ids
    assert training[_id(802)].action_id in validation_model_decisions[1].dependency_action_ids


def test_completed_resume_reuses_every_identity_and_produces_no_work() -> None:
    planner = BacktestExecutionPlanner()
    initial = planner.compile(_run())
    observations = tuple(
        BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MATCHED_COMPLETE,
            (
                BacktestResearchState.ESTIMABLE
                if action.kind
                in {
                    BacktestActionKind.COMPLETE_FOLD_EVALUATION,
                    BacktestActionKind.COMPLETE_AGGREGATE_EVALUATION,
                }
                else BacktestResearchState.NOT_APPLICABLE
            ),
        )
        for action in initial.expected_actions
    )

    resumed = planner.compile(_run(), observations)
    replayed = planner.compile(_run(), observations)

    assert resumed.expected_actions == replayed.expected_actions
    assert resumed.action_roster_sha256 == initial.action_roster_sha256
    assert resumed.ready_actions == ()
    assert resumed.execution_state is BacktestExecutionState.COMPLETED
    assert resumed.research_state is BacktestResearchState.ESTIMABLE
    assert all(
        fold.execution_state is BacktestExecutionState.COMPLETED
        for fold in resumed.fold_lifecycles
    )


def test_not_estimable_is_completed_research_not_execution_failure() -> None:
    planner = BacktestExecutionPlanner()
    initial = planner.compile(_run())
    observations = tuple(
        BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MATCHED_COMPLETE,
            (
                BacktestResearchState.NOT_ESTIMABLE
                if action.kind
                in {
                    BacktestActionKind.COMPLETE_FOLD_EVALUATION,
                    BacktestActionKind.COMPLETE_AGGREGATE_EVALUATION,
                }
                else BacktestResearchState.NOT_APPLICABLE
            ),
        )
        for action in initial.expected_actions
    )

    result = planner.compile(_run(), observations)

    assert result.execution_state is BacktestExecutionState.COMPLETED
    assert result.research_state is BacktestResearchState.NOT_ESTIMABLE
    assert all(
        fold.research_state is BacktestResearchState.NOT_ESTIMABLE
        for fold in result.fold_lifecycles
    )


def test_integrity_mismatch_stops_all_later_work_and_is_not_retryable() -> None:
    planner = BacktestExecutionPlanner()
    initial = planner.compile(_run())
    mismatch = BacktestActionObservation(
        initial.expected_actions[0].action_id,
        BacktestObservedState.MISMATCH,
    )

    result = planner.compile(_run(), (mismatch,))

    assert result.execution_state is BacktestExecutionState.INTEGRITY_ERROR
    assert result.ready_actions == ()
    assert result.integrity_mismatch_action_ids == (mismatch.action_id,)


def test_incomplete_and_retryable_actions_select_recovery_and_new_attempt() -> None:
    planner = BacktestExecutionPlanner()
    initial = planner.compile(_run())
    first, second = initial.ready_actions[:2]
    result = planner.compile(
        _run(),
        (
            BacktestActionObservation(
                first.action.action_id,
                BacktestObservedState.MATCHED_INCOMPLETE,
            ),
            BacktestActionObservation(
                second.action.action_id,
                BacktestObservedState.FAILED_RETRYABLE,
            ),
        ),
    )
    operation_by_id = {
        item.action.action_id: item.operation for item in result.ready_actions
    }

    assert operation_by_id[first.action.action_id] is BacktestNextOperation.RECOVER
    assert operation_by_id[second.action.action_id] is BacktestNextOperation.RETRY
    assert result.execution_state is BacktestExecutionState.FAILED
