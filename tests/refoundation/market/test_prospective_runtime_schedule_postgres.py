from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketDatabaseClock,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.market.application import (
    ArchiveSliceExecutionResult,
    ArchiveSliceExecutionStatus,
    ProspectiveArchiveRuntimeApplication,
    compile_prospective_runtime_plan,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
    RuntimeApplication,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from tests.refoundation.market.test_prospective_runtime_plan import _manifest

@pytest.mark.parametrize("runtime_revision", [1, 2])
def test_continuation_keeps_the_registered_schedule_revision(
    prospective_stack, target_database_url, runtime_revision,
):
    """Real PG Schedule/Runtime, stub Market ports; no real-time capture proof."""
    from datetime import UTC
    from uuid import UUID
    from market_regime_alpha.market.ports.prospective_continuity import ProspectiveGenerationRuntimeReference
    from tests.refoundation.market.test_prospective_archive_planner import _contract, _manifest as target_manifest
    from tests.refoundation.market.test_prospective_continuity import _calendar

    runtime, artifacts, pool = prospective_stack
    manifest = target_manifest(planned_not_before=datetime(2026, 9, 3, tzinfo=UTC))
    stored_bytes = {}
    database_clock = SimpleNamespace(now=lambda: datetime(2026, 9, 4, 8, tzinfo=UTC))
    application = ProspectiveArchiveRuntimeApplication(
        runtime=runtime, artifacts=artifacts, archives=_Archives(runtime),
        operations=_Operations(runtime), database_clock=database_clock,
        due_query=lambda archive_id: (),
        continuity=SimpleNamespace(
            generations=lambda series: (reference,), overdue_slice_ids=lambda archive_id: (),
        ),
        trading_sessions=SimpleNamespace(available_from=lambda **kwargs: tuple(
            SimpleNamespace(session_id=SimpleNamespace(value=s.session_id), exchange=s.exchange,
                            session_date=s.session_date, open_at=s.open_at, close_at=s.close_at)
            for s in _calendar()
        )),
        target_schedules=SimpleNamespace(exact_contract=lambda identity: _contract()),
        manifest_reader=lambda digest, size: stored_bytes[digest],
        archive_verification=SimpleNamespace(verify=lambda identity: SimpleNamespace(matched=True)),
    )
    initial = application.predeclare(
        manifest, code_sha="1" * 40, actor_id="revision-test",
        lease_duration=timedelta(seconds=30), runtime_revision=runtime_revision,
    )
    plan = compile_prospective_runtime_plan(
        manifest, code_sha="1" * 40, runtime_revision=runtime_revision,
    )
    stored_bytes[initial.config_sha256] = manifest.to_bytes()
    reference = ProspectiveGenerationRuntimeReference(
        initial.market_archive_id, 1, None, initial.config_artifact_id,
        initial.config_sha256, len(manifest.to_bytes()), "1" * 40, runtime_revision,
    )
    result = application.continue_series(
        series_code="xshg_target_archive", code_sha="2" * 40, actor_id="revision-test",
        worker_id="revision-worker", lease_duration=timedelta(seconds=30),
        provider=object(), normalizer_for=lambda item: object(),
    )
    assert result["new_generation_id"] is not None
    with psycopg.connect(target_database_url) as connection:
        schedules = connection.execute(
            "SELECT schedule_id,revision,enabled FROM mra.runtime_schedule WHERE schedule_code=%s",
            ("prospective-archive",),
        ).fetchall()
        successor = connection.execute(
            "SELECT schedule_id,code_sha FROM mra.runtime_run WHERE fire_key=%s",
            (f'archive:{result["new_generation_id"]}:predeclare',),
        ).fetchone()
    assert schedules == [(plan.schedule.schedule_id, runtime_revision, True)]
    assert successor == (plan.schedule.schedule_id, "2" * 40)
    assert runtime.inspect_run(initial.predeclare_run_id).run_state == "SUCCEEDED"
    assert isinstance(result["new_generation_id"], UUID)

    def facts():
        with psycopg.connect(target_database_url) as connection:
            return {
                table: connection.execute(
                    f"SELECT to_jsonb(row) FROM mra.{table} AS row ORDER BY to_jsonb(row)::text"
                ).fetchall()
                for table in ("runtime_schedule", "runtime_run", "runtime_step", "runtime_attempt",
                              "artifact", "artifact_verification", "command_receipt", "audit_event")
            }

    before = facts()
    repeated = application.continue_series(
        series_code="xshg_target_archive", code_sha="2" * 40, actor_id="revision-test",
        worker_id="revision-worker", lease_duration=timedelta(seconds=30),
        provider=object(), normalizer_for=lambda item: object(),
    )
    # Recovery output lists only work performed by this invocation; persistent
    # identities and every stored row must remain unchanged on the repeat.
    assert any(item.recovered_attempt_ids for item in result["executions"])
    assert repeated == {
        **result,
        "executions": tuple(replace(item, recovered_attempt_ids=()) for item in result["executions"]),
    }
    assert facts() == before



def _runtime_fixture_at(observed_at: datetime):
    """Stub capture windows share the real lease clock; no Provider proof."""
    manifest = _manifest()
    first = compile_prospective_runtime_plan(manifest, code_sha="1" * 40).capture_runs[0]
    midpoint = first.window_start + (first.window_end - first.window_start) / 2
    delta = observed_at - midpoint
    slices = tuple(
        replace(
            item,
            plan=replace(
                item.plan,
                event_window_start=item.plan.event_window_start + delta,
                event_window_end=item.plan.event_window_end + delta,
            ),
        )
        for item in manifest.slices
    )
    return replace(
        manifest,
        slices=slices,
        start_request=replace(
            manifest.start_request,
            event_window_start=manifest.start_request.event_window_start + delta,
            event_window_end=manifest.start_request.event_window_end + delta,
            slices=tuple(item.plan for item in slices),
        ),
    )


class _Archives:
    def __init__(self, runtime: RuntimeApplication) -> None:
        self._runtime = runtime
        self.claims = []

    def start(self, request, context, *, runtime_claim=None):
        assert runtime_claim is not None
        self.claims.append(runtime_claim)
        result_hash = canonical_json_sha256(
            {"market_archive_id": request.market_archive_id, "predeclared": True}
        )
        self._runtime.succeed_attempt(
            runtime_claim,
            result_hash=result_hash,
            context=CommandContext(
                idempotency_key=f"stub-archive-success:{runtime_claim.attempt_id}",
                actor_type=ActorType.WORKER,
                actor_id="prospective-test",
                reason_code="PROSPECTIVE_ARCHIVE_TEST",
            ),
        )
        return SimpleNamespace(result_hash=result_hash)


class _Operations:
    def __init__(self, runtime: RuntimeApplication) -> None:
        self._runtime = runtime
        self.requests = []

    def execute_slice(
        self,
        request,
        *,
        provider,
        normalizer,
        context,
        runtime_claim=None,
    ):
        assert runtime_claim is not None
        self.requests.append(request)
        result_hash = canonical_json_sha256(
            {
                "market_archive_slice_id": request.market_archive_slice_id,
                "status": "CAPTURED",
            }
        )
        self._runtime.succeed_attempt(
            runtime_claim,
            result_hash=result_hash,
            context=CommandContext(
                idempotency_key=f"stub-capture-success:{runtime_claim.attempt_id}",
                actor_type=ActorType.WORKER,
                actor_id="prospective-test",
                reason_code="PROSPECTIVE_ARCHIVE_TEST",
            ),
        )
        return ArchiveSliceExecutionResult(
            market_archive_id=request.market_archive_id,
            market_archive_slice_id=request.market_archive_slice_id,
            status=ArchiveSliceExecutionStatus.CAPTURED,
            capture_id=None,
            source_gap_id=None,
        )


@pytest.fixture
def prospective_stack(target_database_url: str, tmp_path):
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    uow = PostgresUnitOfWorkProvider(pool)
    runtime = RuntimeApplication(uow)
    artifacts = ArtifactApplication(
        LocalArtifactStore(tmp_path / "prospective-runtime-artifacts"),
        uow,
    )
    try:
        yield runtime, artifacts, pool
    finally:
        pool.close()


@pytest.mark.parametrize("persisted_due", [True, False])
def test_prospective_predeclare_and_due_capture_use_exact_runtime_fences(
    prospective_stack,
    target_database_url: str,
    persisted_due: bool,
) -> None:
    runtime, artifacts, pool = prospective_stack
    database_clock = PostgresMarketDatabaseClock(pool)
    manifest = _runtime_fixture_at(database_clock.now())
    plan = compile_prospective_runtime_plan(manifest, code_sha="1" * 40)
    first_window = plan.capture_runs[0]
    from tests.refoundation.market.test_runtime_vertical_slice import _capture_step, _schedule_run
    unrelated_step = _capture_step()
    unrelated_run, _ = _schedule_run(runtime, artifacts, (replace(
        unrelated_step, retry_policy=replace(
            unrelated_step.retry_policy, deadline=database_clock.now() - timedelta(seconds=1),
        ),
    ),))
    unrelated_before = runtime.inspect_run(unrelated_run)
    archives = _Archives(runtime)
    operations = _Operations(runtime)
    application = ProspectiveArchiveRuntimeApplication(
        runtime=runtime,
        artifacts=artifacts,
        archives=archives,
        operations=operations,
        database_clock=database_clock,
        due_query=lambda archive_id: tuple(item.plan.market_archive_slice_id for item in first_window.slices) if persisted_due else (),
    )

    registered = application.predeclare(
        manifest,
        code_sha="1" * 40,
        actor_id="prospective-test",
        lease_duration=timedelta(seconds=30),
    )
    executed = application.run_due(
        manifest,
        code_sha="1" * 40,
        actor_id="prospective-test",
        worker_id="prospective-worker",
        lease_duration=timedelta(seconds=30),
        provider=object(),
        normalizer_for=lambda _item: object(),
    )

    assert runtime.inspect_run(unrelated_run) == unrelated_before
    assert runtime.inspect_run(registered.predeclare_run_id).run_state == "SUCCEEDED"
    if not persisted_due:
        assert executed.slice_results == () and executed.due_run_ids == ()
        assert not operations.requests
        assert runtime.inspect_run(first_window.run_id).steps[0].state == "READY"
        return
    assert len(executed.slice_results) == 2
    assert executed.due_run_ids == (first_window.run_id,)
    assert first_window.window_start <= executed.observed_at <= first_window.window_end
    assert runtime.inspect_run(first_window.run_id).run_state == "SUCCEEDED"
    assert all(
        runtime.inspect_run(run.run_id).run_state == "RUNNING"
        for run in plan.capture_runs[1:]
    )
    assert len(archives.claims) == 1
    assert len(operations.requests) == 2
    with psycopg.connect(target_database_url) as connection:
        row = connection.execute(
            """
            SELECT count(*), count(DISTINCT attempt.fence_token)
            FROM mra.runtime_attempt AS attempt
            JOIN mra.runtime_step AS step ON step.step_id = attempt.step_id
            JOIN mra.runtime_run AS run ON run.run_id = step.run_id
            WHERE run.schedule_id = %s
            """,
            (plan.schedule.schedule_id,),
        ).fetchone()
    assert row == (3, 1)

    replay = application.predeclare(
        manifest,
        code_sha="1" * 40,
        actor_id="prospective-test",
        lease_duration=timedelta(seconds=30),
    )
    assert replay == registered


@pytest.mark.parametrize("committed_capture", [False, True])
def test_restarted_prospective_attempt_reconciles_without_repeating_provider_effect(
    prospective_stack, target_database_url, committed_capture,
):
    import time
    from market_regime_alpha.market.application.prospective_runtime import ProspectiveRuntimeIntegrityError
    runtime, artifacts, pool = prospective_stack
    clock = PostgresMarketDatabaseClock(pool)
    manifest = _runtime_fixture_at(clock.now())
    plan = compile_prospective_runtime_plan(manifest, code_sha="1" * 40)
    first = plan.capture_runs[0]
    item = first.slices[0]

    class Provider:
        calls = 0
        def capture(self, request):
            self.calls += 1
            if not committed_capture:
                raise RuntimeError("provider response lost after request")
            return object()

    class Operations(_Operations):
        committed = False
        def execute_slice(self, request, **kwargs):
            if not self.committed:
                kwargs["provider"].capture(request.capture_request)
                self.committed = True
                raise RuntimeError("capture commit response lost")
            return super().execute_slice(request, **kwargs)

    provider = Provider()
    operations = Operations(runtime)
    def application():
        return ProspectiveArchiveRuntimeApplication(
            runtime=runtime, artifacts=artifacts, archives=_Archives(runtime),
            operations=operations, database_clock=clock,
            due_query=lambda _archive: (item.plan.market_archive_slice_id,),
        )
    app = application()
    app.predeclare(manifest, code_sha="1" * 40, actor_id="recovery-test", lease_duration=timedelta(seconds=30))
    kwargs = dict(code_sha="1" * 40, actor_id="recovery-test", worker_id="recovery-worker", lease_duration=timedelta(seconds=30), provider=provider, normalizer_for=lambda _item: object())
    result = app.run_due(manifest, **kwargs)
    assert len(result.failures) == 1 and provider.calls == 1
    assert runtime.inspect_run(first.run_id).steps[1].state == "READY"
    assert runtime.inspect_run(first.run_id).steps[1].attempt_states == ()
    time.sleep(2.1)  # Let the actual PostgreSQL retry backoff expire.
    restarted = application()
    if committed_capture:
        result = restarted.run_due(manifest, **kwargs)
        assert len(result.slice_results) == 1
        assert runtime.inspect_run(first.run_id).steps[0].state == "SUCCEEDED"
    else:
        with pytest.raises(ProspectiveRuntimeIntegrityError, match="EXTERNAL_EFFECT_UNKNOWN"):
            restarted.run_due(manifest, **kwargs)
        assert runtime.inspect_run(first.run_id).steps[0].state == "FAILED"
        with pool.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT error_code FROM mra.runtime_attempt WHERE step_id=%s ORDER BY attempt_no DESC LIMIT 1",
                (runtime.inspect_run(first.run_id).steps[0].step_id,),
            ).fetchone()
        assert row == ("EXTERNAL_EFFECT_UNKNOWN",)
        failed_trace = runtime.inspect_run(first.run_id)
        assert failed_trace.steps[0].latest_attempt_error_code == "EXTERNAL_EFFECT_UNKNOWN"
        with pytest.raises(ProspectiveRuntimeIntegrityError, match="is FAILED"):
            restarted.predeclare(
                manifest, code_sha="1" * 40, actor_id="recovery-test",
                lease_duration=timedelta(seconds=30),
            )
        assert runtime.inspect_run(first.run_id) == failed_trace
    assert provider.calls == 1


