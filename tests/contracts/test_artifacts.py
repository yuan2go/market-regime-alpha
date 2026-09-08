from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import psycopg
import pytest

import market_regime_alpha.infrastructure.artifacts.local as local_artifacts
from market_regime_alpha.infrastructure.artifacts import ArtifactStoreError, LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    ArtifactIntegrityError,
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


def _context(key: str, reason: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.OPERATOR,
        actor_id="artifact-test",
        reason_code=reason,
    )


@pytest.fixture
def artifact_stack(
    target_database_url: str,
    tmp_path,
) -> tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str]:
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=4)
    store = LocalArtifactStore(tmp_path / "artifact-root")
    application = ArtifactApplication(store, PostgresUnitOfWorkProvider(pool))
    try:
        yield application, store, pool, target_database_url
    finally:
        pool.close()


def test_content_addressed_publish_is_atomic_deduplicated_and_verified(
    tmp_path,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifact-root")

    first = store.publish_bytes(b"canonical bytes", media_type="application/octet-stream")
    second = store.publish_bytes(b"canonical bytes", media_type="application/octet-stream")
    verification = store.verify(first.content_sha256, expected_size=first.size_bytes)

    assert first == second
    assert verification.result == "VERIFIED"
    assert verification.observed_sha256 == first.content_sha256
    assert len(store.list_objects()) == 1


def test_publish_serializes_with_quarantine_and_cannot_recreate_orphan(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifact-root")
    content = b"publish versus quarantine"
    published = store.publish_bytes(
        content,
        media_type="application/octet-stream",
    )
    quarantine_entered = Event()
    release_quarantine = Event()
    original_replace = local_artifacts.os.replace

    def paused_replace(source, destination) -> None:
        quarantine_entered.set()
        if not release_quarantine.wait(timeout=10):
            raise TimeoutError("test did not release Artifact quarantine")
        original_replace(source, destination)

    monkeypatch.setattr(local_artifacts.os, "replace", paused_replace)
    with ThreadPoolExecutor(max_workers=2) as executor:
        quarantine_future = executor.submit(
            store.quarantine,
            published.content_sha256,
        )
        assert quarantine_entered.wait(timeout=10)
        publish_future = executor.submit(
            store.publish_bytes,
            content,
            media_type="application/octet-stream",
        )
        with pytest.raises(FutureTimeoutError):
            publish_future.result(timeout=0.2)
        release_quarantine.set()
        quarantine_future.result(timeout=10)
        with pytest.raises(ArtifactStoreError, match="cannot be republished"):
            publish_future.result(timeout=10)

    assert not store.object_path(published.content_sha256).exists()
    assert store.quarantine_path(published.content_sha256).is_file()
    store.delete_quarantined(published.content_sha256)
    assert not store.object_path(published.content_sha256).exists()
    assert not store.quarantine_path(published.content_sha256).exists()


def test_artifact_store_rejects_extra_objects_and_locator_tamper(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
) -> None:
    application, store, _, database_url = artifact_stack
    registered = application.publish(
        b"strict artifact layout",
        media_type="application/octet-stream",
        context=_context("publish-strict-layout", "REGISTER_TEST_ARTIFACT"),
    )
    unexpected = store.root / "objects" / "unexpected.txt"
    unexpected.write_text("not content addressed", encoding="utf-8")
    with pytest.raises(ArtifactStoreError, match="unexpected object-store entry"):
        store.list_objects()
    unexpected.unlink()

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("ALTER TABLE mra.artifact DISABLE TRIGGER USER")
        connection.execute(
            "UPDATE mra.artifact SET locator = 'objects/ff/wrong' WHERE artifact_id = %s",
            (registered.artifact_id,),
        )
        connection.execute("ALTER TABLE mra.artifact ENABLE TRIGGER USER")
    with pytest.raises(ArtifactIntegrityError, match="locator"):
        application.verify(
            registered.artifact_id,
            verifier_id="artifact-test",
            context=_context("verify-locator-tamper", "VERIFY_ARTIFACT"),
        )


def test_publish_verifies_bytes_before_atomic_database_binding(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
) -> None:
    application, store, _, database_url = artifact_stack

    registered = application.publish(
        b"runtime configuration",
        media_type="application/json",
        context=_context("publish-config", "REGISTER_RUNTIME_CONFIG"),
        pin_reason_code="ACTIVE_RUNTIME_CONFIG",
    )
    replayed = application.publish(
        b"runtime configuration",
        media_type="application/json",
        context=_context("publish-config", "REGISTER_RUNTIME_CONFIG"),
        pin_reason_code="ACTIVE_RUNTIME_CONFIG",
    )

    assert replayed.artifact_id == registered.artifact_id
    assert replayed.replayed is True
    assert store.verify(
        registered.content_sha256,
        expected_size=registered.size_bytes,
    ).result == "VERIFIED"
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT content_sha256, size_bytes, media_type, integrity_state, pin_reason_code
            FROM mra.artifact
            WHERE artifact_id = %s
            """,
            (registered.artifact_id,),
        ).fetchone()
    assert row == (
        registered.content_sha256,
        registered.size_bytes,
        "application/json",
        "AVAILABLE",
        "ACTIVE_RUNTIME_CONFIG",
    )


def test_duplicate_content_cannot_silently_change_canonical_metadata(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
) -> None:
    application, _, _, _ = artifact_stack
    application.publish(
        b"same immutable bytes",
        media_type="application/octet-stream",
        context=_context("publish-first-metadata", "REGISTER_TEST_ARTIFACT"),
    )

    with pytest.raises(ArtifactIntegrityError, match="conflicting metadata"):
        application.publish(
            b"same immutable bytes",
            media_type="application/octet-stream",
            context=_context("publish-second-metadata", "REGISTER_TEST_ARTIFACT"),
            pin_reason_code="QUALIFICATION_EVIDENCE",
        )


def test_database_failure_after_publish_leaves_only_a_physical_orphan(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
) -> None:
    _, store, _, database_url = artifact_stack

    class FailingUowProvider:
        def __call__(self):
            raise RuntimeError("database unavailable after byte publication")

    application = ArtifactApplication(store, FailingUowProvider())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="database unavailable"):
        application.publish(
            b"orphan after database failure",
            media_type="application/octet-stream",
            context=_context("publish-orphan", "REGISTER_TEST_ARTIFACT"),
        )

    objects = store.list_objects()
    assert len(objects) == 1
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.artifact").fetchone() == (0,)


def test_corruption_is_recorded_and_blocks_authoritative_read(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
) -> None:
    application, store, _, database_url = artifact_stack
    registered = application.publish(
        b"evidence bytes",
        media_type="application/octet-stream",
        context=_context("publish-evidence", "REGISTER_TEST_ARTIFACT"),
    )
    store.object_path(registered.content_sha256).write_bytes(b"corrupted bytes")

    with pytest.raises(ArtifactIntegrityError, match="ARTIFACT_INTEGRITY_FAILED"):
        application.verify(
            registered.artifact_id,
            verifier_id="artifact-test",
            context=_context("verify-corrupt", "VERIFY_ARTIFACT"),
        )

    with psycopg.connect(database_url) as connection:
        state = connection.execute(
            "SELECT integrity_state FROM mra.artifact WHERE artifact_id = %s",
            (registered.artifact_id,),
        ).fetchone()
        verification = connection.execute(
            """
            SELECT result, observed_exists, observed_size_bytes
            FROM mra.artifact_verification
            WHERE artifact_id = %s
            ORDER BY verified_at DESC
            LIMIT 1
            """,
            (registered.artifact_id,),
        ).fetchone()
    assert state == ("CORRUPT",)
    assert verification == ("SIZE_MISMATCH", True, len(b"corrupted bytes"))


def test_verification_exact_retry_replays_and_new_key_records_new_observation(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
) -> None:
    application, store, _, database_url = artifact_stack
    registered = application.publish(
        b"verification observations are append-only",
        media_type="application/octet-stream",
        context=_context("publish-observation", "REGISTER_TEST_ARTIFACT"),
    )
    repeated_context = _context("same-verification-command", "VERIFY_ARTIFACT")
    first = application.verify(
        registered.artifact_id,
        verifier_id="artifact-observation-test",
        context=repeated_context,
    )
    assert first.result == "VERIFIED"
    store.object_path(registered.content_sha256).write_bytes(b"corrupt")

    replay = application.verify(
        registered.artifact_id,
        verifier_id="artifact-observation-test",
        context=repeated_context,
    )
    assert replay == first

    with pytest.raises(ArtifactIntegrityError, match="SIZE_MISMATCH"):
        application.verify(
            registered.artifact_id,
            verifier_id="artifact-observation-test",
            context=_context("new-verification-command", "VERIFY_ARTIFACT"),
        )

    with psycopg.connect(database_url) as connection:
        observations = connection.execute(
            """
            SELECT result
            FROM mra.artifact_verification
            WHERE artifact_id = %s
              AND verification_policy = 'AUTHORITATIVE_READ'
            ORDER BY verified_at
            """,
            (registered.artifact_id,),
        ).fetchall()
        receipts = connection.execute(
            """
            SELECT count(*), count(DISTINCT idempotency_key)
            FROM mra.command_receipt
            WHERE command_kind = 'VERIFY_ARTIFACT'
            """
        ).fetchone()
    assert observations == [("VERIFIED",), ("SIZE_MISMATCH",)]
    assert receipts == (2, 2)


def test_orphan_gc_requires_two_scans_quarantine_and_explicit_delete(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
) -> None:
    application, store, _, database_url = artifact_stack
    orphan = store.publish_bytes(
        b"unbound physical bytes",
        media_type="application/octet-stream",
    )

    first = application.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="artifact-scanner",
    )
    assert first.observed == (orphan.content_sha256,)
    assert first.quarantined == ()
    assert store.object_path(orphan.content_sha256).exists()

    second = application.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="artifact-scanner",
    )
    assert second.quarantined == (orphan.content_sha256,)
    assert not store.object_path(orphan.content_sha256).exists()
    assert store.quarantine_path(orphan.content_sha256).exists()

    application.delete_quarantined(
        orphan.content_sha256,
        context=_context("delete-orphan", "DELETE_CONFIRMED_ORPHAN"),
    )
    assert not store.quarantine_path(orphan.content_sha256).exists()
    with psycopg.connect(database_url) as connection:
        candidate = connection.execute(
            """
            SELECT state, first_seen_at IS NOT NULL, second_seen_at IS NOT NULL,
                   quarantined_at IS NOT NULL, deleted_at IS NOT NULL
            FROM mra.artifact_gc_candidate
            WHERE content_sha256 = %s
            """,
            (orphan.content_sha256,),
        ).fetchone()
        audit_actions = connection.execute(
            """
            SELECT action FROM mra.audit_event
            WHERE aggregate_id = %s ORDER BY recorded_at
            """,
            (orphan.content_sha256,),
        ).fetchall()
    assert candidate == ("DELETED", True, True, True, True)
    assert ("DELETE_ARTIFACT_BYTES",) in audit_actions

    recreated = store.publish_bytes(
        b"unbound physical bytes",
        media_type="application/octet-stream",
    )
    assert recreated.content_sha256 == orphan.content_sha256
    application.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="artifact-scanner",
    )
    assert not store.object_path(orphan.content_sha256).exists()
    assert not store.quarantine_path(orphan.content_sha256).exists()
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT count(*) FROM mra.audit_event
            WHERE aggregate_id = %s
              AND action = 'RECONCILE_DELETED_ARTIFACT_BYTES'
            """,
            (orphan.content_sha256,),
        ).fetchone() == (1,)


def test_referenced_or_pinned_artifact_is_never_an_orphan_candidate(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
) -> None:
    application, _, _, database_url = artifact_stack
    registered = application.publish(
        b"pinned evidence",
        media_type="application/octet-stream",
        context=_context("publish-pinned", "REGISTER_TEST_ARTIFACT"),
        pin_reason_code="QUALIFICATION_EVIDENCE",
    )

    result = application.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="artifact-scanner",
    )

    assert registered.content_sha256 not in result.observed
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.artifact_gc_candidate"
        ).fetchone() == (0,)


