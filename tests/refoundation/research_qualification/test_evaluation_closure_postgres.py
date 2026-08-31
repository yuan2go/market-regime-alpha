from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.evaluation_uow import PostgresEvaluationUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.experiment_uow import PostgresExperimentUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.partition_uow import PostgresPartitionUnitOfWorkProvider
from market_regime_alpha.research_qualification.application import EvaluationCommands, ExperimentCommands, ResearchPartitionCommands
from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationProtocolPlan,
    EvaluationRunPlan,
    ProtocolMetricDefinition,
)
from market_regime_alpha.research_qualification.domain.experiment import (
    ExperimentDefinition,
    ExperimentPartitionBinding,
    ExperimentRunPlan,
)
from market_regime_alpha.research_qualification.domain.partition import ResearchPartitionPlan
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    AcceptanceOperator,
    EvaluationReducer,
    EvaluationSliceKind,
    MetricDirection,
    PartitionOverlapPolicy,
    PartitionPopulationScope,
    PartitionPurpose,
    SourceMetricValueType,
)
from market_regime_alpha.research_qualification.errors import EvaluationAcquisitionError
from market_regime_alpha.runtime.errors import RuntimeStateConflictError
from market_regime_alpha.outcome.application import SettleMarketTargetOutcomeRequest
from tests.refoundation.outcome import test_outcome_postgres as _outcome


@pytest.fixture
def wp11_stack(target_database_url, tmp_path, request):
    return _outcome.outcome_stack.__wrapped__(target_database_url, tmp_path, request)


def _wp11_context(key: str, reason: str):
    return _outcome._context(f"wp11-{key}", reason)


def _settle_two_visible_revisions(stack):
    target = _outcome._register_midnight_target(stack)
    commitment_id = _outcome._open_decision(stack, target)
    event_end, first_known_at, first_bar_id = _outcome._add_outcome_bar(stack)
    second_known_at, _ = _outcome._correct_outcome_bar(
        stack, first_bar_id, close_value=Decimal("10.70")
    )
    application = _outcome._application(stack)
    first = application.settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=first_known_at,
            expected_current_revision_id=None,
        ),
        _wp11_context("settle-first", "SETTLE_DUE_OUTCOME"),
        runtime_claim=_outcome._outcome_claim(stack),
    )
    second = application.settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=second_known_at,
            expected_current_revision_id=first.market_target_outcome_revision_id,
        ),
        _wp11_context("settle-second", "CORRECT_MARKET_OUTCOME"),
        runtime_claim=_outcome._outcome_claim(stack),
    )
    with psycopg.connect(stack.database_url) as connection:
        settled = connection.execute(
            """
            SELECT market_target_outcome_revision_id, settled_at
            FROM mra.market_target_outcome_revision
            WHERE market_target_outcome_id = %s
            ORDER BY revision_ordinal
            """,
            (first.market_target_outcome_id,),
        ).fetchall()
    return target, first, second, settled


