"""Guard failures touch only a disposable database and its private byte root."""
from dataclasses import replace
from datetime import timedelta
import json
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.infrastructure.postgres.queries.evidence import read_evidence_snapshot
from market_regime_alpha.interfaces.prospective_operation_guard import operational_session
from market_regime_alpha.interfaces.prospective_operations import ProspectiveOperationConfig, implementation_source_sha256
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.shared.hashing import canonical_json_sha256
from tests.contracts.market.prospective_health_fixture import canonical_prospective_stack  # noqa: F401


def test_first_predeclare_requires_positive_frozen_series_before_any_write(
    request,
):
    from uuid import uuid4

    from market_regime_alpha.infrastructure.postgres.prospective_operation_session import (
        prospective_operation_session,
    )
    from market_regime_alpha.market.application import ArchiveOperatorManifest

    fixture = request.getfixturevalue("canonical_prospective_stack")
    app, settings = fixture.application, fixture.settings
    original = fixture.manifest
    generation = original.start_request.prospective_generation
    assert generation is not None
    archive_id = uuid4()
    foreign = ArchiveOperatorManifest(
        replace(
            original.start_request,
            market_archive_id=archive_id,
            archive_code="positive-series-counterexample",
            prospective_generation=replace(
                generation,
                market_archive_id=archive_id,
                series_code="intended_series",
                generation=1,
                predecessor_market_archive_id=None,
            ),
        ),
        original.slices,
    )
    identity = app.evidence.inventory()["database"]
    with fixture.pool.connection(read_only=True) as connection:
        before = connection.execute(
            "SELECT (SELECT count(*) FROM mra.artifact), "
            "(SELECT count(*) FROM mra.runtime_run), "
            "(SELECT count(*) FROM mra.market_archive), "
            "(SELECT count(*) FROM mra.prospective_archive_generation)"
        ).fetchone()
    with prospective_operation_session(
        settings.database_url,
        database_name=identity["name"],
        database_oid=identity["oid"],
        cluster_identity=identity["cluster_identity"],
        series_code="wrong_series",
    ):
        with pytest.raises(ValueError, match="OUTSIDE_SERIES"):
            app.prospective_archives.predeclare(
                foreign,
                code_sha="1" * 40,
                actor_id="positive-series-test",
                lease_duration=timedelta(seconds=30),
            )
    with fixture.pool.connection(read_only=True) as connection:
        after = connection.execute(
            "SELECT (SELECT count(*) FROM mra.artifact), "
            "(SELECT count(*) FROM mra.runtime_run), "
            "(SELECT count(*) FROM mra.market_archive), "
            "(SELECT count(*) FROM mra.prospective_archive_generation)"
        ).fetchone()
    assert after == before


