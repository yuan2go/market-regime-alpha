from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.schema import (
    OperationalUpgradeAuthorization,
    OperationalUpgradeIntegrityError,
    OperationalUpgradePlan,
    OperationalUpgradePlanStaleError,
    SchemaManager,
    UnsafeOperationalUpgradeError,
    _OperationalUpgradeDefinition,
)
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
    RuntimeApplication,
)
from market_regime_alpha.runtime.domain import (
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepSpec,
)
from market_regime_alpha.shared.hashing import sha256_bytes


def _dump(database_url: str, path: Path) -> tuple[str, int]:
    subprocess.run(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            f"--file={path}",
            database_url,
        ],
        check=True,
        capture_output=True,
    )
    payload = path.read_bytes()
    return sha256_bytes(payload), len(payload)


def _test_manager(
    database_url: str,
    *,
    bundle_sql: str = "SELECT 1",
) -> tuple[SchemaManager, _OperationalUpgradeDefinition]:
    baseline = SchemaManager(database_url)
    verification = baseline.bootstrap()
    definition = _OperationalUpgradeDefinition(
        upgrade_code="test_exact_noop_v1",
        prior_baseline_sha256=verification.baseline_checksum,
        prior_catalog_sha256=verification.catalog_checksum,
        prior_reference_vocabulary_sha256=(
            verification.reference_vocabulary_checksum
        ),
        next_baseline_sha256=verification.baseline_checksum,
        next_catalog_sha256=verification.catalog_checksum,
        next_reference_vocabulary_sha256=(
            verification.reference_vocabulary_checksum
        ),
        additive_sql=bundle_sql,
    )
    return (
        SchemaManager(database_url, operational_upgrade_definition=definition),
        definition,
    )


def _authorization(
    manager: SchemaManager,
    backup_path: Path,
    backup_sha256: str,
    backup_size_bytes: int,
    *,
    minimum_free_bytes: int = 1,
) -> OperationalUpgradeAuthorization:
    identity = manager.database_identity()
    return OperationalUpgradeAuthorization(
        expected_database_name=identity.database_name,
        expected_database_oid=identity.database_oid,
        operator_id="wp18q-test",
        reason="exercise exact additive operational upgrade protocol",
        backup_path=backup_path,
        backup_sha256=backup_sha256,
        backup_size_bytes=backup_size_bytes,
        minimum_free_bytes=minimum_free_bytes,
        code_sha="1" * 40,
    )


def _context(key: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.OPERATOR,
        actor_id="wp18q-test",
        reason_code="OPERATIONAL_UPGRADE_TEST",
    )


def test_wp18q_registered_upgrade_bundle_is_exact_and_additive(
    target_database_url: str,
) -> None:
    definition = SchemaManager(target_database_url)._resolve_operational_upgrade_definition(
        prior_baseline_sha256=(
            "2faf445b96aaa9f89f13c59094e35af23d5b5142270ee465a9e7d483aa330c26"
        ),
        prior_catalog_sha256=(
            "351270cbd354a4a914d5664ccf7c551b6b807cb0696d1b04a9156a38c6c8511f"
        ),
        prior_reference_vocabulary_sha256=(
            "65168428b2edecf6434454c32a4c5f4e6b96e706ec047466153e6c9ef87e4c25"
        ),
    )

    assert definition.prior_baseline_sha256 == (
        "2faf445b96aaa9f89f13c59094e35af23d5b5142270ee465a9e7d483aa330c26"
    )
    assert definition.next_baseline_sha256 == (
        "9da7396d6dd46e3a896b8845df2ef8619a55d66f1d05285a0dd802d1381dfa98"
    )
    assert definition.next_catalog_sha256 == (
        "c5ea34221f82e38358943215e48d4ba3f58bb46d814669dda72d6af28835326a"
    )
    assert definition.additive_bundle_sha256 == (
        "cbd98d6502e675d0b11d0f1b542861d615bb2f007087fdd49203a0bfc2af8241"
    )
    assert definition.additive_sql.count("CREATE TABLE mra.") == 16
    assert "DROP SCHEMA" not in definition.additive_sql
    assert "DROP TABLE" not in definition.additive_sql
    assert "TRUNCATE" not in definition.additive_sql


