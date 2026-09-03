"""Pure reconciliation planner for generic Runtime-backed Backtest execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestExecutionKind,
    BacktestSessionRole,
    FrozenBacktestRun,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestActionKind,
    BacktestActionObservation,
    BacktestExecutionPlan,
    BacktestExecutionState,
    BacktestExpectedAction,
    BacktestFoldLifecycle,
    BacktestNextOperation,
    BacktestObservedState,
    BacktestReadyAction,
    BacktestResearchState,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)


@dataclass(frozen=True, slots=True)
class _ActionDraft:
    action_id: UUID
    kind: BacktestActionKind
    arm_id: UUID | None = None
    fold_id: UUID | None = None
    fold_session_id: UUID | None = None
    model_training_requirement_id: UUID | None = None
    dependency_action_ids: tuple[UUID, ...] = ()


class BacktestExecutionPlanner:
    """Rebuild expected work from frozen facts; owns no mutable cursor."""

    def compile(
        self,
        run: FrozenBacktestRun,
        observations: Iterable[BacktestActionObservation] = (),
    ) -> BacktestExecutionPlan:
        drafts = self._draft_actions(run)
        ordered = _topological_actions(drafts)
        actions = tuple(
            BacktestExpectedAction(
                action_id=draft.action_id,
                ordinal=ordinal,
                kind=draft.kind,
                exploratory_backtest_run_id=run.exploratory_backtest_run_id,
                arm_id=draft.arm_id,
                fold_id=draft.fold_id,
                fold_session_id=draft.fold_session_id,
                model_training_requirement_id=(
                    draft.model_training_requirement_id
                ),
                dependency_action_ids=draft.dependency_action_ids,
            )
            for ordinal, draft in enumerate(ordered, start=1)
        )
        expected_by_id = {action.action_id: action for action in actions}
        observed_by_id: dict[UUID, BacktestActionObservation] = {}
        duplicate_ids: set[UUID] = set()
        for observation in observations:
            if observation.action_id in observed_by_id:
                duplicate_ids.add(observation.action_id)
            observed_by_id[observation.action_id] = observation
        unexpected = set(observed_by_id).difference(expected_by_id)
        mismatch_ids = set(duplicate_ids).union(unexpected)
        mismatch_ids.update(
            action_id
            for action_id, observation in observed_by_id.items()
            if observation.state is BacktestObservedState.MISMATCH
        )
        integrity_error = bool(mismatch_ids)
        ready = () if integrity_error else self._ready(actions, observed_by_id)
        folds = tuple(
            self._fold_lifecycle(
                fold.exploratory_backtest_fold_id,
                actions,
                observed_by_id,
            )
            for fold in run.folds
        )
        execution = _execution_state(
            tuple(_state(action.action_id, observed_by_id) for action in actions),
            integrity_error=integrity_error,
        )
        research_results: list[BacktestResearchState] = []
        for action in actions:
            recorded = observed_by_id.get(action.action_id)
            if (
                action.kind
                in {
                    BacktestActionKind.COMPLETE_FOLD_EVALUATION,
                    BacktestActionKind.COMPLETE_AGGREGATE_EVALUATION,
                }
                and recorded is not None
                and recorded.state is BacktestObservedState.MATCHED_COMPLETE
            ):
                research_results.append(recorded.research_state)
        research = _research_state(tuple(research_results))
        return BacktestExecutionPlan(
            exploratory_backtest_run_id=run.exploratory_backtest_run_id,
            expected_actions=actions,
            ready_actions=ready,
            fold_lifecycles=folds,
            execution_state=(
                BacktestExecutionState.INTEGRITY_ERROR
                if integrity_error
                else execution
            ),
            research_state=research,
            integrity_mismatch_action_ids=tuple(sorted(mismatch_ids, key=str)),
        )

    def _draft_actions(self, run: FrozenBacktestRun) -> tuple[_ActionDraft, ...]:
        arm_by_id = {
            arm.exploratory_backtest_arm_id: arm for arm in run.arms
        }
        fold_by_id = {
            fold.exploratory_backtest_fold_id: fold for fold in run.folds
        }
        requirement_by_validation = {
            (item.model_arm_id, item.validation_fold_id): item
            for item in run.model_training_requirements
        }
        drafts: list[_ActionDraft] = []
        outcome_ids_by_fold: dict[UUID, list[UUID]] = {}
        evaluation_ids: dict[UUID, UUID] = {}

        for arm_fold in run.arm_folds:
            arm = arm_by_id[arm_fold.arm_id]
            fold = fold_by_id[arm_fold.fold_id]
            required_role = (
                BacktestSessionRole.FIT_INPUT
                if fold.purpose is PartitionPurpose.FIT
                else BacktestSessionRole.EVALUATION
            )
            for session in fold.sessions:
                if session.role is not required_role:
                    continue
                dataset_id = _action_id(
                    run,
                    BacktestActionKind.MATERIALIZE_DATASET,
                    arm_id=arm_fold.arm_id,
                    fold_id=arm_fold.fold_id,
                    session_id=session.exploratory_backtest_fold_session_id,
                )
                decision_dependencies = [dataset_id]
                if (
                    arm.execution_kind is BacktestExecutionKind.MODEL
                    and fold.purpose is PartitionPurpose.VALIDATION
                ):
                    requirement = requirement_by_validation[
                        (arm_fold.arm_id, arm_fold.fold_id)
                    ]
                    decision_dependencies.append(
                        _action_id(
                            run,
                            BacktestActionKind.TRAIN_MODEL,
                            arm_id=arm_fold.arm_id,
                            fold_id=requirement.fit_fold_id,
                            requirement_id=requirement.requirement_id,
                        )
                    )
                decision_id = _action_id(
                    run,
                    BacktestActionKind.GENERATE_DECISION_SUPPORT,
                    arm_id=arm_fold.arm_id,
                    fold_id=arm_fold.fold_id,
                    session_id=session.exploratory_backtest_fold_session_id,
                )
                outcome_id = _action_id(
                    run,
                    BacktestActionKind.SETTLE_OUTCOME,
                    arm_id=arm_fold.arm_id,
                    fold_id=arm_fold.fold_id,
                    session_id=session.exploratory_backtest_fold_session_id,
                )
                drafts.extend(
                    (
                        _ActionDraft(
                            dataset_id,
                            BacktestActionKind.MATERIALIZE_DATASET,
                            arm_fold.arm_id,
                            arm_fold.fold_id,
                            session.exploratory_backtest_fold_session_id,
                        ),
                        _ActionDraft(
                            decision_id,
                            BacktestActionKind.GENERATE_DECISION_SUPPORT,
                            arm_fold.arm_id,
                            arm_fold.fold_id,
                            session.exploratory_backtest_fold_session_id,
                            dependency_action_ids=tuple(decision_dependencies),
                        ),
                        _ActionDraft(
                            outcome_id,
                            BacktestActionKind.SETTLE_OUTCOME,
                            arm_fold.arm_id,
                            arm_fold.fold_id,
                            session.exploratory_backtest_fold_session_id,
                            dependency_action_ids=(decision_id,),
                        ),
                    )
                )
                outcome_ids_by_fold.setdefault(arm_fold.fold_id, []).append(outcome_id)

        for fold in run.folds:
            evaluation_id = _action_id(
                run,
                BacktestActionKind.COMPLETE_FOLD_EVALUATION,
                fold_id=fold.exploratory_backtest_fold_id,
            )
            evaluation_ids[fold.exploratory_backtest_fold_id] = evaluation_id
            drafts.append(
                _ActionDraft(
                    evaluation_id,
                    BacktestActionKind.COMPLETE_FOLD_EVALUATION,
                    fold_id=fold.exploratory_backtest_fold_id,
                    dependency_action_ids=tuple(
                        outcome_ids_by_fold[fold.exploratory_backtest_fold_id]
                    ),
                )
            )

        for requirement in run.model_training_requirements:
            drafts.append(
                _ActionDraft(
                    _action_id(
                        run,
                        BacktestActionKind.TRAIN_MODEL,
                        arm_id=requirement.model_arm_id,
                        fold_id=requirement.fit_fold_id,
                        requirement_id=requirement.requirement_id,
                    ),
                    BacktestActionKind.TRAIN_MODEL,
                    requirement.model_arm_id,
                    requirement.fit_fold_id,
                    model_training_requirement_id=requirement.requirement_id,
                    dependency_action_ids=(
                        evaluation_ids[requirement.fit_fold_id],
                    ),
                )
            )
        return tuple(drafts)

    @staticmethod
    def _ready(
        actions: tuple[BacktestExpectedAction, ...],
        observations: Mapping[UUID, BacktestActionObservation],
    ) -> tuple[BacktestReadyAction, ...]:
        ready: list[BacktestReadyAction] = []
        for action in actions:
            state = _state(action.action_id, observations)
            if state is BacktestObservedState.MATCHED_COMPLETE:
                continue
            if not all(
                _state(dependency, observations)
                is BacktestObservedState.MATCHED_COMPLETE
                for dependency in action.dependency_action_ids
            ):
                continue
            operation = {
                BacktestObservedState.ABSENT: BacktestNextOperation.EXECUTE,
                BacktestObservedState.MATCHED_INCOMPLETE: (
                    BacktestNextOperation.RECOVER
                ),
                BacktestObservedState.FAILED_RETRYABLE: BacktestNextOperation.RETRY,
            }.get(state)
            if operation is not None:
                ready.append(BacktestReadyAction(action, operation))
        return tuple(ready)

    @staticmethod
    def _fold_lifecycle(
        fold_id: UUID,
        actions: tuple[BacktestExpectedAction, ...],
        observations: Mapping[UUID, BacktestActionObservation],
    ) -> BacktestFoldLifecycle:
        fold_actions = tuple(action for action in actions if action.fold_id == fold_id)
        states = tuple(_state(action.action_id, observations) for action in fold_actions)
        integrity = any(state is BacktestObservedState.MISMATCH for state in states)
        evaluation_research = tuple(
            observation.research_state
            for action in fold_actions
            if action.kind is BacktestActionKind.COMPLETE_FOLD_EVALUATION
            and (observation := observations.get(action.action_id)) is not None
            and observation.state is BacktestObservedState.MATCHED_COMPLETE
        )
        return BacktestFoldLifecycle(
            fold_id=fold_id,
            execution_state=_execution_state(states, integrity_error=integrity),
            research_state=_research_state(evaluation_research),
        )


def _state(
    action_id: UUID,
    observations: Mapping[UUID, BacktestActionObservation],
) -> BacktestObservedState:
    observation = observations.get(action_id)
    return (
        BacktestObservedState.ABSENT if observation is None else observation.state
    )


def _execution_state(
    states: tuple[BacktestObservedState, ...], *, integrity_error: bool
) -> BacktestExecutionState:
    if integrity_error or any(state is BacktestObservedState.MISMATCH for state in states):
        return BacktestExecutionState.INTEGRITY_ERROR
    if states and all(
        state is BacktestObservedState.MATCHED_COMPLETE for state in states
    ):
        return BacktestExecutionState.COMPLETED
    if any(state is BacktestObservedState.FAILED_RETRYABLE for state in states):
        return BacktestExecutionState.FAILED
    if any(state is BacktestObservedState.MATCHED_INCOMPLETE for state in states):
        return BacktestExecutionState.RUNNING
    return BacktestExecutionState.PLANNED


def _research_state(
    states: tuple[BacktestResearchState, ...],
) -> BacktestResearchState:
    if any(state is BacktestResearchState.ESTIMABLE for state in states):
        return BacktestResearchState.ESTIMABLE
    if states and any(
        state is BacktestResearchState.NOT_ESTIMABLE for state in states
    ):
        return BacktestResearchState.NOT_ESTIMABLE
    return BacktestResearchState.NOT_APPLICABLE


def _action_id(
    run: FrozenBacktestRun,
    kind: BacktestActionKind,
    *,
    arm_id: UUID | None = None,
    fold_id: UUID | None = None,
    session_id: UUID | None = None,
    requirement_id: UUID | None = None,
) -> UUID:
    key = ":".join(
        (
            "mra",
            "backtest-action",
            str(run.exploratory_backtest_run_id),
            str(run.definition_sha256),
            kind.value,
            "-" if arm_id is None else str(arm_id),
            "-" if fold_id is None else str(fold_id),
            "-" if session_id is None else str(session_id),
            "-" if requirement_id is None else str(requirement_id),
        )
    )
    return uuid5(NAMESPACE_URL, key)


def _topological_actions(drafts: tuple[_ActionDraft, ...]) -> tuple[_ActionDraft, ...]:
    by_id = {draft.action_id: draft for draft in drafts}
    if len(by_id) != len(drafts):
        raise ValueError("Backtest execution graph contains duplicate action identities")
    missing = {
        dependency
        for draft in drafts
        for dependency in draft.dependency_action_ids
        if dependency not in by_id
    }
    if missing:
        raise ValueError("Backtest execution graph has missing dependencies")
    remaining = dict(by_id)
    completed: set[UUID] = set()
    ordered: list[_ActionDraft] = []
    while remaining:
        ready = sorted(
            (
                draft
                for draft in remaining.values()
                if set(draft.dependency_action_ids).issubset(completed)
            ),
            key=lambda draft: (
                draft.kind.value,
                "" if draft.fold_id is None else str(draft.fold_id),
                "" if draft.arm_id is None else str(draft.arm_id),
                "" if draft.fold_session_id is None else str(draft.fold_session_id),
                str(draft.action_id),
            ),
        )
        if not ready:
            raise ValueError("Backtest execution graph contains a cycle")
        for draft in ready:
            ordered.append(draft)
            completed.add(draft.action_id)
            del remaining[draft.action_id]
    return tuple(ordered)


__all__ = ["BacktestExecutionPlanner"]