def test_gc_candidate_is_cleared_when_a_canonical_reference_is_added(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
) -> None:
    artifacts, _, pool, database_url = artifact_stack
    config = artifacts.publish(
        b'{"runtime":"config"}',
        media_type="application/json",
        context=_context("publish-referenced-later", "REGISTER_RUNTIME_CONFIG"),
    )
    first_scan_id = uuid4()
    assert artifacts.scan_orphans(
        scan_id=first_scan_id,
        grace=timedelta(hours=1),
        actor_id="artifact-scanner",
    ).observed == (config.content_sha256,)

    runtime = RuntimeApplication(PostgresUnitOfWorkProvider(pool))
    schedule = ScheduleSpec(
        schedule_id=uuid4(),
        schedule_code="gc-reference",
        revision=1,
        runtime_mode=RuntimeMode.OPERATIONAL,
        schedule_expression=None,
        timezone_name="Asia/Shanghai",
        step_catalog_hash="a" * 64,
        enabled=True,
    )
    runtime.create_schedule(
        schedule,
        _context("gc-reference-schedule", "CREATE_RUNTIME_SCHEDULE"),
    )
    runtime.schedule_run(
        RunSpec(
            run_id=uuid4(),
            schedule_id=schedule.schedule_id,
            fire_key="gc-reference-run",
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
                implementation="tests.capture",
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
        _context("gc-reference-run", "SCHEDULE_RUNTIME_RUN"),
    )

    protected = artifacts.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(hours=1),
        actor_id="artifact-scanner",
    )
    assert protected.protected == (config.content_sha256,)
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT state FROM mra.artifact_gc_candidate WHERE content_sha256 = %s",
            (config.content_sha256,),
        ).fetchone() == ("CLEARED",)


