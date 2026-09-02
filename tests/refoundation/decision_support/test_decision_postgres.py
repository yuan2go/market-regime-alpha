from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import time
from threading import Barrier
from uuid import UUID

import psycopg
import pytest

from market_regime_alpha.decision_support.application import (
    DecisionRunVerifier,
    DecisionSupportApplication,
)
from market_regime_alpha.decision_support.domain import (
    DecisionRunMismatchKind,
    OpenDecisionRunRequest,
    ResearchPurpose,
    RequestedDecisionTarget,
)
from market_regime_alpha.decision_support.errors import (
    DecisionAuthorityIntegrityError,
    DecisionReferenceResolutionError,
)
from market_regime_alpha.infrastructure.postgres.decision_uow import (
    PostgresDecisionSupportUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_inputs import (
    PostgresDecisionInputPreparationProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_runs import (
    PostgresDecisionRunQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_verification import (
    PostgresDecisionRunVerificationProvider,
)
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.research_qualification.domain.target_vocabulary import (
    TargetValueField,
)
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    StaleFenceError,
)
from market_regime_alpha.shared.errors import ConflictError
from tests.refoundation.research_qualification import (
    test_research_postgres as _research,
)
from tests.refoundation.research_qualification.test_target_domain import valid_target
from tests.refoundation.selection import (
    test_candidate_vertical_slice_postgres as _candidate,
)
from tests.refoundation.selection import (
    test_candidate_repository_postgres as _candidate_repository,
)


@pytest.fixture
def candidate_vertical_stack(target_database_url, tmp_path, request):
    return _research.dataset_stack.__wrapped__(
        target_database_url,
        tmp_path,
        request,
    )


def _binding(record: object) -> ArtifactBinding:
    return ArtifactBinding(
        artifact_id=record.artifact_id,  # type: ignore[attr-defined]
        content_sha256=record.content_sha256,  # type: ignore[attr-defined]
        size_bytes=record.size_bytes,  # type: ignore[attr-defined]
    )


def _register_target(
    stack: object,
    *,
    reference_local_time: time = time(14, 55),
):
    code = stack.artifacts.publish(  # type: ignore[attr-defined]
        b"def simple_return(reference, observation): return observation / reference - 1\n",
        media_type="text/plain",
        context=_research._context("decision-target-code", "REGISTER_TARGET_CODE"),
    )
    config = stack.artifacts.publish(  # type: ignore[attr-defined]
        b'{"reference":"14:55","outcome":"T+1 10:30"}\n',
        media_type="application/json",
        context=_research._context("decision-target-config", "REGISTER_TARGET_CONFIG"),
    )
    definition = valid_target()
    reference_checkpoint = replace(
        definition.checkpoints[0],
        checkpoint_code=(
            f"decision_reference_{reference_local_time.hour:02d}"
            f"{reference_local_time.minute:02d}"
        ),
        local_time=reference_local_time,
    )
    definition = replace(
        definition,
        checkpoints=(reference_checkpoint, definition.checkpoints[1]),
    )
    algorithm = replace(
        definition.algorithm,
        code_artifact=_binding(code),
        config_artifact=_binding(config),
    )
    definition = replace(
        definition,
        algorithm=algorithm,
        metrics=tuple(
            replace(metric, algorithm=algorithm) for metric in definition.metrics
        ),
    )
    stack.research.register_target_definition(  # type: ignore[attr-defined]
        definition,
        _research._context("decision-register-target", "REGISTER_TARGET_DEFINITION"),
    )
    return definition


def _register_second_target(stack: object):
    code = stack.artifacts.publish(  # type: ignore[attr-defined]
        b"def open_return(reference, observation): return observation / reference - 1\n",
        media_type="text/plain",
        context=_research._context(
            "decision-target-code-second",
            "REGISTER_TARGET_CODE",
        ),
    )
    config = stack.artifacts.publish(  # type: ignore[attr-defined]
        b'{"reference":"14:55","value_field":"OPEN"}\n',
        media_type="application/json",
        context=_research._context(
            "decision-target-config-second",
            "REGISTER_TARGET_CONFIG",
        ),
    )
    original = valid_target()
    target_id = UUID("00000000-0000-4000-8000-000000009201")
    checkpoint_ids = {
        item.target_checkpoint_id: UUID(
            f"00000000-0000-4000-8000-0000000092{index:02d}"
        )
        for index, item in enumerate(original.checkpoints, start=2)
    }
    metric_ids = {
        item.target_metric_definition_id: UUID(
            f"00000000-0000-4000-8000-0000000093{index:02d}"
        )
        for index, item in enumerate(original.metrics, start=1)
    }
    algorithm = replace(
        original.algorithm,
        algorithm_code="open_return",
        code_artifact=_binding(code),
        config_artifact=_binding(config),
    )
    checkpoints = tuple(
        replace(
            item,
            target_checkpoint_id=checkpoint_ids[item.target_checkpoint_id],
            target_definition_id=target_id,
            value_field=(
                TargetValueField.OPEN if item.ordinal == 1 else item.value_field
            ),
        )
        for item in original.checkpoints
    )
    metrics = tuple(
        replace(
            item,
            target_metric_definition_id=metric_ids[
                item.target_metric_definition_id
            ],
            target_definition_id=target_id,
            algorithm=algorithm,
        )
        for item in original.metrics
    )
    dependencies = tuple(
        replace(
            item,
            target_metric_dependency_id=UUID(
                f"00000000-0000-4000-8000-0000000094{index:02d}"
            ),
            target_definition_id=target_id,
            target_metric_definition_id=metric_ids[
                item.target_metric_definition_id
            ],
            target_checkpoint_id=checkpoint_ids[item.target_checkpoint_id],
        )
        for index, item in enumerate(original.dependencies, start=1)
    )
    definition = replace(
        original,
        target_definition_id=target_id,
        target_code="mr1_next_session_open_return",
        algorithm=algorithm,
        checkpoints=checkpoints,
        metrics=metrics,
        dependencies=dependencies,
    )
    stack.research.register_target_definition(  # type: ignore[attr-defined]
        definition,
        _research._context(
            "decision-register-target-second",
            "REGISTER_TARGET_DEFINITION",
        ),
    )
    return definition


def _application(stack: object) -> DecisionSupportApplication:
    pool = stack.pool  # type: ignore[attr-defined]
    return DecisionSupportApplication(
        PostgresDecisionInputPreparationProvider(pool),
        PostgresDecisionSupportUnitOfWorkProvider(pool),
        PostgresDecisionRunQueryProvider(pool),
    )


class _BarrierPreparation:
    def __init__(self, delegate, barrier: Barrier) -> None:
        self._delegate = delegate
        self._barrier = barrier

    def prepare(self, request, runtime_claim):
        prepared = self._delegate.prepare(request, runtime_claim)
        self._barrier.wait(timeout=10)
        return prepared


def _insert_exact_source_gap(stack: object) -> UUID:
    source_gap_id = UUID("00000000-0000-4000-8000-000000009099")
    with psycopg.connect(stack.database_url) as connection:  # type: ignore[attr-defined]
        inserted = connection.execute(
            """
            INSERT INTO mra.source_gap (
                gap_id, provider_product_id, capture_id, instrument_id,
                session_id, instrument_code, identifier_scheme,
                identifier_value, exchange, session_date,
                classification_scheme, classification_code, action_key,
                gap_kind, reason_code, fact_kind, instrument_fact_kind,
                evidence_scope, timeframe, price_basis, event_start,
                event_end, effective_from, effective_to, detail,
                recorded_at, known_at, decision_visible_at
            )
            SELECT %s, bar.provider_product_id, bar.capture_id,
                   bar.instrument_id, bar.session_id,
                   NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                   'MISSING', 'EXACT_BAR_MISSING', 'MARKET_BAR',
                   NULL, NULL, bar.timeframe, bar.price_basis,
                   bar.event_start - interval '5 minutes',
                   bar.event_start, NULL, NULL,
                   'fixture exact Decision reference gap',
                   bar.recorded_at, bar.known_at, bar.known_at
            FROM mra.market_bar_revision AS bar
            WHERE bar.bar_revision_id = %s
            RETURNING gap_id
            """,
            (source_gap_id, stack.market_bar_revision_id),  # type: ignore[attr-defined]
        ).fetchone()
    assert inserted == (source_gap_id,)
    return source_gap_id


def _build_candidate_for_decision(stack: object, *, key_prefix: str):
    ready = _candidate._ready_candidate(stack, key_prefix=key_prefix)
    runtime, run_id = _candidate._schedule_run(
        stack,
        steps=(
            _candidate._step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="7",
            ),
            _candidate._step(
                key="open-decision-run",
                kind="OPEN_DECISION_RUN",
                ordinal=2,
                request_character="8",
            ),
            _candidate._step(
                key="assess-context",
                kind="ASSESS_CONTEXT",
                ordinal=3,
                request_character="9",
            ),
        ),
        canonical_decision_time=stack.decision_time,  # type: ignore[attr-defined]
    )
    built = ready.application.build_candidate_set(
        ready.policy.candidate_policy_id,
        ready.dataset.dataset_id,
        _research._context(f"{key_prefix}-build", "BUILD_CANDIDATE_SET"),
        runtime_claim=_candidate._claim(runtime, step_key="build-candidate-set"),
    )
    claim = _candidate._claim(runtime, step_key="open-decision-run")
    return runtime, run_id, built, claim


def _open_default_decision(stack: object, *, key_prefix: str):
    target = _register_target(stack)
    runtime, run_id, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix=key_prefix,
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=(
                    stack.product.provider_product_id  # type: ignore[attr-defined]
                ),
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )
    result = _application(stack).open_decision_run(
        request,
        _research._context(f"{key_prefix}-open", "OPEN_DECISION_RUN"),
        runtime_claim=claim,
    )
    return runtime, run_id, result


