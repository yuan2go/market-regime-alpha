"""Project-local lifecycle/backup orchestration; all business work stays in mra."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import shlex
import subprocess
import sys
from time import monotonic, sleep

from market_regime_alpha.bootstrap import TargetSettings
from market_regime_alpha.interfaces.prospective_operation_guard import ProspectiveOperationGuard, operational_session
from market_regime_alpha.interfaces.prospective_operations import load_operation_config, implementation_source_sha256
from market_regime_alpha.interfaces.deployment_profile import require_installation
from verify_prospective_artifacts import verify_scope
from market_regime_alpha.interfaces.daily_research import decode_daily_plan
from market_regime_alpha.infrastructure.postgres.queries.evidence import read_service_restart_state
from market_regime_alpha.interfaces.operational_reliability import (
    MAXIMUM_RESTART_REQUESTS, RECOVERY_BACKOFF_SECONDS, require_reconciled_restart, scheduled_fire_evidence,
)

HERE = Path(__file__).resolve().parent
DEPLOYMENT = json.loads((HERE / "deployment.json").read_text())
UID = os.getuid()
LABEL = DEPLOYMENT["label"]
TARGET = f"gui/{UID}/{LABEL}"
PROFILE = HERE / "operation.json"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
RECORDS = HERE / "receipts" / f"refresh-{STAMP}"
RECORDS.mkdir(mode=0o700)
MRA = [DEPLOYMENT["uv"], "run", "--no-project", "--python", DEPLOYMENT["runtime_python"], DEPLOYMENT["mra_executable"]]
events = []
restart_identity = None


def event(phase, **fields):
    row = {"phase": phase, "observed_at": datetime.now(timezone.utc).isoformat(), **fields}
    events.append(row)
    (RECORDS / "events.json").write_text(json.dumps(events, indent=2) + "\n")
    print(json.dumps(row, sort_keys=True), flush=True)


def command(name, args, *, required=True):
    with (RECORDS / (name + ".log")).open("xb") as output:
        result = subprocess.run(
            args, stdout=output, stderr=subprocess.STDOUT, check=False, timeout=3600 if name == "canonical-backup" else 180
        )
    event(name, exit_code=result.returncode)
    if required and result.returncode:
        raise RuntimeError(f"{name} failed; service stays stopped; inspect {RECORDS.name}")
    return result.returncode


def job():
    result = subprocess.run(["launchctl", "print", TARGET], capture_output=True, text=True, check=False, timeout=10)
    if result.returncode:
        return None
    match = re.search(r"^\s*pid = (\d+)\s*$", result.stdout, re.MULTILINE)
    return 0 if match is None else int(match.group(1))


def owned_job(*, expected=None):
    """Re-read the owned job and OS process; never act on a remembered PID."""
    pid = job()
    if not pid:
        return None
    result = subprocess.run(["ps", "-p", str(pid), "-o", "uid=", "-o", "lstart=", "-o", "command="],
                            capture_output=True, text=True, check=False, timeout=10)
    if result.returncode:
        if not job():
            return None
        raise ValueError("OWNED_SERVICE_PROCESS_IDENTITY_UNAVAILABLE")
    process = result.stdout.strip().split(maxsplit=6)
    if len(process) != 7 or int(process[0]) != UID:
        raise ValueError("OWNED_SERVICE_PROCESS_IDENTITY_MISMATCH")
    arguments = shlex.split(process[6])
    wrapper = arguments == ["/bin/sh", str(HERE / "launch.sh")]
    serving = (arguments[:len(MRA)] == MRA and arguments[len(MRA):len(MRA) + 3] == ["archive", "prospective", "serve"]
               and "--operation-config" in arguments
               and arguments[arguments.index("--operation-config") + 1:arguments.index("--operation-config") + 2] == [str(PROFILE)])
    if not (wrapper or serving) or job() != pid:
        raise ValueError("OWNED_SERVICE_PROCESS_IDENTITY_MISMATCH")
    identity = {"pid": pid, "uid": UID, "started": " ".join(process[1:6]),
                "command_sha256": hashlib.sha256(process[6].encode()).hexdigest(),
                "command_kind": "LAUNCH_WRAPPER" if wrapper else "CANONICAL_SERVICE"}
    if expected is not None and identity != expected:
        raise ValueError("OWNED_SERVICE_PID_STALE_OR_REPLACED")
    return identity


def prior_failure():
    for path in sorted((HERE / "logs").glob("service-*.jsonl"), key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True):
        rows = []
        for line in path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        terminal = next((row for row in reversed(rows) if row.get("stop_reason")), None)
        return {"source_log": path.name, "source_sha256": sha(path),
                "reason_code": terminal["stop_reason"] if terminal else "STOPPED_WITHOUT_OBSERVED_TERMINAL_REASON"}
    return {"reason_code": "SERVICE_LOG_UNAVAILABLE"}


def owner_restart_gate(guard):
    guard.session.require_supervisor_lock(guard.config.series_code)
    guard.verify_runtime_principal()
    state = read_service_restart_state(guard.connection)
    with (RECORDS / f"runtime-restart-observation-{len(events):04d}.json").open("x") as output:
        json.dump(state, output, indent=2, default=str)
        output.write("\n")
    event("runtime-restart-observation", observed_at_database=str(state["observed_at"]),
          unresolved_attempts=len(state["unresolved_attempts"]), waiting_work=len(state["waiting_work"]),
          historical_attempt_counts=state["historical_attempt_counts"], business_writes=0)
    require_reconciled_restart(state)


def renewed_backup_guard(guard, updated, snapshot):
    """A permitted backup renewal gets a fresh complete installation verification."""
    changed = {name for name, value in asdict(guard.config).items() if value != getattr(updated, name)}
    if changed - {"backup_directory", "backup_sha256", "backup_receipt_sha256"}:
        raise ValueError("BACKUP_RENEWAL_SCOPE_CHANGED")
    guard.session.require_supervisor_lock(guard.config.series_code)
    renewed = ProspectiveOperationGuard(guard.settings, updated, guard.session)
    renewed.verify_runtime_principal()
    renewed.verify_backup(snapshot)
    return renewed


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def observe_day_ledger(config, *, backup_directory):
    """Immutable scheduled observation; no new day or research fact is created."""
    if not DEPLOYMENT.get("daily_plan_template"):
        return
    command("day-ledger", MRA + ["research", "daily", "health", "--series-code", config.series_code,
        "--cutover-at", DEPLOYMENT["health_cutover_at"], "--recent-sessions", "5", "--replay"])
    ledger = json.loads((RECORDS / "day-ledger.log").read_text())
    if ledger["daily"]["business_writes"] != 0:
        raise ValueError("DAY_LEDGER_MUST_BE_READ_ONLY")
    logs = [{"file": path.name, "sha256": sha(path), "size_bytes": path.stat().st_size}
            for path in sorted((HERE / "logs").glob("service-*")) if path.suffix in {".jsonl", ".log"}]
    event("day-ledger-observed", ledger_sha256=sha(RECORDS / "day-ledger.log"),
          observed_at_database=ledger["daily"]["observed_at"], source_sha256=config.source_sha256,
          backup_directory=str(backup_directory), service_logs=logs,
          day_membership="CANONICAL_TRADING_SESSION_IDENTITIES_ONLY", business_writes=0)


def observe_restarted_tick(config, *, started_at):
    """Bound restart observation by the existing tick/wakeup budgets."""
    global restart_identity
    restart_identity = None
    deadline = monotonic() + config.maximum_tick_seconds + config.wakeup_seconds + 30
    expected_identity = None
    while monotonic() < deadline:
        identity = owned_job(expected=expected_identity)
        if identity is None:
            if expected_identity is not None:
                raise ValueError("BACKUP_RESTARTED_SERVICE_STOPPED")
            sleep(0.2)
            continue
        if identity["command_kind"] == "LAUNCH_WRAPPER":
            sleep(0.2)
            continue
        expected_identity = identity
        restart_identity = identity
        for path in sorted((HERE / "logs").glob("service-*.jsonl"), reverse=True):
            if path.stat().st_mtime < started_at.timestamp():
                continue
            rows = []
            for line in path.read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    # The writer can be between bytes of its next appended line.
                    continue
            preflight = next((row for row in rows if row.get("event") == "PROSPECTIVE_PREFLIGHT"), None)
            if preflight is None or preflight.get("configuration_sha256") != config.content_sha256:
                continue
            if datetime.fromisoformat(preflight["observed_at"]) < started_at:
                continue
            if any(row.get("stop_reason") for row in rows):
                raise ValueError("BACKUP_RESTARTED_SERVICE_STOPPED")
            tick = next((row for row in rows if row.get("event") == "PROSPECTIVE_TICK"
                         and row.get("configuration_sha256") == config.content_sha256
                         and datetime.fromisoformat(row["observed_at"]) >= datetime.fromisoformat(preflight["observed_at"])
                         and row.get("backup_observation", {}).get("receipt_sha256") == config.backup_receipt_sha256), None)
            if tick is not None:
                if not 0 <= tick["tick_elapsed_seconds"] <= config.maximum_tick_seconds:
                    raise ValueError("BACKUP_RESTART_TICK_EXCEEDED_BUDGET")
                rechecked_identity = owned_job(expected=expected_identity)
                if rechecked_identity is None:
                    raise ValueError("BACKUP_RESTARTED_SERVICE_STOPPED")
                with (RECORDS / "subsequent-tick.json").open("x") as output:
                    json.dump(tick, output, indent=2, sort_keys=True)
                    output.write("\n")
                proof = {"restart_requested_at": started_at.isoformat(),
                         "observed_at": datetime.now(timezone.utc).isoformat(),
                         "configuration_sha256": config.content_sha256, "backup_receipt_sha256": config.backup_receipt_sha256,
                         "maximum_tick_seconds": config.maximum_tick_seconds, "log_file": path.name, "preflight": preflight,
                         "owned_service_identity": identity, "rechecked_owned_service_identity": rechecked_identity}
                with (RECORDS / "restart-observation.json").open("x") as output:
                    json.dump(proof, output, indent=2, sort_keys=True)
                    output.write("\n")
                event("subsequent-tick", log_file=path.name,
                      restart_observation_sha256=sha(RECORDS / "restart-observation.json"),
                      tick_sha256=sha(RECORDS / "subsequent-tick.json"),
                      tick_elapsed_seconds=tick["tick_elapsed_seconds"],
                      tick_observed_at=tick["observed_at"], configuration_sha256=config.content_sha256,
                      backup_receipt_sha256=config.backup_receipt_sha256, owned_service_identity=identity)
                return
        sleep(0.2)
    raise ValueError("BACKUP_RESTART_TICK_NOT_OBSERVED_WITHIN_BUDGET")


def main():
    if sys.argv[1:] not in ([], ["--recover-stopped"], ["--scheduled"]):
        raise ValueError("Use --scheduled, --recover-stopped, or an explicit manual backup with no flags")
    invocation_kind = "MANUAL_CONTROLLED_RECOVERY" if "--recover-stopped" in sys.argv else "MANUAL_BACKUP"
    scheduler_pid = None
    fire_evidence = None
    scheduler_source = None
    if "--scheduled" in sys.argv:
        source = subprocess.run(["launchctl", "print", TARGET + ".backup-refresh"], capture_output=True, text=True,
                                check=False, timeout=10)
        match = re.search(r"^\s*pid = (\d+)\s*$", source.stdout, re.MULTILINE)
        scheduler_pid = None if match is None else int(match.group(1))
        if source.returncode or scheduler_pid not in {os.getpid(), os.getppid()}:
            raise ValueError("SCHEDULED_FIRE_SOURCE_UNVERIFIED")
        invocation_at = datetime.now(timezone.utc)
        fire_evidence = scheduled_fire_evidence(invocation_at)
        scheduler_source = {"target": TARGET + ".backup-refresh", "uid": UID, "job_pid": scheduler_pid,
                            "caller_pid": os.getpid(), "parent_pid": os.getppid()}
        invocation_kind = "SCHEDULED"
    else:
        invocation_at = datetime.now(timezone.utc)
    event("invocation", observed_at=invocation_at.isoformat(), invocation_kind=invocation_kind, scheduled_job_pid=scheduler_pid,
          scheduled_job_source=scheduler_source, scheduled_fire_evidence=fire_evidence,
          maximum_restart_requests=MAXIMUM_RESTART_REQUESTS, automatic_retry=False)
    if UID != DEPLOYMENT["uid"] or LABEL != "local.mra.prospective.r2-xshg32":
        raise ValueError("OPERATOR_SCOPE_MISMATCH")
    disabled = subprocess.run(["launchctl", "print-disabled", f"gui/{UID}"], capture_output=True, text=True, check=True, timeout=10).stdout
    if re.search(r'"' + re.escape(LABEL) + r'"\s*=>\s*(?:true|disabled)\b', disabled):
        raise ValueError("SERVICE_INTENTIONALLY_DISABLED")
    plist_path = Path(DEPLOYMENT["plist"])
    if plist_path.stat().st_uid != UID or plist_path.stat().st_mode & 0o077:
        raise ValueError("SUPERVISOR_FILE_OWNER_OR_MODE_MISMATCH")
    plist = plistlib.loads(plist_path.read_bytes())
    if plist["Label"] != LABEL or plist["ProgramArguments"] != ["/bin/sh", str(HERE / "launch.sh")]:
        raise ValueError("SUPERVISOR_COMMAND_MISMATCH")
    # Manual recovery uses the exact same private environment as supervision.
    for key in ("PATH", "MRA_DATABASE_URL", "MRA_ARTIFACT_ROOT", "MRA_POOL_MIN_SIZE", "MRA_POOL_MAX_SIZE"):
        os.environ[key] = plist["EnvironmentVariables"][key]
    config = load_operation_config(PROFILE)
    require_installation(config)
    if (config.database_name, config.database_oid, config.cluster_identity, config.source_sha256) != (
        DEPLOYMENT["database_name"],
        DEPLOYMENT["database_oid"],
        DEPLOYMENT["cluster_identity"],
        DEPLOYMENT["source_sha256"],
    ) or implementation_source_sha256() != config.source_sha256:
        raise ValueError("OPERATION_SCOPE_OR_SOURCE_MISMATCH")
    command(
        "current-scope",
        MRA
        + [
            "archive",
            "prospective",
            "status",
            "--series-code",
            config.series_code,
            "--expected-database-name",
            config.database_name,
            "--expected-database-oid",
            str(config.database_oid),
            "--expected-cluster-identity",
            config.cluster_identity,
        ],
    )
    running = owned_job()
    event("current-service-observation", state="RUNNING" if running else "STOPPED", owned_service_identity=running,
          prior_failure=prior_failure() if not running else None)
    if not running and "--recover-stopped" not in sys.argv:
        observe_day_ledger(config, backup_directory=config.backup_directory)
        raise ValueError("SERVICE_NOT_RUNNING_MANUAL_RECOVERY_REQUIRED")
    if running:
        event("owned-service-drain", owned_service_identity=running)
        if owned_job(expected=running) is None:
            raise ValueError("OWNED_SERVICE_PID_STALE_OR_REPLACED")
        command("sigterm", ["launchctl", "kill", "SIGTERM", TARGET])
        deadline = monotonic() + 180
        while owned_job(expected=running):
            if monotonic() >= deadline:
                raise RuntimeError("SERVICE_DID_NOT_DRAIN; no kill escalation or second writer")
            sleep(0.2)
    if job() is not None:
        command("unload", ["launchctl", "bootout", TARGET])
    # The same current Runtime admission reservation excludes racing claims
    # throughout the source snapshot. The backup itself has no business writes.
    destination = HERE / "backups" / f"original-{config.catalog_checksum[:12]}-{STAMP}"
    with operational_session(TargetSettings.from_environ(os.environ), config) as guard:
        owner_restart_gate(guard)
        snapshot = guard.snapshot()
        # Creating a new read-only backup does not depend on the old backup's
        # freshness. No owner append is allowed until the new bytes verify.
        command(
            "canonical-backup",
            MRA
            + [
                "evidence",
                "backup",
                "--directory",
                str(destination),
                "--expected-database-name",
                config.database_name,
                "--expected-database-oid",
                str(config.database_oid),
                "--minimum-free-bytes",
                str(config.minimum_free_bytes),
            ],
        )
        receipt = json.loads((destination / "receipt.json").read_text())
        updated = replace(
            config,
            backup_directory=str(destination),
            backup_sha256=receipt["backup_sha256"],
            backup_receipt_sha256=sha(destination / "receipt.json"),
        )
        guard = renewed_backup_guard(guard, updated, snapshot)
        daily_template = DEPLOYMENT.get("daily_plan_template")
        observations = verify_scope(
            TargetSettings.from_environ(os.environ), updated, guard, f"operation-refresh:{STAMP}",
            daily_plan=decode_daily_plan(Path(daily_template).read_bytes()) if daily_template else None,
        )
        event(
            "prospective-artifact-observations",
            observations=observations,
            capture_known_times_changed=False,
            observations_after_backup_snapshot=True,
        )
        # The destination is explicit local intent. Operators must verify the
        # physical failure domain; another path alone does not prove redundancy.
        mirror = Path(DEPLOYMENT["external_backup_directory"]) / destination.name
        required = sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())
        if shutil.disk_usage(mirror.parent).free < required + config.minimum_free_bytes:
            raise ValueError("BACKUP_MIRROR_DISK_RESERVE_EXHAUSTED")
        shutil.copytree(destination, mirror)
        for source in destination.rglob("*"):
            if source.is_file() and sha(source) != sha(mirror / source.relative_to(destination)):
                raise ValueError("BACKUP_MIRROR_BYTES_MISMATCH")
        previous = HERE / "profiles" / f"previous-{STAMP}.json"
        shutil.copy2(PROFILE, previous)
        pending = HERE / f".operation-{STAMP}.json"
        payload = json.dumps(asdict(updated), sort_keys=True, indent=2) + "\n"
        with pending.open("x") as output:
            pending.chmod(0o600)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        pending.replace(PROFILE)
        event(
            "profile-advanced",
            configuration_sha256=updated.content_sha256,
            backup_sha256=updated.backup_sha256,
            backup_receipt_sha256=updated.backup_receipt_sha256,
            previous_configuration_sha256=config.content_sha256,
            backup_file=str(destination),
            mirrored_backup_file=str(mirror),
        )
        observe_day_ledger(updated, backup_directory=destination)
        owner_restart_gate(guard)
    # One bounded preflight request. Failure does not restart or retry a Provider.
    if invocation_kind == "MANUAL_CONTROLLED_RECOVERY":
        event("controlled-recovery-backoff", seconds=RECOVERY_BACKOFF_SECONDS, restart_request=1)
        sleep(RECOVERY_BACKOFF_SECONDS)
    command(
        "preflight",
        MRA + ["archive", "prospective", "preflight", "--operation-config", str(PROFILE), "--expected-database-name", config.database_name]
        + (["--daily-plan-template", DEPLOYMENT["daily_plan_template"]] if DEPLOYMENT.get("daily_plan_template") else []),
    )
    with operational_session(TargetSettings.from_environ(os.environ), updated) as guard:
        owner_restart_gate(guard)
        guard.snapshot()
    if job() is not None:
        raise ValueError("SERVICE_REAPPEARED_BEFORE_OWNED_RESTART")
    started_at = datetime.now(timezone.utc)
    command("start", ["launchctl", "bootstrap", f"gui/{UID}", str(plist_path)])
    try:
        observe_restarted_tick(updated, started_at=started_at)
    except Exception:
        if restart_identity is not None and owned_job(expected=restart_identity):
            command("unverified-restart-drain", ["launchctl", "kill", "SIGTERM", TARGET], required=False)
        raise
    # Rotation follows controlled process restarts; old log originals stay intact.
    for source in (HERE / "logs").glob("service-*.jsonl"):
        compressed = source.with_suffix(source.suffix + ".gz")
        if not compressed.exists() and source.stat().st_mtime < previous.stat().st_mtime:
            with source.open("rb") as stream, gzip.open(compressed, "xb") as output:
                shutil.copyfileobj(stream, output)
    event("complete", status="PASS", continuous_service_proof="NOT_IMPLIED_BY_RESTART")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        event("failed", error_type=type(exc).__name__, reason=str(exc), automatic_retry=False)
        raise