def test_quarantine_pending_blocks_artifact_reactivation_after_filesystem_failure(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, store, _, database_url = artifact_stack
    registered = application.publish(
        b"registered orphan",
        media_type="application/octet-stream",
        context=_context("publish-registered-orphan", "REGISTER_TEST_ARTIFACT"),
    )
    application.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="artifact-scanner",
    )

    def fail_quarantine(_: str) -> None:
        raise OSError("injected quarantine failure")

    monkeypatch.setattr(store, "quarantine", fail_quarantine)
    with pytest.raises(OSError, match="injected quarantine failure"):
        application.scan_orphans(
            scan_id=uuid4(),
            grace=timedelta(0),
            actor_id="artifact-scanner",
        )

    with pytest.raises(ArtifactIntegrityError):
        application.verify(
            registered.artifact_id,
            verifier_id="artifact-test",
            context=_context("verify-pending-quarantine", "VERIFY_ARTIFACT"),
        )
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT candidate.state, artifact.integrity_state
            FROM mra.artifact_gc_candidate AS candidate
            JOIN mra.artifact AS artifact ON artifact.artifact_id = candidate.artifact_id
            """
        ).fetchone() == ("QUARANTINE_PENDING", "QUARANTINED")


def test_same_size_hash_corruption_is_distinguished_from_size_mismatch(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
) -> None:
    application, store, _, database_url = artifact_stack
    registered = application.publish(
        b"original",
        media_type="application/octet-stream",
        context=_context("publish-hash-check", "REGISTER_TEST_ARTIFACT"),
    )
    store.object_path(registered.content_sha256).write_bytes(b"tampered")

    with pytest.raises(ArtifactIntegrityError):
        application.verify(
            registered.artifact_id,
            verifier_id="artifact-test",
            context=_context("verify-hash-check", "VERIFY_ARTIFACT"),
        )
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT result
            FROM mra.artifact_verification
            ORDER BY verified_at DESC
            LIMIT 1
            """
        ).fetchone() == ("HASH_MISMATCH",)


def test_quarantine_pending_recovers_after_filesystem_failure(
    artifact_stack: tuple[ArtifactApplication, LocalArtifactStore, TargetPostgresPool, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, store, _, database_url = artifact_stack
    orphan = store.publish_bytes(
        b"recoverable orphan",
        media_type="application/octet-stream",
    )
    application.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="artifact-scanner",
    )
    original_quarantine = store.quarantine

    def fail_quarantine(_: str) -> None:
        raise OSError("injected quarantine failure")

    monkeypatch.setattr(store, "quarantine", fail_quarantine)
    with pytest.raises(OSError, match="injected quarantine failure"):
        application.scan_orphans(
            scan_id=uuid4(),
            grace=timedelta(0),
            actor_id="artifact-scanner",
        )
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT state FROM mra.artifact_gc_candidate"
        ).fetchone() == ("QUARANTINE_PENDING",)

    monkeypatch.setattr(store, "quarantine", original_quarantine)
    recovered = application.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="artifact-scanner",
    )
    assert recovered.quarantined == (orphan.content_sha256,)
    assert store.is_quarantined(orphan.content_sha256)