@pytest.mark.usefixtures("canonical_prospective_stack")
@pytest.mark.parametrize("canonical_prospective_stack", ["interrupt_capture_registration"], indirect=True)
def test_service_recovers_partial_capture_registration_before_strict_health(request, tmp_path, monkeypatch):
    from dataclasses import asdict
    from importlib import import_module
    from io import StringIO
    from market_regime_alpha.interfaces.cli import main
    from market_regime_alpha.infrastructure.postgres.evidence_backup import _table_hashes
    from market_regime_alpha.runtime.errors import ArtifactIntegrityError

    fixture = request.getfixturevalue("canonical_prospective_stack")
    app, settings = fixture.application, fixture.settings
    assert fixture.registration is None
    with pytest.raises(ArtifactIntegrityError, match="canonical root/roster"):
        app.prospective_health.inspect("health_fixture")
    with fixture.pool.connection(read_only=True) as connection:
        snapshot = read_evidence_snapshot(connection)
    assert len(snapshot["prospective_generations"]) == 1
    bundle = tmp_path/"interrupted-backup"
    receipt = app.evidence.backup(bundle, expected_name=snapshot["database"]["name"],
        expected_oid=snapshot["database"]["oid"], minimum_free_bytes=1)
    generation = fixture.manifest.start_request.prospective_generation
    config = replace(config_for(settings, snapshot, bundle, receipt),
        series_code="health_fixture", target_definition_id=str(generation.target_definition_id),
        target_sha256=str(generation.target_definition_sha256))
    profile = tmp_path/"operation.json"
    profile.write_text(json.dumps(asdict(config)))
    module = import_module(main.__module__)
    # This is an editable-composition recovery drill. Installed-wheel/profile
    # admission is exercised separately against the frozen built artifact.
    monkeypatch.setattr(module, "require_installation", lambda _: None)
    monkeypatch.setattr(module, "verify_provider_access", lambda *_, **__: {"access": "SYNTHETIC_NO_DUE_FIXTURE"})
    arguments = ["archive", "prospective", "serve", "--operation-config", str(profile),
        "--series-code", config.series_code, "--code-sha", config.code_sha,
        "--expected-database-name", config.database_name, "--actor-id", config.actor_id,
        "--worker-id", config.worker_id, "--lease-seconds", str(config.lease_seconds),
        "--wakeup-seconds", str(config.wakeup_seconds), "--maximum-wakeups", "1"]
    environment = {"MRA_DATABASE_URL": settings.database_url, "MRA_ARTIFACT_ROOT": str(settings.artifact_root)}
    def invoke():
        output, errors = StringIO(), StringIO()
        assert main(arguments, environ=environment, stdout=output, stderr=errors) == 0, errors.getvalue()
        return [json.loads(line) for line in output.getvalue().splitlines()]
    rows = invoke()
    assert rows[0]["health"]["state"] == "OWNER_RECONCILIATION_PENDING"
    assert rows[1]["continuation"]["due_attempt_count"] == 0
    assert rows[1]["health"]["operational_state"] == "NOT_DUE"
    assert app.prospective_health.inspect("health_fixture")["summary"]["operational_state"] == "NOT_DUE"
    with fixture.pool.connection(read_only=True) as connection:
        before = _table_hashes(connection)
    invoke()
    with fixture.pool.connection(read_only=True) as connection:
        assert _table_hashes(connection) == before



def config_for(settings, snapshot, bundle, receipt):
    return ProspectiveOperationConfig(
        version=1, database_name=snapshot["database"]["name"], database_oid=snapshot["database"]["oid"],
        cluster_identity=snapshot["database"]["cluster_identity"], schema_epoch=snapshot["schema"]["epoch"],
        baseline_checksum=snapshot["schema"]["baseline_checksum"], catalog_checksum=snapshot["schema"]["catalog_checksum"],
        artifact_root_binding_sha256=str(canonical_json_sha256({
            "cluster_identity": snapshot["database"]["cluster_identity"], "database_oid": snapshot["database"]["oid"],
            "path": str(settings.artifact_root.resolve()),
        })), source_sha256=implementation_source_sha256(), series_code="operations-fixture",
        target_definition_id=str(UUID(int=1)), target_sha256="1"*64,
        backup_directory=str(bundle.resolve()), backup_sha256=receipt["backup_sha256"],
        backup_receipt_sha256=sha256((bundle/"receipt.json").read_bytes()).hexdigest(),
        maximum_backup_age_hours=24, minimum_free_bytes=1, minimum_calendar_sessions=3,
        maximum_pool_connections=4, provider_kind="BAOSTOCK_EXPLORATORY", provider_timeout_seconds=1,
        provider_maximum_rows=100_000, provider_maximum_response_bytes=33_554_432,
        maximum_attempts_per_tick=2, maximum_tick_seconds=60, code_sha="1"*40,
        actor_id="operator", worker_id="worker", lease_seconds=120, wakeup_seconds=1,
    )


@pytest.fixture
def guarded_scope(target_database_url, tmp_path):
    settings = TargetSettings(target_database_url, (tmp_path/"artifacts").resolve())
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        app.artifacts.publish(b"operation evidence", media_type="text/plain",
            context=CommandContext("guard-seed", ActorType.OPERATOR, "operator", "GUARD_TEST"))
        identity = app.evidence.inventory()["database"]
        bundle = tmp_path/"backup"
        receipt = app.evidence.backup(bundle, expected_name=identity["name"], expected_oid=identity["oid"],
                                      minimum_free_bytes=1)
    with psycopg.connect(target_database_url) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        snapshot = read_evidence_snapshot(connection)
    return settings, snapshot, config_for(settings, snapshot, bundle, receipt)


