from __future__ import annotations

from io import StringIO
import json
from pathlib import Path

import psycopg

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.interfaces.cli import main
from market_regime_alpha.runtime.application import ActorType, CommandContext


def test_inventory_and_verify_are_read_only_and_detect_physical_corruption(
    target_database_url: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    settings = TargetSettings(target_database_url, root)
    bootstrap_database(settings)
    with bootstrap_application(settings) as application:
        artifact = application.artifacts.publish(
            b"immutable evidence",
            media_type="text/plain",
            context=CommandContext("evidence-test", ActorType.OPERATOR, "test", "TEST"),
        )
    environment = {"MRA_DATABASE_URL": target_database_url, "MRA_ARTIFACT_ROOT": str(root)}
    with psycopg.connect(target_database_url) as connection:
        before = connection.execute("SELECT count(*) FROM mra.command_receipt").fetchone()
    output = StringIO()
    assert main(["evidence", "inventory", "--role", "OPERATIONAL"], environ=environment, stdout=output) == 0
    inventory = json.loads(output.getvalue())
    assert inventory["authority"] == "NON_AUTHORITATIVE_OPERATIONAL_INDEX"
    assert inventory["database"]["logical_role"] == "OPERATIONAL"
    assert inventory["database"]["oid"] > 0
    assert inventory["database"]["cluster_identity"]
    assert inventory["schema"]["epoch"] == "MRA_REFOUNDATION_1"
    assert inventory["artifact_count"] == 1
    assert inventory["latest_successful_backup"] is None
    assert "password" not in output.getvalue().lower()
    output = StringIO()
    assert main(["evidence", "verify"], environ=environment, stdout=output) == 0
    result = json.loads(output.getvalue())
    assert result["matched"] is True
    assert result["mismatch_count"] == 0
    assert result["verified_artifacts"] == 1
    records = tmp_path / "operator-records"
    records.mkdir()
    scan_bytes = output.getvalue()
    (records / "integrity-scan-01.json").write_text(scan_bytes)
    wrong_scope = json.loads(scan_bytes)
    wrong_scope["database"]["oid"] += 1
    wrong_scope["observed_at"] = "2099-01-01T00:00:00+00:00"
    (records / "integrity-scan-02.json").write_text(json.dumps(wrong_scope))
    inventory_output = StringIO()
    assert main(["evidence", "inventory", "--records-directory", str(records)], environ=environment, stdout=inventory_output) == 0
    assert json.loads(inventory_output.getvalue())["artifact_root"] == inventory["artifact_root"]
    last_scan = json.loads(inventory_output.getvalue())["last_artifact_integrity_scan"]
    assert last_scan["observed_at"] == result["observed_at"]
    assert last_scan["matched"] is True
    assert last_scan["artifact_roster_sha256"] == result["artifact_roster_sha256"]
    (root / artifact.locator).write_bytes(b"corrupt")
    output = StringIO()
    assert main(["evidence", "verify"], environ=environment, stdout=output) == 2
    result = json.loads(output.getvalue())
    assert result["matched"] is False
    assert result["mismatches"][0]["reason"] == "ARTIFACT_BYTES_MISMATCH"
    with psycopg.connect(target_database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.command_receipt").fetchone() == before
        assert connection.execute("SELECT integrity_state FROM mra.artifact").fetchone() == ("AVAILABLE",)


def test_backup_snapshot_restores_exact_rows_and_bytes_in_a_distinct_scope(
    target_database_url: str,
    tmp_path: Path,
) -> None:
    from uuid import uuid4
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    root = tmp_path / "source"
    settings = TargetSettings(target_database_url, root)
    bootstrap_database(settings)
    with bootstrap_application(settings) as application:
        application.artifacts.publish(
            b"backup evidence",
            media_type="text/plain",
            context=CommandContext("backup-test", ActorType.OPERATOR, "test", "TEST"),
        )
        from market_regime_alpha.runtime.domain import ScheduleSpec, RuntimeMode
        for code in ("a-b", "a_b"):
            application.runtime.create_schedule(
                ScheduleSpec(uuid4(), code, 1, RuntimeMode.OPERATIONAL, None, "UTC", "1" * 64, False),
                CommandContext(code, ActorType.OPERATOR, "test", "TEST"),
            )
        identity = application.evidence.inventory()["database"]
    environment = {"MRA_DATABASE_URL": target_database_url, "MRA_ARTIFACT_ROOT": str(root)}
    bundle = tmp_path / "bundle"
    guard = ["--expected-database-name", identity["name"], "--expected-database-oid", str(identity["oid"])]
    output = StringIO()
    assert main(["evidence", "backup-plan", *guard, "--directory", str(bundle)], environ=environment, stdout=output) == 0
    assert json.loads(output.getvalue())["ready"] is True
    assert not bundle.exists()
    output = StringIO()
    assert main(["evidence", "backup", *guard, "--directory", str(bundle)], environ=environment, stdout=output) == 0
    receipt = json.loads(output.getvalue())
    assert receipt["snapshot_contract"] == "POSTGRES_EXPORTED_SNAPSHOT_AND_EXACT_ARTIFACT_ROSTER"
    assert receipt["backup_size_bytes"] > 0
    output = StringIO()
    assert main(["evidence", "inventory", "--records-directory", str(tmp_path)], environ=environment, stdout=output) == 0
    assert json.loads(output.getvalue())["latest_successful_backup"]["backup_sha256"] == receipt["backup_sha256"]
    restored_name = "mra_evidence_restore_test_" + uuid4().hex[:12]
    params = conninfo_to_dict(target_database_url)
    restored_url = make_conninfo(**{**params, "dbname": restored_name})
    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 LC_COLLATE 'en_US.UTF-8' LC_CTYPE 'en_US.UTF-8'").format(sql.Identifier(restored_name)))
        restored_oid = connection.execute("SELECT oid::bigint FROM pg_database WHERE datname=%s", (restored_name,)).fetchone()[0]
    try:
        restored_root = tmp_path / "restored-artifacts"
        restored_environment = {"MRA_DATABASE_URL": restored_url, "MRA_ARTIFACT_ROOT": str(restored_root)}
        output = StringIO()
        assert main(["evidence", "fresh-restore", "--bundle", str(bundle), "--disposable",
            "--expected-cluster-identity", identity["cluster_identity"], "--expected-backup-sha256", receipt["backup_sha256"],
            "--expected-database-name", restored_name, "--expected-database-oid", str(restored_oid)],
            environ=restored_environment, stdout=output) == 0, output.getvalue()
        checked = json.loads(output.getvalue())
        assert checked["matched"] is True
        assert checked["mismatch_count"] == 0
        assert checked["database"]["oid"] != identity["oid"]
        (bundle / "database.dump").write_bytes(b"not a backup")
        output = StringIO()
        assert main(["evidence", "restore-check", "--bundle", str(bundle)], environ=restored_environment, stdout=output) == 2
        assert json.loads(output.getvalue())["matched"] is False
    finally:
        with psycopg.connect(target_database_url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(restored_name)))