def _index_names(node: dict) -> set[str]:
    names = {str(node["Index Name"])} if "Index Name" in node else set()
    for child in node.get("Plans", ()):
        names.update(_index_names(child))
    return names


def test_open_decision_run_closes_real_cross_product_and_replays_exactly(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    ready = _candidate._ready_candidate(stack, key_prefix="decision-open")
    target = _register_target(stack)
    steps = (
        _candidate._step(
            key="build-candidate-set",
            kind="BUILD_CANDIDATE_SET",
            ordinal=1,
            request_character="1",
        ),
        _candidate._step(
            key="open-decision-run",
            kind="OPEN_DECISION_RUN",
            ordinal=2,
            request_character="2",
        ),
        _candidate._step(
            key="assess-context",
            kind="ASSESS_CONTEXT",
            ordinal=3,
            request_character="3",
        ),
    )
    runtime, run_id = _candidate._schedule_run(
        stack,
        steps=steps,
        canonical_decision_time=stack.decision_time,
    )
    built = ready.application.build_candidate_set(
        ready.policy.candidate_policy_id,
        ready.dataset.dataset_id,
        _research._context("decision-build-candidates", "BUILD_CANDIDATE_SET"),
        runtime_claim=_candidate._claim(runtime, step_key="build-candidate-set"),
    )
    candidate_set_id = UUID(built.aggregate_id)
    open_claim = _candidate._claim(runtime, step_key="open-decision-run")
    request = OpenDecisionRunRequest(
        candidate_set_id=candidate_set_id,
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )
    context = _research._context("decision-open-command", "OPEN_DECISION_RUN")
    application = _application(stack)

    first = application.open_decision_run(
        request,
        context,
        runtime_claim=open_claim,
    )
    replay = application.open_decision_run(
        request,
        context,
        runtime_claim=open_claim,
    )

    assert first.replayed is False
    assert replay == first.as_replay()
    assert (first.candidate_count, first.target_count) == (1, 1)
    assert (first.commitment_count, first.reference_count) == (1, 1)
    persisted = PostgresDecisionRunQueryProvider(stack.pool).load(
        first.decision_run_id
    )
    assert persisted.authority.definition_summary_sha256 == (
        first.definition_summary_sha256
    )
    reference = persisted.authority.commitments[0].reference.prepared
    assert reference.bar_revision_id == stack.market_bar_revision_id
    assert reference.source_gap_id is None
    assert reference.decimal_value is not None
    assert reference.known_at <= persisted.authority.runtime.decision_time
    verification = DecisionRunVerifier(
        PostgresDecisionRunVerificationProvider(stack.pool)
    ).verify(first.decision_run_id)
    assert verification.matched is True
    assert verification.mismatch_count == 0

    trace = runtime.inspect_run(run_id)
    assert tuple(step.state for step in trace.steps) == (
        "SUCCEEDED",
        "SUCCEEDED",
        "READY",
    )
    assert trace.steps[2].step_key == "assess-context"

    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.decision_run),
              (SELECT count(*) FROM mra.decision_run_target),
              (SELECT count(*) FROM mra.decision_target_commitment),
              (SELECT count(*) FROM mra.decision_reference_observation),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'OPEN_DECISION_RUN'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'OPEN_DECISION_RUN')
            """
        ).fetchone()
    assert counts == (1, 1, 1, 1, 1, 1)


def test_ordered_multi_target_roster_closes_full_relational_cross_product(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    first_target = _register_target(stack)
    second_target = _register_second_target(stack)
    _, _, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix="decision-multi-target",
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=tuple(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            )
            for target in (second_target, first_target)
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )

    result = _application(stack).open_decision_run(
        request,
        _research._context("decision-multi-target-open", "OPEN_DECISION_RUN"),
        runtime_claim=claim,
    )

    persisted = PostgresDecisionRunQueryProvider(stack.pool).load(
        result.decision_run_id
    )
    assert (result.candidate_count, result.target_count) == (1, 2)
    assert (result.commitment_count, result.reference_count) == (2, 2)
    assert tuple(item.ordinal for item in persisted.authority.targets) == (1, 2)
    assert tuple(
        item.target.target_definition_id for item in persisted.authority.targets
    ) == (
        second_target.target_definition_id,
        first_target.target_definition_id,
    )
    assert {
        item.target_definition_id for item in persisted.authority.commitments
    } == {
        first_target.target_definition_id,
        second_target.target_definition_id,
    }
    assert all(
        item.reference.prepared.bar_revision_id == stack.market_bar_revision_id
        for item in persisted.authority.commitments
    )
    verification = DecisionRunVerifier(
        PostgresDecisionRunVerificationProvider(stack.pool)
    ).verify(result.decision_run_id)
    assert verification.matched is True
    assert verification.mismatch_count == 0


def test_open_decision_run_freezes_exact_source_gap_without_value_fallback(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    source_gap_id = _insert_exact_source_gap(stack)
    target = _register_target(stack, reference_local_time=time(14, 50))
    _, _, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix="decision-gap",
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )

    result = _application(stack).open_decision_run(
        request,
        _research._context("decision-gap-open", "OPEN_DECISION_RUN"),
        runtime_claim=claim,
    )

    persisted = PostgresDecisionRunQueryProvider(stack.pool).load(
        result.decision_run_id
    )
    reference = persisted.authority.commitments[0].reference.prepared
    assert reference.source_gap_id == source_gap_id
    assert reference.bar_revision_id is None
    assert reference.decimal_value is None
    assert reference.source_gap_kind == "MISSING"
    assert reference.source_gap_reason_code == "EXACT_BAR_MISSING"
    assert reference.value_status.value == "UNAVAILABLE"
    assert reference.availability_status.value == "UNAVAILABLE"
    assert reference.finality_status.value == "UNKNOWN"
    assert reference.known_at <= persisted.authority.runtime.decision_time
    verification = DecisionRunVerifier(
        PostgresDecisionRunVerificationProvider(stack.pool)
    ).verify(result.decision_run_id)
    assert verification.matched is True
    assert verification.mismatch_count == 0


def test_open_decision_run_closes_empty_candidate_set_with_non_empty_target_roster(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    feature = _candidate_repository._feature(
        stack.artifacts,
        key_prefix="decision-empty-feature",
    )
    stack.research.register_feature_definition(
        feature,
        _research._context(
            "decision-empty-feature",
            "REGISTER_FEATURE_DEFINITION",
        ),
    )
    policy = _candidate_repository._policy(stack, feature=feature)
    candidate_application = _candidate._candidate_application(stack)
    candidate_application.register_candidate_policy(
        policy,
        _research._context(
            "decision-empty-policy",
            "REGISTER_CANDIDATE_POLICY",
        ),
    )
    dataset = _candidate_repository._seed_empty_dataset(stack, feature=feature)
    target = _register_target(stack)
    runtime, _ = _candidate._schedule_run(
        stack,
        steps=(
            _candidate._step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="a",
            ),
            _candidate._step(
                key="open-decision-run",
                kind="OPEN_DECISION_RUN",
                ordinal=2,
                request_character="b",
            ),
            _candidate._step(
                key="assess-context",
                kind="ASSESS_CONTEXT",
                ordinal=3,
                request_character="c",
            ),
        ),
        canonical_decision_time=stack.decision_time,
    )
    built = candidate_application.build_candidate_set(
        policy.candidate_policy_id,
        dataset.dataset_id,
        _research._context(
            "decision-empty-build",
            "BUILD_CANDIDATE_SET",
        ),
        runtime_claim=_candidate._claim(runtime, step_key="build-candidate-set"),
    )
    result = _application(stack).open_decision_run(
        OpenDecisionRunRequest(
            candidate_set_id=UUID(built.aggregate_id),
            targets=(
                RequestedDecisionTarget(
                    target_definition_id=target.target_definition_id,
                    reference_provider_product_id=(
                        stack.product.provider_product_id
                    ),
                ),
            ),
            research_purpose=ResearchPurpose.DISCOVERY,
            research_qualifications=(),
        ),
        _research._context("decision-empty-open", "OPEN_DECISION_RUN"),
        runtime_claim=_candidate._claim(runtime, step_key="open-decision-run"),
    )

    assert (result.candidate_count, result.target_count) == (0, 1)
    assert (result.commitment_count, result.reference_count) == (0, 0)
    verification = DecisionRunVerifier(
        PostgresDecisionRunVerificationProvider(stack.pool)
    ).verify(result.decision_run_id)
    assert verification.matched is True
    assert verification.mismatch_count == 0
    trace = runtime.inspect_run(result.runtime_run_id)
    assert tuple(step.state for step in trace.steps) == (
        "SUCCEEDED",
        "SUCCEEDED",
        "READY",
    )
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.decision_run_target),
              (SELECT count(*) FROM mra.decision_target_commitment),
              (SELECT count(*) FROM mra.decision_reference_observation)
            """
        ).fetchone()
    assert counts == (1, 0, 0)