def test_wp18q_v2_route_is_selected_only_from_the_exact_v1_epoch(
    target_database_url: str,
) -> None:
    manager = SchemaManager(target_database_url)

    definition = manager._resolve_operational_upgrade_definition(
        prior_baseline_sha256=(
            "9da7396d6dd46e3a896b8845df2ef8619a55d66f1d05285a0dd802d1381dfa98"
        ),
        prior_catalog_sha256=(
            "c5ea34221f82e38358943215e48d4ba3f58bb46d814669dda72d6af28835326a"
        ),
        prior_reference_vocabulary_sha256=(
            "d08800892f5e843a756f53e46205dfbb2787386ebf8281564c31049c45659a1b"
        ),
    )

    assert definition.upgrade_code == "wp18q_track_a_c_v2"
    assert definition.prior_baseline_sha256 == (
        "9da7396d6dd46e3a896b8845df2ef8619a55d66f1d05285a0dd802d1381dfa98"
    )
    assert definition.next_baseline_sha256 == manager.baseline_checksum
    assert definition.next_reference_vocabulary_sha256 == (
        manager.reference_vocabulary_checksum
    )
    assert definition.next_catalog_sha256 == (
        "a61a4ed2a4ae93521942053c37ab6560386bc49c43e64ef3a03f21ab4ab14a71"
    )
    assert definition.additive_bundle_sha256 == (
        "2dfe756539fccf1d25b73d190248ad6e819b3c67192400db2f444338c3cad91e"
    )
    assert definition.additive_sql.count("CREATE TABLE mra.") == 11
    assert "DROP SCHEMA" not in definition.additive_sql
    assert "DROP TABLE" not in definition.additive_sql
    assert "TRUNCATE" not in definition.additive_sql

    with pytest.raises(
        OperationalUpgradeIntegrityError,
        match="NO_APPROVED_OPERATIONAL_UPGRADE_ROUTE",
    ):
        manager._resolve_operational_upgrade_definition(
            prior_baseline_sha256="0" * 64,
            prior_catalog_sha256="1" * 64,
            prior_reference_vocabulary_sha256="2" * 64,
        )


def test_operational_upgrade_plan_is_read_only_exact_and_round_trips(
    target_database_url: str,
    tmp_path: Path,
) -> None:
    manager, definition = _test_manager(target_database_url)
    backup_path = tmp_path / "before.dump"
    backup_sha256, backup_size = _dump(target_database_url, backup_path)

    plan = manager.plan_operational_upgrade(
        _authorization(manager, backup_path, backup_sha256, backup_size)
    )

    assert OperationalUpgradePlan.from_json(plan.to_json()) == plan
    assert plan.prior_baseline_sha256 == definition.prior_baseline_sha256
    assert plan.prior_catalog_sha256 == definition.prior_catalog_sha256
    assert plan.next_baseline_sha256 == definition.next_baseline_sha256
    assert plan.next_catalog_sha256 == definition.next_catalog_sha256
    assert plan.additive_bundle_sha256 == definition.additive_bundle_sha256
    assert plan.active_attempt_ids == ()
    assert plan.active_connection_pids == ()
    assert plan.backup_database_name == plan.database_name
    assert len(plan.historical_projection_sha256) == 64
    with psycopg.connect(target_database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.operational_schema_upgrade_receipt"
        ).fetchone() == (0,)


def test_operational_upgrade_rejects_wrong_identity_corrupt_backup_and_low_disk(
    target_database_url: str,
    tmp_path: Path,
) -> None:
    manager, _ = _test_manager(target_database_url)
    backup_path = tmp_path / "before.dump"
    backup_sha256, backup_size = _dump(target_database_url, backup_path)
    authorization = _authorization(
        manager,
        backup_path,
        backup_sha256,
        backup_size,
    )

    with pytest.raises(UnsafeOperationalUpgradeError, match="database OID"):
        manager.plan_operational_upgrade(
            replace(
                authorization,
                expected_database_oid=authorization.expected_database_oid + 1,
            )
        )

    backup_path.write_bytes(b"x" * backup_size)
    with pytest.raises(UnsafeOperationalUpgradeError, match="BACKUP_SHA256_MISMATCH"):
        manager.plan_operational_upgrade(authorization)

    backup_sha256, backup_size = _dump(target_database_url, backup_path)
    with pytest.raises(UnsafeOperationalUpgradeError, match="INSUFFICIENT_FREE_SPACE"):
        manager.plan_operational_upgrade(
            _authorization(
                manager,
                backup_path,
                backup_sha256,
                backup_size,
                minimum_free_bytes=2**63 - 1,
            )
        )


def test_operational_upgrade_apply_is_atomic_preserves_history_and_reconciles_retry(
    target_database_url: str,
    tmp_path: Path,
) -> None:
    manager, _ = _test_manager(target_database_url)
    with psycopg.connect(target_database_url, autocommit=True) as connection:
        before_artifact = connection.execute(
            "SELECT count(*), coalesce(string_agg(content_sha256, ',' ORDER BY artifact_id), '') "
            "FROM mra.artifact"
        ).fetchone()
    backup_path = tmp_path / "before.dump"
    backup_sha256, backup_size = _dump(target_database_url, backup_path)
    plan = manager.plan_operational_upgrade(
        _authorization(manager, backup_path, backup_sha256, backup_size)
    )

    with pytest.raises(
        OperationalUpgradePlanStaleError,
        match="UPGRADE_CHALLENGE_MISMATCH",
    ):
        manager.apply_operational_upgrade(
            plan,
            challenge="wrong",
            operator_id=plan.operator_id,
        )

    result = manager.apply_operational_upgrade(
        plan,
        challenge=plan.challenge,
        operator_id=plan.operator_id,
    )
    replay = manager.apply_operational_upgrade(
        plan,
        challenge=plan.challenge,
        operator_id=plan.operator_id,
    )

    assert result.replayed is False
    assert replay.replayed is True
    assert replay.receipt_id == result.receipt_id
    assert result.historical_projection_sha256 == plan.historical_projection_sha256
    assert result.verification.catalog_checksum == plan.next_catalog_sha256
    with psycopg.connect(target_database_url) as connection:
        after_artifact = connection.execute(
            "SELECT count(*), coalesce(string_agg(content_sha256, ',' ORDER BY artifact_id), '') "
            "FROM mra.artifact"
        ).fetchone()
        assert after_artifact == before_artifact
        assert connection.execute(
            "SELECT count(*) FROM mra.operational_schema_upgrade_receipt"
        ).fetchone() == (1,)


