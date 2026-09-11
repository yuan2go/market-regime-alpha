"""Bounded process/receipt checks; Runtime alone owns recovery and fences."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo


RECOVERY_BACKOFF_SECONDS = 5
MAXIMUM_RESTART_REQUESTS = 1


def require_reconciled_restart(state: dict[str, Any]) -> None:
    """A restart request cannot interpret an unknown effect as a safe retry."""
    if state.get("business_writes") != 0 or "observed_at" not in state:
        raise ValueError("RESTART_OWNER_OBSERVATION_UNQUALIFIED")
    if state.get("waiting_work") or any(row["state"] == "RECONCILIATION_REQUIRED"
                                       for row in state.get("unresolved_attempts", ())):
        raise ValueError("RESTART_WAITING_UNKNOWN_EFFECT_OWNER_RECONCILIATION_REQUIRED")
    if "unresolved_attempts" not in state or "waiting_work" not in state:
        raise ValueError("RESTART_OWNER_OBSERVATION_INCOMPLETE")
    if state["unresolved_attempts"]:
        if any(row["fence_token"] != row["current_fence"] or row["attempt_id"] != row["current_attempt_id"]
               for row in state["unresolved_attempts"]):
            raise ValueError("RESTART_ATTEMPT_FENCE_IDENTITY_MISMATCH")
        reason = "ACTIVE_ATTEMPT" if any(row["lease_live"] for row in state["unresolved_attempts"]) else "EXPIRED_ATTEMPT"
        raise ValueError(f"RESTART_{reason}_OWNER_RECONCILIATION_REQUIRED")


def _instant(value: Any) -> datetime:
    result = datetime.fromisoformat(str(value))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("RELIABILITY_OBSERVATION_TIME_UNQUALIFIED")
    return result


SCHEDULE_WINDOW_SECONDS = 300
SCHEDULE_EVIDENCE_CLASS = "OWNED_JOB_AND_SCHEDULE_WINDOW"


def scheduled_fire_evidence(observed_at: datetime) -> dict[str, Any]:
    """A narrow fire window is evidence, not proof of launchd's internal cause."""
    local = _instant(observed_at).astimezone(ZoneInfo("Asia/Shanghai"))
    slot = local.replace(minute=0, second=0, microsecond=0)
    if local.hour not in {3, 19} or not slot <= local < slot + timedelta(seconds=SCHEDULE_WINDOW_SECONDS):
        raise ValueError("SCHEDULED_FIRE_WINDOW_UNVERIFIED")
    return {"evidence_class": SCHEDULE_EVIDENCE_CLASS, "scheduled_for": slot.isoformat(),
            "window_seconds": SCHEDULE_WINDOW_SECONDS, "timezone": "Asia/Shanghai",
            "limitation": "OPERATOR_KICK_WITHIN_WINDOW_INDISTINGUISHABLE"}


def _qualified_scheduled_invocation(start: dict[str, Any]) -> bool:
    try:
        pid = start["scheduled_job_pid"]
        source = start["scheduled_job_source"]
        return (type(pid) is int and pid > 0 and source["job_pid"] == pid
                and type(source["caller_pid"]) is int and source["caller_pid"] > 0
                and type(source["parent_pid"]) is int and source["parent_pid"] > 0
                and pid in {source["caller_pid"], source["parent_pid"]}
                and type(source["uid"]) is int and source["uid"] >= 0
                and source["target"] == f'gui/{source["uid"]}/local.mra.prospective.r2-xshg32.backup-refresh'
                and start["scheduled_fire_evidence"] == scheduled_fire_evidence(_instant(start["observed_at"])))
    except (KeyError, TypeError, ValueError):
        return False


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _artifact(directory: Path, name: str, expected_sha: Any) -> dict[str, Any]:
    path = directory / name
    if not path.is_file() or path.is_symlink():
        raise ValueError("BACKUP_RESTART_PROOF_ARTIFACT_MISSING")
    raw = path.read_bytes()
    if not _sha(expected_sha) or hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("BACKUP_RESTART_PROOF_ARTIFACT_HASH_MISMATCH")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("BACKUP_RESTART_PROOF_ARTIFACT_MALFORMED")
    return result


