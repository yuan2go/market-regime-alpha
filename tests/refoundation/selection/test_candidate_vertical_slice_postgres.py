from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from threading import Barrier, Event, Lock, local
from typing import Any, Callable, cast
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
import pytest

from market_regime_alpha.infrastructure.postgres.candidate_uow import (
    PostgresCandidateUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketDatabaseClock,
)
from market_regime_alpha.infrastructure.postgres.queries import (
    PostgresCandidateQueryProvider,
    PostgresCandidateResearchInputLoader,
)
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
)
from market_regime_alpha.infrastructure.postgres.runtime_finalization import (
    PostgresRuntimeCommandFinalization,
)
from market_regime_alpha.infrastructure.postgres.repositories.candidate import (
    PostgresCandidateRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.candidate_artifacts import (
    PostgresCandidateArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.uow import (
    PostgresUnitOfWorkProvider,
)
from market_regime_alpha.market.domain import (
    EvidenceScope,
    NormalizationBatch,
    SecurityStatus,
    SecurityStatusFactRevision,
)
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.research_qualification.domain import (
    FeatureCellStatus,
    FeatureSourceRequirement,
)
from market_regime_alpha.runtime.application import RuntimeApplication
from market_regime_alpha.runtime.domain import (
    ExternalEffectClass,
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepDependency,
    StepSpec,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.selection.application import CandidateApplication
from market_regime_alpha.selection.domain import (
    CandidateArtifactBinding,
    CandidateFeatureValueType,
    CandidatePolicy,
    CandidatePolicyComponent,
    DesirabilityDirection,
    UniverseDefinition,
    UniverseScopeSpecification,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import DecisionTime
from tests.refoundation.research_qualification import (
    test_research_postgres as _research,
)


UTC = timezone.utc


@pytest.fixture
def candidate_vertical_stack(target_database_url, tmp_path, request):
    return _research.dataset_stack.__wrapped__(
        target_database_url,
        tmp_path,
        request,
    )


@dataclass(frozen=True, slots=True)
class _CandidateReady:
    application: CandidateApplication
    policy: CandidatePolicy
    dataset: Any


class _RecordingResearchInputLoader:
    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.prepare_calls = 0

    def prepare(self, **kwargs: Any) -> Any:
        prepared = self._delegate.prepare(**kwargs)
        self.prepare_calls += 1
        return prepared


class _BarrierAfterPrepareResearchInputLoader:
    def __init__(self, delegate: Any, barrier: Barrier) -> None:
        self._delegate = delegate
        self._barrier = barrier
        self._lock = Lock()
        self.prepare_calls = 0

    def prepare(self, **kwargs: Any) -> Any:
        prepared = self._delegate.prepare(**kwargs)
        with self._lock:
            self.prepare_calls += 1
        self._barrier.wait(timeout=10)
        return prepared


class _HookedCandidateUnitOfWorkProvider:
    def __init__(
        self,
        delegate: Any,
        *,
        before_call: int,
        hook: Callable[[], None],
    ) -> None:
        self._delegate = delegate
        self._before_call = before_call
        self._hook = hook
        self.calls = 0

    def __call__(self, *, read_only: bool = False) -> Any:
        if not read_only:
            self.calls += 1
            if self.calls == self._before_call:
                self._hook()
        return self._delegate(read_only=read_only)


class _BarrierAtFinalBindUnitOfWorkProvider:
    def __init__(self, delegate: Any, barrier: Barrier) -> None:
        self._delegate = delegate
        self._barrier = barrier
        self._local = local()
        self._lock = Lock()
        self.final_bind_calls = 0

    def __call__(self, *, read_only: bool = False) -> Any:
        if not read_only:
            calls = getattr(self._local, "write_calls", 0) + 1
            self._local.write_calls = calls
            if calls == 2:
                with self._lock:
                    self.final_bind_calls += 1
                self._barrier.wait(timeout=10)
        return self._delegate(read_only=read_only)


def _install_test_insert_failure_trigger(stack: Any, *, table: str) -> None:
    if table not in {"candidate", "candidate_score_component"}:
        raise ValueError(f"unsupported Candidate failure table: {table}")
    function_name = f"test_fail_{table}_insert"
    trigger_name = f"test_fail_{table}_insert_trigger"
    with psycopg.connect(stack.database_url) as connection:
        connection.execute(
            sql.SQL(
                """
                CREATE FUNCTION mra.{}()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'injected Candidate atomicity failure'
                        USING ERRCODE = '23514';
                END
                $$
                """
            ).format(sql.Identifier(function_name))
        )
        connection.execute(
            sql.SQL(
                """
                CREATE TRIGGER {}
                AFTER INSERT ON mra.{}
                FOR EACH STATEMENT
                EXECUTE FUNCTION mra.{}()
                """
            ).format(
                sql.Identifier(trigger_name),
                sql.Identifier(table),
                sql.Identifier(function_name),
            )
        )
        connection.commit()


def _candidate_binding(artifact: Any) -> CandidateArtifactBinding:
    return CandidateArtifactBinding(
        artifact_id=artifact.artifact_id,
        content_sha256=artifact.content_sha256,
        size_bytes=artifact.size_bytes,
    )


def _candidate_application(stack: Any) -> CandidateApplication:
    return CandidateApplication(
        PostgresCandidateResearchInputLoader(stack.pool, stack.store),
        PostgresCandidateUnitOfWorkProvider(stack.pool),
    )


def _numeric_feature(stack: Any, *, key_prefix: str) -> Any:
    feature = replace(
        _research._feature(stack.artifacts, key_prefix=key_prefix),
        source_requirements=(FeatureSourceRequirement.INSTRUMENT_FACT_REVISION,),
    )
    stack.research.register_feature_definition(
        feature,
        _research._context(
            f"{key_prefix}-register",
            "REGISTER_FEATURE_DEFINITION",
        ),
    )
    return feature


def _numeric_dataset_definition(
    stack: Any,
    *,
    feature: Any,
    key_prefix: str,
) -> Any:
    definition, payload = _research._dataset_input(
        stack,
        feature,
        key_prefix=key_prefix,
        status=FeatureCellStatus.AVAILABLE,
    )
    rows = cast(list[dict[str, object]], payload["rows"])
    cells = cast(list[dict[str, object]], rows[0]["cells"])
    cells[0]["value"] = "12.5"
    manifest_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    manifest = stack.artifacts.publish(
        manifest_bytes,
        media_type="application/json",
        context=_research._context(
            f"{key_prefix}-numeric-manifest",
            "REGISTER_DATASET_MANIFEST",
        ),
    )
    return replace(
        definition,
        manifest_artifact=_research._binding(manifest),
    )


def _candidate_policy(
    stack: Any,
    *,
    feature: Any,
    key_prefix: str,
) -> CandidatePolicy:
    code = stack.artifacts.publish(
        b"candidate-policy: arithmetic-midrank-v1\n",
        media_type="text/plain",
        context=_research._context(
            f"{key_prefix}-code",
            "REGISTER_CANDIDATE_POLICY_CODE",
        ),
    )
    config = stack.artifacts.publish(
        b'{"missing":"STRICT_COMPLETE_CASE","top_k":1}\n',
        media_type="application/json",
        context=_research._context(
            f"{key_prefix}-config",
            "REGISTER_CANDIDATE_POLICY_CONFIG",
        ),
    )
    policy_id = uuid4()
    return CandidatePolicy(
        candidate_policy_id=policy_id,
        policy_code=key_prefix.replace("-", "_"),
        version=1,
        code_artifact=_candidate_binding(code),
        config_artifact=_candidate_binding(config),
        requested_top_k=1,
        components=(
            CandidatePolicyComponent(
                candidate_policy_component_id=uuid4(),
                candidate_policy_id=policy_id,
                component_code="mean_turnover",
                ordinal=1,
                feature_definition_id=feature.feature_definition_id,
                feature_content_sha256=feature.content_sha256,
                feature_value_type=CandidateFeatureValueType.DECIMAL,
                direction=DesirabilityDirection.HIGHER_IS_BETTER,
                declared_weight=Decimal("1"),
            ),
        ),
    )


def _ready_candidate(stack: Any, *, key_prefix: str) -> _CandidateReady:
    feature = _numeric_feature(stack, key_prefix=f"{key_prefix}-feature")
    dataset = _numeric_dataset_definition(
        stack,
        feature=feature,
        key_prefix=f"{key_prefix}-dataset",
    )
    stack.research.register_dataset(
        dataset,
        _research._context(
            f"{key_prefix}-register-dataset",
            "REGISTER_DATASET",
        ),
    )
    policy = _candidate_policy(
        stack,
        feature=feature,
        key_prefix=f"{key_prefix}-policy",
    )
    application = _candidate_application(stack)
    application.register_candidate_policy(
        policy,
        _research._context(
            f"{key_prefix}-register-policy",
            "REGISTER_CANDIDATE_POLICY",
        ),
    )
    return _CandidateReady(application, policy, dataset)


def _step(
    *,
    key: str,
    kind: str,
    ordinal: int,
    request_character: str,
) -> StepSpec:
    return StepSpec(
        step_key=key,
        step_kind=kind,
        implementation=f"tests.candidate_vertical.{key}",
        implementation_version="1",
        ordinal=ordinal,
        required=True,
        request_hash=request_character * 64,
        input_evidence_hash=None,
        retry_policy=RetryPolicy(
            max_attempts=1,
            backoff=(),
            retryable_codes=frozenset(),
        ),
        external_effect_class=(ExternalEffectClass.CONTENT_PUT if kind == "CAPTURE" else ExternalEffectClass.PURE_READ),
    )


def _schedule_run(
    stack: Any,
    *,
    steps: tuple[StepSpec, ...],
    canonical_decision_time: DecisionTime | None = None,
) -> tuple[RuntimeApplication, UUID]:
    kinds = {step.step_kind for step in steps}
    if "BUILD_CANDIDATE_SET" in kinds and not {
        "OPEN_DECISION_RUN",
        "ASSESS_CONTEXT",
    }.issubset(kinds):
        next_ordinal = max(step.ordinal for step in steps) + 1
        steps = (
            *steps,
            _step(
                key="open-decision-run",
                kind="OPEN_DECISION_RUN",
                ordinal=next_ordinal,
                request_character="e",
            ),
            _step(
                key="assess-context",
                kind="ASSESS_CONTEXT",
                ordinal=next_ordinal + 1,
                request_character="f",
            ),
        )
    runtime = RuntimeApplication(PostgresUnitOfWorkProvider(stack.pool))
    schedule = ScheduleSpec(
        schedule_id=uuid4(),
        schedule_code=f"candidate-vertical-{uuid4().hex[:8]}",
        revision=1,
        runtime_mode=RuntimeMode.SHADOW,
        schedule_expression=None,
        timezone_name="Asia/Shanghai",
        step_catalog_hash="9" * 64,
        enabled=True,
    )
    runtime.create_schedule(
        schedule,
        _research._context(
            f"candidate-schedule-{schedule.schedule_id}",
            "CREATE_RUNTIME_SCHEDULE",
        ),
    )
    config = stack.artifacts.publish(
        b'{"slice":"candidate-test-only"}\n',
        media_type="application/json",
        context=_research._context(
            f"candidate-runtime-config-{schedule.schedule_id}",
            "REGISTER_RUNTIME_CONFIG",
        ),
    )
    run_id = uuid4()
    dependencies = tuple(
        StepDependency(
            predecessor_key=left.step_key,
            successor_key=right.step_key,
        )
        for left, right in zip(steps, steps[1:], strict=False)
    )
    runtime.schedule_run(
        RunSpec(
            run_id=run_id,
            schedule_id=schedule.schedule_id,
            fire_key=f"candidate-run-{uuid4().hex}",
            runtime_mode=RuntimeMode.SHADOW,
            requested_at=datetime.now(UTC),
            decision_time=(canonical_decision_time or stack.decision_time).value,
            code_sha="8" * 40,
            config_artifact_id=config.artifact_id,
            config_hash=config.content_sha256,
        ),
        steps,
        dependencies,
        _research._context(
            f"candidate-plan-{run_id}",
            "SCHEDULE_RUNTIME_RUN",
        ),
    )
    runtime.start_run(
        run_id,
        _research._context(
            f"candidate-start-{run_id}",
            "START_RUNTIME_RUN",
        ),
    )
    return runtime, run_id


def _wait_until_database_time(
    clock: PostgresMarketDatabaseClock,
    decision_time: DecisionTime,
) -> None:
    while True:
        remaining = (decision_time.value - clock.now()).total_seconds()
        if remaining <= 0:
            return
        Event().wait(min(remaining, 0.1))


def _claim(
    runtime: RuntimeApplication,
    *,
    step_key: str,
    lease_duration: timedelta = timedelta(seconds=30),
):
    claim = runtime.claim_next(
        worker_id=f"candidate-{step_key}-worker",
        lease_duration=lease_duration,
        context=_research._context(
            f"candidate-claim-{step_key}-{uuid4().hex}",
            "WORKER_CLAIM",
        ),
    )
    assert claim is not None
    assert claim.step_key == step_key
    runtime.start_attempt(
        claim,
        _research._context(
            f"candidate-attempt-{step_key}-{uuid4().hex}",
            "WORKER_START",
        ),
    )
    return claim


def _replay_scope(stack: Any) -> tuple[UUID, UniverseScopeSpecification]:
    with stack.pool.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT universe_id, scope_artifact_id, scope_content_sha256,
                   scope_size_bytes, market_provider_product_id,
                   classification_scheme, classification_code
            FROM mra.universe_revision
            WHERE universe_revision_id = %s
            """,
            (stack.universe_revision_id,),
        ).fetchone()
    assert row is not None
    return UUID(str(row[0])), UniverseScopeSpecification(
        artifact_id=UUID(str(row[1])),
        content_sha256=str(row[2]),
        size_bytes=int(row[3]),
        market_provider_product_id=UUID(str(row[4])),
        classification_scheme=str(row[5]),
        classification_code=str(row[6]),
        instrument_ids=(stack.instrument_id,),
    )


def test_target_runtime_freshly_closes_capture_through_candidate_set_and_replays_recovery(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    feature = _numeric_feature(stack, key_prefix="vertical-feature")
    application = _candidate_application(stack)
    policy = _candidate_policy(
        stack,
        feature=feature,
        key_prefix="vertical-policy",
    )
    application.register_candidate_policy(
        policy,
        _research._context(
            "vertical-register-policy",
            "REGISTER_CANDIDATE_POLICY",
        ),
    )
    steps = (
        _step(key="capture", kind="CAPTURE", ordinal=1, request_character="1"),
        _step(
            key="normalize-pit",
            kind="NORMALIZE_PIT",
            ordinal=2,
            request_character="2",
        ),
        _step(
            key="freeze-universe",
            kind="FREEZE_UNIVERSE",
            ordinal=3,
            request_character="3",
        ),
        _step(
            key="assess-eligibility",
            kind="ASSESS_ELIGIBILITY",
            ordinal=4,
            request_character="4",
        ),
        _step(
            key="register-dataset",
            kind="REGISTER_DATASET",
            ordinal=5,
            request_character="5",
        ),
        _step(
            key="build-candidate-set",
            kind="BUILD_CANDIDATE_SET",
            ordinal=6,
            request_character="6",
        ),
    )
    database_clock = PostgresMarketDatabaseClock(stack.pool)
    planned_decision_time = DecisionTime(database_clock.now() + timedelta(seconds=5))
    runtime, run_id = _schedule_run(
        stack,
        steps=steps,
        canonical_decision_time=planned_decision_time,
    )

    capture = stack.market.capture(
        CaptureRequest(
            provider_product_id=stack.product.provider_product_id,
            capture_key="candidate-vertical-fresh-source",
            resource="fixture://candidate-vertical-fresh-source",
            request_headers_hash="a" * 64,
        ),
        _research._BytesProvider(),
        _research._context(
            "vertical-fresh-capture",
            "CAPTURE_PROVIDER_RESPONSE",
        ),
        runtime_claim=_claim(runtime, step_key="capture"),
    )
    assert capture.replayed is False
    assert capture.capture.capture_id != stack.market_capture_id
    with stack.pool.connection(read_only=True) as connection:
        previous_fact = connection.execute(
            """
            SELECT fact.session_id, fact.evidence_scope,
                   fact.status_value, fact.event_start, fact.event_end,
                   fact.revision, session.session_date,
                   session.timezone_name, session.open_at,
                   session.break_start_at, session.break_end_at,
                   session.close_at, session.decision_reference_at
            FROM mra.instrument_fact_revision AS fact
            JOIN mra.trading_session AS session
              ON session.session_id = fact.session_id
            WHERE fact.fact_revision_id = %s
            """,
            (stack.market_fact_revision_id,),
        ).fetchone()
    assert previous_fact is not None
    fresh_fact_revision_id = uuid4()
    fresh_session_id = uuid4()
    planned_session_date = planned_decision_time.value.astimezone(
        _research.SHANGHAI
    ).date()
    session_shift = timedelta(days=(planned_session_date - previous_fact[6]).days)

    def fresh_batch(source: Any) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=source.capture_id,
            source_provider_product_id=source.provider_product_id,
            trading_sessions=(
                _research.TradingSession(
                    session_id=fresh_session_id,
                    exchange="XSHG",
                    session_date=planned_session_date,
                    timezone_name=str(previous_fact[7]),
                    open_at=previous_fact[8] + session_shift,
                    break_start_at=previous_fact[9] + session_shift,
                    break_end_at=previous_fact[10] + session_shift,
                    close_at=previous_fact[11] + session_shift,
                    decision_reference_at=previous_fact[12] + session_shift,
                    source_capture_id=source.capture_id,
                ),
            ),
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=fresh_fact_revision_id,
                    provider_product_id=stack.product.provider_product_id,
                    capture_id=source.capture_id,
                    instrument_id=stack.instrument_id,
                    session_id=fresh_session_id,
                    evidence_scope=EvidenceScope(str(previous_fact[1])),
                    status=SecurityStatus(str(previous_fact[2])),
                    event_start=previous_fact[3] + session_shift,
                    event_end=previous_fact[4] + session_shift,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    normalized = stack.market.normalize(
        capture.capture.capture_id,
        _research._Normalizer(fresh_batch),
        _research._context(
            "vertical-fresh-normalize",
            "NORMALIZE_MARKET_PIT",
        ),
        runtime_claim=_claim(runtime, step_key="normalize-pit"),
    )
    assert normalized.replayed is False
    assert normalized.decision_visible_at is not None
    assert normalized.decision_visible_at.value > stack.decision_time.value
    assert capture.capture.temporal.decision_visible_at.value <= normalized.decision_visible_at.value <= planned_decision_time.value
    _, scope = _replay_scope(stack)
    universe = UniverseDefinition(
        universe_id=uuid4(),
        universe_code=f"candidate-vertical-{uuid4().hex[:8]}",
        purpose="fresh Candidate target Runtime lineage",
    )
    stack.selection.register_universe(
        universe,
        _research._context(
            "vertical-fresh-universe",
            "REGISTER_UNIVERSE",
        ),
    )
    _wait_until_database_time(database_clock, planned_decision_time)
    frozen = stack.selection.freeze_universe(
        universe_id=universe.universe_id,
        scope=scope,
        decision_time=planned_decision_time,
        context=_research._context(
            "vertical-fresh-freeze",
            "FREEZE_UNIVERSE",
        ),
        runtime_claim=_claim(runtime, step_key="freeze-universe"),
    )
    assert frozen.replayed is False
    assert frozen.universe_revision_id != stack.universe_revision_id
    assert frozen.included_count == 1
    assessed = stack.selection.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=stack.eligibility_policy_id,
        decision_time=planned_decision_time,
        context=_research._context(
            "vertical-fresh-assess",
            "ASSESS_ELIGIBILITY",
        ),
        runtime_claim=_claim(runtime, step_key="assess-eligibility"),
    )
    assert assessed.replayed is False
    assert assessed.eligible_count == 1
    fresh_stack = replace(
        stack,
        decision_time=planned_decision_time,
        universe_revision_id=frozen.universe_revision_id,
        universe_member_id=frozen.members[0].universe_member_id,
        eligibility_assessment_id=(assessed.assessments[0].eligibility_assessment_id),
        market_capture_id=capture.capture.capture_id,
        market_fact_revision_id=fresh_fact_revision_id,
        market_session_id=fresh_session_id,
    )
    dataset = _numeric_dataset_definition(
        fresh_stack,
        feature=feature,
        key_prefix="vertical-dataset",
    )
    registered = fresh_stack.research.register_dataset(
        dataset,
        _research._context(
            "vertical-fresh-register-dataset",
            "REGISTER_DATASET",
        ),
        runtime_claim=_claim(runtime, step_key="register-dataset"),
    )
    assert registered.replayed is False
    recovery_runtime, recovery_run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="7",
            ),
        ),
    )
    build_claim = _claim(runtime, step_key="build-candidate-set")
    recovery_claim = _claim(
        recovery_runtime,
        step_key="build-candidate-set",
    )
    built = application.build_candidate_set(
        policy.candidate_policy_id,
        dataset.dataset_id,
        _research._context(
            "vertical-fresh-build-candidate-set",
            "BUILD_CANDIDATE_SET",
        ),
        runtime_claim=build_claim,
    )
    assert built.replayed is False

    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "RUNNING"
    assert tuple(item.state for item in trace.steps) == (
        *("SUCCEEDED",) * 6,
        "READY",
        "PENDING",
    )
    funnel = PostgresCandidateQueryProvider(stack.pool).funnel(UUID(built.aggregate_id))
    assert (
        funnel.dataset_population_count,
        funnel.population_count,
        funnel.rankable_count,
        funnel.selected_count,
        funnel.ranked_not_selected_count,
        funnel.unrankable_count,
        funnel.score_component_count,
        funnel.ranking_status,
        funnel.composite_distinct_count,
    ) == (1, 1, 1, 1, 0, 0, 1, "CONSTANT", 1)
    assert funnel.population_reconciled
    assert funnel.rankable_reconciled
    assert funnel.component_matrix_reconciled

    with psycopg.connect(stack.database_url) as connection:
        lineage = connection.execute(
            """
            SELECT candidate_set.dataset_id,
                   candidate_set.universe_revision_id,
                   population.universe_member_id,
                   population.eligibility_assessment_id,
                   market_source.market_instrument_fact_revision_id,
                   fact.capture_id, fact.supersedes_revision_id,
                   fact.revision
            FROM mra.candidate_set AS candidate_set
            JOIN mra.dataset_source AS population
              ON population.dataset_id = candidate_set.dataset_id
             AND population.source_role = 'POPULATION'
            JOIN mra.dataset_source AS market_source
              ON market_source.dataset_id = candidate_set.dataset_id
             AND market_source.source_role =
                 'MARKET_INSTRUMENT_FACT_REVISION'
            JOIN mra.instrument_fact_revision AS fact
              ON fact.fact_revision_id =
                 market_source.market_instrument_fact_revision_id
            WHERE candidate_set.candidate_set_id = %s
            """,
            (UUID(built.aggregate_id),),
        ).fetchone()
        decision_times = connection.execute(
            """
            SELECT runtime_run.decision_time,
                   universe_revision.decision_time,
                   dataset.decision_time,
                   candidate_set.decision_time
            FROM mra.runtime_run AS runtime_run
            JOIN mra.universe_revision AS universe_revision
              ON universe_revision.universe_revision_id = %s
            JOIN mra.dataset AS dataset ON dataset.dataset_id = %s
            JOIN mra.candidate_set AS candidate_set
              ON candidate_set.candidate_set_id = %s
            WHERE runtime_run.run_id = %s
            """,
            (
                frozen.universe_revision_id,
                dataset.dataset_id,
                UUID(built.aggregate_id),
                run_id,
            ),
        ).fetchone()
    assert lineage == (
        dataset.dataset_id,
        frozen.universe_revision_id,
        frozen.members[0].universe_member_id,
        assessed.assessments[0].eligibility_assessment_id,
        fresh_fact_revision_id,
        capture.capture.capture_id,
        None,
        1,
    )
    assert decision_times == (planned_decision_time.value,) * 4

    stack.store.object_path(str(dataset.manifest_artifact.content_sha256)).write_bytes(b"corrupt after committed CandidateSet")
    replay = application.build_candidate_set(
        policy.candidate_policy_id,
        dataset.dataset_id,
        _research._context(
            "vertical-fresh-build-candidate-set",
            "BUILD_CANDIDATE_SET",
        ),
        runtime_claim=recovery_claim,
    )
    assert replay.replayed is True
    assert replay.result_hash == built.result_hash
    assert recovery_runtime.inspect_run(recovery_run_id).run_state == "RUNNING"

    with psycopg.connect(stack.database_url) as connection:
        runtime_facts = connection.execute(
            """
            SELECT step.step_kind, attempt.state,
                   receipt.status, audit.action
            FROM mra.runtime_step AS step
            JOIN mra.runtime_attempt AS attempt
              ON attempt.step_id = step.step_id
            JOIN mra.command_receipt AS receipt
              ON receipt.receipt_id = attempt.result_receipt_id
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            WHERE step.run_id = %s
            ORDER BY step.ordinal
            """,
            (run_id,),
        ).fetchall()
    assert [item[0] for item in runtime_facts] == [
        "CAPTURE",
        "NORMALIZE_PIT",
        "FREEZE_UNIVERSE",
        "ASSESS_ELIGIBILITY",
        "REGISTER_DATASET",
        "BUILD_CANDIDATE_SET",
    ]
    assert all(item[1] == "SUCCEEDED" for item in runtime_facts)
    assert all(item[2] == "SUCCEEDED" for item in runtime_facts)


def test_concurrent_exact_builds_converge_on_one_candidate_set_and_receipt(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    ready = _ready_candidate(stack, key_prefix="concurrent-candidate")
    loader = _BarrierAfterPrepareResearchInputLoader(
        PostgresCandidateResearchInputLoader(stack.pool, stack.store),
        Barrier(2),
    )
    uow_provider = _BarrierAtFinalBindUnitOfWorkProvider(
        PostgresCandidateUnitOfWorkProvider(stack.pool),
        Barrier(2),
    )
    application = CandidateApplication(loader, uow_provider)
    context = _research._context(
        "concurrent-build-candidate-set",
        "BUILD_CANDIDATE_SET",
    )
    runtime_runs = tuple(
        _schedule_run(
            stack,
            steps=(
                _step(
                    key="build-candidate-set",
                    kind="BUILD_CANDIDATE_SET",
                    ordinal=1,
                    request_character=request_character,
                ),
            ),
        )
        for request_character in ("d", "e")
    )
    claims = tuple(
        _claim(runtime, step_key="build-candidate-set")
        for runtime, _run_id in runtime_runs
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(
            executor.submit(
                application.build_candidate_set,
                ready.policy.candidate_policy_id,
                ready.dataset.dataset_id,
                context,
                runtime_claim=claim,
            )
            for claim in claims
        )
        results = tuple(item.result(timeout=15) for item in futures)

    assert sorted(item.replayed for item in results) == [False, True]
    assert len({item.result_hash for item in results}) == 1
    assert loader.prepare_calls == 2
    assert uow_provider.final_bind_calls == 2
    for runtime, run_id in runtime_runs:
        trace = runtime.inspect_run(run_id)
        assert trace.run_state == "RUNNING"
        assert trace.steps[0].state == "SUCCEEDED"
        assert trace.steps[0].attempt_states == ("SUCCEEDED",)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.candidate_set),
                (SELECT count(*) FROM mra.candidate),
                (SELECT count(*) FROM mra.candidate_score_component),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'concurrent-build-candidate-set')
            """
        ).fetchone()
    assert counts == (1, 1, 1, 1)


def test_concurrent_different_policies_share_one_dataset_without_artifact_lock_upgrade_deadlock(
    candidate_vertical_stack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = candidate_vertical_stack
    ready = _ready_candidate(stack, key_prefix="shared-dataset-candidate")
    policies = []
    for suffix in ("first", "second"):
        policy_id = uuid4()
        policy = replace(
            ready.policy,
            candidate_policy_id=policy_id,
            policy_code=f"shared_dataset_candidate_policy_{suffix}",
            config_artifact=_candidate_binding(
                ready.dataset.manifest_artifact,
            ),
            components=(
                replace(
                    ready.policy.components[0],
                    candidate_policy_component_id=uuid4(),
                    candidate_policy_id=policy_id,
                ),
            ),
        )
        ready.application.register_candidate_policy(
            policy,
            _research._context(
                f"shared-dataset-register-{suffix}-policy",
                "REGISTER_CANDIDATE_POLICY",
            ),
        )
        policies.append(policy)

    verification_lock_barrier = Barrier(2)
    require_exact_for_verification = (
        PostgresCandidateArtifactRepository.require_exact_for_verification
    )

    def meet_before_manifest_verification_lock(
        repository: PostgresCandidateArtifactRepository,
        binding: CandidateArtifactBinding,
    ) -> Any:
        verification_lock_barrier.wait(timeout=10)
        return require_exact_for_verification(repository, binding)

    monkeypatch.setattr(
        PostgresCandidateArtifactRepository,
        "require_exact_for_verification",
        meet_before_manifest_verification_lock,
    )
    runtime_runs = tuple(
        _schedule_run(
            stack,
            steps=(
                _step(
                    key="build-candidate-set",
                    kind="BUILD_CANDIDATE_SET",
                    ordinal=1,
                    request_character=request_character,
                ),
            ),
        )
        for request_character in ("a", "b")
    )
    claims = tuple(
        _claim(runtime, step_key="build-candidate-set")
        for runtime, _run_id in runtime_runs
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(
            executor.submit(
                ready.application.build_candidate_set,
                policy.candidate_policy_id,
                ready.dataset.dataset_id,
                _research._context(
                    f"shared-dataset-build-{index}",
                    "BUILD_CANDIDATE_SET",
                ),
                runtime_claim=claim,
            )
            for index, (policy, claim) in enumerate(
                zip(policies, claims, strict=True),
                start=1,
            )
        )
        results = tuple(item.result(timeout=15) for item in futures)

    assert all(item.replayed is False for item in results)
    assert len({item.aggregate_id for item in results}) == 2
    for runtime, run_id in runtime_runs:
        trace = runtime.inspect_run(run_id)
        assert trace.run_state == "RUNNING"
        assert trace.steps[0].state == "SUCCEEDED"
        assert trace.steps[0].attempt_states == ("SUCCEEDED",)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.candidate_set),
                (SELECT count(*) FROM mra.candidate),
                (SELECT count(*) FROM mra.candidate_score_component),
                (SELECT count(*)
                   FROM mra.command_receipt
                      WHERE idempotency_key LIKE 'shared-dataset-build-%%'),
                (SELECT count(*)
                   FROM mra.artifact_verification
                  WHERE artifact_id = %s
                    AND verification_policy =
                        'CANDIDATE_DATASET_MANIFEST_READ')
            """,
            (ready.dataset.manifest_artifact.artifact_id,),
        ).fetchone()
    assert counts == (2, 2, 2, 2, 2)


def test_candidate_build_rejects_live_claim_for_a_different_runtime_step_kind(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    ready = _ready_candidate(stack, key_prefix="wrong-step-candidate")
    loader = _RecordingResearchInputLoader(
        PostgresCandidateResearchInputLoader(stack.pool, stack.store)
    )
    application = CandidateApplication(
        loader,
        PostgresCandidateUnitOfWorkProvider(stack.pool),
    )
    runtime, run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="capture",
                kind="CAPTURE",
                ordinal=1,
                request_character="6",
            ),
        ),
    )
    claim = _claim(runtime, step_key="capture")

    with pytest.raises(StaleFenceError, match="STALE_FENCE"):
        application.build_candidate_set(
            ready.policy.candidate_policy_id,
            ready.dataset.dataset_id,
            _research._context(
                "wrong-step-build-candidate-set",
                "BUILD_CANDIDATE_SET",
            ),
            runtime_claim=claim,
        )

    assert loader.prepare_calls == 0
    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "RUNNING"
    assert trace.steps[0].state == "RUNNING"
    assert trace.steps[0].attempt_states == ("RUNNING",)
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.candidate_set),
                (SELECT count(*) FROM mra.candidate),
                (SELECT count(*) FROM mra.candidate_score_component),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'wrong-step-build-candidate-set'),
                (SELECT count(*) FROM mra.audit_event
                 WHERE action = 'BUILD_CANDIDATE_SET')
            """
        ).fetchone()
    assert counts == (0, 0, 0, 0, 0)


def test_candidate_final_fence_rejects_lease_that_stales_after_prepare_and_ranking(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    ready = _ready_candidate(stack, key_prefix="late-stale-candidate")
    runtime, run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="c",
            ),
        ),
    )
    claim = _claim(
        runtime,
        step_key="build-candidate-set",
        lease_duration=timedelta(seconds=1),
    )
    loader = _RecordingResearchInputLoader(PostgresCandidateResearchInputLoader(stack.pool, stack.store))

    def wait_for_claim_to_stale_after_ranking() -> None:
        remaining = (claim.lease_until - datetime.now(UTC)).total_seconds()
        Event().wait(max(remaining, 0) + 0.05)
        with psycopg.connect(stack.database_url) as connection:
            live = connection.execute(
                """
                SELECT lease_until > clock_timestamp()
                FROM mra.runtime_attempt
                WHERE attempt_id = %s
                """,
                (claim.attempt_id,),
            ).fetchone()
        assert live == (False,)

    uow_provider = _HookedCandidateUnitOfWorkProvider(
        PostgresCandidateUnitOfWorkProvider(stack.pool),
        before_call=2,
        hook=wait_for_claim_to_stale_after_ranking,
    )
    application = CandidateApplication(loader, uow_provider)

    with pytest.raises(StaleFenceError, match="STALE_FENCE"):
        application.build_candidate_set(
            ready.policy.candidate_policy_id,
            ready.dataset.dataset_id,
            _research._context(
                "late-stale-build-candidate-set",
                "BUILD_CANDIDATE_SET",
            ),
            runtime_claim=claim,
        )

    assert loader.prepare_calls == 1
    assert uow_provider.calls == 2
    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "RUNNING"
    assert trace.steps[0].state == "RUNNING"
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.candidate_set),
                (SELECT count(*) FROM mra.candidate),
                (SELECT count(*) FROM mra.candidate_score_component),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key =
                     'late-stale-build-candidate-set'),
                (SELECT count(*)
                 FROM mra.audit_event AS audit
                 JOIN mra.command_receipt AS receipt
                   ON receipt.receipt_id = audit.command_receipt_id
                 WHERE receipt.idempotency_key =
                     'late-stale-build-candidate-set')
            """
        ).fetchone()
    assert counts == (0, 0, 0, 0, 0)


def test_stale_candidate_fence_writes_no_candidate_receipt_or_audit(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    ready = _ready_candidate(stack, key_prefix="stale-candidate")
    runtime, run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="a",
            ),
        ),
    )
    claim = _claim(runtime, step_key="build-candidate-set")

    with pytest.raises(StaleFenceError):
        ready.application.build_candidate_set(
            ready.policy.candidate_policy_id,
            ready.dataset.dataset_id,
            _research._context(
                "stale-build-candidate-set",
                "BUILD_CANDIDATE_SET",
            ),
            runtime_claim=replace(
                claim,
                fence_token=claim.fence_token + 1,
            ),
        )

    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "RUNNING"
    assert trace.steps[0].state == "RUNNING"
    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.candidate_set),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'stale-build-candidate-set'),
                (SELECT count(*) FROM mra.audit_event
                 WHERE aggregate_id LIKE 'BUILD_CANDIDATE_SET:%')
            """
        ).fetchone()
    assert counts == (0, 0, 0)