def test_predeclare_recovers_expired_claim_after_process_crash(prospective_stack):
    import time

    runtime, artifacts, pool = prospective_stack
    clock = PostgresMarketDatabaseClock(pool)
    manifest = _runtime_fixture_at(clock.now())

    class CrashingArchives(_Archives):
        crashed = False

        def start(self, request, context, *, runtime_claim=None):
            if not self.crashed:
                self.crashed = True
                raise SystemExit("process died before archive command")
            return super().start(request, context, runtime_claim=runtime_claim)

    archives = CrashingArchives(runtime)

    def application():
        return ProspectiveArchiveRuntimeApplication(
            runtime=runtime, artifacts=artifacts, archives=archives,
            operations=_Operations(runtime), database_clock=clock,
            due_query=lambda _archive: (),
        )

    with pytest.raises(SystemExit, match="process died"):
        application().predeclare(
            manifest, code_sha="1" * 40, actor_id="crash-test",
            lease_duration=timedelta(milliseconds=100),
        )
    time.sleep(0.15)  # Expire the actual PostgreSQL lease, without changing its clock.
    registered = application().predeclare(
        manifest, code_sha="1" * 40, actor_id="crash-test",
        lease_duration=timedelta(seconds=30),
    )
    trace = runtime.inspect_run(registered.predeclare_run_id)
    assert trace.run_state == "SUCCEEDED"
    assert len(trace.steps[0].attempt_states) == 2
    assert len(archives.claims) == 1


