from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.evaluation_uow import PostgresEvaluationUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.experiment_uow import PostgresExperimentUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.partition_uow import PostgresPartitionUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.queries.research_verification import (
    PostgresResearchEvaluationVerificationProvider,
)
from market_regime_alpha.research_qualification.application import (
    EvaluationCommands,
    ExperimentCommands,
    ResearchEvaluationVerifier,
    ResearchPartitionCommands,
)
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
from market_regime_alpha.research_qualification.errors import (
    EvaluationAcquisitionError,
    PartitionInputError,
    ResearchRetryableTransactionError,
)
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.outcome.application import SettleMarketTargetOutcomeRequest
from tests.refoundation.outcome import test_outcome_postgres as _outcome


@pytest.fixture
def wp11_stack(target_database_url, tmp_path, request):
    return _outcome.outcome_stack.__wrapped__(target_database_url, tmp_path, request)


def _wp11_context(key: str, reason: str):
    return _outcome._context(f"wp11-{key}", reason)


def _partition_plan(
    stack,
    target,
    *,
    code: str,
    purpose: PartitionPurpose = PartitionPurpose.VALIDATION,
    overlap_policy: PartitionOverlapPolicy = PartitionOverlapPolicy.DIAGNOSTIC_REUSE,
) -> ResearchPartitionPlan:
    return ResearchPartitionPlan(
        research_partition_id=uuid4(),
        partition_code=code,
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        purpose=purpose,
        population_scope=PartitionPopulationScope.ALL_COMMITMENTS,
        overlap_policy=overlap_policy,
        exchange_code="XSHG",
        decision_start_session_id=stack.market_session_id,
        decision_end_session_id=stack.market_session_id,
        purge_before_sessions=0,
        purge_after_sessions=0,
        embargo_sessions=0,
        series_code=f"{code}-series",
        fold_ordinal=1,
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="9" * 64,
    )


