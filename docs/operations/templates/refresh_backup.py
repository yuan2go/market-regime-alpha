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
import subprocess
import sys
from time import monotonic, sleep

from market_regime_alpha.bootstrap import TargetSettings
from market_regime_alpha.interfaces.prospective_operation_guard import operational_session
from market_regime_alpha.interfaces.prospective_operations import load_operation_config, implementation_source_sha256
from verify_prospective_artifacts import verify_scope

HERE = Path(__file__).resolve().parent
DEPLOYMENT = json.loads((HERE / "deployment.json").read_text())
UID = os.getuid()
LABEL = DEPLOYMENT["label"]
TARGET = f"gui/{UID}/{LABEL}"
PROFILE = HERE / "operation.json"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
RECORDS = HERE / "receipts" / f"refresh-{STAMP}"
RECORDS.mkdir(mode=0o700)
MRA = [DEPLOYMENT["uv"], "run", "--no-project", "--no-sync", "--python", DEPLOYMENT["runtime_python"], DEPLOYMENT["mra_executable"]]
events = []


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
    result = subprocess.run(["launchctl", "print", TARGET], capture_output=True, text=True, check=False)
    if result.returncode:
        return None
    match = re.search(r"^\s*pid = (\d+)\s*$", result.stdout, re.MULTILINE)
    return 0 if match is None else int(match.group(1))


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    if sys.argv[1:] not in ([], ["--recover-stopped"]):
        raise ValueError("Only explicit --recover-stopped is supported")
    if UID != DEPLOYMENT["uid"] or LABEL != "local.mra.prospective.r2-xshg32":
        raise ValueError("OPERATOR_SCOPE_MISMATCH")
    disabled = subprocess.run(["launchctl", "print-disabled", f"gui/{UID}"], capture_output=True, text=True, check=True).stdout
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
    running = job()
    if not running and "--recover-stopped" not in sys.argv:
        raise ValueError("SERVICE_NOT_RUNNING_MANUAL_RECOVERY_REQUIRED")
    if running:
        event("owned-service-drain", pid=running)
        command("sigterm", ["launchctl", "kill", "SIGTERM", TARGET])
        deadline = monotonic() + 180
        while job():
            if monotonic() >= deadline:
                raise RuntimeError("SERVICE_DID_NOT_DRAIN; no kill escalation or second writer")
            sleep(0.2)
    if job() is not None:
        command("unload", ["launchctl", "bootout", TARGET])
    # The same current Runtime admission reservation excludes racing claims
    # throughout the source snapshot. The backup itself has no business writes.
    destination = HERE / "backups" / f"original-{config.catalog_checksum[:12]}-{STAMP}"
    with operational_session(TargetSettings.from_environ(os.environ), config) as guard:
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
        guard.config = updated
        guard.verify_backup(snapshot)
        observations = verify_scope(TargetSettings.from_environ(os.environ), updated, guard, f"operation-refresh:{STAMP}")
        event(
            "prospective-artifact-observations",
            observations=observations,
            capture_known_times_changed=False,
            observations_after_backup_snapshot=True,
        )
        # Copy exact new snapshot to the other local physical device. Neither
        # copy is a writer or an automatically adopted database scope.
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
    # One bounded preflight request. Failure does not restart or retry a Provider.
    command(
        "preflight",
        MRA + ["archive", "prospective", "preflight", "--operation-config", str(PROFILE), "--expected-database-name", config.database_name],
    )
    command("start", ["launchctl", "bootstrap", f"gui/{UID}", str(plist_path)])
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