def test_missing_exact_reference_rolls_back_authority_and_records_fenced_failure(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    target = _register_target(stack, reference_local_time=time(14, 45))
    runtime, _, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix="decision-missing-reference",
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )

    with pytest.raises(
        DecisionReferenceResolutionError,
        match="neither an exact bar revision nor an exact SourceGap",
    ):
        _application(stack).open_decision_run(
            request,
            _research._context(
                "decision-missing-reference-open",
                "OPEN_DECISION_RUN",
            ),
            runtime_claim=claim,
        )

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "FAILED"
    assert tuple(step.state for step in trace.steps) == (
        "SUCCEEDED",
        "FAILED",
        "PENDING",
    )
    assert trace.steps[1].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.decision_run),
              (SELECT count(*) FROM mra.decision_run_target),
              (SELECT count(*) FROM mra.decision_target_commitment),
              (SELECT count(*) FROM mra.decision_reference_observation),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'OPEN_DECISION_RUN'
                 AND status = 'FAILED'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'OPEN_DECISION_RUN_FAILED')
            """
        ).fetchone()
    assert counts == (0, 0, 0, 0, 1, 1)


def test_failure_recording_failure_rolls_back_incident_and_leaves_runtime_recoverable(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    target = _register_target(stack, reference_local_time=time(14, 45))
    runtime, _, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix="decision-failure-recording-failure",
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION mra.fail_wp09_failure_audit()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.action = 'OPEN_DECISION_RUN_FAILED' THEN
                    RAISE EXCEPTION 'injected failure-recording failure'
                      USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER wp09_injected_failure_audit
            BEFORE INSERT ON mra.audit_event
            FOR EACH ROW EXECUTE FUNCTION mra.fail_wp09_failure_audit()
            """
        )
    request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )

    try:
        with pytest.raises(DecisionAuthorityIntegrityError):
            _application(stack).open_decision_run(
                request,
                _research._context(
                    "decision-failure-recording-failure-open",
                    "OPEN_DECISION_RUN",
                ),
                runtime_claim=claim,
            )
    finally:
        with psycopg.connect(stack.database_url) as connection:
            connection.execute(
                "DROP TRIGGER wp09_injected_failure_audit ON mra.audit_event"
            )
            connection.execute("DROP FUNCTION mra.fail_wp09_failure_audit()")

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "RUNNING"
    assert tuple(step.state for step in trace.steps) == (
        "SUCCEEDED",
        "RUNNING",
        "PENDING",
    )
    assert trace.steps[1].attempt_states == ("RUNNING",)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.decision_run),
              (SELECT count(*) FROM mra.decision_run_target),
              (SELECT count(*) FROM mra.decision_target_commitment),
              (SELECT count(*) FROM mra.decision_reference_observation),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind LIKE 'OPEN_DECISION_RUN%'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action LIKE 'OPEN_DECISION_RUN%')
            """
        ).fetchone()
    assert counts == (0, 0, 0, 0, 0, 0)


def test_mid_write_database_failure_rolls_back_partial_roster_before_failure_record(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    target = _register_target(stack)
    runtime, _, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix="decision-mid-write-failure",
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION mra.fail_wp09_commitment_insert()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'injected Decision commitment failure'
                  USING ERRCODE = '55000';
            END;
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER wp09_injected_commitment_failure
            BEFORE INSERT ON mra.decision_target_commitment
            FOR EACH ROW EXECUTE FUNCTION mra.fail_wp09_commitment_insert()
            """
        )
    request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )

    with pytest.raises(DecisionAuthorityIntegrityError):
        _application(stack).open_decision_run(
            request,
            _research._context(
                "decision-mid-write-failure-open",
                "OPEN_DECISION_RUN",
            ),
            runtime_claim=claim,
        )

    trace = runtime.inspect_run(claim.run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[1].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.decision_run),
              (SELECT count(*) FROM mra.decision_run_target),
              (SELECT count(*) FROM mra.decision_target_commitment),
              (SELECT count(*) FROM mra.decision_reference_observation),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'OPEN_DECISION_RUN'
                 AND status = 'FAILED'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'OPEN_DECISION_RUN_FAILED')
            """
        ).fetchone()
    assert counts == (0, 0, 0, 0, 1, 1)


def test_stale_runtime_fence_produces_zero_decision_and_failure_writes(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    target = _register_target(stack)
    _, _, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix="decision-stale-fence",
    )
    stale_claim = replace(claim, fence_token=claim.fence_token + 1)
    request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )

    with pytest.raises(StaleFenceError):
        _application(stack).open_decision_run(
            request,
            _research._context("decision-stale-open", "OPEN_DECISION_RUN"),
            runtime_claim=stale_claim,
        )

    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.decision_run),
              (SELECT count(*) FROM mra.decision_run_target),
              (SELECT count(*) FROM mra.decision_target_commitment),
              (SELECT count(*) FROM mra.decision_reference_observation),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind LIKE 'OPEN_DECISION_RUN%'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action LIKE 'OPEN_DECISION_RUN%')
            """
        ).fetchone()
    assert counts == (0, 0, 0, 0, 0, 0)