def _freeze_and_predeclare(
    stack,
    target,
    *,
    purpose: PartitionPurpose = PartitionPurpose.VALIDATION,
    overlap_policy: PartitionOverlapPolicy = PartitionOverlapPolicy.DIAGNOSTIC_REUSE,
):
    ids = uuid4
    partition_commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(stack.pool, id_factory=ids),
        id_factory=ids,
    )
    plan = ResearchPartitionPlan(
        research_partition_id=uuid4(),
        partition_code=f"wp11-validation-{uuid4().hex[:8]}",
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        purpose=purpose,
        population_scope=PartitionPopulationScope.ALL_COMMITMENTS,
        overlap_policy=overlap_policy,
        decision_start_session_id=stack.market_session_id,
        decision_end_session_id=stack.market_session_id,
        purge_before_sessions=0,
        purge_after_sessions=0,
        embargo_sessions=0,
        series_code="wp11-validation-series",
        fold_ordinal=1,
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="9" * 64,
    )
    partition = partition_commands.freeze(
        plan, _wp11_context("freeze-partition", "FREEZE_RESEARCH_PARTITION")
    )

    experiment_commands = ExperimentCommands(
        PostgresExperimentUnitOfWorkProvider(stack.pool), id_factory=ids
    )
    experiment = ExperimentDefinition(
        experiment_id=uuid4(), experiment_code=f"wp11-exp-{uuid4().hex[:8]}",
        research_question="Does the declared change meet its frozen metric?",
        primary_change="Evaluate one declared candidate rule change.",
        hypothesis="The exact frozen roster has positive mean return.",
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        protocol_identity="wp11-mean-return-v1",
        acceptance_semantics="Descriptive in this correctness fixture.",
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="8" * 64,
    )
    binding = ExperimentPartitionBinding(
        experiment_partition_id=uuid4(), experiment_id=experiment.experiment_id,
        research_partition_id=partition.research_partition_id,
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        purpose=purpose,
        partition_content_sha256=partition.content_sha256,
    )
    experiment_commands.register(
        experiment, binding,
        _wp11_context("register-experiment", "REGISTER_EXPERIMENT"),
    )
    experiment_run_id = uuid4()
    experiment_commands.open_run(
        ExperimentRunPlan(
            experiment_run_id=experiment_run_id,
            experiment_id=experiment.experiment_id,
            experiment_partition_id=binding.experiment_partition_id,
            run_identity="wp11-run-1",
        ),
        _wp11_context("open-experiment-run", "OPEN_EXPERIMENT_RUN"),
    )

    evaluation_commands = EvaluationCommands(
        PostgresEvaluationUnitOfWorkProvider(stack.pool, id_factory=ids),
        id_factory=ids,
    )
    source_metric = target.metrics[0]
    protocol = EvaluationProtocolPlan(
        evaluation_protocol_id=uuid4(),
        protocol_code=f"wp11-protocol-{uuid4().hex[:8]}",
        protocol_version=1,
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        applicable_purpose=purpose,
        decision_rule="Report the frozen mean without changing membership.",
        metrics=(
            ProtocolMetricDefinition(
                evaluation_protocol_metric_id=uuid4(),
                metric_code="mean-return", ordinal=1,
                source_target_metric_definition_id=source_metric.target_metric_definition_id,
                source_metric_code=source_metric.metric_code,
                source_value_type=SourceMetricValueType.DECIMAL,
                reducer=EvaluationReducer.MEAN_DECIMAL,
                slice_kind=EvaluationSliceKind.ALL_MEMBERS,
                candidate_disposition=None,
                direction=MetricDirection.DESCRIPTIVE,
                minimum_estimable_count=1,
                acceptance_operator=AcceptanceOperator.NONE,
                acceptance_threshold=None,
            ),
        ),
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="7" * 64,
    )
    evaluation_commands.register_protocol(
        protocol,
        _wp11_context("register-protocol", "REGISTER_EVALUATION_PROTOCOL"),
    )
    return evaluation_commands, partition, experiment_run_id, protocol


def _run_evaluation(commands, experiment_run_id: UUID, protocol, cutoff, suffix: str):
    evaluation_run_id = uuid4()
    commands.open_run(
        EvaluationRunPlan(
            evaluation_run_id=evaluation_run_id,
            experiment_run_id=experiment_run_id,
            evaluation_protocol_id=protocol.evaluation_protocol_id,
            requested_knowledge_cutoff=cutoff,
            request_identity=f"evaluation-{suffix}",
            code_artifact=protocol.code_artifact,
            config_artifact=protocol.config_artifact,
            provenance_sha256="8" * 64,
        ),
        _wp11_context(f"open-evaluation-{suffix}", "OPEN_EVALUATION_RUN"),
    )
    acquired = commands.acquire_outcome_inputs(
        evaluation_run_id,
        _wp11_context(f"acquire-{suffix}", "ACQUIRE_OUTCOME_INPUTS"),
    )
    completed = commands.complete(
        evaluation_run_id,
        _wp11_context(f"complete-{suffix}", "COMPLETE_EVALUATION_RUN"),
    )
    return evaluation_run_id, acquired, completed