def test_candidate_manifest_failure_uses_shared_atomic_failure_contract(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    ready = _ready_candidate(stack, key_prefix="failed-candidate")
    runtime, run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="b",
            ),
        ),
    )
    claim = _claim(runtime, step_key="build-candidate-set")
    stack.store.object_path(str(ready.dataset.manifest_artifact.content_sha256)).write_bytes(b"corrupt before Candidate build")

    command_context = _research._context(
        "failed-build-candidate-set",
        "BUILD_CANDIDATE_SET",
    )
    with pytest.raises(ArtifactIntegrityError):
        ready.application.build_candidate_set(
            ready.policy.candidate_policy_id,
            ready.dataset.dataset_id,
            command_context,
            runtime_claim=claim,
        )

    assert runtime.inspect_run(run_id).run_state == "FAILED"
    with psycopg.connect(stack.database_url) as connection:
        facts = connection.execute(
            """
            SELECT receipt.status, receipt.error_code, audit.action,
                   attempt.state,
                   (SELECT count(*) FROM mra.candidate_set),
                   (SELECT count(*) FROM mra.candidate),
                   (SELECT count(*) FROM mra.candidate_score_component)
            FROM mra.command_receipt AS receipt
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = receipt.receipt_id
            WHERE receipt.idempotency_key = 'failed-build-candidate-set'
            """
        ).fetchone()
        original_receipt_id = connection.execute(
            """
            SELECT receipt_id
            FROM mra.command_receipt
            WHERE command_kind = 'BUILD_CANDIDATE_SET'
              AND idempotency_key = 'failed-build-candidate-set'
            """
        ).fetchone()
    assert facts == (
        "FAILED",
        "BUILD_CANDIDATE_SET_REJECTED",
        "CANDIDATE_COMMAND_FAILED",
        "FAILED_TERMINAL",
        0,
        0,
        0,
    )
    assert original_receipt_id is not None

    replay_runtime, replay_run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="c",
            ),
        ),
    )
    replay_claim = _claim(replay_runtime, step_key="build-candidate-set")
    with pytest.raises(CommandPreviouslyFailedError) as raised:
        ready.application.build_candidate_set(
            ready.policy.candidate_policy_id,
            ready.dataset.dataset_id,
            command_context,
            runtime_claim=replay_claim,
        )

    assert raised.value.error_code == "BUILD_CANDIDATE_SET_REJECTED"
    replay_trace = replay_runtime.inspect_run(replay_run_id)
    assert replay_trace.run_state == "FAILED"
    assert replay_trace.steps[0].state == "FAILED"
    assert replay_trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(stack.database_url) as connection:
        replay_facts = connection.execute(
            """
            SELECT
                receipt.receipt_id,
                receipt.status,
                receipt.error_code,
                replay_attempt.result_receipt_id,
                replay_attempt.error_code,
                replay_step.state,
                replay_run.state,
                (SELECT count(*) FROM mra.candidate_set),
                (SELECT count(*) FROM mra.candidate),
                (SELECT count(*) FROM mra.candidate_score_component),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE command_kind = 'BUILD_CANDIDATE_SET'
                   AND scope_id = receipt.scope_id
                   AND idempotency_key = receipt.idempotency_key),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE command_kind = 'CANDIDATE_COMMAND_REJECTION'
                   AND runtime_attempt_id = %s),
                (SELECT count(*) FROM mra.audit_event
                 WHERE command_receipt_id = receipt.receipt_id)
            FROM mra.command_receipt AS receipt
            JOIN mra.runtime_attempt AS replay_attempt
              ON replay_attempt.attempt_id = %s
            JOIN mra.runtime_step AS replay_step
              ON replay_step.step_id = replay_attempt.step_id
            JOIN mra.runtime_run AS replay_run
              ON replay_run.run_id = replay_step.run_id
            WHERE receipt.command_kind = 'BUILD_CANDIDATE_SET'
              AND receipt.idempotency_key = 'failed-build-candidate-set'
            """,
            (replay_claim.attempt_id, replay_claim.attempt_id),
        ).fetchone()
    assert replay_facts == (
        original_receipt_id[0],
        "FAILED",
        "BUILD_CANDIDATE_SET_REJECTED",
        original_receipt_id[0],
        "BUILD_CANDIDATE_SET_REJECTED",
        "FAILED",
        "FAILED",
        0,
        0,
        0,
        1,
        0,
        1,
    )