def _owned_identity(identity: dict[str, Any]) -> None:
    if (type(identity.get("pid")) is not int or identity["pid"] <= 0
            or type(identity.get("uid")) is not int or identity["uid"] < 0
            or not _sha(identity.get("command_sha256"))
            or identity.get("command_kind") != "CANONICAL_SERVICE"):
        raise ValueError("BACKUP_RESTART_PROOF_OWNED_IDENTITY_INVALID")
    datetime.strptime(identity["started"], "%a %b %d %H:%M:%S %Y")


def _restart_proof(directory: Path, events: list[dict[str, Any]]) -> tuple[bool, str]:
    try:
        selected = []
        for phase in ("invocation", "profile-advanced", "subsequent-tick", "complete"):
            indexes = [index for index, row in enumerate(events) if row.get("phase") == phase]
            if len(indexes) != 1:
                raise ValueError("BACKUP_RESTART_PROOF_EVENT_INCOMPLETE")
            selected.append(indexes[0])
        if selected != sorted(selected):
            raise ValueError("BACKUP_RESTART_PROOF_EVENT_ORDER_INVALID")
        start, advance, tick_event, ending = (events[index] for index in selected)
        if ending.get("status") != "PASS":
            raise ValueError("BACKUP_RESTART_PROOF_COMPLETION_UNQUALIFIED")
        tick = _artifact(directory, "subsequent-tick.json", tick_event["tick_sha256"])
        proof = _artifact(directory, "restart-observation.json", tick_event["restart_observation_sha256"])
        preflight = proof["preflight"]
        profile, receipt = advance["configuration_sha256"], advance["backup_receipt_sha256"]
        if (not _sha(profile) or not _sha(receipt) or tick.get("event") != "PROSPECTIVE_TICK"
                or preflight.get("event") != "PROSPECTIVE_PREFLIGHT"
                or any(row.get("configuration_sha256") != profile for row in (tick_event, tick, proof, preflight))
                or any(row.get("backup_receipt_sha256") != receipt for row in (tick_event, proof))
                or tick["backup_observation"].get("receipt_sha256") != receipt
                or tick["observed_at"] != tick_event["tick_observed_at"]
                or tick_event["log_file"] != proof["log_file"]):
            raise ValueError("BACKUP_RESTART_PROOF_BINDING_MISMATCH")
        identity = proof["owned_service_identity"]
        _owned_identity(identity)
        if start.get("invocation_kind") == "SCHEDULED" and identity["uid"] != start["scheduled_job_source"]["uid"]:
            raise ValueError("BACKUP_RESTART_PROOF_OWNED_IDENTITY_MISMATCH")
        if (identity != proof["rechecked_owned_service_identity"] or identity != tick_event["owned_service_identity"]):
            raise ValueError("BACKUP_RESTART_PROOF_OWNED_IDENTITY_MISMATCH")
        times = [_instant(value) for value in (start["observed_at"], advance["observed_at"], proof["restart_requested_at"],
                 preflight["observed_at"], tick["observed_at"], proof["observed_at"], tick_event["observed_at"], ending["observed_at"])]
        if times != sorted(times):
            raise ValueError("BACKUP_RESTART_PROOF_TIME_ORDER_INVALID")
        latency, maximum = tick["tick_elapsed_seconds"], proof["maximum_tick_seconds"]
        if (type(latency) not in {float, int} or type(maximum) not in {float, int}
                or not math.isfinite(latency) or not math.isfinite(maximum)
                or not 0 <= latency <= maximum <= 120 or maximum <= 0
                or tick_event["tick_elapsed_seconds"] != latency):
            raise ValueError("BACKUP_RESTART_PROOF_TICK_BUDGET_INVALID")
        return True, "VERIFIED_EXACT_PROFILE_RECEIPT_OWNED_PROCESS_AND_TICK_BYTES"
    except (OSError, KeyError, TypeError, ValueError) as exc:
        reason = str(exc)
        return False, reason if reason.startswith("BACKUP_RESTART_PROOF_") else "BACKUP_RESTART_PROOF_MALFORMED"