def test_concurrent_identical_open_has_one_canonical_writer_and_exact_replay(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    target = _register_target(stack)
    _, _, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix="decision-concurrent",
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )
    context = _research._context(
        "decision-concurrent-open",
        "OPEN_DECISION_RUN",
    )
    application = DecisionSupportApplication(
        _BarrierPreparation(
            PostgresDecisionInputPreparationProvider(stack.pool),
            Barrier(2),
        ),
        PostgresDecisionSupportUnitOfWorkProvider(stack.pool),
        PostgresDecisionRunQueryProvider(stack.pool),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(
            executor.submit(
                application.open_decision_run,
                request,
                context,
                runtime_claim=claim,
            )
            for _ in range(2)
        )
        results = tuple(future.result(timeout=20) for future in futures)

    assert len({item.decision_run_id for item in results}) == 1
    assert len({item.receipt_id for item in results}) == 1
    assert sorted(item.replayed for item in results) == [False, True]
    assert results[0].as_replay() == results[1].as_replay()
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.decision_run),
              (SELECT count(*) FROM mra.decision_run_target),
              (SELECT count(*) FROM mra.decision_target_commitment),
              (SELECT count(*) FROM mra.decision_reference_observation),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'OPEN_DECISION_RUN'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'OPEN_DECISION_RUN')
            """
        ).fetchone()
    assert counts == (1, 1, 1, 1, 1, 1)


def test_candidate_set_allows_only_one_canonical_decision_run(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    ready = _candidate._ready_candidate(stack, key_prefix="decision-single")
    target = _register_target(stack)
    runtime, _ = _candidate._schedule_run(
        stack,
        steps=(
            _candidate._step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="4",
            ),
            _candidate._step(
                key="open-decision-run",
                kind="OPEN_DECISION_RUN",
                ordinal=2,
                request_character="5",
            ),
            _candidate._step(
                key="assess-context",
                kind="ASSESS_CONTEXT",
                ordinal=3,
                request_character="6",
            ),
        ),
        canonical_decision_time=stack.decision_time,
    )
    built = ready.application.build_candidate_set(
        ready.policy.candidate_policy_id,
        ready.dataset.dataset_id,
        _research._context("decision-single-build", "BUILD_CANDIDATE_SET"),
        runtime_claim=_candidate._claim(runtime, step_key="build-candidate-set"),
    )
    claim = _candidate._claim(runtime, step_key="open-decision-run")
    request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )
    application = _application(stack)
    application.open_decision_run(
        request,
        _research._context("decision-single-open", "OPEN_DECISION_RUN"),
        runtime_claim=claim,
    )

    with pytest.raises(ConflictError):
        application.open_decision_run(
            request,
            _research._context("decision-single-changed", "OPEN_DECISION_RUN"),
            runtime_claim=claim,
        )


def test_same_decision_request_identity_rejects_changed_target_roster_without_new_facts(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    first_target = _register_target(stack)
    second_target = _register_second_target(stack)
    _, _, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix="decision-changed-request",
    )
    context = _research._context(
        "decision-changed-request-open",
        "OPEN_DECISION_RUN",
    )
    application = _application(stack)
    first_request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=(
            RequestedDecisionTarget(
                target_definition_id=first_target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )
    application.open_decision_run(
        first_request,
        context,
        runtime_claim=claim,
    )
    changed_request = replace(
        first_request,
        targets=(
            RequestedDecisionTarget(
                target_definition_id=second_target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
    )

    with pytest.raises(IdempotencyKeyReusedError):
        application.open_decision_run(
            changed_request,
            context,
            runtime_claim=claim,
        )

    with psycopg.connect(stack.database_url) as connection:
        persisted = connection.execute(
            """
            SELECT target_definition_id
            FROM mra.decision_run_target
            ORDER BY ordinal
            """
        ).fetchall()
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.decision_run),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'OPEN_DECISION_RUN'),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'OPEN_DECISION_RUN_REJECTION'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action LIKE 'OPEN_DECISION_RUN%')
            """
        ).fetchone()
    assert persisted == [(first_target.target_definition_id,)]
    assert counts == (1, 1, 0, 1)