def test_late_candidate_reconciliation_failure_rolls_back_then_terminalizes_runtime(
    candidate_vertical_stack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = candidate_vertical_stack
    ready = _ready_candidate(stack, key_prefix="late-failure-candidate")
    runtime, run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="d",
            ),
        ),
    )
    claim = _claim(runtime, step_key="build-candidate-set")
    in_transaction_counts: list[tuple[int, int, int]] = []

    def fail_after_verified_reload(
        repository: PostgresCandidateRepository,
        candidate_set_id: UUID,
    ) -> None:
        observed = repository._connection.execute(  # noqa: SLF001 - fault injection
            """
            SELECT
                (SELECT count(*) FROM mra.candidate_set
                 WHERE candidate_set_id = %s),
                (SELECT count(*) FROM mra.candidate
                 WHERE candidate_set_id = %s),
                (SELECT count(*) FROM mra.candidate_score_component
                 WHERE candidate_set_id = %s)
            """,
            (candidate_set_id, candidate_set_id, candidate_set_id),
        ).fetchone()
        assert observed is not None
        in_transaction_counts.append((int(observed[0]), int(observed[1]), int(observed[2])))
        raise ArtifactIntegrityError("injected failure after verified Candidate reload")

    monkeypatch.setattr(
        PostgresCandidateRepository,
        "reconciliation",
        fail_after_verified_reload,
    )
    with pytest.raises(
        ArtifactIntegrityError,
        match="injected failure after verified Candidate reload",
    ):
        ready.application.build_candidate_set(
            ready.policy.candidate_policy_id,
            ready.dataset.dataset_id,
            _research._context(
                "late-failure-build-candidate-set",
                "BUILD_CANDIDATE_SET",
            ),
            runtime_claim=claim,
        )

    assert in_transaction_counts == [(1, 1, 1)]
    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(stack.database_url) as connection:
        facts = connection.execute(
            """
            SELECT receipt.status, receipt.error_code, audit.action,
                   attempt.state, step.state, run.state,
                   (SELECT count(*) FROM mra.candidate_set),
                   (SELECT count(*) FROM mra.candidate),
                   (SELECT count(*) FROM mra.candidate_score_component),
                   (SELECT count(*) FROM mra.artifact_verification
                    WHERE verification_policy =
                        'CANDIDATE_DATASET_MANIFEST_READ')
            FROM mra.command_receipt AS receipt
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = receipt.receipt_id
            JOIN mra.runtime_step AS step ON step.step_id = attempt.step_id
            JOIN mra.runtime_run AS run ON run.run_id = step.run_id
            WHERE receipt.idempotency_key =
                'late-failure-build-candidate-set'
            """
        ).fetchone()
    assert facts == (
        "FAILED",
        "BUILD_CANDIDATE_SET_REJECTED",
        "CANDIDATE_COMMAND_FAILED",
        "FAILED_TERMINAL",
        "FAILED",
        "FAILED",
        0,
        0,
        0,
        0,
    )