def test_tick_claim_budget_preserves_unclaimed_roster_and_restart(prospective_stack):
    runtime, artifacts, pool = prospective_stack
    clock = PostgresMarketDatabaseClock(pool)
    manifest = _runtime_fixture_at(clock.now())
    plan = compile_prospective_runtime_plan(manifest, code_sha="1" * 40)
    first = plan.capture_runs[0]
    assert len(first.slices) == 2
    operations = _Operations(runtime)
    app = ProspectiveArchiveRuntimeApplication(
        runtime=runtime, artifacts=artifacts, archives=_Archives(runtime), operations=operations,
        database_clock=clock,
        due_query=lambda _: tuple(item.plan.market_archive_slice_id for item in first.slices),
    )
    app.predeclare(manifest, code_sha="1" * 40, actor_id="budget-test",
                   lease_duration=timedelta(seconds=30))
    def tick():
        return app.run_due(manifest, code_sha="1" * 40, actor_id="budget-test",
                           worker_id="budget-worker", lease_duration=timedelta(seconds=30),
                           provider=object(), normalizer_for=lambda _: object(), maximum_attempts=1)
    initial = tick()
    assert len(initial.attempt_ids) == len(initial.slice_results) == 1
    trace = runtime.inspect_run(first.run_id)
    assert [step.state for step in trace.steps] == ["SUCCEEDED", "READY"]
    resumed = tick()
    assert len(resumed.attempt_ids) == 1
    assert set(initial.attempt_ids).isdisjoint(resumed.attempt_ids)
    complete = runtime.inspect_run(first.run_id)
    assert complete.run_state == "SUCCEEDED"
    assert tick().attempt_ids == ()
    assert runtime.inspect_run(first.run_id) == complete
    assert len(operations.requests) == 2