def test_concurrent_conflicting_target_rosters_choose_one_canonical_run_and_reject_loser(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    first_target = _register_target(stack)
    second_target = _register_second_target(stack)
    _, _, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix="decision-concurrent-conflict",
    )
    context = _research._context(
        "decision-concurrent-conflict-open",
        "OPEN_DECISION_RUN",
    )
    requests = tuple(
        OpenDecisionRunRequest(
            candidate_set_id=UUID(built.aggregate_id),
            targets=(
                RequestedDecisionTarget(
                    target_definition_id=target.target_definition_id,
                    reference_provider_product_id=stack.product.provider_product_id,
                ),
            ),
            research_purpose=ResearchPurpose.DISCOVERY,
            research_qualifications=(),
        )
        for target in (first_target, second_target)
    )
    application = DecisionSupportApplication(
        _BarrierPreparation(
            PostgresDecisionInputPreparationProvider(stack.pool),
            Barrier(2),
        ),
        PostgresDecisionSupportUnitOfWorkProvider(stack.pool),
        PostgresDecisionRunQueryProvider(stack.pool),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(
            executor.submit(
                application.open_decision_run,
                request,
                context,
                runtime_claim=claim,
            )
            for request in requests
        )
        outcomes: list[object] = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=20))
            except Exception as exc:  # noqa: BLE001 - assert the exact conflict below
                outcomes.append(exc)

    successes = tuple(
        item for item in outcomes if not isinstance(item, Exception)
    )
    conflicts = tuple(
        item for item in outcomes if isinstance(item, Exception)
    )
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert isinstance(conflicts[0], IdempotencyKeyReusedError)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.decision_run),
              (SELECT count(*) FROM mra.decision_run_target),
              (SELECT count(*) FROM mra.decision_target_commitment),
              (SELECT count(*) FROM mra.decision_reference_observation),
              (SELECT count(*) FROM mra.command_receipt
               WHERE command_kind = 'OPEN_DECISION_RUN'),
              (SELECT count(*) FROM mra.audit_event
               WHERE action = 'OPEN_DECISION_RUN')
            """
        ).fetchone()
    assert counts == (1, 1, 1, 1, 1, 1)


def test_reconciliation_reports_missing_count_and_hash_mismatches(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    _, _, result = _open_default_decision(
        stack,
        key_prefix="decision-verify-missing",
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            ALTER TABLE mra.decision_reference_observation
              DROP CONSTRAINT decision_reference_commitment_fk
            """
        )
        connection.execute(
            """
            ALTER TABLE mra.decision_target_commitment
              DROP CONSTRAINT decision_commitment_reference_fk
            """
        )
        connection.execute(
            """
            DROP TRIGGER decision_reference_append_only
              ON mra.decision_reference_observation
            """
        )
        connection.execute(
            """
            DROP TRIGGER decision_commitment_append_only
              ON mra.decision_target_commitment
            """
        )
        connection.execute(
            """
            DELETE FROM mra.decision_reference_observation
            WHERE decision_run_id = %s
            """,
            (result.decision_run_id,),
        )
        connection.execute(
            """
            DELETE FROM mra.decision_target_commitment
            WHERE decision_run_id = %s
            """,
            (result.decision_run_id,),
        )

    verification = DecisionRunVerifier(
        PostgresDecisionRunVerificationProvider(stack.pool)
    ).verify(result.decision_run_id)
    kinds = {item.kind for item in verification.mismatches}
    assert verification.matched is False
    assert DecisionRunMismatchKind.MISSING_ROW in kinds
    assert DecisionRunMismatchKind.COUNT_MISMATCH in kinds
    assert DecisionRunMismatchKind.HASH_MISMATCH in kinds


