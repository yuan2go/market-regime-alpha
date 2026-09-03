"""Reconcile generic Backtest actions from existing canonical Authorities."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.decision_verification import (
    PostgresDecisionRunVerificationProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.outcome_verification import (
    PostgresOutcomeVerificationProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.research_verification import (
    PostgresResearchEvaluationVerificationProvider,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    FrozenBacktestRun,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestActionKind,
    BacktestActionObservation,
    BacktestExpectedAction,
    BacktestObservedState,
    BacktestResearchState,
)


_Scope = tuple[UUID, UUID, UUID]


class PostgresBacktestExecutionObservationPort:
    """Observe owner state without persisting a second workflow cursor."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._decisions = PostgresDecisionRunVerificationProvider(pool)
        self._outcomes = PostgresOutcomeVerificationProvider(pool)
        self._evaluations = PostgresResearchEvaluationVerificationProvider(pool)

    def observe(
        self,
        run: FrozenBacktestRun,
        expected_actions: tuple[BacktestExpectedAction, ...],
    ) -> tuple[BacktestActionObservation, ...]:
        with self._pool.connection(read_only=True) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                datasets = cursor.execute(
                    """
                    SELECT dataset_id, exploratory_backtest_arm_id,
                           exploratory_backtest_fold_id,
                           exploratory_backtest_fold_session_id
                    FROM mra.exploratory_backtest_dataset
                    WHERE exploratory_backtest_run_id = %s
                    """,
                    (run.exploratory_backtest_run_id,),
                ).fetchall()
                decisions = cursor.execute(
                    """
                    SELECT decision_run_id, exploratory_backtest_arm_id,
                           exploratory_backtest_fold_id,
                           exploratory_backtest_fold_session_id
                    FROM mra.exploratory_retrospective_decision_run
                    WHERE exploratory_backtest_run_id = %s
                    """,
                    (run.exploratory_backtest_run_id,),
                ).fetchall()
                outcomes = cursor.execute(
                    """
                    SELECT backtest.exploratory_backtest_arm_id,
                           backtest.exploratory_backtest_fold_id,
                           backtest.exploratory_backtest_fold_session_id,
                           commitment.commitment_id,
                           revision.market_target_outcome_revision_id
                    FROM mra.exploratory_retrospective_decision_run AS backtest
                    JOIN mra.decision_target_commitment AS commitment
                      ON commitment.decision_run_id = backtest.decision_run_id
                    LEFT JOIN LATERAL (
                        SELECT candidate.market_target_outcome_revision_id
                        FROM mra.market_target_outcome_revision AS candidate
                        WHERE candidate.commitment_id = commitment.commitment_id
                        ORDER BY candidate.revision_ordinal DESC
                        LIMIT 1
                    ) AS revision ON true
                    WHERE backtest.exploratory_backtest_run_id = %s
                    """,
                    (run.exploratory_backtest_run_id,),
                ).fetchall()
                evaluation_sources = cursor.execute(
                    """
                    SELECT source.exploratory_backtest_fold_id,
                           source.exploratory_backtest_arm_id,
                           source.evaluation_run_id, run.status
                    FROM mra.evaluation_backtest_arm_source AS source
                    JOIN mra.evaluation_run AS run
                      ON run.evaluation_run_id = source.evaluation_run_id
                    WHERE source.exploratory_backtest_run_id = %s
                    """,
                    (run.exploratory_backtest_run_id,),
                ).fetchall()
                metric_states = cursor.execute(
                    """
                    SELECT source.exploratory_backtest_fold_id,
                           metric.metric_state
                    FROM mra.evaluation_backtest_arm_source AS source
                    JOIN mra.evaluation_metric AS metric
                      ON metric.evaluation_run_id = source.evaluation_run_id
                    WHERE source.exploratory_backtest_run_id = %s
                    GROUP BY source.exploratory_backtest_fold_id,
                             metric.metric_state
                    """,
                    (run.exploratory_backtest_run_id,),
                ).fetchall()
                training_rows = cursor.execute(
                    """
                    SELECT training.exploratory_backtest_arm_id,
                           training.exploratory_backtest_fold_id,
                           training.model_id,
                           training.model_training_run_id,
                           version.model_version_id
                    FROM mra.model_training_run AS training
                    LEFT JOIN mra.model_version AS version
                      ON version.model_training_run_id =
                         training.model_training_run_id
                    WHERE training.exploratory_backtest_run_id = %s
                    """,
                    (run.exploratory_backtest_run_id,),
                ).fetchall()

        dataset_by_scope = _rows_by_scope(datasets)
        decision_by_scope = _rows_by_scope(decisions)
        outcome_by_scope = _rows_by_scope(outcomes)
        evaluations_by_fold: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in evaluation_sources:
            evaluations_by_fold[UUID(str(row["exploratory_backtest_fold_id"]))].append(
                row
            )
        metrics_by_fold: dict[UUID, set[str]] = defaultdict(set)
        for row in metric_states:
            metrics_by_fold[UUID(str(row["exploratory_backtest_fold_id"]))].add(
                str(row["metric_state"])
            )
        training_by_scope: dict[tuple[UUID, UUID], list[dict[str, Any]]] = defaultdict(
            list
        )
        for row in training_rows:
            training_by_scope[
                (
                    UUID(str(row["exploratory_backtest_arm_id"])),
                    UUID(str(row["exploratory_backtest_fold_id"])),
                )
            ].append(row)
        expected_arms_by_fold: dict[UUID, set[UUID]] = defaultdict(set)
        for binding in run.arm_folds:
            expected_arms_by_fold[binding.fold_id].add(binding.arm_id)
        requirement_by_id = {
            requirement.requirement_id: requirement
            for requirement in run.model_training_requirements
        }

        observed: list[BacktestActionObservation] = []
        for action in expected_actions:
            if action.kind is BacktestActionKind.MATERIALIZE_DATASET:
                state = _unique_presence(dataset_by_scope.get(_scope(action), ()))
                observed.append(BacktestActionObservation(action.action_id, state))
            elif action.kind is BacktestActionKind.GENERATE_DECISION_SUPPORT:
                observed.append(self._decision(action, decision_by_scope))
            elif action.kind is BacktestActionKind.SETTLE_OUTCOME:
                observed.append(
                    self._outcome(action, decision_by_scope, outcome_by_scope)
                )
            elif action.kind is BacktestActionKind.COMPLETE_FOLD_EVALUATION:
                observed.append(
                    self._evaluation(
                        action,
                        evaluations_by_fold,
                        metrics_by_fold,
                        expected_arms_by_fold,
                    )
                )
            elif action.kind is BacktestActionKind.TRAIN_MODEL:
                observed.append(
                    self._training(action, training_by_scope, requirement_by_id)
                )
        return tuple(
            observation
            for observation in observed
            if observation.state is not BacktestObservedState.ABSENT
        )

    def _decision(
        self,
        action: BacktestExpectedAction,
        rows_by_scope: dict[_Scope, list[dict[str, Any]]],
    ) -> BacktestActionObservation:
        rows = rows_by_scope.get(_scope(action), ())
        if len(rows) != 1:
            return BacktestActionObservation(
                action.action_id,
                BacktestObservedState.ABSENT if not rows else BacktestObservedState.MISMATCH,
            )
        decision_id = UUID(str(rows[0]["decision_run_id"]))
        verification = self._decisions.verify(decision_id)
        return BacktestActionObservation(
            action.action_id,
            (
                BacktestObservedState.MATCHED_COMPLETE
                if verification.matched
                else BacktestObservedState.MISMATCH
            ),
        )

    def _outcome(
        self,
        action: BacktestExpectedAction,
        decisions: dict[_Scope, list[dict[str, Any]]],
        outcomes: dict[_Scope, list[dict[str, Any]]],
    ) -> BacktestActionObservation:
        scope = _scope(action)
        decision_rows = decisions.get(scope, ())
        if len(decision_rows) != 1:
            return BacktestActionObservation(
                action.action_id,
                (
                    BacktestObservedState.ABSENT
                    if not decision_rows
                    else BacktestObservedState.MISMATCH
                ),
            )
        rows = outcomes.get(scope, ())
        if not rows or any(
            row["market_target_outcome_revision_id"] is None for row in rows
        ):
            return BacktestActionObservation(
                action.action_id, BacktestObservedState.MATCHED_INCOMPLETE
            )
        mismatched = any(
            self._outcomes.inspect(
                UUID(str(row["market_target_outcome_revision_id"]))
            )
            for row in rows
        )
        return BacktestActionObservation(
            action.action_id,
            (
                BacktestObservedState.MISMATCH
                if mismatched
                else BacktestObservedState.MATCHED_COMPLETE
            ),
        )

    def _evaluation(
        self,
        action: BacktestExpectedAction,
        rows_by_fold: dict[UUID, list[dict[str, Any]]],
        metrics_by_fold: dict[UUID, set[str]],
        expected_arms_by_fold: dict[UUID, set[UUID]],
    ) -> BacktestActionObservation:
        assert action.fold_id is not None
        rows = rows_by_fold.get(action.fold_id, ())
        if not rows:
            return BacktestActionObservation(
                action.action_id, BacktestObservedState.ABSENT
            )
        evaluation_ids = {UUID(str(row["evaluation_run_id"])) for row in rows}
        observed_arms = {
            UUID(str(row["exploratory_backtest_arm_id"])) for row in rows
        }
        if len(evaluation_ids) != 1 or observed_arms != expected_arms_by_fold[
            action.fold_id
        ]:
            return BacktestActionObservation(
                action.action_id, BacktestObservedState.MISMATCH
            )
        evaluation_id = next(iter(evaluation_ids))
        statuses = {str(row["status"]) for row in rows}
        if statuses != {"COMPLETED"}:
            return BacktestActionObservation(
                action.action_id, BacktestObservedState.MATCHED_INCOMPLETE
            )
        if self._evaluations.inspect_evaluation_run(evaluation_id):
            return BacktestActionObservation(
                action.action_id, BacktestObservedState.MISMATCH
            )
        metric_states = metrics_by_fold[action.fold_id]
        research_state = (
            BacktestResearchState.ESTIMABLE
            if "ESTIMATED" in metric_states
            else (
                BacktestResearchState.NOT_ESTIMABLE
                if "NOT_ESTIMABLE" in metric_states
                else BacktestResearchState.NOT_APPLICABLE
            )
        )
        return BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MATCHED_COMPLETE,
            research_state,
        )

    @staticmethod
    def _training(
        action: BacktestExpectedAction,
        rows_by_scope: dict[tuple[UUID, UUID], list[dict[str, Any]]],
        requirement_by_id: dict[UUID, Any],
    ) -> BacktestActionObservation:
        assert action.arm_id is not None and action.fold_id is not None
        assert action.model_training_requirement_id is not None
        requirement = requirement_by_id[action.model_training_requirement_id]
        rows = rows_by_scope.get((action.arm_id, action.fold_id), ())
        matching = tuple(
            row
            for row in rows
            if UUID(str(row["model_id"])) == requirement.model_definition.authority_id
        )
        if not matching:
            return BacktestActionObservation(
                action.action_id,
                BacktestObservedState.MISMATCH if rows else BacktestObservedState.ABSENT,
            )
        if len(matching) != 1:
            return BacktestActionObservation(
                action.action_id, BacktestObservedState.MISMATCH
            )
        return BacktestActionObservation(
            action.action_id,
            (
                BacktestObservedState.MATCHED_INCOMPLETE
                if matching[0]["model_version_id"] is None
                else BacktestObservedState.MATCHED_COMPLETE
            ),
        )


def _rows_by_scope(rows: list[dict[str, Any]]) -> dict[_Scope, list[dict[str, Any]]]:
    result: dict[_Scope, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result[
            (
                UUID(str(row["exploratory_backtest_arm_id"])),
                UUID(str(row["exploratory_backtest_fold_id"])),
                UUID(str(row["exploratory_backtest_fold_session_id"])),
            )
        ].append(row)
    return result


def _scope(action: BacktestExpectedAction) -> _Scope:
    assert (
        action.arm_id is not None
        and action.fold_id is not None
        and action.fold_session_id is not None
    )
    return action.arm_id, action.fold_id, action.fold_session_id


def _unique_presence(rows: list[dict[str, Any]] | tuple[()]) -> BacktestObservedState:
    if not rows:
        return BacktestObservedState.ABSENT
    if len(rows) != 1:
        return BacktestObservedState.MISMATCH
    return BacktestObservedState.MATCHED_COMPLETE


__all__ = ["PostgresBacktestExecutionObservationPort"]