@pytest.mark.parametrize("reason", ["TICK_BUDGET_EXCEEDED", "STOP_REQUESTED", "SUPERVISOR_CONNECTION_LOST"])
def test_operation_guard_stops_new_claims_after_draining_current_action(prospective_stack, reason):
    runtime, artifacts, pool = prospective_stack
    clock = PostgresMarketDatabaseClock(pool)
    manifest = _runtime_fixture_at(clock.now())
    plan = compile_prospective_runtime_plan(manifest, code_sha="1"*40)
    due = plan.capture_runs[0]
    operations = _Operations(runtime)
    app = ProspectiveArchiveRuntimeApplication(
        runtime=runtime, artifacts=artifacts, archives=_Archives(runtime),
        operations=operations, database_clock=clock,
        due_query=lambda _: tuple(item.plan.market_archive_slice_id for item in due.slices),
    )
    app.predeclare(manifest, code_sha="1"*40, actor_id="guard", lease_duration=timedelta(seconds=30))
    def guard():
        if operations.requests:
            raise ValueError(reason)
    with pytest.raises(ValueError, match=reason):
        app.run_due(manifest, code_sha="1"*40, actor_id="guard", worker_id="worker",
            lease_duration=timedelta(seconds=30), provider=object(), normalizer_for=lambda _: object(),
            before_action=guard)
    trace = runtime.inspect_run(due.run_id)
    assert trace.steps[0].state == "SUCCEEDED"
    assert trace.steps[1].state == "READY"
    assert trace.steps[1].attempt_states == ()
    assert len(operations.requests) == 1