def test_exact_identity_duplicate_supervisor_and_disconnect_release(guarded_scope):
    settings, snapshot, config = guarded_scope
    for wrong in (replace(config, database_name="wrong"), replace(config, database_oid=config.database_oid+1),
                  replace(config, cluster_identity="1")):
        with pytest.raises(ValueError, match="DATABASE_IDENTITY"):
            with operational_session(settings, wrong):
                pytest.fail("wrong scope acquired the service")
    with operational_session(settings, config) as first:
        with pytest.raises(ValueError, match="DUPLICATE_SUPERVISOR"):
            with operational_session(settings, config):
                pytest.fail("second service entered")
        # No long business transaction spans the lifecycle lock.
        assert first.connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        first.before_action()
        first.connection.close()  # a worker crash releases its session lock
        with pytest.raises(ValueError, match="SUPERVISOR"):
            first.before_action()
    with operational_session(settings, config) as restarted:
        assert restarted.verify_backup(snapshot)["backup_sha256"] == config.backup_sha256
        assert restarted.connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        restarted.connection.execute("SELECT pg_advisory_unlock_all()")
        with pytest.raises(ValueError, match="SUPERVISOR"):
            restarted.before_action()
    with psycopg.connect(settings.database_url) as connection:
        assert read_evidence_snapshot(connection)["artifacts"] == snapshot["artifacts"]
        assert connection.execute("SELECT count(*) FROM mra.command_receipt").fetchone() == (1,)


