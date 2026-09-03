from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import time
from uuid import UUID, uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
)
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.uow import (
    PostgresUnitOfWork,
    PostgresUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
    IdempotencyKeyReusedError,
    RuntimeApplication,
    StaleFenceError,
)
from market_regime_alpha.runtime.domain import (
    ExternalEffectClass,
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepDependency,
    StepSpec,
)


@pytest.fixture
def runtime_stack(
    target_database_url: str,
    tmp_path,
) -> tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str]:
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    uow_provider = PostgresUnitOfWorkProvider(pool)
    application = RuntimeApplication(uow_provider)
    artifacts = ArtifactApplication(
        LocalArtifactStore(tmp_path / "runtime-artifacts"),
        uow_provider,
    )
    try:
        yield application, artifacts, pool, target_database_url
    finally:
        pool.close()


def _context(key: str, *, reason: str = "FOUNDATION_TEST") -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.OPERATOR,
        actor_id="foundation-test",
        reason_code=reason,
    )


def _schedule(application: RuntimeApplication, *, key: str = "schedule-1") -> ScheduleSpec:
    schedule = ScheduleSpec(
        schedule_id=uuid4(),
        schedule_code="foundation-test",
        revision=1,
        runtime_mode=RuntimeMode.OPERATIONAL,
        schedule_expression=None,
        timezone_name="Asia/Shanghai",
        step_catalog_hash="a" * 64,
        enabled=True,
    )
    result = application.create_schedule(schedule, _context(key))
    assert result.aggregate_id == str(schedule.schedule_id)
    return schedule


def _step(
    key: str,
    ordinal: int,
    *,
    effect: ExternalEffectClass = ExternalEffectClass.NONE,
    max_attempts: int = 2,
) -> StepSpec:
    return StepSpec(
        step_key=key,
        step_kind="CAPTURE" if ordinal == 1 else "NORMALIZE_PIT",
        implementation=f"tests.{key}",
        implementation_version="1",
        ordinal=ordinal,
        required=True,
        request_hash=f"{ordinal}" * 64,
        input_evidence_hash=None,
        retry_policy=RetryPolicy(
            max_attempts=max_attempts,
            backoff=tuple(timedelta(0) for _ in range(max_attempts - 1)),
            retryable_codes=frozenset({"TRANSIENT"}),
        ),
        external_effect_class=effect,
    )


def _run(
    application: RuntimeApplication,
    artifacts: ArtifactApplication,
    schedule: ScheduleSpec,
    *,
    steps: tuple[StepSpec, ...],
    dependencies: tuple[StepDependency, ...] = (),
    key: str = "run-1",
) -> UUID:
    run_id = uuid4()
    config = artifacts.publish(
        f'{{"run":"{key}"}}'.encode(),
        media_type="application/json",
        context=_context(f"config-{key}", reason="REGISTER_RUNTIME_CONFIG"),
    )
    result = application.schedule_run(
        RunSpec(
            run_id=run_id,
            schedule_id=schedule.schedule_id,
            fire_key=key,
            runtime_mode=schedule.runtime_mode,
            requested_at=datetime.now(timezone.utc),
            decision_time=None,
            code_sha="1" * 40,
            config_artifact_id=config.artifact_id,
            config_hash=config.content_sha256,
        ),
        steps,
        dependencies,
        _context(f"schedule-{key}"),
    )
    assert result.aggregate_id == str(run_id)
    application.start_run(run_id, _context(f"start-{key}"))
    return run_id