def _attempt(callable_):
    try:
        return "SUCCEEDED", callable_()
    except BaseException as exc:  # qualification captures the losing transaction
        return "FAILED", exc


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
        exchange_code="XSHG",
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
        binding_ordinal=1,
        research_partition_id=partition.research_partition_id,
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        purpose=purpose,
        partition_content_sha256=partition.content_sha256,
    )
    experiment_commands.register(
        experiment, (binding,),
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


def test_partition_freezes_one_exact_exchange_calendar_and_excludes_other_roster(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, _, _ = _settle_two_visible_revisions(stack)
    other_session_id = uuid4()
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            INSERT INTO mra.trading_session (
                session_id, exchange, session_date, timezone_name,
                open_at, break_start_at, break_end_at, close_at,
                decision_reference_at, source_capture_id,
                recorded_at, known_at, decision_visible_at
            )
            SELECT %s, 'XSHE', session_date, timezone_name,
                   open_at, break_start_at, break_end_at, close_at,
                   decision_reference_at, source_capture_id,
                   recorded_at, known_at, decision_visible_at
            FROM mra.trading_session
            WHERE session_id = %s
            """,
            (other_session_id, stack.market_session_id),
        )
        connection.commit()

    _, partition, _, _ = _freeze_and_predeclare(stack, target)
    with psycopg.connect(stack.database_url) as connection:
        root = connection.execute(
            """
            SELECT exchange_code, timezone_name, calendar_session_count,
                   calendar_roster_sha256, protected_start_date,
                   protected_end_date
            FROM mra.research_partition
            WHERE research_partition_id = %s
            """,
            (partition.research_partition_id,),
        ).fetchone()
        assert root is not None
        counts = dict(
            connection.execute(
                """
                SELECT exchange, count(*)
                FROM mra.trading_session
                WHERE exchange IN ('XSHG', 'XSHE')
                  AND session_date BETWEEN %s AND %s
                GROUP BY exchange
                """,
                (root[4], root[5]),
            ).fetchall()
        )
        member_exchanges = connection.execute(
            """
            SELECT DISTINCT exchange_code
            FROM mra.research_partition_member
            WHERE research_partition_id = %s
            """,
            (partition.research_partition_id,),
        ).fetchall()
    assert root[0:2] == ("XSHG", "Asia/Shanghai")
    assert root[2] == counts["XSHG"]
    assert len(str(root[3])) == 64
    assert counts["XSHG"] != counts["XSHE"]
    assert member_exchanges == [("XSHG",)]

    wrong_exchange_plan = ResearchPartitionPlan(
        research_partition_id=uuid4(),
        partition_code=f"wp11-wrong-exchange-{uuid4().hex[:8]}",
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        purpose=PartitionPurpose.VALIDATION,
        population_scope=PartitionPopulationScope.ALL_COMMITMENTS,
        overlap_policy=PartitionOverlapPolicy.DIAGNOSTIC_REUSE,
        exchange_code="XSHE",
        decision_start_session_id=stack.market_session_id,
        decision_end_session_id=stack.market_session_id,
        purge_before_sessions=0,
        purge_after_sessions=0,
        embargo_sessions=0,
        series_code="wp11-wrong-exchange-series",
        fold_ordinal=1,
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="5" * 64,
    )
    commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    with pytest.raises(PartitionInputError, match="declared exchange calendar"):
        commands.freeze(
            wrong_exchange_plan,
            _wp11_context("freeze-wrong-exchange", "FREEZE_RESEARCH_PARTITION"),
        )


def test_experiment_registration_freezes_complete_ordered_partition_roster(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, _, _ = _settle_two_visible_revisions(stack)
    partition_commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    declared = (
        (PartitionPurpose.FIT, PartitionOverlapPolicy.DIAGNOSTIC_REUSE),
        (PartitionPurpose.VALIDATION, PartitionOverlapPolicy.DIAGNOSTIC_REUSE),
        (PartitionPurpose.LOCKED_OOS, PartitionOverlapPolicy.ISOLATED_PROTECTED),
    )
    partitions = []
    for ordinal, (purpose, policy) in enumerate(declared, start=1):
        plan = ResearchPartitionPlan(
            research_partition_id=uuid4(),
            partition_code=f"wp11-roster-{ordinal}-{uuid4().hex[:8]}",
            target_definition_id=target.target_definition_id,
            target_version=target.version,
            target_definition_sha256=target.content_sha256,
            purpose=purpose,
            population_scope=PartitionPopulationScope.ALL_COMMITMENTS,
            overlap_policy=policy,
            exchange_code="XSHG",
            decision_start_session_id=stack.market_session_id,
            decision_end_session_id=stack.market_session_id,
            purge_before_sessions=0,
            purge_after_sessions=0,
            embargo_sessions=0,
            series_code=f"wp11-roster-series-{ordinal}",
            fold_ordinal=1,
            code_artifact=target.algorithm.code_artifact,
            config_artifact=target.algorithm.config_artifact,
            provenance_sha256=f"{ordinal}" * 64,
        )
        partitions.append(
            partition_commands.freeze(
                plan,
                _wp11_context(
                    f"freeze-roster-{ordinal}", "FREEZE_RESEARCH_PARTITION"
                ),
            )
        )

    definition = ExperimentDefinition(
        experiment_id=uuid4(),
        experiment_code=f"wp11-roster-exp-{uuid4().hex[:8]}",
        research_question="Can one experiment predeclare all purpose partitions?",
        primary_change="Freeze one exact ordered Partition binding roster.",
        hypothesis="All declared partitions remain relationally complete.",
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        protocol_identity="wp11-roster-protocol-v1",
        acceptance_semantics="No posterior Partition binding is permitted.",
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="4" * 64,
    )
    bindings = tuple(
        ExperimentPartitionBinding(
            experiment_partition_id=uuid4(),
            experiment_id=definition.experiment_id,
            binding_ordinal=ordinal,
            research_partition_id=partition.research_partition_id,
            target_definition_id=target.target_definition_id,
            target_version=target.version,
            target_definition_sha256=target.content_sha256,
            purpose=purpose,
            partition_content_sha256=partition.content_sha256,
        )
        for ordinal, ((purpose, _), partition) in enumerate(
            zip(declared, partitions, strict=True), start=1
        )
    )
    commands = ExperimentCommands(
        PostgresExperimentUnitOfWorkProvider(stack.pool), id_factory=uuid4
    )
    context = _wp11_context("register-roster-experiment", "REGISTER_EXPERIMENT")
    registered = commands.register(definition, bindings, context)
    replay = commands.register(definition, bindings, context)
    assert registered.replayed is False
    assert replay.replayed is True

    with psycopg.connect(stack.database_url) as connection:
        root = connection.execute(
            """
            SELECT partition_count, partition_roster_sha256,
                   definition_sha256, content_sha256
            FROM mra.experiment
            WHERE experiment_id = %s
            """,
            (definition.experiment_id,),
        ).fetchone()
        children = connection.execute(
            """
            SELECT binding_ordinal, research_partition_id,
                   partition_purpose, content_sha256
            FROM mra.experiment_partition
            WHERE experiment_id = %s
            ORDER BY binding_ordinal
            """,
            (definition.experiment_id,),
        ).fetchall()
        assert root is not None
        assert root[0] == len(bindings) == 3
        assert root[1] == str(definition.partition_roster_sha256(bindings))
        assert root[2] == str(definition.content_sha256)
        assert len(str(root[3])) == 64
        assert [row[0] for row in children] == [1, 2, 3]
        assert [row[2] for row in children] == [
            "FIT",
            "VALIDATION",
            "LOCKED_OOS",
        ]
        with pytest.raises(
            psycopg.errors.ObjectNotInPrerequisiteState,
            match="already frozen",
        ):
            connection.execute(
                """
                INSERT INTO mra.experiment_partition (
                    experiment_partition_id, experiment_id,
                    binding_ordinal, research_partition_id,
                    target_definition_id, target_version,
                    target_definition_sha256, partition_purpose,
                    partition_content_sha256, content_sha256
                ) VALUES (%s, %s, 4, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid4(),
                    definition.experiment_id,
                    partitions[0].research_partition_id,
                    target.target_definition_id,
                    target.version,
                    str(target.content_sha256),
                    PartitionPurpose.FIT.value,
                    partitions[0].content_sha256,
                    "f" * 64,
                ),
            )

    with pytest.raises(IdempotencyKeyReusedError):
        commands.register(definition, bindings[:-1], context)


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


def test_read_only_verifier_reconciles_partition_experiment_and_evaluation(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, _, settled = _settle_two_visible_revisions(stack)
    commands, partition, experiment_run_id, protocol = _freeze_and_predeclare(
        stack, target
    )
    evaluation_run_id, _, _ = _run_evaluation(
        commands,
        experiment_run_id,
        protocol,
        settled[1][1] + timedelta(microseconds=1),
        "verification",
    )
    with psycopg.connect(stack.database_url) as connection:
        experiment_id = connection.execute(
            """
            SELECT experiment_id FROM mra.experiment_run
            WHERE experiment_run_id = %s
            """,
            (experiment_run_id,),
        ).fetchone()
    assert experiment_id is not None
    verifier = ResearchEvaluationVerifier(
        PostgresResearchEvaluationVerificationProvider(stack.pool)
    )
    reports = (
        verifier.verify_partition(partition.research_partition_id),
        verifier.verify_experiment(UUID(str(experiment_id[0]))),
        verifier.verify_evaluation_run(evaluation_run_id),
    )
    assert all(report.matched for report in reports)
    assert all(report.mismatch_count == 0 for report in reports)
    missing = verifier.verify_evaluation_run(uuid4())
    assert missing.matched is False
    assert missing.mismatch_count == 1


def test_read_only_verifier_detects_fault_injected_partition_drift(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, _, _ = _settle_two_visible_revisions(stack)
    _, partition, _, _ = _freeze_and_predeclare(stack, target)
    with psycopg.connect(stack.database_url) as connection:
        connection.execute("SET LOCAL session_replication_role = replica")
        connection.execute(
            """
            UPDATE mra.research_partition_member
            SET content_sha256 = %s
            WHERE research_partition_id = %s
            """,
            ("f" * 64, partition.research_partition_id),
        )
        connection.commit()
    verifier = ResearchEvaluationVerifier(
        PostgresResearchEvaluationVerificationProvider(stack.pool)
    )
    report = verifier.verify_partition(partition.research_partition_id)
    assert report.matched is False
    assert report.mismatch_count >= 2
    assert {mismatch.path for mismatch in report.mismatches} >= {
        "partition.member_content_sha256",
        "partition.member_roster_sha256",
    }


def test_partition_concurrency_has_one_truth_and_symmetric_overlap_guard(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, _, _ = _settle_two_visible_revisions(stack)
    commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    plan = _partition_plan(
        stack,
        target,
        code=f"wp11-concurrent-{uuid4().hex[:8]}",
    )
    context = _wp11_context("freeze-concurrent", "FREEZE_RESEARCH_PARTITION")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: commands.freeze(plan, context), range(2)))
    assert {result.research_partition_id for result in results} == {
        plan.research_partition_id
    }
    assert sorted(result.replayed for result in results) == [False, True]
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.research_partition
               WHERE partition_code = %s),
              (SELECT count(*) FROM mra.research_partition_member
               WHERE research_partition_id = %s)
            """,
            (plan.partition_code, plan.research_partition_id),
        ).fetchone()
    assert counts == (1, 1)

    changed = replace(plan, research_partition_id=uuid4())
    with pytest.raises(RuntimeStateConflictError):
        commands.freeze(
            changed,
            _wp11_context("freeze-concurrent-changed", "FREEZE_RESEARCH_PARTITION"),
        )

    overlap_plans = tuple(
        _partition_plan(
            stack,
            target,
            code=f"wp11-overlap-{ordinal}-{uuid4().hex[:8]}",
            purpose=PartitionPurpose.LOCKED_OOS,
            overlap_policy=PartitionOverlapPolicy.ISOLATED_PROTECTED,
        )
        for ordinal in (1, 2)
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                _attempt,
                (
                    lambda: commands.freeze(
                        overlap_plans[0],
                        _wp11_context("overlap-race-1", "FREEZE_RESEARCH_PARTITION"),
                    ),
                    lambda: commands.freeze(
                        overlap_plans[1],
                        _wp11_context("overlap-race-2", "FREEZE_RESEARCH_PARTITION"),
                    ),
                ),
            )
        )
    assert sorted(state for state, _ in outcomes) == ["FAILED", "SUCCEEDED"]
    assert any(
        isinstance(value, RuntimeStateConflictError)
        for state, value in outcomes
        if state == "FAILED"
    )
    with psycopg.connect(stack.database_url) as connection:
        protected_count = connection.execute(
            """
            SELECT count(*) FROM mra.research_partition
            WHERE research_partition_id = ANY(%s::uuid[])
            """,
            ([plan.research_partition_id for plan in overlap_plans],),
        ).fetchone()
    assert protected_count == (1,)


def test_experiment_and_evaluation_concurrency_preserve_rosters_and_ordinals(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, _, settled = _settle_two_visible_revisions(stack)
    partition_commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    plan = _partition_plan(
        stack, target, code=f"wp11-evaluation-race-{uuid4().hex[:8]}"
    )
    partition = partition_commands.freeze(
        plan, _wp11_context("freeze-evaluation-race", "FREEZE_RESEARCH_PARTITION")
    )
    definition = ExperimentDefinition(
        experiment_id=uuid4(),
        experiment_code=f"wp11-evaluation-race-{uuid4().hex[:8]}",
        research_question="Do concurrent commands retain one exact Authority?",
        primary_change="Exercise the frozen concurrency contract only.",
        hypothesis="The database serializes every shared identity.",
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        protocol_identity="wp11-concurrency-v1",
        acceptance_semantics="Concurrency cannot change the declared roster.",
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="8" * 64,
    )
    binding = ExperimentPartitionBinding(
        experiment_partition_id=uuid4(),
        experiment_id=definition.experiment_id,
        binding_ordinal=1,
        research_partition_id=partition.research_partition_id,
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        purpose=PartitionPurpose.VALIDATION,
        partition_content_sha256=partition.content_sha256,
    )
    experiment_commands = ExperimentCommands(
        PostgresExperimentUnitOfWorkProvider(stack.pool), id_factory=uuid4
    )
    experiment_context = _wp11_context(
        "register-experiment-race", "REGISTER_EXPERIMENT"
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        registered = list(
            executor.map(
                lambda _: experiment_commands.register(
                    definition, (binding,), experiment_context
                ),
                range(2),
            )
        )
    assert sorted(result.replayed for result in registered) == [False, True]

    experiment_run_id = uuid4()
    experiment_commands.open_run(
        ExperimentRunPlan(
            experiment_run_id=experiment_run_id,
            experiment_id=definition.experiment_id,
            experiment_partition_id=binding.experiment_partition_id,
            run_identity="wp11-concurrent-evaluation-run",
        ),
        _wp11_context("open-experiment-race", "OPEN_EXPERIMENT_RUN"),
    )
    source_metric = target.metrics[0]
    protocol = EvaluationProtocolPlan(
        evaluation_protocol_id=uuid4(),
        protocol_code=f"wp11-concurrency-{uuid4().hex[:8]}",
        protocol_version=1,
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        applicable_purpose=PartitionPurpose.VALIDATION,
        decision_rule="Evaluate the complete frozen roster.",
        metrics=(
            ProtocolMetricDefinition(
                evaluation_protocol_metric_id=uuid4(),
                metric_code="mean-return",
                ordinal=1,
                source_target_metric_definition_id=(
                    source_metric.target_metric_definition_id
                ),
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
    evaluation_commands = EvaluationCommands(
        PostgresEvaluationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    evaluation_commands.register_protocol(
        protocol,
        _wp11_context("register-concurrency-protocol", "REGISTER_EVALUATION_PROTOCOL"),
    )
    cutoff = settled[1][1] + timedelta(microseconds=1)
    first_plan = EvaluationRunPlan(
        evaluation_run_id=uuid4(),
        experiment_run_id=experiment_run_id,
        evaluation_protocol_id=protocol.evaluation_protocol_id,
        requested_knowledge_cutoff=cutoff,
        request_identity="wp11-concurrent-open-1",
        code_artifact=protocol.code_artifact,
        config_artifact=protocol.config_artifact,
        provenance_sha256="6" * 64,
    )
    first_context = _wp11_context("open-evaluation-race", "OPEN_EVALUATION_RUN")
    with ThreadPoolExecutor(max_workers=2) as executor:
        opened = list(
            executor.map(
                lambda _: evaluation_commands.open_run(first_plan, first_context),
                range(2),
            )
        )
    assert sorted(result.replayed for result in opened) == [False, True]
    second_plan = replace(
        first_plan,
        evaluation_run_id=uuid4(),
        request_identity="wp11-concurrent-open-2",
    )
    evaluation_commands.open_run(
        second_plan,
        _wp11_context("open-evaluation-race-2", "OPEN_EVALUATION_RUN"),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        acquisitions = list(
            executor.map(
                lambda item: evaluation_commands.acquire_outcome_inputs(
                    item[0],
                    _wp11_context(item[1], "ACQUIRE_OUTCOME_INPUTS"),
                ),
                (
                    (first_plan.evaluation_run_id, "acquire-race-1"),
                    (second_plan.evaluation_run_id, "acquire-race-2"),
                ),
            )
        )
    assert all(result.count == 1 for result in acquisitions)
    with psycopg.connect(stack.database_url) as connection:
        access_ordinals = connection.execute(
            """
            SELECT access_ordinal
            FROM mra.research_partition_outcome_access
            ORDER BY access_ordinal
            """
        ).fetchall()
        authority_counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.experiment_partition
               WHERE experiment_id = %s),
              (SELECT count(*) FROM mra.evaluation_run
               WHERE evaluation_run_id = ANY(%s::uuid[])),
              (SELECT count(*) FROM mra.evaluation_observation
               WHERE evaluation_run_id = ANY(%s::uuid[]))
            """,
            (
                definition.experiment_id,
                [first_plan.evaluation_run_id, second_plan.evaluation_run_id],
                [first_plan.evaluation_run_id, second_plan.evaluation_run_id],
            ),
        ).fetchone()
    assert access_ordinals == [(1,), (2,)]
    assert authority_counts == (1, 2, 2)