def test_backup_bytes_scope_contract_and_age_fail_closed(guarded_scope):
    settings, snapshot, config = guarded_scope
    bundle = Path(config.backup_directory)
    receipt_bytes = (bundle/"receipt.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    with operational_session(settings, config) as guard:
        assert guard.verify_backup(snapshot)["artifact_count"] == 1
        corruptions = (
            ({**receipt, "database": {**receipt["database"], "oid": config.database_oid+1}}, "SCOPE"),
            ({**receipt, "snapshot_contract": "directory-is-enough"}, "CONTRACT"),
            ({**receipt, "verified_at": (guard.backup_verified_at-timedelta(hours=25)).isoformat()}, "EXPIRED"),
            ({**receipt, "verified_at": (guard.backup_verified_at+timedelta(hours=1)).isoformat()}, "EXPIRED"),
        )
        for damaged, reason in corruptions:
            (bundle/"receipt.json").write_text(json.dumps(damaged))
            # A separately pinned invalid intent must still fail semantic checks.
            guard.config = replace(config, backup_receipt_sha256=sha256((bundle/"receipt.json").read_bytes()).hexdigest())
            with pytest.raises(ValueError, match=reason):
                guard.verify_backup(snapshot)
        (bundle/"receipt.json").write_bytes(receipt_bytes)
        guard.config = config
        guard.verify_backup(snapshot)
        reference = snapshot["artifacts"][0]
        artifact = bundle/"artifacts"/reference["locator"]
        payload = artifact.read_bytes()
        artifact.write_bytes(b"corrupt")
        with pytest.raises(ValueError, match="ARTIFACT_MISMATCH"):
            guard.verify_backup(snapshot)
        artifact.write_bytes(payload)
        (bundle/"database.dump").write_bytes(b"not a database backup")
        with pytest.raises(ValueError, match="BACKUP_BYTES_MISMATCH"):
            guard.verify_backup(snapshot)


def test_fresh_verification_cannot_disguise_an_old_snapshot_or_unreadable_dump(guarded_scope):
    settings, snapshot, config = guarded_scope
    bundle = Path(config.backup_directory)
    receipt_bytes = (bundle/"receipt.json").read_bytes()
    inventory_bytes = (bundle/"inventory.json").read_bytes()
    receipt, inventory = json.loads(receipt_bytes), json.loads(inventory_bytes)
    from datetime import datetime
    inventory["observed_at"] = (datetime.fromisoformat(inventory["observed_at"])-timedelta(hours=25)).isoformat()
    (bundle/"inventory.json").write_text(json.dumps(inventory))
    receipt["inventory_sha256"] = sha256((bundle/"inventory.json").read_bytes()).hexdigest()
    (bundle/"receipt.json").write_text(json.dumps(receipt))
    with operational_session(settings, replace(config,
        backup_receipt_sha256=sha256((bundle/"receipt.json").read_bytes()).hexdigest())) as guard:
        with pytest.raises(ValueError, match="BACKUP_BASELINE_EXPIRED"):
            guard.verify_backup(snapshot)
    (bundle/"inventory.json").write_bytes(inventory_bytes)
    receipt = json.loads(receipt_bytes)
    invalid_dump = b"hash-matched but not a readable pg_dump archive"
    (bundle/"database.dump").write_bytes(invalid_dump)
    receipt["backup_sha256"] = sha256(invalid_dump).hexdigest()
    receipt["backup_size_bytes"] = len(invalid_dump)
    (bundle/"receipt.json").write_text(json.dumps(receipt))
    with operational_session(settings, replace(config, backup_sha256=receipt["backup_sha256"],
        backup_receipt_sha256=sha256((bundle/"receipt.json").read_bytes()).hexdigest())) as guard:
        with pytest.raises(ValueError, match="BACKUP_UNREADABLE"):
            guard.verify_backup(snapshot)


def test_pinned_backup_cannot_mix_new_inventory_with_the_old_dump(guarded_scope):
    settings, snapshot, config = guarded_scope
    bundle = Path(config.backup_directory)
    receipt = json.loads((bundle/"receipt.json").read_bytes())
    inventory = json.loads((bundle/"inventory.json").read_bytes())
    inventory["observed_at"] = receipt["verified_at"]
    inventory["prospective_generations"] = []
    (bundle/"inventory.json").write_text(json.dumps(inventory))
    receipt["inventory_sha256"] = sha256((bundle/"inventory.json").read_bytes()).hexdigest()
    (bundle/"receipt.json").write_text(json.dumps(receipt))
    with operational_session(settings, config) as guard:
        with pytest.raises(ValueError, match="BACKUP_RECEIPT_MISMATCH"):
            guard.verify_backup(snapshot)


def test_disk_pool_source_root_and_schema_mismatches_prevent_tick(guarded_scope, monkeypatch):
    from importlib import import_module
    module = import_module("market_regime_alpha.interfaces.prospective_operation_guard")
    settings, snapshot, config = guarded_scope
    with operational_session(settings, config) as guard:
        guard.check_resources()
        for changed, reason in (
            (replace(config, maximum_pool_connections=1), "CONNECTION_BUDGET"),
            (replace(config, source_sha256="0"*64), "IMPLEMENTATION"),
            (replace(config, artifact_root_binding_sha256="0"*64), "ROOT_MISMATCH"),
            (replace(config, catalog_checksum="0"*64), "SCHEMA_IDENTITY"),
        ):
            guard.config = changed
            with pytest.raises(ValueError, match=reason):
                if reason in {"ROOT_MISMATCH", "SCHEMA_IDENTITY"}:
                    guard.validate_scope(snapshot)
                else:
                    guard.check_resources()
        guard.config = config
        usage = module.shutil.disk_usage(settings.artifact_root)
        monkeypatch.setattr(module.shutil, "disk_usage", lambda _: usage._replace(free=0))
        with pytest.raises(ValueError, match="DISK_RESERVE"):
            guard.check_resources()


def test_complete_canonical_preflight_calendar_target_and_repeated_start_are_read_only(
    request, tmp_path,
):
    fixture = request.getfixturevalue("canonical_prospective_stack")
    settings, app = fixture.settings, fixture.application
    with psycopg.connect(settings.database_url) as connection:
        snapshot = read_evidence_snapshot(connection)
        receipts = connection.execute("SELECT count(*) FROM mra.command_receipt").fetchone()
    bundle = tmp_path/"canonical-backup"
    receipt = app.evidence.backup(bundle, expected_name=snapshot["database"]["name"],
        expected_oid=snapshot["database"]["oid"], minimum_free_bytes=1)
    generation = fixture.manifest.start_request.prospective_generation
    config = replace(config_for(settings, snapshot, bundle, receipt),
        series_code=generation.series_code, target_definition_id=str(generation.target_definition_id),
        target_sha256=str(generation.target_definition_sha256))
    for _ in range(2):
        with operational_session(settings, config) as guard:
            result = guard.verify_startup(app)
            assert result["ready"] is True
            assert result["calendar_session_count"] == 3
            assert result["generation_ids"] == (str(generation.market_archive_id),)
    with operational_session(settings, replace(config, minimum_calendar_sessions=4)) as guard:
        with pytest.raises(ValueError, match="CALENDAR_COVERAGE"):
            guard.verify_startup(app)
    with operational_session(settings, replace(config, target_sha256="0"*64)) as guard:
        with pytest.raises(ValueError, match="TARGET_IDENTITY"):
            guard.verify_startup(app)
    with psycopg.connect(settings.database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.command_receipt").fetchone() == receipts
        assert read_evidence_snapshot(connection)["artifacts"] == snapshot["artifacts"]
    assert list(settings.artifact_root.glob(".mra-operation-probe-*")) == []


def test_live_writer_blocks_but_expired_same_series_requires_owner_recovery(request, tmp_path):
    import time
    from tests.contracts.test_runtime_postgres import _context, _run, _schedule, _step
    fixture = request.getfixturevalue("canonical_prospective_stack")
    settings, app = fixture.settings, fixture.application
    with psycopg.connect(settings.database_url) as connection:
        snapshot = read_evidence_snapshot(connection)
    bundle = tmp_path/"single-writer-backup"
    receipt = app.evidence.backup(bundle, expected_name=snapshot["database"]["name"],
        expected_oid=snapshot["database"]["oid"], minimum_free_bytes=1)
    config = replace(config_for(settings, snapshot, bundle, receipt), series_code="health_fixture")
    run_id = fixture.registration.capture_run_ids[0]
    from market_regime_alpha.market.application import (
        compile_prospective_runtime_admission,
        compile_prospective_runtime_plan,
    )
    from market_regime_alpha.infrastructure.postgres.prospective_operation_session import (
        prospective_series_admission,
    )
    plan = compile_prospective_runtime_plan(fixture.manifest, code_sha="1" * 40)
    scope = compile_prospective_runtime_admission(fixture.manifest, plan, plan.runs)
    claim = app.runtime.claim_next(run_id=run_id, worker_id="crashed-same-series",
        lease_duration=timedelta(seconds=1), context=_context("guard-claim"))
    assert claim is not None
    with operational_session(settings, config) as guard:
        guard.session.allow_prospective_recovery((scope,))
        with pytest.raises(ValueError, match="ACTIVE_ATTEMPT_CONFLICT"):
            guard.snapshot()

        time.sleep(1.1)  # Actual PG lease expiry in an explicitly synthetic fixture.
        assert guard.snapshot()["active_attempts"] == 1
        # Guard inspection leaves the expired Attempt for the canonical owner.
        assert app.runtime.inspect_run(run_id).steps[0].attempt_states == ("CLAIMED",)
        with prospective_series_admission(scope):
            assert app.runtime.recover_expired(actor_id="operator", reason_code="GUARD_DRILL", run_id=run_id) == (claim.attempt_id,)
        assert guard.snapshot()["active_attempts"] == 0
    foreign_run = _run(app.runtime, app.artifacts, _schedule(app.runtime),
                       steps=(_step("foreign-step", 1),), key="foreign-research")
    foreign = app.runtime.claim_next(run_id=foreign_run, worker_id="unknown-worker",
        lease_duration=timedelta(seconds=1), context=_context("foreign-claim"))
    assert foreign is not None
    time.sleep(1.1)
    with operational_session(settings, config) as guard:
        with pytest.raises(ValueError, match="ACTIVE_ATTEMPT_CONFLICT"):
            guard.before_action()

def test_foreign_claim_after_last_check_cannot_enter_supervised_database(request, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from tests.contracts.test_runtime_postgres import _context

    fixture = request.getfixturevalue("canonical_prospective_stack")
    app, settings = fixture.application, fixture.settings
    snapshot = app.evidence.inventory()
    bundle = tmp_path / "atomic-admission-backup"
    receipt = app.evidence.backup(bundle, expected_name=snapshot["database"]["name"],
        expected_oid=snapshot["database"]["oid"], minimum_free_bytes=1)
    config = replace(config_for(settings, snapshot, bundle, receipt), series_code="health_fixture")
    run_id = fixture.registration.capture_run_ids[0]
    from market_regime_alpha.market.application import (
        compile_prospective_runtime_admission,
        compile_prospective_runtime_plan,
    )
    from market_regime_alpha.infrastructure.postgres.prospective_operation_session import (
        prospective_series_admission,
    )
    plan = compile_prospective_runtime_plan(fixture.manifest, code_sha="1" * 40)
    scope = compile_prospective_runtime_admission(fixture.manifest, plan, plan.runs)
    barrier = Barrier(2)

    def enter_after_check():
        barrier.wait(timeout=5)
        # Matching text is not ownership: another thread has no admitted session.
        return app.runtime.claim_next(run_id=run_id, worker_id=config.worker_id,
            lease_duration=timedelta(seconds=60), context=_context("foreign-after-check"))

    with operational_session(settings, config) as guard, ThreadPoolExecutor(max_workers=1) as executor:
        guard.before_action()
        with fixture.pool.connection(read_only=True) as connection:
            before = connection.execute("SELECT (SELECT count(*) FROM mra.runtime_attempt), "
                "(SELECT count(*) FROM mra.command_receipt), (SELECT count(*) FROM mra.audit_event)").fetchone()
        future = executor.submit(enter_after_check)
        barrier.wait(timeout=5)
        with pytest.raises(ValueError, match="OPERATION_RUNTIME_ADMISSION_CONFLICT"):
            future.result(timeout=10)
        with fixture.pool.connection(read_only=True) as connection:
            assert connection.execute("SELECT (SELECT count(*) FROM mra.runtime_attempt), "
                "(SELECT count(*) FROM mra.command_receipt), (SELECT count(*) FROM mra.audit_event)").fetchone() == before
        guard.before_action()
        with prospective_series_admission(scope):
            own = app.runtime.claim_next(run_id=run_id, worker_id=config.worker_id,
                lease_duration=timedelta(seconds=60), context=_context("own-after-foreign-refusal"))
        assert own is not None
        app.runtime.start_attempt(own, _context("own-start"))
        # A canonical admitted Attempt must remain usable before the Provider effect.
        guard.before_action()
        assert guard.snapshot()["active_attempts"] == 1
        guard.connection.close()
        with pytest.raises(ValueError, match="SUPERVISOR_CONNECTION_LOST"):
            app.runtime.claim_next(run_id=fixture.registration.capture_run_ids[1],
                worker_id=config.worker_id, lease_duration=timedelta(seconds=60),
                context=_context("claim-after-supervision-lost"))
        # Draining an already admitted effect retains its live Runtime fence.
        app.runtime.succeed_attempt(own, result_hash="a"*64, context=_context("own-drain"))
        assert app.runtime.inspect_run(run_id).steps[0].state == "SUCCEEDED"


def test_claim_commit_and_supervisor_start_share_atomic_admission(request, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from time import monotonic, sleep
    from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWork
    from tests.contracts.test_runtime_postgres import _context

    fixture = request.getfixturevalue("canonical_prospective_stack")
    app, settings = fixture.application, fixture.settings
    snapshot = app.evidence.inventory()
    bundle = tmp_path / "claim-start-race-backup"
    receipt = app.evidence.backup(bundle, expected_name=snapshot["database"]["name"],
        expected_oid=snapshot["database"]["oid"], minimum_free_bytes=1)
    config = replace(config_for(settings, snapshot, bundle, receipt), series_code="health_fixture")
    prepared, release = Event(), Event()
    original_commit = PostgresUnitOfWork.commit

    def held_commit(self):
        prepared.set()
        assert release.wait(timeout=10)
        original_commit(self)

    monkeypatch.setattr(PostgresUnitOfWork, "commit", held_commit)

    def start_supervisor():
        with operational_session(settings, config) as guard:
            guard.before_action()

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = executor.submit(app.runtime.claim_next,
            run_id=fixture.registration.capture_run_ids[0], worker_id="earlier-claimant",
            lease_duration=timedelta(seconds=60), context=_context("claim-before-admission"))
        assert prepared.wait(timeout=5)
        starting = executor.submit(start_supervisor)
        try:
            deadline = monotonic()+5
            with psycopg.connect(settings.database_url, autocommit=True) as observer:
                while True:
                    waiting = observer.execute("SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname=current_database() AND application_name='mra-prospective-supervisor' "
                        "AND wait_event='advisory'").fetchone()[0]
                    if waiting == 1:
                        break
                    assert monotonic() < deadline, "supervisor did not wait for the uncommitted claim"
                    sleep(0.01)
        finally:
            release.set()
        assert claimed.result(timeout=10) is not None
        with pytest.raises(ValueError, match="ACTIVE_ATTEMPT_CONFLICT"):
            starting.result(timeout=10)
