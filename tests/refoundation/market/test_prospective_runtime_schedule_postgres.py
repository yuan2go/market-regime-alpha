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


def _runtime_fixture_at(observed_at: datetime):
    """Align stub work to the real lease clock; this is not Provider evidence."""
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


def test_prospective_predeclare_and_due_capture_use_exact_runtime_fences(
    prospective_stack,
    target_database_url: str,
) -> None:
    runtime, artifacts, pool = prospective_stack
    database_clock = PostgresMarketDatabaseClock(pool)
    manifest = _runtime_fixture_at(database_clock.now())
    plan = compile_prospective_runtime_plan(manifest, code_sha="1" * 40)
    first_window = plan.capture_runs[0]
    archives = _Archives(runtime)
    operations = _Operations(runtime)
    application = ProspectiveArchiveRuntimeApplication(
        runtime=runtime,
        artifacts=artifacts,
        archives=archives,
        operations=operations,
        database_clock=database_clock,
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

    assert runtime.inspect_run(registered.predeclare_run_id).run_state == "SUCCEEDED"
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