def scheduled_backup_reliability(receipts_directory: Path) -> dict[str, Any]:
    """Read physical proofs; an invocation marker alone cannot prove scheduling."""
    rows = []
    for path in sorted(receipts_directory.glob("refresh-*/events.json")):
        content = path.read_bytes()
        events = json.loads(content)
        if not isinstance(events, list) or not events:
            raise ValueError("BACKUP_EVENT_RECEIPT_MALFORMED")
        starts = [row for row in events if row.get("phase") == "invocation"]
        if len(starts) > 1:
            raise ValueError("BACKUP_EVENT_INVOCATION_DUPLICATE")
        start = starts[0] if starts else None
        kind = start.get("invocation_kind", "UNCLASSIFIED") if start else "UNCLASSIFIED"
        if kind not in {"SCHEDULED", "MANUAL_BACKUP", "MANUAL_CONTROLLED_RECOVERY", "UNCLASSIFIED"}:
            raise ValueError("BACKUP_EVENT_INVOCATION_UNKNOWN")
        invocation_reason = "EXPLICIT_MANUAL_INVOCATION" if kind.startswith("MANUAL_") else "INVOCATION_PROVENANCE_UNQUALIFIED"
        if kind == "SCHEDULED":
            if start is not None and _qualified_scheduled_invocation(start):
                invocation_reason = SCHEDULE_EVIDENCE_CLASS
            else:
                kind = "UNCLASSIFIED"
        terminal = [row for row in events if row.get("phase") in {"complete", "failed"}]
        if len(terminal) > 1:
            raise ValueError("BACKUP_EVENT_TERMINAL_DUPLICATE")
        ending = terminal[0] if terminal else None
        status = "PASS" if ending and ending["phase"] == "complete" and ending.get("status") == "PASS" else "FAIL" if ending else "INCOMPLETE"
        verified, proof_reason = _restart_proof(path.parent, events)
        duration = None
        if start and ending:
            duration = (_instant(ending["observed_at"]) - _instant(start["observed_at"])).total_seconds()
            if duration < 0:
                raise ValueError("BACKUP_EVENT_TIME_ORDER_INVALID")
        reason = ending.get("reason", ending.get("status")) if ending else "TERMINAL_RECEIPT_UNOBSERVED"
        if status == "PASS" and not verified:
            reason = proof_reason
        rows.append({"receipt": path.parent.name, "receipt_sha256": hashlib.sha256(content).hexdigest(),
                     "invocation_kind": kind, "invocation_reason_code": invocation_reason,
                     "observed_at": (start or events[0])["observed_at"],
                     "state": status, "restart_verified": verified, "restart_reason_code": proof_reason, "duration_seconds": duration,
                     "reason_code": reason})
    rows.sort(key=lambda row: _instant(row["observed_at"]))
    scheduled = [row for row in rows if row["invocation_kind"] == "SCHEDULED"]
    completed = sum(row["state"] == "PASS" and row["restart_verified"] for row in scheduled)
    failed = sum(row["state"] == "FAIL" for row in scheduled)
    return {"SCHEDULED_BACKUP_RELIABILITY": {
        "scheduled_fires": len(scheduled), "completed": completed, "failed": failed,
        "restart_verified": sum(row["restart_verified"] for row in scheduled),
        "incomplete_or_unverified": len(scheduled) - completed - failed,
        "duration_seconds": [row["duration_seconds"] for row in scheduled if row["duration_seconds"] is not None],
        "latest_reason": scheduled[-1]["reason_code"] if scheduled else "NO_CLASSIFIED_SCHEDULED_RECEIPT",
        "latest_failure_reason": next((row["reason_code"] for row in reversed(scheduled) if row["state"] == "FAIL"), None),
        "numerator": completed, "denominator": len(scheduled), "denominator_kind": "OBSERVED_SCHEDULED_FIRES",
        "evidence_class": SCHEDULE_EVIDENCE_CLASS,
        "limitation": "OPERATOR_KICK_WITHIN_WINDOW_INDISTINGUISHABLE",
        "state": "OBSERVED" if scheduled else "NOT_ESTIMABLE", "reason_code": "IMMUTABLE_INVOCATION_RECEIPTS" if scheduled else "NO_CLASSIFIED_SCHEDULED_RECEIPT",
    }, "unclassified_receipt_count": sum(row["invocation_kind"] == "UNCLASSIFIED" for row in rows),
        "manual_receipt_count": sum(row["invocation_kind"].startswith("MANUAL_") for row in rows),
        "receipts": rows, "business_writes": 0}