def test_supervision_lost_after_claim_prevents_first_provider_effect(prospective_stack):
    runtime, artifacts, pool = prospective_stack
    clock = PostgresMarketDatabaseClock(pool)
    manifest = _runtime_fixture_at(clock.now())
    due = compile_prospective_runtime_plan(manifest, code_sha="1"*40).capture_runs[0]

    class Provider:
        calls = 0
        def capture(self, request):
            self.calls += 1
            return object()

    class Operations(_Operations):
        def execute_slice(self, request, **kwargs):
            kwargs["provider"].capture(request.capture_request)
            return super().execute_slice(request, **kwargs)

    provider = Provider()
    app = ProspectiveArchiveRuntimeApplication(
        runtime=runtime, artifacts=artifacts, archives=_Archives(runtime),
        operations=Operations(runtime), database_clock=clock,
        due_query=lambda _: (due.slices[0].plan.market_archive_slice_id,),
    )
    app.predeclare(manifest, code_sha="1"*40, actor_id="guard", lease_duration=timedelta(seconds=30))
    def guard():
        if runtime.inspect_run(due.run_id).steps[0].state == "RUNNING":
            raise ValueError("OPERATION_SUPERVISOR_CONNECTION_LOST")
    with pytest.raises(ValueError, match="OPERATION_SUPERVISOR_CONNECTION_LOST"):
        app.run_due(manifest, code_sha="1"*40, actor_id="guard", worker_id="worker",
            lease_duration=timedelta(seconds=30), provider=provider,
            normalizer_for=lambda _: object(), before_action=guard)
    assert provider.calls == 0
    trace = runtime.inspect_run(due.run_id)
    assert trace.steps[0].state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    assert trace.steps[1].attempt_states == ()
