from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.research_qualification.application import (
    build_due_proof_runtime_profile,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
    RuntimeApplication,
)
from market_regime_alpha.runtime.domain import RunSpec, RuntimeMode, ScheduleSpec


def _context(key: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.OPERATOR,
        actor_id="wp14-runtime-profile-test",
        reason_code="WP14_ENGINEERING_REHEARSAL",
    )


def test_due_profile_is_persisted_exactly_and_database_rejects_partial_edge_roster(
    target_database_url: str,
    tmp_path,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=4)
    runtime = RuntimeApplication(PostgresUnitOfWorkProvider(pool))
    artifacts = ArtifactApplication(
        LocalArtifactStore(tmp_path / "wp14-runtime-profile"),
        PostgresUnitOfWorkProvider(pool),
    )
    try:
        schedule = ScheduleSpec(
            schedule_id=uuid4(),
            schedule_code="formal-due-rehearsal",
            revision=1,
            runtime_mode=RuntimeMode.SHADOW,
            schedule_expression=None,
            timezone_name="Asia/Shanghai",
            step_catalog_hash="1" * 64,
            enabled=True,
        )
        runtime.create_schedule(schedule, _context("create-due-schedule"))
        artifact = artifacts.publish(
            b'{"profile":"due"}',
            media_type="application/json",
            context=_context("publish-due-config"),
        )
        steps, dependencies = build_due_proof_runtime_profile(
            request_seed="postgres-due-profile"
        )
        run_id = uuid4()
        runtime.schedule_run(
            RunSpec(
                run_id=run_id,
                schedule_id=schedule.schedule_id,
                fire_key="due-2026-09-02",
                runtime_mode=RuntimeMode.SHADOW,
                requested_at=datetime.now(UTC),
                decision_time=datetime.now(UTC),
                code_sha="2" * 40,
                config_artifact_id=artifact.artifact_id,
                config_hash=artifact.content_sha256,
            ),
            steps,
            dependencies,
            _context("schedule-due-run"),
        )

        with psycopg.connect(target_database_url) as connection:
            persisted = connection.execute(
                """
                SELECT array_agg(step_kind ORDER BY ordinal), count(*)
                FROM mra.runtime_step
                WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()
        assert persisted == (
            [
                "SETTLE_OUTCOME",
                "ACQUIRE_OUTCOME_INPUTS",
                "EVALUATE",
                "RECORD_EVIDENCE",
                "ASSESS_RESEARCH",
                "QUALIFY",
            ],
            6,
        )

        with pytest.raises(psycopg.errors.CheckViolation, match="profile edges"):
            with psycopg.connect(target_database_url) as connection:
                connection.execute(
                    """
                    INSERT INTO mra.runtime_step_dependency (
                        run_id, predecessor_step_id, successor_step_id,
                        dependency_kind
                    )
                    SELECT %s, predecessor.step_id, successor.step_id,
                           'REQUIRED_SUCCESS'
                    FROM mra.runtime_step AS predecessor
                    CROSS JOIN mra.runtime_step AS successor
                    WHERE predecessor.run_id = %s AND predecessor.ordinal = 1
                      AND successor.run_id = %s AND successor.ordinal = 3
                    """,
                    (run_id, run_id, run_id),
                )
    finally:
        pool.close()