def test_replay_reports_declared_extra_order_and_immutable_mutation(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    _, _, result = _open_default_decision(
        stack,
        key_prefix="decision-verify-extra",
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute("DROP TRIGGER decision_run_append_only ON mra.decision_run")
        connection.execute(
            """
            ALTER TABLE mra.decision_run
              DROP CONSTRAINT decision_run_counts_ck,
              DROP CONSTRAINT decision_run_definition_summary_ck
            """
        )
        connection.execute(
            """
            UPDATE mra.decision_run
            SET target_count = 0,
                commitment_count = 0,
                reference_count = 0,
                created_by_actor_id = 'mutated-after-closure'
            WHERE decision_run_id = %s
            """,
            (result.decision_run_id,),
        )

    verification = DecisionRunVerifier(
        PostgresDecisionRunVerificationProvider(stack.pool)
    ).verify(result.decision_run_id)
    kinds = {item.kind for item in verification.mismatches}
    assert verification.matched is False
    assert DecisionRunMismatchKind.EXTRA_ROW in kinds
    assert DecisionRunMismatchKind.COUNT_MISMATCH in kinds
    assert DecisionRunMismatchKind.ORDER_MISMATCH in kinds
    assert DecisionRunMismatchKind.IMMUTABLE_FACT_MUTATION in kinds


def test_replay_distinguishes_identity_reference_and_runtime_mismatches(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    _, _, result = _open_default_decision(
        stack,
        key_prefix="decision-verify-scopes",
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute("DROP TRIGGER decision_run_append_only ON mra.decision_run")
        connection.execute(
            """
            ALTER TABLE mra.decision_run
              DROP CONSTRAINT decision_run_runtime_step_fk
            """
        )
        connection.execute(
            """
            UPDATE mra.decision_run
            SET runtime_step_key = 'mutated-open-step'
            WHERE decision_run_id = %s
            """,
            (result.decision_run_id,),
        )
        connection.execute(
            """
            DROP TRIGGER decision_commitment_append_only
              ON mra.decision_target_commitment
            """
        )
        connection.execute(
            """
            ALTER TABLE mra.decision_target_commitment
              DROP CONSTRAINT decision_commitment_candidate_fk,
              DROP CONSTRAINT decision_commitment_content_ck
            """
        )
        connection.execute(
            """
            UPDATE mra.decision_target_commitment
            SET candidate_disposition = 'UNRANKABLE'
            WHERE decision_run_id = %s
            """,
            (result.decision_run_id,),
        )
        connection.execute(
            """
            DROP TRIGGER decision_reference_append_only
              ON mra.decision_reference_observation
            """
        )
        connection.execute(
            """
            ALTER TABLE mra.decision_reference_observation
              DROP CONSTRAINT decision_reference_bar_fk,
              DROP CONSTRAINT decision_reference_known_at_ck,
              DROP CONSTRAINT decision_reference_content_ck
            """
        )
        connection.execute(
            """
            UPDATE mra.decision_reference_observation
            SET known_at = decision_time + interval '1 second'
            WHERE decision_run_id = %s
            """,
            (result.decision_run_id,),
        )

    verification = DecisionRunVerifier(
        PostgresDecisionRunVerificationProvider(stack.pool)
    ).verify(result.decision_run_id)
    kinds = {item.kind for item in verification.mismatches}
    assert verification.matched is False
    assert DecisionRunMismatchKind.IDENTITY_MISMATCH in kinds
    assert DecisionRunMismatchKind.REFERENCE_STATE_MISMATCH in kinds
    assert DecisionRunMismatchKind.RUNTIME_IDENTITY_MISMATCH in kinds
    assert DecisionRunMismatchKind.IMMUTABLE_FACT_MUTATION in kinds


def test_closed_decision_authority_rejects_update_delete_and_late_children(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    _, _, result = _open_default_decision(
        stack,
        key_prefix="decision-immutable",
    )
    identities = {
        "decision_run": ("decision_run_id", result.decision_run_id),
        "decision_run_target": ("decision_run_id", result.decision_run_id),
        "decision_target_commitment": (
            "decision_run_id",
            result.decision_run_id,
        ),
        "decision_reference_observation": (
            "decision_run_id",
            result.decision_run_id,
        ),
    }
    with psycopg.connect(stack.database_url) as connection:
        for table_name, (column_name, identity) in identities.items():
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                connection.execute(
                    f"""
                    UPDATE mra.{table_name}
                    SET created_at = created_at
                    WHERE {column_name} = %s
                    """,
                    (identity,),
                )
            connection.rollback()
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                connection.execute(
                    f"DELETE FROM mra.{table_name} WHERE {column_name} = %s",
                    (identity,),
                )
            connection.rollback()
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """
                INSERT INTO mra.decision_run_target (
                    decision_run_target_id, decision_run_id, ordinal,
                    target_definition_id, target_code, target_version,
                    target_definition_sha256, target_checkpoint_id,
                    target_checkpoint_sha256, target_checkpoint_ordinal,
                    target_checkpoint_role, timeframe, price_basis,
                    value_field, reference_rule, availability_rule,
                    finality_rule, reference_provider_product_id,
                    reference_provider_id, reference_provider_product_code,
                    reference_provider_product_revision,
                    decision_visibility_policy, source_availability_policy,
                    commitment_recorded_at, content_sha256, created_at
                )
                SELECT gen_random_uuid(), decision_run_id, ordinal + 1,
                       target_definition_id, target_code, target_version,
                       target_definition_sha256, target_checkpoint_id,
                       target_checkpoint_sha256, target_checkpoint_ordinal,
                       target_checkpoint_role, timeframe, price_basis,
                       value_field, reference_rule, availability_rule,
                       finality_rule, reference_provider_product_id,
                       reference_provider_id, reference_provider_product_code,
                       reference_provider_product_revision,
                       decision_visibility_policy, source_availability_policy,
                       commitment_recorded_at, content_sha256, created_at
                FROM mra.decision_run_target
                WHERE decision_run_id = %s
                """,
                (result.decision_run_id,),
            )


def test_later_provider_repair_cannot_replace_frozen_decision_reference(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    target = _register_target(stack)
    _, _, built, claim = _build_candidate_for_decision(
        stack,
        key_prefix="decision-provider-repair",
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=UUID(built.aggregate_id),
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=stack.product.provider_product_id,
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )
    context = _research._context(
        "decision-provider-repair-open",
        "OPEN_DECISION_RUN",
    )
    application = _application(stack)
    first = application.open_decision_run(
        request,
        context,
        runtime_claim=claim,
    )
    with psycopg.connect(stack.database_url) as connection:
        window = connection.execute(
            """
            SELECT event_start, event_end
            FROM mra.market_bar_revision
            WHERE bar_revision_id = %s
            """,
            (stack.market_bar_revision_id,),
        ).fetchone()
    assert window is not None
    later_capture = stack.market.capture(
        _research.CaptureRequest(
            provider_product_id=stack.product.provider_product_id,
            capture_key="decision-provider-repair-source",
            resource="fixture://decision-provider-repair-source",
            request_headers_hash="5" * 64,
        ),
        _research._BytesProvider(),
        _research._context(
            "decision-provider-repair-capture",
            "CAPTURE_PROVIDER_RESPONSE",
        ),
    )
    repaired_bar_id = UUID("00000000-0000-4000-8000-000000009098")

    def repaired_batch(capture):
        return _research.NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            bars=(
                _research.MarketBarRevision(
                    bar_revision_id=repaired_bar_id,
                    provider_product_id=stack.product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=stack.instrument_id,
                    session_id=stack.market_session_id,
                    timeframe=_research.BarTimeframe.MINUTE_5,
                    price_basis=_research.PriceBasis.RAW_UNADJUSTED,
                    event_start=window[0],
                    event_end=window[1],
                    revision=2,
                    supersedes_revision_id=stack.market_bar_revision_id,
                    open=_research.Money(_research.Decimal("10.30"), "CNY"),
                    high=_research.Money(_research.Decimal("10.50"), "CNY"),
                    low=_research.Money(_research.Decimal("10.20"), "CNY"),
                    close=_research.Money(_research.Decimal("10.40"), "CNY"),
                    volume=_research.Quantity(
                        _research.Decimal("1100"),
                        _research.QuantityUnit.SHARES,
                    ),
                    turnover=_research.Money(
                        _research.Decimal("11440"),
                        "CNY",
                    ),
                ),
            ),
        )

    repaired = stack.market.normalize(
        later_capture.capture.capture_id,
        _research._Normalizer(repaired_batch),
        _research._context(
            "decision-provider-repair-normalize",
            "NORMALIZE_MARKET_PIT",
        ),
    )
    assert repaired.decision_visible_at.value > stack.decision_time.value

    replay = application.open_decision_run(
        request,
        context,
        runtime_claim=claim,
    )
    persisted = PostgresDecisionRunQueryProvider(stack.pool).load(
        first.decision_run_id
    )
    reference = persisted.authority.commitments[0].reference.prepared
    assert replay == first.as_replay()
    assert reference.bar_revision_id == stack.market_bar_revision_id
    assert reference.bar_revision_id != repaired_bar_id
    assert reference.known_at <= persisted.authority.runtime.decision_time


def test_decision_replay_and_reconciliation_queries_have_bounded_index_plans(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    _, _, result = _open_default_decision(
        stack,
        key_prefix="decision-query-plans",
    )
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            """
            ANALYZE mra.decision_run, mra.decision_run_target,
                    mra.decision_target_commitment,
                    mra.decision_reference_observation
            """
        )
        connection.execute("SET LOCAL enable_seqscan = off")
        plans = (
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT decision_run_id
                FROM mra.decision_run
                WHERE candidate_set_id = %s
                """,
                (result.candidate_set_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT decision_run_target_id
                FROM mra.decision_run_target
                WHERE decision_run_id = %s
                ORDER BY ordinal
                """,
                (result.decision_run_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT commitment_id
                FROM mra.decision_target_commitment
                WHERE decision_run_id = %s
                ORDER BY decision_run_target_id, candidate_id
                """,
                (result.decision_run_id,),
            ).fetchone()[0][0]["Plan"],
            connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT decision_reference_observation_id
                FROM mra.decision_reference_observation
                WHERE decision_run_id = %s
                ORDER BY decision_run_target_id, candidate_id
                """,
                (result.decision_run_id,),
            ).fetchone()[0][0]["Plan"],
        )
    used = set().union(*(_index_names(plan) for plan in plans))
    assert {
        "decision_run_target_replay_idx",
        "decision_commitment_cross_product_idx",
        "decision_reference_replay_idx",
    } <= used
    assert used & {
        "decision_run_candidate_set_uk",
        "decision_run_candidate_set_idx",
        "decision_run_candidate_fk_idx",
        "decision_run_context_authority_uk",
        "decision_run_request_uk",
    }