def test_operational_upgrade_apply_rolls_back_ddl_and_receipt_on_bundle_failure(
    target_database_url: str,
    tmp_path: Path,
) -> None:
    manager, _ = _test_manager(
        target_database_url,
        bundle_sql="CREATE TABLE mra.must_rollback (id bigint PRIMARY KEY); SELECT 1 / 0",
    )
    backup_path = tmp_path / "before.dump"
    backup_sha256, backup_size = _dump(target_database_url, backup_path)
    plan = manager.plan_operational_upgrade(
        _authorization(manager, backup_path, backup_sha256, backup_size)
    )

    with pytest.raises(psycopg.errors.DivisionByZero):
        manager.apply_operational_upgrade(
            plan,
            challenge=plan.challenge,
            operator_id=plan.operator_id,
        )

    with psycopg.connect(target_database_url) as connection:
        assert connection.execute(
            "SELECT to_regclass('mra.must_rollback')"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT count(*) FROM mra.operational_schema_upgrade_receipt"
        ).fetchone() == (0,)


def test_operational_upgrade_fails_closed_for_active_attempt_and_stale_catalog(
    target_database_url: str,
    tmp_path: Path,
) -> None:
    manager, _ = _test_manager(target_database_url)
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=2)
    runtime = RuntimeApplication(PostgresUnitOfWorkProvider(pool))
    artifacts = ArtifactApplication(
        LocalArtifactStore(tmp_path / "artifacts"),
        PostgresUnitOfWorkProvider(pool),
    )
    schedule = ScheduleSpec(
        schedule_id=uuid4(),
        schedule_code="upgrade-fence-test",
        revision=1,
        runtime_mode=RuntimeMode.OPERATIONAL,
        schedule_expression=None,
        timezone_name="Asia/Shanghai",
        step_catalog_hash="a" * 64,
        enabled=True,
    )
    runtime.create_schedule(schedule, _context("schedule"))
    config = artifacts.publish(
        b'{"upgrade":"fence"}',
        media_type="application/json",
        context=_context("artifact"),
    )
    run_id = uuid4()
    runtime.schedule_run(
        RunSpec(
            run_id=run_id,
            schedule_id=schedule.schedule_id,
            fire_key="once",
            runtime_mode=RuntimeMode.OPERATIONAL,
            requested_at=datetime.now(timezone.utc),
            decision_time=None,
            code_sha="1" * 40,
            config_artifact_id=config.artifact_id,
            config_hash=config.content_sha256,
        ),
        (
            StepSpec(
                step_key="capture",
                step_kind="CAPTURE",
                implementation="tests.upgrade_fence",
                implementation_version="1",
                ordinal=1,
                required=True,
                request_hash="b" * 64,
                input_evidence_hash=None,
                retry_policy=RetryPolicy(
                    max_attempts=1,
                    backoff=(),
                    retryable_codes=frozenset(),
                ),
            ),
        ),
        (),
        _context("run"),
    )
    runtime.start_run(run_id, _context("start"))
    claim = runtime.claim_next(
        worker_id="upgrade-fence-worker",
        lease_duration=timedelta(minutes=5),
        run_id=run_id,
        context=_context("claim"),
    )
    assert claim is not None
    pool.close()

    backup_path = tmp_path / "active.dump"
    backup_sha256, backup_size = _dump(target_database_url, backup_path)
    with pytest.raises(UnsafeOperationalUpgradeError, match="ACTIVE_RUNTIME_ATTEMPTS"):
        manager.plan_operational_upgrade(
            _authorization(manager, backup_path, backup_sha256, backup_size)
        )

    terminal_pool = TargetPostgresPool(target_database_url, min_size=0, max_size=1)
    terminal_runtime = RuntimeApplication(PostgresUnitOfWorkProvider(terminal_pool))
    terminal_runtime.start_attempt(claim, _context("attempt-start"))
    terminal_runtime.fail_attempt(
        claim,
        error_class="TEST_FAILURE",
        error_code="TEST_END",
        context=_context("attempt-fail"),
    )
    terminal_pool.close()
    backup_sha256, backup_size = _dump(target_database_url, backup_path)
    plan = manager.plan_operational_upgrade(
        _authorization(manager, backup_path, backup_sha256, backup_size)
    )
    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("COMMENT ON SCHEMA mra IS 'stale after upgrade plan'")
    with pytest.raises(
        OperationalUpgradePlanStaleError,
        match="UPGRADE_PRIOR_CATALOG_CHANGED",
    ):
        manager.apply_operational_upgrade(
            plan,
            challenge=plan.challenge,
            operator_id=plan.operator_id,
        )
