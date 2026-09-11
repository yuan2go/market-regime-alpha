"""Process recovery cannot retry unresolved effects or upgrade manual evidence."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import hashlib

import pytest

from market_regime_alpha.interfaces.operational_reliability import require_reconciled_restart, scheduled_backup_reliability, scheduled_fire_evidence


def state():
    return {"observed_at": "2026-09-11T00:00:00+00:00", "unresolved_attempts": [], "waiting_work": [],
            "historical_attempt_counts": [{"state": "FAILED_TERMINAL", "count": 43}], "business_writes": 0}


def test_terminal_failures_are_retained_and_do_not_authorize_reopening():
    observed = state()
    before = deepcopy(observed)
    require_reconciled_restart(observed)
    assert observed == before


@pytest.mark.parametrize("case,reason", [("live", "ACTIVE_ATTEMPT"), ("expired", "EXPIRED_ATTEMPT"),
    ("fence", "FENCE_IDENTITY"), ("unknown", "UNKNOWN_EFFECT"), ("waiting", "UNKNOWN_EFFECT"), ("incomplete", "INCOMPLETE")])
def test_restart_refuses_every_unreconciled_runtime_case(case, reason):
    observed = state()
    if case == "waiting":
        observed["waiting_work"] = [{"run_id": "run", "step_id": "step"}]
    elif case == "incomplete":
        del observed["waiting_work"]
    else:
        observed["unresolved_attempts"] = [{"attempt_id": "a", "state": "RECONCILIATION_REQUIRED" if case == "unknown" else "RUNNING",
            "fence_token": 1, "current_fence": 2 if case == "fence" else 1, "current_attempt_id": "a", "lease_live": case == "live"}]
    with pytest.raises(ValueError, match=reason):
        require_reconciled_restart(observed)


PROFILE = "a" * 64
BACKUP = "b" * 64
IDENTITY = {"pid": 123, "uid": 501, "started": "Fri Sep 11 19:00:00 2026",
            "command_sha256": "c" * 64, "command_kind": "CANONICAL_SERVICE"}


def write_artifact(path, value):
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def receipt(directory, number, kind, *, fail=False, verified=True, terminal=True):
    path = directory / f"refresh-{number}" / "events.json"
    path.parent.mkdir()
    instant = datetime(2026, 9, 11, 11, tzinfo=timezone.utc) + timedelta(seconds=number)
    event = {"phase": "invocation", "observed_at": instant.isoformat(), "invocation_kind": kind}
    if kind == "SCHEDULED":
        event.update(scheduled_job_pid=123, scheduled_fire_evidence=scheduled_fire_evidence(instant),
            scheduled_job_source={"job_pid": 123, "uid": 501, "caller_pid": 124, "parent_pid": 123,
                                  "target": "gui/501/local.mra.prospective.r2-xshg32.backup-refresh"})
    events = [event]
    if kind is None:
        events = [{"phase": "current-scope", "observed_at": instant.isoformat()}]
    if verified:
        tick = {"event": "PROSPECTIVE_TICK", "observed_at": instant.isoformat(), "configuration_sha256": PROFILE,
                "backup_observation": {"receipt_sha256": BACKUP}, "tick_elapsed_seconds": 20}
        proof = {"restart_requested_at": instant.isoformat(), "observed_at": instant.isoformat(),
                 "configuration_sha256": PROFILE, "backup_receipt_sha256": BACKUP,
                 "maximum_tick_seconds": 120, "log_file": "service-observed.jsonl",
                 "preflight": {"event": "PROSPECTIVE_PREFLIGHT", "observed_at": instant.isoformat(), "configuration_sha256": PROFILE},
                 "owned_service_identity": IDENTITY, "rechecked_owned_service_identity": IDENTITY}
        tick_sha = write_artifact(path.parent / "subsequent-tick.json", tick)
        proof_sha = write_artifact(path.parent / "restart-observation.json", proof)
        events += [{"phase": "profile-advanced", "observed_at": instant.isoformat(), "configuration_sha256": PROFILE, "backup_receipt_sha256": BACKUP},
                   {"phase": "subsequent-tick", "observed_at": instant.isoformat(), "configuration_sha256": PROFILE,
                    "backup_receipt_sha256": BACKUP, "owned_service_identity": IDENTITY, "tick_sha256": tick_sha,
                    "restart_observation_sha256": proof_sha, "log_file": "service-observed.jsonl",
                    "tick_elapsed_seconds": 20, "tick_observed_at": instant.isoformat()}]
    if terminal:
        events += [{"phase": "failed" if fail else "complete", "observed_at": (instant + timedelta(seconds=30)).isoformat(),
                    "status": "FAIL" if fail else "PASS", "reason": "SERVICE_NOT_RUNNING_MANUAL_RECOVERY_REQUIRED" if fail else "PASS"}]
    path.write_text(json.dumps(events))
    return path


def test_summary_keeps_scheduled_failure_and_manual_recovery_separate(tmp_path):
    receipt(tmp_path, 1, "SCHEDULED", fail=True, verified=False)
    receipt(tmp_path, 2, "MANUAL_CONTROLLED_RECOVERY")
    receipt(tmp_path, 3, "SCHEDULED")
    receipt(tmp_path, 4, None)
    receipt(tmp_path, 5, "SCHEDULED", verified=False, terminal=False)
    before = {str(path): path.read_bytes() for path in tmp_path.glob("*/events.json")}
    result = scheduled_backup_reliability(tmp_path)
    summary = result["SCHEDULED_BACKUP_RELIABILITY"]
    assert (summary["scheduled_fires"], summary["completed"], summary["failed"], summary["restart_verified"]) == (3, 1, 1, 1)
    assert summary["incomplete_or_unverified"] == 1 and summary["duration_seconds"] == [30.0, 30.0]
    assert summary["numerator"] == 1 and summary["denominator"] == 3
    assert summary["latest_reason"] == "TERMINAL_RECEIPT_UNOBSERVED"
    assert summary["latest_failure_reason"] == "SERVICE_NOT_RUNNING_MANUAL_RECOVERY_REQUIRED"
    assert result["manual_receipt_count"] == result["unclassified_receipt_count"] == 1
    assert result["business_writes"] == 0
    assert {str(path): path.read_bytes() for path in tmp_path.glob("*/events.json")} == before


def test_summary_cannot_claim_restart_with_wrong_profile_or_backup(tmp_path):
    path = receipt(tmp_path, 1, "SCHEDULED")
    events = json.loads(path.read_text())
    events[2]["configuration_sha256"] = "old"
    path.write_text(json.dumps(events))
    summary = scheduled_backup_reliability(tmp_path)["SCHEDULED_BACKUP_RELIABILITY"]
    assert summary["completed"] == summary["restart_verified"] == 0
    assert summary["incomplete_or_unverified"] == 1


def test_empty_receipts_have_no_fabricated_scheduled_success(tmp_path):
    summary = scheduled_backup_reliability(tmp_path)["SCHEDULED_BACKUP_RELIABILITY"]
    assert summary["scheduled_fires"] == summary["numerator"] == summary["denominator"] == 0
    assert summary["state"] == "NOT_ESTIMABLE"
    assert summary["latest_failure_reason"] is None


@pytest.mark.parametrize("case", ["missing-tick", "changed-tick", "missing-proof", "changed-proof", "hash", "profile", "backup",
    "pid", "uid", "started", "command", "recheck", "event-pid", "time", "budget", "nan", "event-latency", "event-order"])
def test_summary_requires_physical_hash_bound_current_process_and_tick(tmp_path, case):
    path = receipt(tmp_path, 1, "SCHEDULED")
    events = json.loads(path.read_text())
    tick_path = path.parent / "subsequent-tick.json"
    proof_path = path.parent / "restart-observation.json"
    tick, proof = json.loads(tick_path.read_text()), json.loads(proof_path.read_text())
    if case == "missing-tick":
        tick_path.unlink()
    elif case == "changed-tick":
        tick_path.write_bytes(tick_path.read_bytes() + b" ")
    elif case == "missing-proof":
        proof_path.unlink()
    elif case == "changed-proof":
        proof_path.write_bytes(proof_path.read_bytes() + b" ")
    elif case == "hash":
        events[2]["tick_sha256"] = "0" * 64
    elif case in {"profile", "backup", "budget", "nan"}:
        if case == "profile":
            tick["configuration_sha256"] = "d" * 64
        elif case == "backup":
            tick["backup_observation"]["receipt_sha256"] = "d" * 64
        else:
            tick["tick_elapsed_seconds"] = 121 if case == "budget" else float("nan")
            events[2]["tick_elapsed_seconds"] = tick["tick_elapsed_seconds"]
        events[2]["tick_sha256"] = write_artifact(tick_path, tick)
    elif case == "event-latency":
        events[2]["tick_elapsed_seconds"] = 19
    elif case == "event-order":
        events[1], events[2] = events[2], events[1]
    elif case == "event-pid":
        events[2]["owned_service_identity"]["pid"] = 124
    else:
        if case == "time":
            proof["restart_requested_at"] = "2026-09-12T11:00:00+00:00"
        elif case == "recheck":
            proof["rechecked_owned_service_identity"]["pid"] = 124
        else:
            key = "command_sha256" if case == "command" else case
            proof["owned_service_identity"][key] = {"pid": 0, "uid": -1, "started": "invalid", "command": "invalid"}[case]
        events[2]["restart_observation_sha256"] = write_artifact(proof_path, proof)
    path.write_text(json.dumps(events))
    result = scheduled_backup_reliability(tmp_path)
    assert result["SCHEDULED_BACKUP_RELIABILITY"]["completed"] == 0
    assert not result["receipts"][0]["restart_verified"]
    assert result["receipts"][0]["reason_code"].startswith("BACKUP_RESTART_PROOF_")


@pytest.mark.parametrize("value,valid", [("2026-09-10T19:00:00+00:00", True), ("2026-09-11T11:04:59+00:00", True),
    ("2026-09-11T11:05:00+00:00", False), ("2026-09-11T10:59:59+00:00", False), ("2026-09-11T00:00:00+00:00", False)])
def test_schedule_provenance_has_exact_owned_calendar_fire_window(value, valid):
    if not valid:
        with pytest.raises(ValueError, match="FIRE_WINDOW_UNVERIFIED"):
            scheduled_fire_evidence(datetime.fromisoformat(value))
    else:
        evidence = scheduled_fire_evidence(datetime.fromisoformat(value))
        assert evidence["evidence_class"] == "OWNED_JOB_AND_SCHEDULE_WINDOW"
        assert evidence["limitation"] == "OPERATOR_KICK_WITHIN_WINDOW_INDISTINGUISHABLE"


@pytest.mark.parametrize("case", ["unmarked-source", "outside-window", "foreign-pid", "wrong-job", "wrong-window"])
def test_scheduled_marker_alone_does_not_prove_scheduler_fire(tmp_path, case):
    path = receipt(tmp_path, 1, "SCHEDULED")
    events = json.loads(path.read_text())
    if case == "unmarked-source":
        del events[0]["scheduled_job_source"]
    elif case == "outside-window":
        events[0]["observed_at"] = "2026-09-11T10:00:00+00:00"
    elif case == "foreign-pid":
        events[0]["scheduled_job_pid"] = 999
    elif case == "wrong-job":
        events[0]["scheduled_job_source"]["target"] = "foreign-job"
    else:
        events[0]["scheduled_fire_evidence"]["window_seconds"] = 3600
    path.write_text(json.dumps(events))
    result = scheduled_backup_reliability(tmp_path)
    assert result["SCHEDULED_BACKUP_RELIABILITY"]["scheduled_fires"] == 0
    assert result["unclassified_receipt_count"] == 1