def test_command_idempotency_returns_original_and_rejects_changed_request(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, _, _, database_url = runtime_stack
    schedule = _schedule(application)

    retried = application.create_schedule(schedule, _context("schedule-1"))
    assert retried.aggregate_id == str(schedule.schedule_id)
    assert retried.replayed is True

    with pytest.raises(IdempotencyKeyReusedError, match="IDEMPOTENCY_KEY_REUSED"):
        application.create_schedule(
            replace(schedule, timezone_name="UTC"),
            _context("schedule-1"),
        )

    with psycopg.connect(database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.runtime_schedule),
                (SELECT count(*) FROM mra.command_receipt
                 WHERE command_kind = 'CREATE_RUNTIME_SCHEDULE'),
                (SELECT count(*) FROM mra.audit_event
                 WHERE action = 'CREATE_RUNTIME_SCHEDULE')
            """
        ).fetchone()
    assert counts == (1, 1, 1)


def test_concurrent_claim_creates_one_live_attempt_and_database_fence(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, artifacts, _, database_url = runtime_stack
    schedule = _schedule(application)
    run_id = _run(application, artifacts, schedule, steps=(_step("capture", 1),))

    def claim(worker: str):
        return application.claim_next(
            worker_id=worker,
            lease_duration=timedelta(seconds=5),
            context=_context(f"claim-{worker}", reason="WORKER_CLAIM"),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = tuple(executor.map(claim, ("worker-a", "worker-b")))

    live = tuple(item for item in claims if item is not None)
    assert len(live) == 1
    assert live[0].fence_token == 1
    assert live[0].run_id == run_id

    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT count(*), min(fence_token), max(fence_token)
            FROM mra.runtime_attempt
            WHERE state IN ('CLAIMED', 'RUNNING')
            """
        ).fetchone()
    assert row == (1, 1, 1)


