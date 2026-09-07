"""Fail-closed process guard around the existing Market/Runtime composition."""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import datetime, timedelta
import hashlib
from io import TextIOBase
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Iterator
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from market_regime_alpha.bootstrap import TargetApplication, TargetSettings, verify_database
from market_regime_alpha.infrastructure.artifacts.evidence import FilesystemEvidenceIntegrity
from market_regime_alpha.infrastructure.postgres.queries.evidence import read_evidence_snapshot
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockSdk, BaoStockSession
from market_regime_alpha.market.ports import MarketProviderError
from market_regime_alpha.interfaces.prospective_operations import (
    ProspectiveOperationConfig, implementation_source_sha256,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import TradingSessionId


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class _DiscardSdkOutput(TextIOBase):
    def write(self, text: str) -> int:
        return len(text)


@contextmanager
def quiet_provider_output() -> Iterator[None]:
    # SDK greetings/errors have no canonical status authority and may contain
    # local data. Do not buffer them or mix them into the JSON operator stream.
    with _DiscardSdkOutput() as sink, redirect_stdout(sink), redirect_stderr(sink):
        yield


def verify_provider_access(sdk: BaoStockSdk, *, timeout_seconds: float) -> dict[str, object]:
    try:
        with quiet_provider_output(), BaoStockSession(
            sdk, timeout_seconds=timeout_seconds, maximum_attempts=1,
        ):
            pass
    except (MarketProviderError, OSError) as exc:
        raise ValueError("OPERATION_PROVIDER_ACCESS_UNAVAILABLE") from exc
    return {"provider": "BAOSTOCK_EXPLORATORY", "access": "LOGIN_LOGOUT_SUCCEEDED",
            "capture_proven": False, "maximum_attempts": 1}


class ProspectiveOperationGuard:
    def __init__(self, settings: TargetSettings, config: ProspectiveOperationConfig,
                 connection: psycopg.Connection[Any]) -> None:
        self.settings, self.config, self.connection = settings, config, connection
        self.root = settings.artifact_root.resolve()
        self.backup_verified_at: datetime | None = None
        self.backup_snapshot_at: datetime | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.connection.transaction():
            self.connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            snapshot = read_evidence_snapshot(self.connection)
        self.validate_scope(snapshot)
        return snapshot

    def before_action(self) -> None:
        if self.connection.closed:
            raise ValueError("OPERATION_SUPERVISOR_CONNECTION_LOST")
        try:
            row = self.connection.execute(
                """WITH intent AS (SELECT hashtextextended(%s,0) AS key)
                   SELECT EXISTS (SELECT 1 FROM pg_locks, intent
                     WHERE pid=pg_backend_pid() AND locktype='advisory' AND granted
                       AND classid::bigint=((intent.key >> 32) & 4294967295)
                       AND objid::bigint=(intent.key & 4294967295) AND objsubid=1)""",
                ("operator:prospective-series:" + self.config.series_code,),
            ).fetchone()
        except psycopg.Error as exc:
            raise ValueError("OPERATION_SUPERVISOR_CONNECTION_LOST") from exc
        if row != (True,):
            raise ValueError("OPERATION_SUPERVISOR_LOCK_LOST")
        self.check_resources()

    def validate_scope(self, snapshot: dict[str, Any]) -> None:
        database = snapshot["database"]
        if (database["name"], database["oid"], database["cluster_identity"]) != (
            self.config.database_name, self.config.database_oid, self.config.cluster_identity,
        ):
            raise ValueError("OPERATION_DATABASE_IDENTITY_MISMATCH")
        schema = snapshot["schema"]
        if (schema["epoch"], schema["baseline_checksum"], schema["catalog_checksum"]) != (
            self.config.schema_epoch, self.config.baseline_checksum, self.config.catalog_checksum,
        ):
            raise ValueError("OPERATION_SCHEMA_IDENTITY_MISMATCH")
        binding = canonical_json_sha256({
            "cluster_identity": database["cluster_identity"], "database_oid": database["oid"],
            "path": str(self.settings.artifact_root.resolve()),
        })
        if str(binding) != self.config.artifact_root_binding_sha256:
            raise ValueError("OPERATION_ARTIFACT_ROOT_MISMATCH")
        if snapshot["active_attempts"]:
            conflict_row = self.connection.execute(
                """SELECT count(*) FROM mra.runtime_attempt AS attempt
                   JOIN mra.runtime_step AS step USING (step_id)
                   JOIN mra.runtime_run AS run ON run.run_id=step.run_id
                   WHERE attempt.state IN ('CLAIMED','RUNNING')
                     AND (attempt.lease_until > clock_timestamp() OR NOT EXISTS (
                       SELECT 1 FROM mra.prospective_archive_generation AS generation
                       WHERE generation.series_code=%s
                         AND run.fire_key LIKE 'archive:' || generation.market_archive_id::text || ':%%'
                     ))""", (self.config.series_code,),
            ).fetchone()
            if conflict_row is None or conflict_row[0]:
                raise ValueError("OPERATION_ACTIVE_ATTEMPT_CONFLICT")
        if not any(row["series_code"] == self.config.series_code for row in snapshot["prospective_generations"]):
            raise ValueError("OPERATION_SERIES_NOT_PREDECLARED")
        self.check_resources()

    def check_resources(self) -> None:
        if self.settings.artifact_root.resolve() != self.root or not self.root.is_dir():
            raise ValueError("OPERATION_ARTIFACT_ROOT_UNAVAILABLE")
        if shutil.disk_usage(self.root).free < self.config.minimum_free_bytes:
            raise ValueError("OPERATION_DISK_RESERVE_EXHAUSTED")
        if self.settings.pool_max_size > self.config.maximum_pool_connections:
            raise ValueError("OPERATION_CONNECTION_BUDGET_EXCEEDED")
        if implementation_source_sha256() != self.config.source_sha256:
            raise ValueError("OPERATION_IMPLEMENTATION_CHANGED")
        if self.backup_verified_at is not None:
            clock_row = self.connection.execute("SELECT clock_timestamp()").fetchone()
            if clock_row is None:
                raise ValueError("OPERATION_DATABASE_CLOCK_UNAVAILABLE")
            now = clock_row[0]
            for instant in (self.backup_verified_at, self.backup_snapshot_at):
                if instant is None:
                    raise ValueError("OPERATION_BACKUP_TIME_UNQUALIFIED")
                age = now - instant
                if age < timedelta(0) or age > timedelta(hours=self.config.maximum_backup_age_hours):
                    raise ValueError("OPERATION_BACKUP_BASELINE_EXPIRED")

    def verify_startup(self, application: TargetApplication) -> dict[str, Any]:
        snapshot = self.snapshot()
        schema = verify_database(self.settings)
        if str(schema.catalog_checksum) != self.config.catalog_checksum:
            raise ValueError("OPERATION_SCHEMA_VERIFICATION_MISMATCH")
        physical = FilesystemEvidenceIntegrity(self.root).verify(snapshot["artifacts"])
        if not physical["matched"]:
            raise ValueError("OPERATION_ARTIFACT_INTEGRITY_MISMATCH")
        # Probe only private temporary bytes; never publish an Artifact or fact.
        with tempfile.TemporaryDirectory(prefix=".mra-operation-probe-", dir=self.root) as directory:
            temporary = Path(directory) / "pending"
            payload = b"mra-research-operation-preflight"
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            published = temporary.with_name("verified")
            temporary.replace(published)
            if published.read_bytes() != payload:
                raise ValueError("OPERATION_ARTIFACT_WRITE_PROBE_FAILED")
        backup = self.verify_backup(snapshot)
        references = application.archive_continuity.generations(self.config.series_code)
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            generations = cursor.execute(
                "SELECT * FROM mra.prospective_archive_generation WHERE series_code=%s ORDER BY generation",
                (self.config.series_code,),
            ).fetchall()
        for generation in generations:
            if (str(generation["target_definition_id"]), generation["target_definition_sha256"]) != (
                self.config.target_definition_id, self.config.target_sha256,
            ):
                raise ValueError("OPERATION_TARGET_IDENTITY_MISMATCH")
            verification = application.archive_verification.verify(generation["market_archive_id"])
            if not verification.matched:
                raise ValueError("OPERATION_GENERATION_RECONCILIATION_FAILED")
        if tuple(row["market_archive_id"] for row in generations) != tuple(item.market_archive_id for item in references):
            raise ValueError("OPERATION_GENERATION_ROSTER_CHANGED")
        head = generations[-1]
        contract = application.target_archive_schedules.exact_contract(UUID(self.config.target_definition_id))
        if str(contract.content_sha256) != self.config.target_sha256:
            raise ValueError("OPERATION_TARGET_OWNER_MISMATCH")
        sessions = application.archive_trading_sessions.available_from(
            exchange=head["exchange_code"], session_id=TradingSessionId(head["decision_session_id"]), limit=512,
        )
        if (len(sessions) < self.config.minimum_calendar_sessions
                or not {head["decision_session_id"], head["outcome_session_id"], head["later_verification_session_id"]}
                <= {item.session_id.value for item in sessions}):
            raise ValueError("OPERATION_CALENDAR_COVERAGE_INCOMPLETE")
        return {
            "ready": True, "authority": "NON_AUTHORITATIVE_OPERATION_PREFLIGHT",
            "database": snapshot["database"], "observed_at": snapshot["observed_at"],
            "configuration_sha256": self.config.content_sha256,
            "source_sha256": self.config.source_sha256,
            "artifact_integrity": physical, "backup": backup,
            "calendar_session_count": len(sessions),
            "generation_ids": tuple(str(row["market_archive_id"]) for row in generations),
            "pool_connection_budget": self.config.maximum_pool_connections,
            "supervisor_connection_budget": 1,
        }

    def verify_backup(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        directory = Path(self.config.backup_directory)
        try:
            receipt_bytes = (directory / "receipt.json").read_bytes()
            inventory_bytes = (directory / "inventory.json").read_bytes()
            if hashlib.sha256(receipt_bytes).hexdigest() != self.config.backup_receipt_sha256:
                raise ValueError("OPERATION_BACKUP_RECEIPT_MISMATCH")
            receipt = json.loads(receipt_bytes)
            inventory = json.loads(inventory_bytes)
            identity = receipt["database"]
            if any(identity[key] != snapshot["database"][key] for key in ("name", "oid", "cluster_identity")):
                raise ValueError("OPERATION_BACKUP_SCOPE_MISMATCH")
            if any(inventory["database"][key] != identity[key] for key in ("name", "oid", "cluster_identity")):
                raise ValueError("OPERATION_BACKUP_SCOPE_MISMATCH")
            if Path(receipt["source_artifact_root"]).resolve() != self.root:
                raise ValueError("OPERATION_BACKUP_ARTIFACT_ROOT_MISMATCH")
            if receipt["snapshot_contract"] != "POSTGRES_EXPORTED_SNAPSHOT_AND_EXACT_ARTIFACT_ROSTER":
                raise ValueError("OPERATION_BACKUP_CONTRACT_UNSUPPORTED")
            if (receipt["backup_sha256"] != self.config.backup_sha256
                    or _digest(directory / "database.dump") != self.config.backup_sha256
                    or (directory / "database.dump").stat().st_size != receipt["backup_size_bytes"]
                    or hashlib.sha256(inventory_bytes).hexdigest() != receipt["inventory_sha256"]
                    or str(canonical_json_sha256(inventory["artifacts"])) != receipt["artifact_roster_sha256"]):
                raise ValueError("OPERATION_BACKUP_BYTES_MISMATCH")
            physical = FilesystemEvidenceIntegrity(directory / "artifacts").verify(inventory["artifacts"])
            if not physical["matched"]:
                raise ValueError("OPERATION_BACKUP_ARTIFACT_MISMATCH")
            self.backup_verified_at = datetime.fromisoformat(receipt["verified_at"])
            self.backup_snapshot_at = datetime.fromisoformat(inventory["observed_at"])
            if self.backup_verified_at.tzinfo is None or self.backup_snapshot_at.tzinfo is None:
                raise ValueError("OPERATION_BACKUP_TIME_UNQUALIFIED")
            self.check_resources()
            if self.backup_verified_at < self.backup_snapshot_at:
                raise ValueError("OPERATION_BACKUP_TIME_UNQUALIFIED")
            subprocess.run(["pg_restore", "--list", str(directory/"database.dump")], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, KeyError, TypeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            raise ValueError("OPERATION_BACKUP_UNREADABLE") from exc
        return {
            "backup_sha256": self.config.backup_sha256, "verified_at": receipt["verified_at"],
            "backup_receipt_sha256": self.config.backup_receipt_sha256,
            "snapshot_contract": receipt["snapshot_contract"], "artifact_count": receipt["artifact_count"],
            "snapshot_observed_at": inventory["observed_at"], "pg_restore_readability": "PASS",
        }


@contextmanager
def operational_session(settings: TargetSettings, config: ProspectiveOperationConfig) -> Iterator[ProspectiveOperationGuard]:
    """One session-level operator lock, with no idle business transaction."""
    with psycopg.connect(settings.database_url, autocommit=True,
                         application_name="mra-prospective-supervisor") as connection:
        row = connection.execute(
            "SELECT current_database(), oid::bigint, (pg_control_system()).system_identifier::text "
            "FROM pg_database WHERE datname=current_database()",
        ).fetchone()
        if row != (config.database_name, config.database_oid, config.cluster_identity):
            raise ValueError("OPERATION_DATABASE_IDENTITY_MISMATCH")
        key = "operator:prospective-series:" + config.series_code
        locked = connection.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))", (key,)).fetchone()
        if locked != (True,):
            raise ValueError("OPERATION_DUPLICATE_SUPERVISOR")
        try:
            yield ProspectiveOperationGuard(settings, config, connection)
        finally:
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))
