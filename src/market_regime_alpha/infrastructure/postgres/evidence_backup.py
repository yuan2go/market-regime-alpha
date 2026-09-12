"""Offline evidence bundles bound to one exported PostgreSQL snapshot."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from market_regime_alpha.infrastructure.artifacts.evidence import FilesystemEvidenceIntegrity
from market_regime_alpha.infrastructure.postgres.queries.evidence import read_evidence_snapshot
from market_regime_alpha.shared.hashing import canonical_json_sha256


_CONTRACT = "POSTGRES_EXPORTED_SNAPSHOT_AND_EXACT_ARTIFACT_ROSTER"


def _table_hashes(connection: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    tables = connection.execute("""
        SELECT tablename FROM pg_tables WHERE schemaname = 'mra' ORDER BY tablename
    """).fetchall()
    result = []
    for (name,) in tables:
        digest = sha256()
        count = 0
        with connection.cursor(name="evidence_rows") as cursor:
            cursor.execute(sql.SQL("SELECT to_jsonb(t)::text FROM mra.{} t ORDER BY to_jsonb(t)::text COLLATE \"C\"").format(sql.Identifier(name)))
            for (row,) in cursor:
                digest.update(row.encode("utf-8") + b"\n")
                count += 1
        result.append({"table": name, "row_count": count, "ordered_sha256": digest.hexdigest()})
    return result


def _write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class PostgresEvidenceBackup:
    def __init__(self, database_url: str, artifact_root: Path) -> None:
        self._url = database_url
        self._root = artifact_root.resolve()

    def plan(self, directory: Path, *, expected_name: str, expected_oid: int, minimum_free_bytes: int) -> dict[str, Any]:
        if minimum_free_bytes < 0:
            raise ValueError("minimum_free_bytes must be non-negative")
        directory = directory.resolve()
        if directory == self._root or directory.is_relative_to(self._root):
            raise ValueError("backup destination must be outside the Artifact root")
        parent = directory.parent
        if not parent.is_dir() or directory.exists():
            raise ValueError("backup requires an existing parent and a fresh destination")
        with psycopg.connect(self._url) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            snapshot = read_evidence_snapshot(connection)
            size_row = connection.execute("SELECT pg_database_size(current_database())").fetchone()
            assert size_row is not None
            database_bytes = int(size_row[0])
        identity = snapshot["database"]
        if identity["name"] != expected_name or identity["oid"] != expected_oid:
            raise ValueError("backup database name/OID differs from exact operator intent")
        required = database_bytes + sum(item["size_bytes"] for item in snapshot["artifacts"]) + minimum_free_bytes
        free = shutil.disk_usage(parent).free
        return {
            "database": identity,
            "ready": snapshot["active_attempts"] == 0 and free >= required,
            "active_attempts": snapshot["active_attempts"],
            "free_bytes": free,
            "required_free_bytes": required,
            "snapshot_contract": _CONTRACT,
            "directory": str(directory),
        }

    def backup(self, directory: Path, *, expected_name: str, expected_oid: int, minimum_free_bytes: int) -> dict[str, Any]:
        plan = self.plan(directory, expected_name=expected_name, expected_oid=expected_oid, minimum_free_bytes=minimum_free_bytes)
        if not plan["ready"]:
            raise ValueError("backup preflight requires free disk and no active Runtime attempts")
        directory.mkdir()
        params = {key: str(value) for key, value in conninfo_to_dict(self._url).items() if value is not None}
        environment = dict(os.environ)
        password = params.pop("password", None)
        if password is not None:
            environment["PGPASSWORD"] = password
        with psycopg.connect(self._url) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL TIME ZONE 'UTC'")
            snapshot_row = connection.execute("SELECT pg_export_snapshot()").fetchone()
            assert snapshot_row is not None
            snapshot_id = str(snapshot_row[0])
            snapshot = read_evidence_snapshot(connection)
            if snapshot["database"] != plan["database"] or snapshot["active_attempts"]:
                raise ValueError("backup identity or active-attempt preflight changed")
            integrity = FilesystemEvidenceIntegrity(self._root).verify(snapshot["artifacts"])
            if not integrity["matched"]:
                raise ValueError("backup source Artifact bytes do not reconcile")
            tables = _table_hashes(connection)
            command = [
                "pg_dump",
                "--format=custom",
                "--snapshot=" + snapshot_id,
                "--file=" + str(directory / "database.dump"),
                "--dbname=" + make_conninfo("", **params),
            ]
            subprocess.run(command, env=environment, check=True, capture_output=True)
            for item in snapshot["artifacts"]:
                target = directory / "artifacts" / item["locator"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self._root / item["locator"], target)
                with target.open("rb") as stream:
                    os.fsync(stream.fileno())
            (directory / "artifacts").mkdir(exist_ok=True)
            copied = FilesystemEvidenceIntegrity(directory / "artifacts").verify(snapshot["artifacts"])
            if not copied["matched"] or copied["extra_object_count"]:
                raise ValueError("backup Artifact copy does not reconcile")
            _write_json(directory / "inventory.json", snapshot)
            subprocess.run(["pg_restore", "--list", str(directory / "database.dump")], check=True, capture_output=True)
            # Decode the complete archive, not just the table-of-contents header.
            subprocess.run(["pg_restore", "--file=" + os.devnull, str(directory / "database.dump")], check=True, capture_output=True)
            time_row = connection.execute("SELECT clock_timestamp()::text").fetchone()
            assert time_row is not None
            now = str(time_row[0])
        dump = (directory / "database.dump").read_bytes()
        receipt = {
            "snapshot_contract": _CONTRACT,
            "database": snapshot["database"],
            "source_artifact_root": str(self._root),
            "backup_sha256": sha256(dump).hexdigest(),
            "backup_size_bytes": len(dump),
            "inventory_sha256": sha256((directory / "inventory.json").read_bytes()).hexdigest(),
            "table_hashes": tables,
            "artifact_roster_sha256": canonical_json_sha256(snapshot["artifacts"]),
            "artifact_count": len(snapshot["artifacts"]),
            "verified_at": now,
            "unreferenced_objects_excluded": integrity["unreferenced_objects"],
        }
        _write_json(directory / "receipt.json", receipt)
        return receipt

    def restore_check(self, bundle: Path) -> dict[str, Any]:
        receipt = json.loads((bundle / "receipt.json").read_text())
        raw_inventory = (bundle / "inventory.json").read_bytes()
        snapshot = json.loads(raw_inventory)
        dump = (bundle / "database.dump").read_bytes()
        mismatches = []
        if self._root == Path(receipt["source_artifact_root"]).resolve():
            mismatches.append("RESTORE_REQUIRES_DISTINCT_ARTIFACT_ROOT")
        if sha256(dump).hexdigest() != receipt["backup_sha256"] or len(dump) != receipt["backup_size_bytes"]:
            mismatches.append("BACKUP_BYTES_MISMATCH")
        if sha256(raw_inventory).hexdigest() != receipt["inventory_sha256"]:
            mismatches.append("INVENTORY_BYTES_MISMATCH")
        if receipt["snapshot_contract"] != _CONTRACT:
            mismatches.append("UNSUPPORTED_SNAPSHOT_CONTRACT")
        with psycopg.connect(self._url) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL TIME ZONE 'UTC'")
            restored = read_evidence_snapshot(connection)
            if (restored["database"]["cluster_identity"], restored["database"]["oid"]) == (
                receipt["database"]["cluster_identity"],
                receipt["database"]["oid"],
            ):
                mismatches.append("RESTORE_REQUIRES_DISTINCT_DATABASE")
            if _table_hashes(connection) != receipt["table_hashes"]:
                mismatches.append("RESTORED_DATABASE_ROWS_MISMATCH")
        if restored["schema"] != snapshot["schema"] or restored["artifacts"] != snapshot["artifacts"]:
            mismatches.append("RESTORED_EVIDENCE_GENERATION_MISMATCH")
        integrity = FilesystemEvidenceIntegrity(self._root).verify(snapshot["artifacts"])
        mismatches.extend(item["reason"] for item in integrity["mismatches"])
        if integrity["extra_object_count"]:
            mismatches.append("RESTORED_EXTRA_ARTIFACT_BYTES")
        return {
            "matched": not mismatches,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches,
            "database": restored["database"],
            "verified_at": restored["observed_at"],
            "artifact_integrity": integrity,
            "backup_sha256": receipt["backup_sha256"],
        }

    def fresh_restore(self, bundle: Path, *, expected_name: str, expected_oid: int,
                      expected_cluster_identity: str, expected_backup_sha256: str) -> None:
        """Explicit empty disposable target only; never select or replace a writer."""
        receipt = json.loads((bundle / "receipt.json").read_text())
        inventory = (bundle / "inventory.json").read_bytes()
        dump = bundle / "database.dump"
        with dump.open("rb") as stream:
            import hashlib
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if (receipt["snapshot_contract"] != _CONTRACT or digest != expected_backup_sha256 or digest != receipt["backup_sha256"]
                or dump.stat().st_size != receipt["backup_size_bytes"]
                or sha256(inventory).hexdigest() != receipt["inventory_sha256"]):
            raise ValueError("RESTORE_BUNDLE_INTEGRITY_FAILED")
        snapshot = json.loads(inventory)
        physical = FilesystemEvidenceIntegrity(bundle / "artifacts").verify(snapshot["artifacts"])
        if not physical["matched"] or physical["extra_object_count"]:
            raise ValueError("RESTORE_ARTIFACT_ROSTER_INVALID")
        if self._root.exists() or self._root == Path(receipt["source_artifact_root"]).resolve():
            raise ValueError("RESTORE_REQUIRES_NEW_DISTINCT_ARTIFACT_ROOT")
        with psycopg.connect(self._url, autocommit=True) as connection:
            from market_regime_alpha.infrastructure.postgres.prospective_operation_session import _DATABASE_WRITER_KEY
            if connection.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))", (_DATABASE_WRITER_KEY,)).fetchone() != (True,):
                raise ValueError("RESTORE_TARGET_WRITER_ADMISSION_CONFLICT")
            identity = connection.execute("SELECT current_database(), oid::bigint, (pg_control_system()).system_identifier::text FROM pg_database WHERE datname=current_database()").fetchone()
            if identity != (expected_name, expected_oid, expected_cluster_identity):
                raise ValueError("RESTORE_TARGET_IDENTITY_CHANGED")
            if (identity[2], identity[1]) == (receipt["database"]["cluster_identity"], receipt["database"]["oid"]):
                raise ValueError("RESTORE_REQUIRES_DISTINCT_DATABASE")
            if connection.execute("SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f'))").fetchone() != (False,):
                raise ValueError("RESTORE_REQUIRES_EMPTY_DISPOSABLE_DATABASE")
            if connection.execute("""SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname NOT IN
                ('pg_catalog','information_schema','public','pg_toast')) OR EXISTS(
                SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public')""").fetchone() != (False,):
                raise ValueError("RESTORE_REQUIRES_PRISTINE_DATABASE_NAMESPACE")
            if connection.execute("SELECT count(*) FROM pg_stat_activity WHERE datid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND pid<>pg_backend_pid()").fetchone() != (0,):
                raise ValueError("RESTORE_TARGET_HAS_OTHER_CONNECTIONS")
            params = {key: str(value) for key, value in conninfo_to_dict(self._url).items() if value is not None}
            environment = dict(os.environ)
            password = params.pop("password", None)
            if password is not None:
                environment["PGPASSWORD"] = password
            try:
                subprocess.run(["pg_restore", "--exit-on-error", "--single-transaction",
                    "--dbname=" + make_conninfo("", **params), str(dump)], env=environment, check=True, capture_output=True)
            except subprocess.CalledProcessError as exc:
                raise ValueError("RESTORE_DATABASE_LOAD_FAILED") from exc
            shutil.copytree(bundle / "artifacts", self._root)

    def records(self, directory: Path, database: dict[str, Any]) -> dict[str, Any]:
        backups = []
        drills = []
        for path in sorted(directory.glob("*/receipt.json")):
            try:
                record = json.loads(path.read_text())
                identity = record["database"]
                if (identity["cluster_identity"], identity["oid"]) != (database["cluster_identity"], database["oid"]):
                    continue
                dump = path.parent / "database.dump"
                if dump.stat().st_size != record["backup_size_bytes"] or sha256(dump.read_bytes()).hexdigest() != record["backup_sha256"]:
                    continue
                if sha256((path.parent / "inventory.json").read_bytes()).hexdigest() != record["inventory_sha256"]:
                    continue
                backups.append(
                    {
                        "path": str(path.parent.resolve()),
                        "backup_sha256": record["backup_sha256"],
                        "backup_size_bytes": record["backup_size_bytes"],
                        "verified_at": record["verified_at"],
                    }
                )
                for result_path in sorted(path.parent.glob("restore-check-*.json")):
                    result = json.loads(result_path.read_text())
                    if result["matched"] is True and result["mismatch_count"] == 0 and result["backup_sha256"] == record["backup_sha256"]:
                        drills.append(result["verified_at"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
        scans = []
        for path in sorted(directory.glob("integrity-scan-*.json")):
            try:
                content = path.read_bytes()
                scan = json.loads(content)
                identity = scan["database"]
                if (identity["cluster_identity"], identity["oid"]) != (database["cluster_identity"], database["oid"]):
                    continue
                if scan["artifact_root"] != str(self._root) or not isinstance(scan["matched"], bool):
                    continue
                scans.append({
                    "path": str(path.resolve()), "report_sha256": sha256(content).hexdigest(),
                    "observed_at": scan["observed_at"], "matched": scan["matched"],
                    "mismatch_count": scan["mismatch_count"],
                    "artifact_roster_sha256": scan["artifact_roster_sha256"],
                })
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return {
            "latest_successful_backup": max(backups, key=lambda item: item["verified_at"], default=None),
            "last_restore_drill_at": max(drills, default=None),
            "last_artifact_integrity_scan": max(scans, key=lambda item: item["observed_at"], default=None),
        }