def test_pit_safe_first_and_repeated_access_close_complete_evaluations(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, first, second, settled = _settle_two_visible_revisions(stack)
    commands, partition, experiment_run_id, protocol = _freeze_and_predeclare(
        stack, target
    )
    first_cutoff = settled[0][1] + (settled[1][1] - settled[0][1]) / 2
    first_run, acquired, completed = _run_evaluation(
        commands, experiment_run_id, protocol, first_cutoff, "first"
    )
    assert acquired.count == partition.member_count == 1
    assert completed.count == 1
    acquisition_replay = commands.acquire_outcome_inputs(
        first_run,
        _wp11_context("acquire-first", "ACQUIRE_OUTCOME_INPUTS"),
    )
    completion_replay = commands.complete(
        first_run,
        _wp11_context("complete-first", "COMPLETE_EVALUATION_RUN"),
    )
    assert acquisition_replay.replayed is True
    assert completion_replay.replayed is True

    second_cutoff = settled[1][1] + timedelta(microseconds=1)
    second_run, _, _ = _run_evaluation(
        commands, experiment_run_id, protocol, second_cutoff, "second"
    )
    with psycopg.connect(stack.database_url) as connection:
        accesses = connection.execute(
            """
            SELECT evaluation_run_id, market_target_outcome_revision_id,
                   access_ordinal
            FROM mra.research_partition_outcome_access
            ORDER BY access_ordinal
            """
        ).fetchall()
        run_states = connection.execute(
            """
            SELECT evaluation_run_id, status, access_count,
                   observation_count, metric_count,
                   metric_observation_count
            FROM mra.evaluation_run
            ORDER BY opened_at
            """
        ).fetchall()
        metric_values = connection.execute(
            """
            SELECT run.evaluation_run_id, metric.decimal_value
            FROM mra.evaluation_run AS run
            JOIN mra.evaluation_metric AS metric
              ON metric.evaluation_run_id = run.evaluation_run_id
            ORDER BY run.opened_at
            """
        ).fetchall()
    assert accesses == [
        (first_run, first.market_target_outcome_revision_id, 1),
        (second_run, second.market_target_outcome_revision_id, 2),
    ]
    assert all(row[1:] == ("COMPLETED", 1, 1, 1, 1) for row in run_states)
    assert Decimal(metric_values[0][1]) == Decimal("0.049504950495049505")
    assert Decimal(metric_values[1][1]) == Decimal("0.059405940594059406")


def test_protected_partition_cannot_open_another_evaluation_after_first_access(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, _, settled = _settle_two_visible_revisions(stack)
    commands, _, experiment_run_id, protocol = _freeze_and_predeclare(
        stack,
        target,
        purpose=PartitionPurpose.LOCKED_OOS,
        overlap_policy=PartitionOverlapPolicy.ISOLATED_PROTECTED,
    )
    cutoff = settled[1][1] + timedelta(microseconds=1)
    _run_evaluation(commands, experiment_run_id, protocol, cutoff, "protected-first")

    with pytest.raises(RuntimeStateConflictError, match="Evaluation"):
        commands.open_run(
            EvaluationRunPlan(
                evaluation_run_id=uuid4(),
                experiment_run_id=experiment_run_id,
                evaluation_protocol_id=protocol.evaluation_protocol_id,
                requested_knowledge_cutoff=cutoff,
                request_identity="protected-second",
                code_artifact=protocol.code_artifact,
                config_artifact=protocol.config_artifact,
                provenance_sha256="8" * 64,
            ),
            _wp11_context("open-protected-second", "OPEN_EVALUATION_RUN"),
        )


def test_evaluation_run_can_fail_once_and_replays_exact_failure(wp11_stack) -> None:
    stack = wp11_stack
    target, _, _, settled = _settle_two_visible_revisions(stack)
    commands, _, experiment_run_id, protocol = _freeze_and_predeclare(stack, target)
    evaluation_run_id = uuid4()
    commands.open_run(
        EvaluationRunPlan(
            evaluation_run_id=evaluation_run_id,
            experiment_run_id=experiment_run_id,
            evaluation_protocol_id=protocol.evaluation_protocol_id,
            requested_knowledge_cutoff=settled[1][1] + timedelta(microseconds=1),
            request_identity="failed-run",
            code_artifact=protocol.code_artifact,
            config_artifact=protocol.config_artifact,
            provenance_sha256="8" * 64,
        ),
        _wp11_context("open-failed-run", "OPEN_EVALUATION_RUN"),
    )
    context = _wp11_context("fail-run", "FAIL_EVALUATION_RUN")
    first = commands.fail_run(evaluation_run_id, "OPERATOR_ABORTED", context)
    replay = commands.fail_run(evaluation_run_id, "OPERATOR_ABORTED", context)

    assert first.replayed is False
    assert replay.replayed is True
    with psycopg.connect(stack.database_url) as connection:
        state = connection.execute(
            """
            SELECT status, failure_reason_code, version,
                   code_artifact_id, config_artifact_id, provenance_sha256
            FROM mra.evaluation_run WHERE evaluation_run_id = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
    assert state is not None
    assert state[:3] == ("FAILED", "OPERATOR_ABORTED", 2)
    assert state[3] == protocol.code_artifact.artifact_id
    assert state[4] == protocol.config_artifact.artifact_id
    assert state[5] == "8" * 64


def test_database_rejects_a_revision_not_visible_at_run_cutoff(wp11_stack) -> None:
    stack = wp11_stack
    target, _, second, settled = _settle_two_visible_revisions(stack)
    commands, partition, experiment_run_id, protocol = _freeze_and_predeclare(
        stack, target
    )
    first_cutoff = settled[0][1] + (settled[1][1] - settled[0][1]) / 2
    evaluation_run_id = uuid4()
    commands.open_run(
        EvaluationRunPlan(
            evaluation_run_id=evaluation_run_id,
            experiment_run_id=experiment_run_id,
            evaluation_protocol_id=protocol.evaluation_protocol_id,
            requested_knowledge_cutoff=first_cutoff,
            request_identity="wrong-pit-revision",
            code_artifact=protocol.code_artifact,
            config_artifact=protocol.config_artifact,
            provenance_sha256="8" * 64,
        ),
        _wp11_context("open-wrong-pit", "OPEN_EVALUATION_RUN"),
    )
    with psycopg.connect(stack.database_url) as connection:
        member = connection.execute(
            """
            SELECT research_partition_member_id, commitment_id
            FROM mra.research_partition_member
            WHERE research_partition_id = %s
            """,
            (partition.research_partition_id,),
        ).fetchone()
        revision = connection.execute(
            """
            SELECT market_target_outcome_revision_id,
                   market_target_outcome_id, revision_ordinal,
                   observation_cutoff, knowledge_cutoff, settled_at,
                   outcome_status
            FROM mra.market_target_outcome_revision
            WHERE market_target_outcome_revision_id = %s
            """,
            (second.market_target_outcome_revision_id,),
        ).fetchone()
        assert member is not None and revision is not None
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """
                INSERT INTO mra.research_partition_outcome_access (
                    research_partition_outcome_access_id,
                    evaluation_run_id, research_partition_member_id,
                    research_partition_id, commitment_id,
                    target_definition_id,
                    market_target_outcome_revision_id,
                    market_target_outcome_id, revision_ordinal,
                    observation_cutoff, knowledge_cutoff, settled_at,
                    outcome_status, access_ordinal, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, 1, %s
                )
                """,
                (
                    uuid4(), evaluation_run_id, member[0],
                    partition.research_partition_id, member[1],
                    target.target_definition_id, *revision, "a" * 64,
                ),
            )


def test_not_due_acquisition_fails_without_access_or_observation(wp11_stack) -> None:
    stack = wp11_stack
    target = _outcome._register_midnight_target(stack)
    _outcome._open_decision(stack, target)
    _outcome._add_outcome_bar(stack)
    commands, _, experiment_run_id, protocol = _freeze_and_predeclare(stack, target)
    with psycopg.connect(stack.database_url) as connection:
        due = connection.execute(
            "SELECT outcome_due_at FROM mra.research_partition_member"
        ).fetchone()
    assert due is not None
    evaluation_run_id = uuid4()
    commands.open_run(
        EvaluationRunPlan(
            evaluation_run_id=evaluation_run_id,
            experiment_run_id=experiment_run_id,
            evaluation_protocol_id=protocol.evaluation_protocol_id,
            requested_knowledge_cutoff=due[0] - timedelta(microseconds=1),
            request_identity="not-due",
            code_artifact=protocol.code_artifact,
            config_artifact=protocol.config_artifact,
            provenance_sha256="8" * 64,
        ),
        _wp11_context("open-not-due", "OPEN_EVALUATION_RUN"),
    )
    with pytest.raises(EvaluationAcquisitionError, match="NOT_DUE"):
        commands.acquire_outcome_inputs(
            evaluation_run_id,
            _wp11_context("acquire-not-due", "ACQUIRE_OUTCOME_INPUTS"),
        )
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT (SELECT count(*) FROM mra.research_partition_outcome_access),
                   (SELECT count(*) FROM mra.evaluation_observation)
            """
        ).fetchone()
    assert counts == (0, 0)


def test_unavailable_outcome_member_is_retained_as_not_estimable(wp11_stack) -> None:
    stack = wp11_stack
    target = _outcome._register_midnight_target(stack)
    commitment_id = _outcome._open_decision(stack, target)
    event_end, known_at, _ = _outcome._add_outcome_gap(stack)
    settled = _outcome._application(stack).settle_market_target_outcome(
        SettleMarketTargetOutcomeRequest(
            commitment_id=commitment_id,
            observation_cutoff=event_end,
            knowledge_cutoff=known_at,
            expected_current_revision_id=None,
        ),
        _wp11_context("settle-unavailable", "SETTLE_DUE_OUTCOME"),
        runtime_claim=_outcome._outcome_claim(stack),
    )
    assert settled.status.value == "UNAVAILABLE"
    commands, _, experiment_run_id, protocol = _freeze_and_predeclare(stack, target)
    with psycopg.connect(stack.database_url) as connection:
        cutoff = connection.execute(
            """
            SELECT settled_at FROM mra.market_target_outcome_revision
            WHERE market_target_outcome_revision_id = %s
            """,
            (settled.market_target_outcome_revision_id,),
        ).fetchone()
    assert cutoff is not None
    evaluation_run_id, acquired, completed = _run_evaluation(
        commands,
        experiment_run_id,
        protocol,
        cutoff[0] + timedelta(microseconds=1),
        "unavailable",
    )
    assert acquired.count == completed.count == 1
    with psycopg.connect(stack.database_url) as connection:
        row = connection.execute(
            """
            SELECT observation.outcome_status, metric.metric_state,
                   input.input_state, metric.decimal_value
            FROM mra.evaluation_observation AS observation
            JOIN mra.evaluation_metric AS metric
              ON metric.evaluation_run_id = observation.evaluation_run_id
            JOIN mra.evaluation_metric_observation AS input
              ON input.evaluation_metric_id = metric.evaluation_metric_id
             AND input.evaluation_observation_id =
                 observation.evaluation_observation_id
            WHERE observation.evaluation_run_id = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
    assert row == ("UNAVAILABLE", "NOT_ESTIMABLE", "NOT_ESTIMABLE", None)


def test_partition_uses_session_shift_and_rejects_protected_overlap(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target = _outcome._register_midnight_target(stack)
    _outcome._open_decision(stack, target)
    _outcome._add_outcome_bar(stack)
    with psycopg.connect(stack.database_url) as connection:
        reference = connection.execute(
            """
            SELECT session_date, source_capture_id
            FROM mra.trading_session WHERE session_id = %s
            """,
            (stack.market_session_id,),
        ).fetchone()
        assert reference is not None
        protected_date = reference[0] + timedelta(days=4)

        def at(hour: int, minute: int):
            return datetime.combine(
                protected_date, time(hour, minute), ZoneInfo("Asia/Shanghai")
            ).astimezone(UTC)

        recorded_at = datetime.now(UTC)
        protected_session_id = uuid4()
        connection.execute(
            """
            INSERT INTO mra.trading_session (
                session_id, exchange, session_date, timezone_name,
                open_at, close_at, decision_reference_at,
                source_capture_id, recorded_at, known_at,
                decision_visible_at
            ) VALUES (
                %s, 'XSHG', %s, 'Asia/Shanghai', %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                protected_session_id, protected_date, at(9, 30), at(15, 0),
                at(14, 55), reference[1], recorded_at, recorded_at, recorded_at,
            ),
        )
        connection.commit()

    commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )

    def plan(
        code: str,
        *,
        purge_after: int,
        purpose: PartitionPurpose = PartitionPurpose.LOCKED_OOS,
        overlap_policy: PartitionOverlapPolicy = PartitionOverlapPolicy.ISOLATED_PROTECTED,
    ) -> ResearchPartitionPlan:
        return ResearchPartitionPlan(
            research_partition_id=uuid4(), partition_code=code,
            target_definition_id=target.target_definition_id,
            target_version=target.version,
            target_definition_sha256=target.content_sha256,
            purpose=purpose,
            population_scope=PartitionPopulationScope.ALL_COMMITMENTS,
            overlap_policy=overlap_policy,
            decision_start_session_id=stack.market_session_id,
            decision_end_session_id=stack.market_session_id,
            purge_before_sessions=0, purge_after_sessions=purge_after,
            embargo_sessions=0, series_code="wp11-locked-series",
            fold_ordinal=1, code_artifact=target.algorithm.code_artifact,
            config_artifact=target.algorithm.config_artifact,
            provenance_sha256="6" * 64,
        )

    first = commands.freeze(
        plan("wp11-locked-first", purge_after=1),
        _wp11_context("freeze-locked-first", "FREEZE_RESEARCH_PARTITION"),
    )
    with psycopg.connect(stack.database_url) as connection:
        protected = connection.execute(
            """
            SELECT protected_end_session_id, protected_end_date
            FROM mra.research_partition WHERE research_partition_id = %s
            """,
            (first.research_partition_id,),
        ).fetchone()
    assert protected == (protected_session_id, protected_date)
    assert protected_date != reference[0] + timedelta(days=2)

    with pytest.raises(RuntimeStateConflictError, match="Partition"):
        commands.freeze(
            plan("wp11-locked-overlap", purge_after=0),
            _wp11_context("freeze-locked-overlap", "FREEZE_RESEARCH_PARTITION"),
        )
    with pytest.raises(RuntimeStateConflictError, match="Partition"):
        commands.freeze(
            plan(
                "wp11-walk-forward-overlap",
                purge_after=0,
                purpose=PartitionPurpose.VALIDATION,
                overlap_policy=PartitionOverlapPolicy.PURGED_WALK_FORWARD,
            ),
            _wp11_context(
                "freeze-walk-forward-overlap", "FREEZE_RESEARCH_PARTITION"
            ),
        )
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.research_partition"
        ).fetchone() == (1,)