@pytest.mark.parametrize(
    ("failure_point", "expected_error"),
    (
        ("candidate_row", RuntimeStateConflictError),
        ("score_row", RuntimeStateConflictError),
        ("receipt", ArtifactIntegrityError),
        ("audit", ArtifactIntegrityError),
        ("runtime_finalization", ArtifactIntegrityError),
    ),
    ids=(
        "candidate-row",
        "score-row",
        "receipt",
        "audit",
        "runtime-finalization",
    ),
)
def test_candidate_failure_points_roll_back_authority_and_terminalize_runtime(
    candidate_vertical_stack,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
    expected_error: type[Exception],
) -> None:
    stack = candidate_vertical_stack
    ready = _ready_candidate(
        stack,
        key_prefix=f"atomic-{failure_point.replace('_', '-')}",
    )
    runtime, run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character={
                    "candidate_row": "1",
                    "score_row": "2",
                    "receipt": "3",
                    "audit": "4",
                    "runtime_finalization": "5",
                }[failure_point],
            ),
        ),
    )
    claim = _claim(runtime, step_key="build-candidate-set")
    idempotency_key = f"atomic-{failure_point}-build-candidate-set"
    injected: list[str] = []

    if failure_point in {"candidate_row", "score_row"}:
        _install_test_insert_failure_trigger(
            stack,
            table=("candidate" if failure_point == "candidate_row" else "candidate_score_component"),
        )
    elif failure_point == "receipt":
        original_receipt_start = PostgresCommandReceiptRepository.start

        def fail_receipt_after_candidate_writes(
            repository: PostgresCommandReceiptRepository,
            **kwargs: Any,
        ) -> Any:
            candidate_count = repository._connection.execute(  # noqa: SLF001
                "SELECT count(*) FROM mra.candidate"
            ).fetchone()
            assert candidate_count is not None
            if (
                not injected
                and kwargs["command_kind"] == "BUILD_CANDIDATE_SET"
                and kwargs["idempotency_key"] == idempotency_key
                and int(candidate_count[0]) > 0
            ):
                injected.append(failure_point)
                raise ArtifactIntegrityError("injected Candidate receipt failure")
            return original_receipt_start(repository, **kwargs)

        monkeypatch.setattr(
            PostgresCommandReceiptRepository,
            "start",
            fail_receipt_after_candidate_writes,
        )
    elif failure_point == "audit":
        original_audit_append = PostgresAuditRepository.append

        def fail_success_audit_once(
            repository: PostgresAuditRepository,
            **kwargs: Any,
        ) -> None:
            if not injected and kwargs["action"] == "BUILD_CANDIDATE_SET":
                injected.append(failure_point)
                raise ArtifactIntegrityError("injected Candidate audit failure")
            original_audit_append(repository, **kwargs)

        monkeypatch.setattr(
            PostgresAuditRepository,
            "append",
            fail_success_audit_once,
        )
    elif failure_point == "runtime_finalization":
        original_runtime_succeed = PostgresRuntimeCommandFinalization.succeed

        def fail_runtime_success_once(
            finalization: PostgresRuntimeCommandFinalization,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            if not injected:
                injected.append(failure_point)
                raise ArtifactIntegrityError("injected Candidate Runtime finalization failure")
            return original_runtime_succeed(finalization, *args, **kwargs)

        monkeypatch.setattr(
            PostgresRuntimeCommandFinalization,
            "succeed",
            fail_runtime_success_once,
        )
    else:
        raise AssertionError(f"unknown failure point: {failure_point}")

    with pytest.raises(expected_error):
        ready.application.build_candidate_set(
            ready.policy.candidate_policy_id,
            ready.dataset.dataset_id,
            _research._context(
                idempotency_key,
                "BUILD_CANDIDATE_SET",
            ),
            runtime_claim=claim,
        )

    if failure_point not in {"candidate_row", "score_row"}:
        assert injected == [failure_point]
    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(stack.database_url) as connection:
        facts = connection.execute(
            """
            SELECT receipt.status, receipt.error_code,
                   audit.action, audit.reason_code,
                   attempt.state, step.state, run.state,
                   (SELECT count(*) FROM mra.candidate_set),
                   (SELECT count(*) FROM mra.candidate),
                   (SELECT count(*) FROM mra.candidate_score_component),
                   (SELECT count(*) FROM mra.candidate_component_diagnostic),
                   (SELECT count(*) FROM mra.artifact_verification
                    WHERE verification_policy =
                        'CANDIDATE_DATASET_MANIFEST_READ'),
                   (SELECT count(*) FROM mra.command_receipt
                    WHERE idempotency_key = %s),
                   (SELECT count(*) FROM mra.audit_event
                    WHERE command_receipt_id = receipt.receipt_id)
            FROM mra.command_receipt AS receipt
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = receipt.receipt_id
            JOIN mra.runtime_step AS step ON step.step_id = attempt.step_id
            JOIN mra.runtime_run AS run ON run.run_id = step.run_id
            WHERE receipt.idempotency_key = %s
            """,
            (idempotency_key, idempotency_key),
        ).fetchone()
    assert facts == (
        "FAILED",
        "BUILD_CANDIDATE_SET_REJECTED",
        "CANDIDATE_COMMAND_FAILED",
        "BUILD_CANDIDATE_SET_REJECTED",
        "FAILED_TERMINAL",
        "FAILED",
        "FAILED",
        0,
        0,
        0,
        0,
        0,
        1,
        1,
    )


def test_candidate_idempotency_key_reuse_with_different_semantic_hash_rejects(
    candidate_vertical_stack,
) -> None:
    stack = candidate_vertical_stack
    ready = _ready_candidate(stack, key_prefix="semantic-conflict-candidate")
    loader = _RecordingResearchInputLoader(PostgresCandidateResearchInputLoader(stack.pool, stack.store))
    application = CandidateApplication(
        loader,
        PostgresCandidateUnitOfWorkProvider(stack.pool),
    )
    authority_context = _research._context(
        "candidate-set-authority",
        "BUILD_CANDIDATE_SET",
    )
    authority_runtime, authority_run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="a",
            ),
        ),
    )
    second_runtime, second_run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="f",
            ),
        ),
    )
    authority_claim = _claim(
        authority_runtime,
        step_key="build-candidate-set",
    )
    second_claim = _claim(
        second_runtime,
        step_key="build-candidate-set",
    )
    original = application.build_candidate_set(
        ready.policy.candidate_policy_id,
        ready.dataset.dataset_id,
        authority_context,
        runtime_claim=authority_claim,
    )
    assert original.replayed is False
    assert loader.prepare_calls == 1
    assert authority_runtime.inspect_run(authority_run_id).run_state == "RUNNING"
    with psycopg.connect(stack.database_url) as connection:
        original_request_hash = connection.execute(
            """
            SELECT request_hash
            FROM mra.command_receipt
            WHERE receipt_id = %s
            """,
            (original.receipt_id,),
        ).fetchone()
    assert original_request_hash is not None
    original_hash = str(original_request_hash[0])
    conflicting_request_hash = canonical_json_sha256(
        {
            "original_request_hash": original_hash,
            "semantic_contract_revision": 2,
        }
    )
    assert original_hash != conflicting_request_hash
    context = _research._context(
        "candidate-set-semantic-conflict",
        "BUILD_CANDIDATE_SET",
    )
    scope_id = f"{ready.policy.candidate_policy_id}:{ready.dataset.dataset_id}"
    seeded_receipt_id = uuid4()
    with PostgresCandidateUnitOfWorkProvider(stack.pool)() as uow:
        seeded = uow.receipts.start(
            receipt_id=seeded_receipt_id,
            command_kind="BUILD_CANDIDATE_SET",
            scope_id=scope_id,
            idempotency_key=context.idempotency_key,
            request_hash=conflicting_request_hash,
        )
        assert seeded.is_new
        uow.receipts.fail(
            receipt_id=seeded_receipt_id,
            error_code="TEST_PRIOR_SEMANTIC_REQUEST",
        )
        uow.commit()

    with pytest.raises(IdempotencyKeyReusedError, match="IDEMPOTENCY_KEY_REUSED"):
        application.build_candidate_set(
            ready.policy.candidate_policy_id,
            ready.dataset.dataset_id,
            context,
            runtime_claim=second_claim,
        )

    assert loader.prepare_calls == 1
    trace = second_runtime.inspect_run(second_run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(stack.database_url) as connection:
        facts = connection.execute(
            """
            SELECT
                original.status, original.request_hash,
                seeded.status, seeded.request_hash,
                rejection.status, rejection.error_code,
                audit.action, attempt.state,
                (SELECT count(*) FROM mra.candidate_set),
                (SELECT count(*) FROM mra.candidate),
                (SELECT count(*) FROM mra.candidate_score_component),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE command_kind = 'BUILD_CANDIDATE_SET'
                   AND scope_id = %s
                   AND idempotency_key =
                       'candidate-set-semantic-conflict')
            FROM mra.command_receipt AS original
            JOIN mra.command_receipt AS seeded
              ON seeded.receipt_id = %s
            JOIN mra.command_receipt AS rejection
              ON rejection.command_kind = 'CANDIDATE_COMMAND_REJECTION'
             AND rejection.runtime_attempt_id = %s
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = rejection.receipt_id
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = rejection.receipt_id
            WHERE original.receipt_id = %s
            """,
            (
                scope_id,
                seeded_receipt_id,
                second_claim.attempt_id,
                original.receipt_id,
            ),
        ).fetchone()
    assert facts == (
        "SUCCEEDED",
        original_hash,
        "FAILED",
        conflicting_request_hash,
        "FAILED",
        "IDEMPOTENCY_KEY_REUSED",
        "CANDIDATE_COMMAND_REJECTED",
        "FAILED_TERMINAL",
        1,
        1,
        1,
        1,
    )


def test_candidate_success_receipt_audit_and_writes_roll_back_together(
    candidate_vertical_stack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = candidate_vertical_stack
    ready = _ready_candidate(stack, key_prefix="rollback-candidate")
    runtime, _run_id = _schedule_run(
        stack,
        steps=(
            _step(
                key="build-candidate-set",
                kind="BUILD_CANDIDATE_SET",
                ordinal=1,
                request_character="b",
            ),
        ),
    )
    claim = _claim(runtime, step_key="build-candidate-set")

    def fail_audit(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected Candidate audit failure")

    monkeypatch.setattr(PostgresAuditRepository, "append", fail_audit)
    with pytest.raises(RuntimeError, match="injected Candidate audit failure"):
        ready.application.build_candidate_set(
            ready.policy.candidate_policy_id,
            ready.dataset.dataset_id,
            _research._context(
                "rollback-build-candidate-set",
                "BUILD_CANDIDATE_SET",
            ),
            runtime_claim=claim,
        )

    with psycopg.connect(stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.candidate_set),
                (SELECT count(*) FROM mra.candidate),
                (SELECT count(*) FROM mra.candidate_score_component),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE idempotency_key = 'rollback-build-candidate-set'),
                (SELECT count(*) FROM mra.artifact_verification
                 WHERE verification_policy =
                     'CANDIDATE_DATASET_MANIFEST_READ')
            """
        ).fetchone()
    assert counts == (0, 0, 0, 0, 0)