def test_worker_can_claim_only_from_one_exact_runtime_run(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, artifacts, _, _ = runtime_stack
    schedule = _schedule(application)
    first_run = _run(
        application,
        artifacts,
        schedule,
        steps=(_step("capture-first", 1),),
        key="first-run",
    )
    second_run = _run(
        application,
        artifacts,
        schedule,
        steps=(_step("capture-second", 1),),
        key="second-run",
    )

    claim = application.claim_next(
        run_id=second_run,
        worker_id="scoped-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("scoped-claim", reason="WORKER_CLAIM"),
    )

    assert claim is not None
    assert claim.run_id == second_run
    assert application.inspect_run(first_run).steps[0].state == "READY"


def test_one_run_never_has_two_live_steps_even_when_nodes_are_parallel_ready(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, artifacts, _, database_url = runtime_stack
    schedule = _schedule(application)
    _run(
        application,
        artifacts,
        schedule,
        steps=(_step("capture-a", 1), _step("capture-b", 2)),
    )

    def claim(worker: str):
        return application.claim_next(
            worker_id=worker,
            lease_duration=timedelta(seconds=5),
            context=_context(f"parallel-{worker}", reason="WORKER_CLAIM"),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = tuple(executor.map(claim, ("worker-a", "worker-b")))

    live = tuple(item for item in claims if item is not None)
    assert len(live) == 1
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT count(*)
            FROM mra.runtime_step
            WHERE state IN ('CLAIMED', 'RUNNING')
            """
        ).fetchone() == (1,)


def test_postgres_uow_rejects_nesting_and_reuse(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    _, _, pool, _ = runtime_stack
    unit_of_work = PostgresUnitOfWork(pool)

    with unit_of_work:
        with pytest.raises(RuntimeError, match="cannot be nested or reused"):
            unit_of_work.__enter__()

    with pytest.raises(RuntimeError, match="cannot be nested or reused"):
        unit_of_work.__enter__()


def test_expired_lease_recovery_rejects_stale_worker_and_completes_new_fence(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, artifacts, _, database_url = runtime_stack
    schedule = _schedule(application)
    run_id = _run(application, artifacts, schedule, steps=(_step("capture", 1),))
    first = application.claim_next(
        worker_id="worker-a",
        lease_duration=timedelta(seconds=1),
        context=_context("claim-a", reason="WORKER_CLAIM"),
    )
    assert first is not None
    application.start_attempt(first, _context("start-a", reason="WORKER_START"))
    time.sleep(1.1)

    recovered = application.recover_expired(
        actor_id="recovery-test",
        reason_code="LEASE_EXPIRED",
    )
    assert recovered == (first.attempt_id,)

    second = application.claim_next(
        worker_id="worker-b",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-b", reason="WORKER_CLAIM"),
    )
    assert second is not None
    assert second.step_id == first.step_id
    assert second.attempt_no == 2
    assert second.fence_token == 2

    with pytest.raises(StaleFenceError, match="STALE_FENCE"):
        application.succeed_attempt(
            first,
            result_hash="c" * 64,
            context=_context("finish-a", reason="WORKER_FINISH"),
        )

    application.start_attempt(second, _context("start-b", reason="WORKER_START"))
    result = application.succeed_attempt(
        second,
        result_hash="d" * 64,
        context=_context("finish-b", reason="WORKER_FINISH"),
    )
    replay = application.succeed_attempt(
        second,
        result_hash="d" * 64,
        context=_context("finish-b", reason="WORKER_FINISH"),
    )
    assert result.replayed is False
    assert replay.replayed is True

    trace = application.inspect_run(run_id)
    assert trace.run_state == "SUCCEEDED"
    assert trace.steps[0].state == "SUCCEEDED"
    with psycopg.connect(database_url) as connection:
        attempts = connection.execute(
            "SELECT attempt_no, fence_token, state FROM mra.runtime_attempt ORDER BY attempt_no"
        ).fetchall()
    assert attempts == [(1, 1, "ABANDONED"), (2, 2, "SUCCEEDED")]


def test_retryable_failure_creates_a_new_attempt_without_reopening_old_attempt(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, artifacts, _, database_url = runtime_stack
    schedule = _schedule(application)
    _run(
        application,
        artifacts,
        schedule,
        steps=(_step("capture", 1, effect=ExternalEffectClass.PURE_READ),),
    )
    first = application.claim_next(
        worker_id="worker-a",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-a", reason="WORKER_CLAIM"),
    )
    assert first is not None
    application.start_attempt(first, _context("start-a", reason="WORKER_START"))
    application.fail_attempt(
        first,
        error_class="ADAPTER",
        error_code="TRANSIENT",
        context=_context("fail-a", reason="TRANSIENT"),
    )
    second = application.claim_next(
        worker_id="worker-b",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-b", reason="WORKER_CLAIM"),
    )
    assert second is not None
    assert (second.attempt_no, second.fence_token) == (2, 2)

    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            "SELECT attempt_no, state FROM mra.runtime_attempt ORDER BY attempt_no"
        ).fetchall()
    assert rows == [(1, "FAILED_RETRYABLE"), (2, "CLAIMED")]


def test_unknown_remote_outcome_waits_for_explicit_resume_and_restart(
    target_database_url: str,
    tmp_path,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    first_pool = TargetPostgresPool(target_database_url, min_size=0, max_size=4)
    first_uow_provider = PostgresUnitOfWorkProvider(first_pool)
    first_application = RuntimeApplication(first_uow_provider)
    first_artifacts = ArtifactApplication(
        LocalArtifactStore(tmp_path / "restart-artifacts"),
        first_uow_provider,
    )
    schedule = _schedule(first_application)
    run_id = _run(
        first_application,
        first_artifacts,
        schedule,
        steps=(
            _step(
                "capture",
                1,
                effect=ExternalEffectClass.IDEMPOTENT_REMOTE_COMMAND,
            ),
        ),
    )
    claim = first_application.claim_next(
        worker_id="worker-a",
        lease_duration=timedelta(seconds=1),
        context=_context("claim-a", reason="WORKER_CLAIM"),
    )
    assert claim is not None
    first_application.start_attempt(claim, _context("start-a", reason="WORKER_START"))
    first_pool.close()
    time.sleep(1.1)

    second_pool = TargetPostgresPool(target_database_url, min_size=0, max_size=4)
    second_application = RuntimeApplication(PostgresUnitOfWorkProvider(second_pool))
    try:
        assert second_application.recover_expired(
            actor_id="restart-recovery",
            reason_code="LEASE_EXPIRED",
        ) == (claim.attempt_id,)
        waiting = second_application.inspect_run(run_id)
        assert waiting.run_state == "WAITING"
        assert waiting.steps[0].state == "WAITING"

        with pytest.raises(ValueError, match="EXTERNAL_EFFECT_PROVEN_ABSENT"):
            second_application.resume_waiting_step(
                run_id=run_id,
                step_id=claim.step_id,
                resolution_code="EXTERNAL_EFFECT_PROVEN_COMMITTED",
                context=_context("resume-invalid", reason="RECONCILIATION_RESOLVED"),
            )

        with psycopg.connect(target_database_url) as connection:
            reasons = connection.execute(
                """
                SELECT run.terminal_reason_code, step.terminal_reason_code
                FROM mra.runtime_run AS run
                JOIN mra.runtime_step AS step ON step.run_id = run.run_id
                WHERE run.run_id = %s
                """,
                (run_id,),
            ).fetchone()
        assert reasons == ("EXTERNAL_EFFECT_UNKNOWN", "EXTERNAL_EFFECT_UNKNOWN")

        second_application.resume_waiting_step(
            run_id=run_id,
            step_id=claim.step_id,
            resolution_code="EXTERNAL_EFFECT_PROVEN_ABSENT",
            context=_context("resume-a", reason="RECONCILIATION_RESOLVED"),
        )
        resumed = second_application.inspect_run(run_id)
        assert resumed.run_state == "RUNNING"
        assert resumed.steps[0].state == "READY"
        replacement = second_application.claim_next(
            worker_id="worker-b",
            lease_duration=timedelta(seconds=5),
            context=_context("claim-b", reason="WORKER_CLAIM"),
        )
        assert replacement is not None
        assert replacement.fence_token == 2
    finally:
        second_pool.close()


def test_dependency_completion_releases_only_the_next_step(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, artifacts, _, _ = runtime_stack
    schedule = _schedule(application)
    run_id = _run(
        application,
        artifacts,
        schedule,
        steps=(_step("capture", 1), _step("normalize", 2)),
        dependencies=(
            StepDependency(
                predecessor_key="capture",
                successor_key="normalize",
            ),
        ),
    )
    before = application.inspect_run(run_id)
    assert [step.state for step in before.steps] == ["READY", "PENDING"]
    claim = application.claim_next(
        worker_id="worker-a",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-a", reason="WORKER_CLAIM"),
    )
    assert claim is not None
    application.start_attempt(claim, _context("start-a", reason="WORKER_START"))
    application.succeed_attempt(
        claim,
        result_hash="e" * 64,
        context=_context("finish-a", reason="WORKER_FINISH"),
    )
    after = application.inspect_run(run_id)
    assert [step.state for step in after.steps] == ["SUCCEEDED", "READY"]


def test_database_rejects_candidate_chain_without_mandatory_open_decision_step(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, artifacts, _, database_url = runtime_stack
    schedule = _schedule(application, key="schedule-decision-chain-guard")
    run_id = _run(
        application,
        artifacts,
        schedule,
        steps=(_step("capture", 1),),
        key="decision-chain-guard",
    )

    with psycopg.connect(database_url) as connection:
        # Remove only the generic immutable-row guard inside this disposable
        # transaction so the dedicated deferred DAG constraint is exercised.
        connection.execute("DROP TRIGGER runtime_step_guard ON mra.runtime_step")
        connection.execute(
            """
            UPDATE mra.runtime_step
            SET step_kind = 'BUILD_CANDIDATE_SET'
            WHERE run_id = %s
            """,
            (run_id,),
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.commit()
        connection.rollback()
        persisted = connection.execute(
            """
            SELECT step_kind
            FROM mra.runtime_step
            WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()
    assert persisted == ("CAPTURE",)


def test_claim_and_heartbeat_retries_return_the_original_receipts(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, artifacts, _, database_url = runtime_stack
    schedule = _schedule(application)
    _run(application, artifacts, schedule, steps=(_step("capture", 1),))
    context = _context("claim-once", reason="WORKER_CLAIM")
    claim = application.claim_next(
        worker_id="worker-a",
        lease_duration=timedelta(seconds=1),
        context=context,
    )
    replay = application.claim_next(
        worker_id="worker-a",
        lease_duration=timedelta(seconds=1),
        context=context,
    )
    assert claim is not None
    assert replay == claim
    application.start_attempt(claim, _context("start-once", reason="WORKER_START"))
    heartbeat_context = _context("heartbeat-once", reason="WORKER_HEARTBEAT")
    first = application.heartbeat_attempt(
        claim,
        lease_duration=timedelta(seconds=1),
        context=heartbeat_context,
    )
    second = application.heartbeat_attempt(
        claim,
        lease_duration=timedelta(seconds=1),
        context=heartbeat_context,
    )
    assert first.receipt_id == second.receipt_id
    assert second.replayed is True
    time.sleep(0.15)
    application.succeed_attempt(
        claim,
        result_hash="f" * 64,
        context=_context("finish-after-heartbeat", reason="WORKER_FINISH"),
    )
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT count(*) FROM mra.command_receipt
            WHERE command_kind IN ('CLAIM_RUNTIME_STEP', 'HEARTBEAT_RUNTIME_ATTEMPT')
            """
        ).fetchone() == (2,)


def test_retry_budget_exhaustion_is_terminal_and_not_claimable(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, artifacts, _, _ = runtime_stack
    schedule = _schedule(application)
    run_id = _run(
        application,
        artifacts,
        schedule,
        steps=(_step("capture", 1, max_attempts=1),),
    )
    claim = application.claim_next(
        worker_id="worker-a",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-terminal", reason="WORKER_CLAIM"),
    )
    assert claim is not None
    application.start_attempt(
        claim,
        _context("start-terminal", reason="WORKER_START"),
    )
    application.fail_attempt(
        claim,
        error_class="ADAPTER",
        error_code="TRANSIENT",
        context=_context("fail-terminal", reason="TRANSIENT"),
    )
    assert application.inspect_run(run_id).run_state == "FAILED"
    assert application.claim_next(
        worker_id="worker-b",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-after-terminal", reason="WORKER_CLAIM"),
    ) is None


def test_deadline_recovery_creates_a_terminal_audited_attempt(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
) -> None:
    application, artifacts, _, database_url = runtime_stack
    schedule = _schedule(application)
    step = _step("capture", 1, max_attempts=1)
    step = replace(
        step,
        retry_policy=replace(
            step.retry_policy,
            deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
        ),
    )
    run_id = _run(application, artifacts, schedule, steps=(step,))

    recovered = application.recover_expired(
        actor_id="deadline-recovery",
        reason_code="DEADLINE_EXHAUSTED",
    )

    assert len(recovered) == 1
    assert application.inspect_run(run_id).run_state == "FAILED"
    with psycopg.connect(database_url) as connection:
        attempt = connection.execute(
            """
            SELECT state, error_class, error_code, result_receipt_id IS NOT NULL
            FROM mra.runtime_attempt
            WHERE attempt_id = %s
            """,
            (recovered[0],),
        ).fetchone()
        audit = connection.execute(
            """
            SELECT action, reason_code
            FROM mra.audit_event
            WHERE aggregate_id = %s
            """,
            (str(recovered[0]),),
        ).fetchone()
    assert attempt == ("FAILED_TERMINAL", "RUNTIME", "DEADLINE_EXHAUSTED", True)
    assert audit == ("EXPIRE_RUNTIME_STEP_DEADLINE", "DEADLINE_EXHAUSTED")


def test_attempt_finalization_receipt_audit_and_state_roll_back_together(
    runtime_stack: tuple[RuntimeApplication, ArtifactApplication, TargetPostgresPool, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, artifacts, _, database_url = runtime_stack
    schedule = _schedule(application)
    _run(application, artifacts, schedule, steps=(_step("capture", 1),))
    claim = application.claim_next(
        worker_id="worker-a",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-atomic", reason="WORKER_CLAIM"),
    )
    assert claim is not None
    application.start_attempt(claim, _context("start-atomic", reason="WORKER_START"))

    def fail_audit(*_args, **_kwargs) -> None:
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(PostgresAuditRepository, "append", fail_audit)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        application.succeed_attempt(
            claim,
            result_hash="9" * 64,
            context=_context("finish-atomic", reason="WORKER_FINISH"),
        )

    with psycopg.connect(database_url) as connection:
        state = connection.execute(
            "SELECT state FROM mra.runtime_attempt WHERE attempt_id = %s",
            (claim.attempt_id,),
        ).fetchone()
        receipt_count = connection.execute(
            """
            SELECT count(*) FROM mra.command_receipt
            WHERE command_kind = 'SUCCEED_RUNTIME_ATTEMPT'
              AND idempotency_key = 'finish-atomic'
            """
        ).fetchone()
    assert state == ("RUNNING",)
    assert receipt_count == (0,)
