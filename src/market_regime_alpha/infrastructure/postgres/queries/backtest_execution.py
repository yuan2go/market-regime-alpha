"""Reconcile generic Backtest actions from existing canonical Authorities."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
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
    FrozenBacktestSource,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestActionKind,
    BacktestActionObservation,
    BacktestExpectedAction,
    BacktestObservedState,
    BacktestResearchState,
    BacktestRuntimeBinding,
)
from market_regime_alpha.research_qualification.ports.model_inputs import (
    ModelTrainingInputProvider,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
)


_Scope = tuple[UUID, UUID, UUID]

_FOLD_METRIC_STATES_SQL = """
    SELECT source.exploratory_backtest_fold_id, metric.metric_state
    FROM (
        SELECT DISTINCT exploratory_backtest_fold_id, evaluation_run_id
        FROM mra.evaluation_backtest_arm_source
        WHERE exploratory_backtest_run_id = %s
    ) AS source
    JOIN mra.evaluation_metric AS metric
      ON metric.evaluation_run_id = source.evaluation_run_id
    GROUP BY source.exploratory_backtest_fold_id, metric.metric_state
"""


_RUNTIME_BINDING_READ_BATCH_SIZE = 8
_RUNTIME_BINDINGS_SQL = """
                    WITH scoped_bindings AS MATERIALIZED (
                        SELECT * FROM mra.backtest_runtime_binding
                        WHERE exploratory_backtest_run_id = %s
                          AND backtest_runtime_binding_id = ANY(%s::uuid[])
                    ), scoped_steps AS MATERIALIZED (
                        SELECT step_id, run_id FROM mra.runtime_step
                        WHERE run_id = ANY(ARRAY(SELECT runtime_run_id FROM scoped_bindings))
                    ), scoped_attempts AS MATERIALIZED (
                        SELECT step_id, state, created_at, attempt_no
                        FROM mra.runtime_attempt
                        WHERE step_id = ANY(ARRAY(SELECT step_id FROM scoped_steps))
                    ), latest_attempt AS (
                        SELECT DISTINCT ON (step.run_id)
                               step.run_id, attempt.state
                        FROM scoped_steps AS step
                        JOIN scoped_attempts AS attempt
                          ON attempt.step_id = step.step_id
                        ORDER BY step.run_id, attempt.created_at DESC,
                                 attempt.attempt_no DESC
                    )
                    SELECT binding.backtest_runtime_binding_id,
                           binding.specification_sha256,
                           binding.action_id, binding.action_kind,
                           binding.action_content_sha256,
                           binding.exploratory_backtest_arm_id,
                           binding.exploratory_backtest_fold_id,
                           binding.exploratory_backtest_fold_session_id,
                           binding.model_training_requirement_id,
                           binding.evaluation_requirement_id,
                           binding.runtime_run_id, binding.content_sha256,
                           runtime.runtime_mode, runtime.fire_key,
                           runtime.code_sha, runtime.config_artifact_id,
                           runtime.config_hash, runtime.state AS runtime_state,
                           root.code_content_sha256 AS root_code_sha,
                           root.config_artifact_id AS root_config_artifact_id,
                           root.config_content_sha256 AS root_config_hash,
                           latest_attempt.state AS latest_attempt_state
                    FROM scoped_bindings AS binding
                    JOIN mra.runtime_run AS runtime
                      ON runtime.run_id = binding.runtime_run_id
                    JOIN mra.exploratory_backtest_run AS root
                      ON root.exploratory_backtest_run_id =
                         binding.exploratory_backtest_run_id
                    LEFT JOIN latest_attempt
                      ON latest_attempt.run_id = runtime.run_id
                    """


def _load_runtime_bindings(cursor: Any, run_id: UUID) -> list[dict[str, Any]]:
    identities = cursor.execute(
        """
        SELECT backtest_runtime_binding_id FROM mra.backtest_runtime_binding
        WHERE exploratory_backtest_run_id = %s ORDER BY backtest_runtime_binding_id
        """,
        (run_id,),
    ).fetchall()
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(identities), _RUNTIME_BINDING_READ_BATCH_SIZE):
        batch = identities[offset:offset + _RUNTIME_BINDING_READ_BATCH_SIZE]
        rows.extend(cursor.execute(
            _RUNTIME_BINDINGS_SQL,
            (run_id, [row["backtest_runtime_binding_id"] for row in batch]),
        ).fetchall())
    return rows


class PostgresBacktestExecutionObservationPort:
    """Observe owner state without persisting a second workflow cursor."""

    def __init__(
        self,
        pool: TargetPostgresPool,
        *,
        model_inputs: ModelTrainingInputProvider | None = None,
    ) -> None:
        self._pool = pool
        self._decisions = PostgresDecisionRunVerificationProvider(pool)
        self._outcomes = PostgresOutcomeVerificationProvider(pool)
        self._evaluations = PostgresResearchEvaluationVerificationProvider(pool)
        self._model_inputs = model_inputs

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
                    _FOLD_METRIC_STATES_SQL,
                    (run.exploratory_backtest_run_id,),
                ).fetchall()
                current_evaluations: list[dict[str, Any]] = []
                current_metric_states: list[dict[str, Any]] = []
                model_lineages: list[dict[str, Any]] = []
                runtime_bindings: list[dict[str, Any]] = []
                if run.source is FrozenBacktestSource.CURRENT_RELATIONAL:
                    current_evaluations = cursor.execute(
                        """
                    SELECT execution.backtest_evaluation_requirement_id,
                           execution.evaluation_run_id,
                           execution.evaluation_protocol_id,
                           execution.evaluation_metric_count,
                           execution.evaluation_metric_roster_sha256,
                           evaluation.status,
                           evaluation.metric_count AS canonical_metric_count,
                           evaluation.metric_roster_sha256 AS canonical_metric_roster_sha256
                    FROM mra.backtest_evaluation_execution AS execution
                    JOIN mra.evaluation_run AS evaluation
                      ON evaluation.evaluation_run_id = execution.evaluation_run_id
                     AND evaluation.evaluation_protocol_id =
                         execution.evaluation_protocol_id
                    WHERE execution.exploratory_backtest_run_id = %s
                        """,
                        (run.exploratory_backtest_run_id,),
                    ).fetchall()
                    current_metric_states = cursor.execute(
                        """
                    SELECT execution.backtest_evaluation_requirement_id,
                           metric.metric_state
                    FROM mra.backtest_evaluation_execution AS execution
                    JOIN mra.evaluation_metric AS metric
                      ON metric.evaluation_run_id = execution.evaluation_run_id
                    WHERE execution.exploratory_backtest_run_id = %s
                    GROUP BY execution.backtest_evaluation_requirement_id,
                             metric.metric_state
                        """,
                        (run.exploratory_backtest_run_id,),
                    ).fetchall()
                    runtime_bindings = _load_runtime_bindings(cursor, run.exploratory_backtest_run_id)
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
                if run.source is FrozenBacktestSource.CURRENT_RELATIONAL:
                    model_lineages = cursor.execute(
                        """
                    SELECT lineage.model_training_requirement_id,
                           lineage.model_id,
                           lineage.model_training_run_id,
                           lineage.model_training_run_sha256,
                           lineage.model_training_reproducibility_sha256,
                           lineage.model_version_id,
                           lineage.model_version_sha256,
                           training.content_sha256 AS canonical_training_sha256,
                           reproducibility.content_sha256 AS canonical_reproducibility_sha256,
                           version.content_sha256 AS canonical_version_sha256
                    FROM mra.backtest_model_lineage AS lineage
                    JOIN mra.model_training_run AS training
                      ON training.model_training_run_id =
                         lineage.model_training_run_id
                    JOIN mra.model_training_reproducibility AS reproducibility
                      ON reproducibility.model_training_run_id =
                         lineage.model_training_run_id
                    JOIN mra.model_version AS version
                      ON version.model_version_id = lineage.model_version_id
                    WHERE lineage.exploratory_backtest_run_id = %s
                        """,
                        (run.exploratory_backtest_run_id,),
                    ).fetchall()

        dataset_by_scope = _rows_by_scope(datasets)
        decision_by_scope = _rows_by_scope(decisions)
        outcome_by_scope = _rows_by_scope(outcomes)
        evaluations_by_fold: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in evaluation_sources:
            evaluations_by_fold[UUID(str(row["exploratory_backtest_fold_id"]))].append(row)
        metrics_by_fold: dict[UUID, set[str]] = defaultdict(set)
        for row in metric_states:
            metrics_by_fold[UUID(str(row["exploratory_backtest_fold_id"]))].add(str(row["metric_state"]))
        training_by_scope: dict[tuple[UUID, UUID], list[dict[str, Any]]] = defaultdict(list)
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
        requirement_by_id = {requirement.requirement_id: requirement for requirement in run.model_training_requirements}
        lineage_by_requirement: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in model_lineages:
            lineage_by_requirement[UUID(str(row["model_training_requirement_id"]))].append(row)
        current_evaluation_by_requirement: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in current_evaluations:
            current_evaluation_by_requirement[UUID(str(row["backtest_evaluation_requirement_id"]))].append(row)
        current_metric_states_by_requirement: dict[UUID, set[str]] = defaultdict(set)
        for row in current_metric_states:
            current_metric_states_by_requirement[UUID(str(row["backtest_evaluation_requirement_id"]))].add(str(row["metric_state"]))
        runtime_by_action: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in runtime_bindings:
            runtime_by_action[UUID(str(row["action_id"]))].append(row)

        def observe_action(action: BacktestExpectedAction) -> BacktestActionObservation:
            if action.kind is BacktestActionKind.MATERIALIZE_DATASET:
                state = _unique_presence(dataset_by_scope.get(_scope(action), ()))
                observation = BacktestActionObservation(action.action_id, state)
            elif action.kind is BacktestActionKind.GENERATE_DECISION_SUPPORT:
                observation = self._decision(action, decision_by_scope)
            elif action.kind is BacktestActionKind.SETTLE_OUTCOME:
                observation = self._outcome(
                    action,
                    decision_by_scope,
                    outcome_by_scope,
                )
            elif action.kind in {
                BacktestActionKind.COMPLETE_FOLD_EVALUATION,
                BacktestActionKind.COMPLETE_AGGREGATE_EVALUATION,
            }:
                if action.evaluation_requirement_id is not None:
                    observation = self._current_evaluation(
                        action,
                        current_evaluation_by_requirement,
                        current_metric_states_by_requirement,
                    )
                else:
                    observation = self._evaluation(
                        action,
                        evaluations_by_fold,
                        metrics_by_fold,
                        expected_arms_by_fold,
                    )
            elif action.kind is BacktestActionKind.TRAIN_MODEL:
                observation = self._training(
                    action,
                    training_by_scope,
                    lineage_by_requirement,
                    requirement_by_id,
                    current=bool(run.evaluation_requirements),
                )
            else:  # pragma: no cover - closed enum exhaustiveness guard
                raise AssertionError(f"unsupported Backtest action {action.kind}")
            if run.source is FrozenBacktestSource.CURRENT_RELATIONAL:
                observation = _reconcile_current_runtime(
                    run,
                    action,
                    observation,
                    runtime_by_action.get(action.action_id, ()),
                )
            return observation

        # Rebuild every owner observation on every call. Workers share the
        # existing bounded PostgreSQL pool; no result is cached or admitted
        # before all owner checks finish. map preserves the frozen action order.
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="backtest-observe") as workers:
            observed = tuple(workers.map(observe_action, expected_actions))
        return tuple(item for item in observed if item.state is not BacktestObservedState.ABSENT)

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
            (BacktestObservedState.MATCHED_COMPLETE if verification.matched else BacktestObservedState.MISMATCH),
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
                (BacktestObservedState.ABSENT if not decision_rows else BacktestObservedState.MISMATCH),
            )
        rows = outcomes.get(scope, ())
        if rows and all(row["market_target_outcome_revision_id"] is None for row in rows):
            return BacktestActionObservation(action.action_id, BacktestObservedState.ABSENT)
        if not rows or any(row["market_target_outcome_revision_id"] is None for row in rows):
            return BacktestActionObservation(action.action_id, BacktestObservedState.MATCHED_INCOMPLETE)
        checks = self._outcomes.inspect_many(
            UUID(str(row["market_target_outcome_revision_id"])) for row in rows
        )
        mismatched = any(checks.values())
        return BacktestActionObservation(
            action.action_id,
            (BacktestObservedState.MISMATCH if mismatched else BacktestObservedState.MATCHED_COMPLETE),
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
            return BacktestActionObservation(action.action_id, BacktestObservedState.ABSENT)
        evaluation_ids = {UUID(str(row["evaluation_run_id"])) for row in rows}
        observed_arms = {UUID(str(row["exploratory_backtest_arm_id"])) for row in rows}
        if len(evaluation_ids) != 1 or observed_arms != expected_arms_by_fold[action.fold_id]:
            return BacktestActionObservation(action.action_id, BacktestObservedState.MISMATCH)
        evaluation_id = next(iter(evaluation_ids))
        statuses = {str(row["status"]) for row in rows}
        if statuses != {"COMPLETED"}:
            return BacktestActionObservation(action.action_id, BacktestObservedState.MATCHED_INCOMPLETE)
        if self._evaluations.inspect_evaluation_run(evaluation_id):
            return BacktestActionObservation(action.action_id, BacktestObservedState.MISMATCH)
        metric_states = metrics_by_fold[action.fold_id]
        research_state = (
            BacktestResearchState.ESTIMABLE
            if "ESTIMATED" in metric_states
            else (BacktestResearchState.NOT_ESTIMABLE if "NOT_ESTIMABLE" in metric_states else BacktestResearchState.NOT_APPLICABLE)
        )
        return BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MATCHED_COMPLETE,
            research_state,
        )

    def _current_evaluation(
        self,
        action: BacktestExpectedAction,
        rows_by_requirement: dict[UUID, list[dict[str, Any]]],
        metrics_by_requirement: dict[UUID, set[str]],
    ) -> BacktestActionObservation:
        assert action.evaluation_requirement_id is not None
        rows = rows_by_requirement.get(action.evaluation_requirement_id, ())
        if not rows:
            return BacktestActionObservation(action.action_id, BacktestObservedState.ABSENT)
        if len(rows) != 1:
            return BacktestActionObservation(action.action_id, BacktestObservedState.MISMATCH)
        row = rows[0]
        if (
            str(row["status"]) != "COMPLETED"
            or int(row["evaluation_metric_count"]) != int(row["canonical_metric_count"])
            or str(row["evaluation_metric_roster_sha256"]) != str(row["canonical_metric_roster_sha256"])
        ):
            return BacktestActionObservation(action.action_id, BacktestObservedState.MISMATCH)
        evaluation_id = UUID(str(row["evaluation_run_id"]))
        if self._evaluations.inspect_evaluation_run(evaluation_id):
            return BacktestActionObservation(action.action_id, BacktestObservedState.MISMATCH)
        metric_states = metrics_by_requirement[action.evaluation_requirement_id]
        research_state = (
            BacktestResearchState.ESTIMABLE
            if "ESTIMATED" in metric_states
            else (BacktestResearchState.NOT_ESTIMABLE if "NOT_ESTIMABLE" in metric_states else BacktestResearchState.NOT_APPLICABLE)
        )
        return BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MATCHED_COMPLETE,
            research_state,
        )

    def _training(
        self,
        action: BacktestExpectedAction,
        rows_by_scope: dict[tuple[UUID, UUID], list[dict[str, Any]]],
        lineage_by_requirement: dict[UUID, list[dict[str, Any]]],
        requirement_by_id: dict[UUID, Any],
        *,
        current: bool,
    ) -> BacktestActionObservation:
        assert action.arm_id is not None and action.fold_id is not None
        assert action.model_training_requirement_id is not None
        requirement = requirement_by_id[action.model_training_requirement_id]
        if current:
            lineages = lineage_by_requirement.get(
                action.model_training_requirement_id,
                (),
            )
            if not lineages:
                return BacktestActionObservation(
                    action.action_id,
                    BacktestObservedState.ABSENT,
                )
            if len(lineages) != 1:
                return BacktestActionObservation(
                    action.action_id,
                    BacktestObservedState.MISMATCH,
                )
            lineage = lineages[0]
            exact = (
                UUID(str(lineage["model_id"])) == requirement.model_definition.authority_id
                and str(lineage["model_training_run_sha256"]) == str(lineage["canonical_training_sha256"])
                and str(lineage["model_training_reproducibility_sha256"]) == str(lineage["canonical_reproducibility_sha256"])
                and str(lineage["model_version_sha256"]) == str(lineage["canonical_version_sha256"])
            )
            if exact:
                if self._model_inputs is None:
                    raise ArtifactIntegrityError("current Model observation requires the canonical training input owner")
                try:
                    registered = self._model_inputs.load_registered_reproducible(
                        UUID(str(lineage["model_training_run_id"]))
                    )
                except (ArtifactIntegrityError, RuntimeNotFoundError):
                    exact = False
                else:
                    exact = (
                        registered.training.model_id == requirement.model_definition.authority_id
                        and str(registered.reproducibility.content_sha256)
                        == str(lineage["canonical_reproducibility_sha256"])
                    )
            return BacktestActionObservation(
                action.action_id,
                (BacktestObservedState.MATCHED_COMPLETE if exact else BacktestObservedState.MISMATCH),
            )
        rows = rows_by_scope.get((action.arm_id, action.fold_id), ())
        matching = tuple(row for row in rows if UUID(str(row["model_id"])) == requirement.model_definition.authority_id)
        if not matching:
            return BacktestActionObservation(
                action.action_id,
                BacktestObservedState.MISMATCH if rows else BacktestObservedState.ABSENT,
            )
        if len(matching) != 1:
            return BacktestActionObservation(action.action_id, BacktestObservedState.MISMATCH)
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
    assert action.arm_id is not None and action.fold_id is not None and action.fold_session_id is not None
    return action.arm_id, action.fold_id, action.fold_session_id


def _reconcile_current_runtime(
    run: FrozenBacktestRun,
    action: BacktestExpectedAction,
    owner: BacktestActionObservation,
    rows: list[dict[str, Any]] | tuple[()],
) -> BacktestActionObservation:
    if not rows:
        return (
            owner
            if owner.state is BacktestObservedState.ABSENT
            else BacktestActionObservation(
                action.action_id,
                BacktestObservedState.MISMATCH,
            )
        )
    if len(rows) != 1:
        return BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MISMATCH,
        )
    row = rows[0]
    try:
        expected_binding = BacktestRuntimeBinding(
            UUID(str(row["backtest_runtime_binding_id"])),
            run.exploratory_backtest_run_id,
            run.specification_sha256,
            action,
            UUID(str(row["runtime_run_id"])),
        )
    except (TypeError, ValueError):
        return BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MISMATCH,
        )
    exact = (
        str(row["specification_sha256"]) == str(run.specification_sha256)
        and str(row["action_kind"]) == action.kind.value
        and str(row["action_content_sha256"]) == str(action.content_sha256)
        and _optional_uuid(row["exploratory_backtest_arm_id"]) == action.arm_id
        and _optional_uuid(row["exploratory_backtest_fold_id"]) == action.fold_id
        and _optional_uuid(row["exploratory_backtest_fold_session_id"])
        == action.fold_session_id
        and _optional_uuid(row["model_training_requirement_id"])
        == action.model_training_requirement_id
        and _optional_uuid(row["evaluation_requirement_id"])
        == action.evaluation_requirement_id
        and str(row["content_sha256"]) == str(expected_binding.content_sha256)
        and str(row["runtime_mode"]) in {"HISTORICAL", "REPLAY"}
        and str(row["fire_key"]) == str(action.action_id)
        and str(row["code_sha"]) == str(row["root_code_sha"])
        and UUID(str(row["config_artifact_id"]))
        == UUID(str(row["root_config_artifact_id"]))
        and str(row["config_hash"]) == str(row["root_config_hash"])
    )
    if not exact or owner.state is BacktestObservedState.MISMATCH:
        return BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MISMATCH,
        )

    runtime_state = str(row["runtime_state"])
    if runtime_state == "SUCCEEDED":
        return (
            owner
            if owner.state is BacktestObservedState.MATCHED_COMPLETE
            else BacktestActionObservation(
                action.action_id,
                BacktestObservedState.MISMATCH,
            )
        )
    if runtime_state in {"FAILED", "BLOCKED", "CANCELLED"}:
        return BacktestActionObservation(
            action.action_id,
            BacktestObservedState.FAILED_TERMINAL,
        )
    if owner.state is BacktestObservedState.MATCHED_COMPLETE:
        return BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MATCHED_INCOMPLETE,
        )
    latest_attempt_state = row["latest_attempt_state"]
    if latest_attempt_state is not None and str(latest_attempt_state) in {
        "FAILED_RETRYABLE",
        "ABANDONED",
    }:
        return BacktestActionObservation(
            action.action_id,
            BacktestObservedState.FAILED_RETRYABLE,
        )
    if latest_attempt_state is not None and str(latest_attempt_state) == "FAILED_TERMINAL":
        return BacktestActionObservation(
            action.action_id,
            BacktestObservedState.FAILED_TERMINAL,
        )
    return BacktestActionObservation(
        action.action_id,
        BacktestObservedState.MATCHED_INCOMPLETE,
    )


def _optional_uuid(value: object) -> UUID | None:
    return None if value is None else UUID(str(value))


def _unique_presence(rows: list[dict[str, Any]] | tuple[()]) -> BacktestObservedState:
    if not rows:
        return BacktestObservedState.ABSENT
    if len(rows) != 1:
        return BacktestObservedState.MISMATCH
    return BacktestObservedState.MATCHED_COMPLETE


__all__ = ["PostgresBacktestExecutionObservationPort"]