def test_acquire_complete_and_fail_races_never_leave_partial_authority(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, _, settled = _settle_two_visible_revisions(stack)
    commands, _, experiment_run_id, protocol = _freeze_and_predeclare(stack, target)
    cutoff = settled[1][1] + timedelta(microseconds=1)

    acquire_plan = EvaluationRunPlan(
        evaluation_run_id=uuid4(),
        experiment_run_id=experiment_run_id,
        evaluation_protocol_id=protocol.evaluation_protocol_id,
        requested_knowledge_cutoff=cutoff,
        request_identity="wp11-acquire-fail-race",
        code_artifact=protocol.code_artifact,
        config_artifact=protocol.config_artifact,
        provenance_sha256="5" * 64,
    )
    commands.open_run(
        acquire_plan,
        _wp11_context("open-acquire-fail-race", "OPEN_EVALUATION_RUN"),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        acquire_fail = list(
            executor.map(
                _attempt,
                (
                    lambda: commands.acquire_outcome_inputs(
                        acquire_plan.evaluation_run_id,
                        _wp11_context("acquire-fail-race", "ACQUIRE_OUTCOME_INPUTS"),
                    ),
                    lambda: commands.fail_run(
                        acquire_plan.evaluation_run_id,
                        "QUALIFICATION_RACE",
                        _wp11_context("fail-acquire-race", "FAIL_EVALUATION_RUN"),
                    ),
                ),
            )
        )
    assert sum(state == "SUCCEEDED" for state, _ in acquire_fail) >= 1

    complete_plan = replace(
        acquire_plan,
        evaluation_run_id=uuid4(),
        request_identity="wp11-complete-fail-race",
    )
    commands.open_run(
        complete_plan,
        _wp11_context("open-complete-fail-race", "OPEN_EVALUATION_RUN"),
    )
    commands.acquire_outcome_inputs(
        complete_plan.evaluation_run_id,
        _wp11_context("acquire-complete-fail-race", "ACQUIRE_OUTCOME_INPUTS"),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        complete_fail = list(
            executor.map(
                _attempt,
                (
                    lambda: commands.complete(
                        complete_plan.evaluation_run_id,
                        _wp11_context("complete-fail-race", "COMPLETE_EVALUATION_RUN"),
                    ),
                    lambda: commands.fail_run(
                        complete_plan.evaluation_run_id,
                        "QUALIFICATION_RACE",
                        _wp11_context("fail-complete-race", "FAIL_EVALUATION_RUN"),
                    ),
                ),
            )
        )
    assert sorted(state for state, _ in complete_fail) == ["FAILED", "SUCCEEDED"]
    with psycopg.connect(stack.database_url) as connection:
        states = connection.execute(
            """
            SELECT evaluation_run_id, status, access_count,
                   observation_count, metric_count,
                   metric_observation_count
            FROM mra.evaluation_run
            WHERE evaluation_run_id = ANY(%s::uuid[])
            ORDER BY evaluation_run_id
            """,
            ([acquire_plan.evaluation_run_id, complete_plan.evaluation_run_id],),
        ).fetchall()
    assert {str(row[1]) for row in states} <= {
        "INPUTS_ACQUIRED",
        "COMPLETED",
        "FAILED",
    }
    for row in states:
        if row[1] == "FAILED" and int(row[2]) == 0:
            assert row[3:] == (0, 0, 0)
        elif row[1] == "FAILED":
            assert row[2:4] == (1, 1)
            assert row[4:] == (0, 0)
        elif row[1] == "INPUTS_ACQUIRED":
            assert row[2:] == (1, 1, 0, 0)
        else:
            assert row[1:] == ("COMPLETED", 1, 1, 1, 1)


def test_outcome_correction_race_cannot_change_evaluation_cutoff_snapshot(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, second, _ = _settle_two_visible_revisions(stack)
    with psycopg.connect(stack.database_url) as connection:
        current_bar = connection.execute(
            """
            SELECT bar_revision_id, event_end
            FROM mra.market_bar_revision
            WHERE instrument_id = %s
            ORDER BY revision DESC
            LIMIT 1
            """,
            (stack.instrument_id.value,),
        ).fetchone()
    assert current_bar is not None
    third_known_at, _ = _outcome._correct_outcome_bar(
        stack,
        UUID(str(current_bar[0])),
        close_value=Decimal("10.80"),
    )
    commands, partition, experiment_run_id, protocol = _freeze_and_predeclare(
        stack, target
    )
    cutoff = datetime.now(UTC)
    evaluation_run_id = uuid4()
    commands.open_run(
        EvaluationRunPlan(
            evaluation_run_id=evaluation_run_id,
            experiment_run_id=experiment_run_id,
            evaluation_protocol_id=protocol.evaluation_protocol_id,
            requested_knowledge_cutoff=cutoff,
            request_identity="wp11-correction-acquire-race",
            code_artifact=protocol.code_artifact,
            config_artifact=protocol.config_artifact,
            provenance_sha256="1" * 64,
        ),
        _wp11_context("open-correction-race", "OPEN_EVALUATION_RUN"),
    )
    correction_claim = _outcome._outcome_claim(stack)
    correction_application = _outcome._application(stack)

    def settle_correction():
        return correction_application.settle_market_target_outcome(
            SettleMarketTargetOutcomeRequest(
                commitment_id=second.commitment_id,
                observation_cutoff=current_bar[1],
                knowledge_cutoff=third_known_at,
                expected_current_revision_id=(
                    second.market_target_outcome_revision_id
                ),
            ),
            _wp11_context("settle-third-race", "CORRECT_MARKET_OUTCOME"),
            runtime_claim=correction_claim,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        correction_future = executor.submit(settle_correction)
        acquisition_future = executor.submit(
            commands.acquire_outcome_inputs,
            evaluation_run_id,
            _wp11_context("acquire-correction-race", "ACQUIRE_OUTCOME_INPUTS"),
        )
        third = correction_future.result()
        acquired = acquisition_future.result()
    assert acquired.count == partition.member_count == 1
    with psycopg.connect(stack.database_url) as connection:
        accessed_revision = connection.execute(
            """
            SELECT market_target_outcome_revision_id
            FROM mra.research_partition_outcome_access
            WHERE evaluation_run_id = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
    assert accessed_revision == (second.market_target_outcome_revision_id,)
    assert third.market_target_outcome_revision_id != accessed_revision[0]
    verifier = ResearchEvaluationVerifier(
        PostgresResearchEvaluationVerificationProvider(stack.pool)
    )
    assert verifier.verify_evaluation_run(evaluation_run_id).matched is True


def test_stale_runtime_fence_writes_no_partition_receipt_audit_or_failure(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, _, _ = _settle_two_visible_revisions(stack)
    claim = _outcome._outcome_claim(stack)
    stale = replace(claim, fence_token=claim.fence_token + 1)
    plan = _partition_plan(
        stack, target, code=f"wp11-stale-fence-{uuid4().hex[:8]}"
    )
    commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    context = _wp11_context("freeze-stale-fence", "FREEZE_RESEARCH_PARTITION")
    with pytest.raises(StaleFenceError):
        commands.freeze(plan, context, runtime_claim=stale)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.research_partition
               WHERE research_partition_id = %s),
              (SELECT count(*) FROM mra.command_receipt
               WHERE idempotency_key = %s),
              (SELECT count(*) FROM mra.audit_event
               WHERE aggregate_id = %s)
            """,
            (
                plan.research_partition_id,
                context.idempotency_key,
                str(plan.research_partition_id),
            ),
        ).fetchone()
    assert counts == (0, 0, 0)


def test_transient_mid_roster_observation_and_metric_failures_recover_exactly(
    wp11_stack,
) -> None:
    stack = wp11_stack
    target, _, _, settled = _settle_two_visible_revisions(stack)
    partition_commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    partition_plan = _partition_plan(
        stack, target, code=f"wp11-mid-partition-{uuid4().hex[:8]}"
    )
    partition_context = _wp11_context(
        "mid-partition", "FREEZE_RESEARCH_PARTITION"
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION mra.wp11q_fail_partition_member()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'injected mid-Partition serialization'
                    USING ERRCODE = '40001';
            END;
            $$;
            CREATE TRIGGER wp11q_fail_partition_member
            BEFORE INSERT ON mra.research_partition_member
            FOR EACH ROW EXECUTE FUNCTION mra.wp11q_fail_partition_member();
            """
        )
        connection.commit()
    with pytest.raises(ResearchRetryableTransactionError):
        partition_commands.freeze(partition_plan, partition_context)
    with psycopg.connect(stack.database_url) as connection:
        partial = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.research_partition
               WHERE research_partition_id = %s),
              (SELECT count(*) FROM mra.research_partition_member
               WHERE research_partition_id = %s),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'FREEZE_RESEARCH_PARTITION'
                 AND idempotency_key = %s)
            """,
            (
                partition_plan.research_partition_id,
                partition_plan.research_partition_id,
                partition_context.idempotency_key,
            ),
        ).fetchone()
        connection.execute(
            "DROP TRIGGER wp11q_fail_partition_member ON mra.research_partition_member"
        )
        connection.execute("DROP FUNCTION mra.wp11q_fail_partition_member()")
        connection.commit()
    assert partial == (0, 0, 0)
    recovered_partition = partition_commands.freeze(
        partition_plan, partition_context
    )
    assert recovered_partition.replayed is False

    second_plan = _partition_plan(
        stack,
        target,
        code=f"wp11-mid-experiment-second-{uuid4().hex[:8]}",
        purpose=PartitionPurpose.FIT,
    )
    second_partition = partition_commands.freeze(
        second_plan,
        _wp11_context("mid-experiment-second", "FREEZE_RESEARCH_PARTITION"),
    )
    definition = ExperimentDefinition(
        experiment_id=uuid4(),
        experiment_code=f"wp11-mid-experiment-{uuid4().hex[:8]}",
        research_question="Does atomic Experiment roster recovery preserve all bindings?",
        primary_change="Inject one transient child insertion failure.",
        hypothesis="No partial binding survives rollback.",
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        protocol_identity="wp11-mid-experiment-v1",
        acceptance_semantics="Only a complete roster may commit.",
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="4" * 64,
    )
    bindings = (
        ExperimentPartitionBinding(
            experiment_partition_id=uuid4(),
            experiment_id=definition.experiment_id,
            binding_ordinal=1,
            research_partition_id=recovered_partition.research_partition_id,
            target_definition_id=target.target_definition_id,
            target_version=target.version,
            target_definition_sha256=target.content_sha256,
            purpose=PartitionPurpose.VALIDATION,
            partition_content_sha256=recovered_partition.content_sha256,
        ),
        ExperimentPartitionBinding(
            experiment_partition_id=uuid4(),
            experiment_id=definition.experiment_id,
            binding_ordinal=2,
            research_partition_id=second_partition.research_partition_id,
            target_definition_id=target.target_definition_id,
            target_version=target.version,
            target_definition_sha256=target.content_sha256,
            purpose=PartitionPurpose.FIT,
            partition_content_sha256=second_partition.content_sha256,
        ),
    )
    experiment_commands = ExperimentCommands(
        PostgresExperimentUnitOfWorkProvider(stack.pool), id_factory=uuid4
    )
    experiment_context = _wp11_context("mid-experiment", "REGISTER_EXPERIMENT")
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION mra.wp11q_fail_experiment_binding()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.binding_ordinal = 2 THEN
                    RAISE EXCEPTION 'injected mid-Experiment serialization'
                        USING ERRCODE = '40001';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER wp11q_fail_experiment_binding
            BEFORE INSERT ON mra.experiment_partition
            FOR EACH ROW EXECUTE FUNCTION mra.wp11q_fail_experiment_binding();
            """
        )
        connection.commit()
    with pytest.raises(ResearchRetryableTransactionError):
        experiment_commands.register(definition, bindings, experiment_context)
    with psycopg.connect(stack.database_url) as connection:
        partial = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.experiment WHERE experiment_id = %s),
              (SELECT count(*) FROM mra.experiment_partition
               WHERE experiment_id = %s)
            """,
            (definition.experiment_id, definition.experiment_id),
        ).fetchone()
        connection.execute(
            "DROP TRIGGER wp11q_fail_experiment_binding ON mra.experiment_partition"
        )
        connection.execute("DROP FUNCTION mra.wp11q_fail_experiment_binding()")
        connection.commit()
    assert partial == (0, 0)
    experiment_commands.register(definition, bindings, experiment_context)
    experiment_run_id = uuid4()
    experiment_commands.open_run(
        ExperimentRunPlan(
            experiment_run_id=experiment_run_id,
            experiment_id=definition.experiment_id,
            experiment_partition_id=bindings[0].experiment_partition_id,
            run_identity="wp11-mid-failure-run",
        ),
        _wp11_context("open-mid-failure-run", "OPEN_EXPERIMENT_RUN"),
    )
    source_metric = target.metrics[0]
    protocol = EvaluationProtocolPlan(
        evaluation_protocol_id=uuid4(),
        protocol_code=f"wp11-mid-failure-{uuid4().hex[:8]}",
        protocol_version=1,
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        applicable_purpose=PartitionPurpose.VALIDATION,
        decision_rule="Retain every frozen member.",
        metrics=(
            ProtocolMetricDefinition(
                evaluation_protocol_metric_id=uuid4(),
                metric_code="mean-return",
                ordinal=1,
                source_target_metric_definition_id=(
                    source_metric.target_metric_definition_id
                ),
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
        provenance_sha256="3" * 64,
    )
    evaluation_commands = EvaluationCommands(
        PostgresEvaluationUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    evaluation_commands.register_protocol(
        protocol,
        _wp11_context("register-mid-failure-protocol", "REGISTER_EVALUATION_PROTOCOL"),
    )
    evaluation_run_id = uuid4()
    evaluation_commands.open_run(
        EvaluationRunPlan(
            evaluation_run_id=evaluation_run_id,
            experiment_run_id=experiment_run_id,
            evaluation_protocol_id=protocol.evaluation_protocol_id,
            requested_knowledge_cutoff=settled[1][1] + timedelta(microseconds=1),
            request_identity="wp11-mid-failure-evaluation",
            code_artifact=protocol.code_artifact,
            config_artifact=protocol.config_artifact,
            provenance_sha256="2" * 64,
        ),
        _wp11_context("open-mid-failure-evaluation", "OPEN_EVALUATION_RUN"),
    )
    acquisition_context = _wp11_context(
        "mid-observation", "ACQUIRE_OUTCOME_INPUTS"
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION mra.wp11q_fail_evaluation_observation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'injected mid-observation serialization'
                    USING ERRCODE = '40001';
            END;
            $$;
            CREATE TRIGGER wp11q_fail_evaluation_observation
            BEFORE INSERT ON mra.evaluation_observation
            FOR EACH ROW EXECUTE FUNCTION mra.wp11q_fail_evaluation_observation();
            """
        )
        connection.commit()
    with pytest.raises(ResearchRetryableTransactionError):
        evaluation_commands.acquire_outcome_inputs(
            evaluation_run_id, acquisition_context
        )
    with psycopg.connect(stack.database_url) as connection:
        partial = connection.execute(
            """
            SELECT run.status,
              (SELECT count(*) FROM mra.research_partition_outcome_access
               WHERE evaluation_run_id = run.evaluation_run_id),
              (SELECT count(*) FROM mra.evaluation_observation
               WHERE evaluation_run_id = run.evaluation_run_id)
            FROM mra.evaluation_run AS run
            WHERE run.evaluation_run_id = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
        connection.execute(
            "DROP TRIGGER wp11q_fail_evaluation_observation ON mra.evaluation_observation"
        )
        connection.execute("DROP FUNCTION mra.wp11q_fail_evaluation_observation()")
        connection.commit()
    assert partial == ("OPEN", 0, 0)
    evaluation_commands.acquire_outcome_inputs(
        evaluation_run_id, acquisition_context
    )

    completion_context = _wp11_context(
        "mid-metric-cartesian", "COMPLETE_EVALUATION_RUN"
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION mra.wp11q_fail_metric_observation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'injected mid-metric serialization'
                    USING ERRCODE = '40001';
            END;
            $$;
            CREATE TRIGGER wp11q_fail_metric_observation
            BEFORE INSERT ON mra.evaluation_metric_observation
            FOR EACH ROW EXECUTE FUNCTION mra.wp11q_fail_metric_observation();
            """
        )
        connection.commit()
    with pytest.raises(ResearchRetryableTransactionError):
        evaluation_commands.complete(evaluation_run_id, completion_context)
    with psycopg.connect(stack.database_url) as connection:
        partial = connection.execute(
            """
            SELECT run.status,
              (SELECT count(*) FROM mra.evaluation_metric
               WHERE evaluation_run_id = run.evaluation_run_id),
              (SELECT count(*) FROM mra.evaluation_metric_observation
               WHERE evaluation_run_id = run.evaluation_run_id)
            FROM mra.evaluation_run AS run
            WHERE run.evaluation_run_id = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
        connection.execute(
            "DROP TRIGGER wp11q_fail_metric_observation ON mra.evaluation_metric_observation"
        )
        connection.execute("DROP FUNCTION mra.wp11q_fail_metric_observation()")
        connection.commit()
    assert partial == ("INPUTS_ACQUIRED", 0, 0)
    completed = evaluation_commands.complete(
        evaluation_run_id, completion_context
    )
    assert completed.count == 1


def test_failure_recorder_failure_cannot_resurrect_rolled_back_partition(
    wp11_stack,
    monkeypatch,
) -> None:
    stack = wp11_stack
    target, _, _, _ = _settle_two_visible_revisions(stack)
    plan = replace(
        _partition_plan(
            stack, target, code=f"wp11-failure-recorder-{uuid4().hex[:8]}"
        ),
        exchange_code="XSHE",
    )
    commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(stack.pool, id_factory=uuid4),
        id_factory=uuid4,
    )

    def fail_recorder(*_args, **_kwargs):
        raise RuntimeError("injected WP-11 failure-recorder failure")

    monkeypatch.setattr(commands._failure_recorder, "record", fail_recorder)
    context = _wp11_context("failure-recorder", "FREEZE_RESEARCH_PARTITION")
    with pytest.raises(RuntimeError, match="failure-recorder failure"):
        commands.freeze(plan, context)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.research_partition
               WHERE research_partition_id = %s),
              (SELECT count(*) FROM mra.command_receipt
               WHERE idempotency_key = %s),
              (SELECT count(*) FROM mra.audit_event
               WHERE aggregate_id = %s)
            """,
            (
                plan.research_partition_id,
                context.idempotency_key,
                str(plan.research_partition_id),
            ),
        ).fetchone()
    assert counts == (0, 0, 0)


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


def test_evaluation_run_rejects_a_future_knowledge_cutoff(wp11_stack) -> None:
    stack = wp11_stack
    target, _, _, _ = _settle_two_visible_revisions(stack)
    commands, _, experiment_run_id, protocol = _freeze_and_predeclare(stack, target)

    with pytest.raises(RuntimeStateConflictError, match="Evaluation"):
        commands.open_run(
            EvaluationRunPlan(
                evaluation_run_id=uuid4(),
                experiment_run_id=experiment_run_id,
                evaluation_protocol_id=protocol.evaluation_protocol_id,
                requested_knowledge_cutoff=datetime.now(UTC) + timedelta(days=1),
                request_identity="future-knowledge-cutoff",
                code_artifact=protocol.code_artifact,
                config_artifact=protocol.config_artifact,
                provenance_sha256="8" * 64,
            ),
            _wp11_context("open-future-cutoff", "OPEN_EVALUATION_RUN"),
        )


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
            exchange_code="XSHG",
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


def _plan_index_names(node: dict) -> set[str]:
    names = {str(node["Index Name"])} if "Index Name" in node else set()
    for child in node.get("Plans", ()):
        names.update(_plan_index_names(child))
    return names


def test_wp11_core_queries_have_bounded_fk_leading_plans(wp11_stack) -> None:
    stack = wp11_stack
    target, _, _, settled = _settle_two_visible_revisions(stack)
    commands, partition, experiment_run_id, protocol = _freeze_and_predeclare(
        stack, target
    )
    cutoff = settled[1][1] + timedelta(microseconds=1)
    evaluation_run_id, _, _ = _run_evaluation(
        commands,
        experiment_run_id,
        protocol,
        cutoff,
        "query-plans",
    )

    with psycopg.connect(stack.database_url) as connection:
        scope = connection.execute(
            """
            SELECT exchange_code, decision_start_date, decision_end_date,
                   protected_start_date, protected_end_date
            FROM mra.research_partition
            WHERE research_partition_id = %s
            """,
            (partition.research_partition_id,),
        ).fetchone()
        member = connection.execute(
            """
            SELECT research_partition_member_id, commitment_id
            FROM mra.research_partition_member
            WHERE research_partition_id = %s
            """,
            (partition.research_partition_id,),
        ).fetchone()
        assert scope is not None and member is not None
        connection.execute("SET LOCAL enable_seqscan = off")
        plans = {
            "commitment_partition_roster": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT commitment.commitment_id
                FROM mra.decision_target_commitment AS commitment
                JOIN mra.decision_reference_observation AS reference
                  ON reference.decision_reference_observation_id =
                     commitment.decision_reference_observation_id
                JOIN mra.trading_session AS decision_session
                  ON decision_session.session_id = reference.session_id
                WHERE commitment.target_definition_id = %s
                  AND decision_session.exchange = %s
                  AND decision_session.session_date BETWEEN %s AND %s
                ORDER BY commitment.commitment_id
                """,
                (target.target_definition_id, scope[0], scope[1], scope[2]),
            ).fetchone()[0][0],
            "protected_overlap": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT research_partition_id
                FROM mra.research_partition
                WHERE target_definition_id = %s
                  AND exchange_code = %s
                  AND overlap_policy <> 'DIAGNOSTIC_REUSE'
                  AND daterange(
                        protected_start_date, protected_end_date, '[]'
                      ) && daterange(%s, %s, '[]')
                """,
                (target.target_definition_id, scope[0], scope[3], scope[4]),
            ).fetchone()[0][0],
            "cutoff_visible_outcome_revision": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                WITH eligible AS (
                    SELECT revision.*
                    FROM mra.market_target_outcome_revision AS revision
                    WHERE revision.commitment_id = %s
                      AND revision.target_definition_id = %s
                      AND revision.observation_cutoff <= %s
                      AND revision.knowledge_cutoff <= %s
                      AND revision.settled_at <= %s
                )
                SELECT eligible.market_target_outcome_revision_id
                FROM eligible
                WHERE NOT EXISTS (
                    SELECT 1 FROM eligible AS successor
                    WHERE successor.supersedes_revision_id =
                          eligible.market_target_outcome_revision_id
                )
                """,
                (member[1], target.target_definition_id, cutoff, cutoff, cutoff),
            ).fetchone()[0][0],
            "member_access_ordinal": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT coalesce(max(access_ordinal), 0) + 1
                FROM mra.research_partition_outcome_access
                WHERE research_partition_member_id = %s
                """,
                (member[0],),
            ).fetchone()[0][0],
            "observation_exact_outcome_metric": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT source.market_target_outcome_metric_id
                FROM mra.evaluation_observation AS observation
                JOIN mra.evaluation_protocol_metric AS protocol_metric
                  ON protocol_metric.evaluation_protocol_id = %s
                JOIN mra.market_target_outcome_metric AS source
                  ON source.market_target_outcome_revision_id =
                     observation.market_target_outcome_revision_id
                 AND source.target_metric_definition_id =
                     protocol_metric.source_target_metric_definition_id
                WHERE observation.evaluation_run_id = %s
                """,
                (protocol.evaluation_protocol_id, evaluation_run_id),
            ).fetchone()[0][0],
            "metric_member_cartesian": connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT metric.evaluation_metric_id,
                       observation.research_partition_member_id,
                       input.evaluation_metric_observation_id
                FROM mra.evaluation_metric AS metric
                CROSS JOIN mra.evaluation_observation AS observation
                LEFT JOIN mra.evaluation_metric_observation AS input
                  ON input.evaluation_metric_id = metric.evaluation_metric_id
                 AND input.evaluation_observation_id =
                     observation.evaluation_observation_id
                WHERE metric.evaluation_run_id = %s
                  AND observation.evaluation_run_id = %s
                """,
                (evaluation_run_id, evaluation_run_id),
            ).fetchone()[0][0],
        }

    expected_index_groups = {
        "commitment_partition_roster": (
            {"decision_commitment_target_idx"},
        ),
        "protected_overlap": (
            {
                "research_partition_target_window_idx",
                "research_partition_target_fk_idx",
            },
        ),
        "cutoff_visible_outcome_revision": (
            {"outcome_revision_request_idx"},
        ),
        "member_access_ordinal": (
            {
                "research_outcome_access_member_ordinal_uk",
                "research_outcome_access_member_fk_idx",
            },
        ),
        "observation_exact_outcome_metric": (
            {
                "evaluation_observation_run_member_uk",
                "evaluation_observation_access_fk_idx",
            },
            {
                "outcome_metric_revision_idx",
                "outcome_metric_definition_idx",
                "outcome_metric_definition_authority_idx",
            },
        ),
        "metric_member_cartesian": (
            {
                "evaluation_metric_run_protocol_metric_uk",
                "evaluation_metric_run_fk_idx",
            },
            {"evaluation_observation_run_member_uk"},
            {
                "evaluation_metric_observation_matrix_uk",
                "evaluation_metric_observation_observation_fk_idx",
            },
        ),
    }
    for label, explanation in plans.items():
        plan = explanation["Plan"]
        names = _plan_index_names(plan)
        for alternatives in expected_index_groups[label]:
            assert alternatives & names, (label, alternatives, names, plan)
        assert int(plan["Actual Rows"]) <= 1, (label, plan)
        assert float(explanation["Execution Time"]) < 100.0, (label, explanation)
