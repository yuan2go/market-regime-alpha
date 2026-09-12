"""Read-only day ledger over original frozen work and reconciled owner reports."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any
from uuid import uuid5

from market_regime_alpha.interfaces.daily_research import decode_daily_plan, encode_daily_plan
from market_regime_alpha.shared.time import require_utc
from market_regime_alpha.research_qualification.domain.daily_inputs import DailyInputState


def daily_health(app: Any, *, cutover_at: datetime | None = None, recent_sessions: int = 5, replay: bool = False,
                 complete_history: bool = False) -> dict[str, Any]:
    reads = app.daily_prediction_reads
    facts = reads.operational_ledger_rows(complete_history=complete_history)
    now = facts["observed_at"]
    if type(recent_sessions) is not int or not 1 <= recent_sessions <= 120:
        raise ValueError("recent_sessions must be between 1 and 120")
    if cutover_at is not None:
        cutover_at = require_utc(cutover_at, field="health cutover_at")
        if cutover_at > now:
            raise ValueError("health cutover cannot be in the future")
    sessions = {s["session_id"]: s for s in facts["sessions"]}
    recent = [s for s in facts["sessions"] if s["open_at"] <= now][:recent_sessions]
    recent_ids = {s["session_id"] for s in recent}
    runs = {r["run_id"]: r for r in facts["runs"]}
    ledger = []
    for run in facts["runs"]:
        if not run["schedule_code"].startswith(("daily-model-", "daily-abstention-")):
            continue
        row: dict[str, Any] = {
            "run_id": run["run_id"],
            "requested_at": run["requested_at"],
            "runtime_state": run["state"],
            "state": "INTEGRITY_BLOCKED",
            "reason_code": None,
            "replay": {"state": "NOT_RUN"},
        }
        ledger.append(row)
        try:
            if run["plan_content"] is None:
                raise ValueError(run.get("plan_error", "FROZEN_PLAN_UNAVAILABLE"))
            plan = decode_daily_plan(run["plan_content"])
            if run["code_sha"] != plan.code_sha or run["run_id"] not in {
                plan.runtime_run_id,
                uuid5(plan.prediction_id, "abstention-runtime"),
            }:
                raise ValueError("FROZEN_RUNTIME_PLAN_IDENTITY_MISMATCH")
            target = sessions[plan.target_session_id]
            row.update(
                prediction_id=plan.prediction_id,
                input_session_id=plan.input_session_id,
                input_session=sessions[plan.input_session_id]["session_date"],
                target_session_id=plan.target_session_id,
                target_session=target["session_date"],
                target_window_start=target["open_at"],
                target_window_end=target["close_at"],
                plan_sha256=plan.content_sha256,
                model_version_id=plan.model_version_id,
                experimental_model_use_id=plan.experimental_model_use_id,
                target_definition_id=plan.target_definition_id,
                dataset_id=plan.dataset_id,
                decision_time=plan.decision_time,
                input_cutoff=plan.input_cutoff,
                sampled=len(plan.instrument_ids),
            )
            if run["state"] == "FAILED":
                row.update(state="FAILED_TERMINAL", reason_code=run["terminal_reason_code"])
                continue
            if run["state"] == "WAITING":
                row.update(state="WAITING_UNKNOWN_EFFECT", reason_code=run["terminal_reason_code"])
                continue
            if run["schedule_code"].startswith("daily-abstention-"):
                reason = app.daily_research.frozen_abstention_reason(plan)
                row.update(
                    state=("MISSED_PUBLICATION" if "MISSED_PUBLICATION" in reason else "ABSTAINED")
                    if run["state"] == "SUCCEEDED"
                    else "ABSTENTION_PENDING",
                    reason_code=reason,
                )
                continue
            if run["state"] != "SUCCEEDED":
                row.update(state="PUBLICATION_PENDING")
                continue
            frozen_inputs = reads.ready(plan)
            row["input_captures"] = [
                {
                    "instrument_id": m.instrument_id,
                    "capture_id": m.capture_id,
                    "bar_revision_id": m.bar_revision_id,
                    "known_at": m.known_at,
                    "recorded_at": m.recorded_at,
                    "state": m.state.value,
                    "reason_code": m.reason_code,
                    "source_gap_id": m.source_gap_id,
                }
                for m in frozen_inputs.members
            ]
            publication = reads.forecast_projection(plan)
            row.update(
                published_at=publication["published_at"],
                denominators=publication["denominators"],
                timely_publication=publication["published_at"] < target["open_at"],
            )
            row['population'] = publication['population']
            row['forecast_dispositions'] = [{k: member[k] for k in (
                'instrument_id','disposition','candidate_reason','forecast_status','forecast_reason',
                'baseline_status','baseline_reason')} for member in publication['predictions']]
            outcome = runs.get(uuid5(plan.prediction_id, "outcome-evaluation-runtime"))
            if outcome is None:
                if publication["denominators"]["model_prediction"] == 0:
                    row.update(state="EMPTY_PUBLICATION", reason_code="NO_PREDICTED_MEMBERS")
                    if replay:
                        row["replay"] = app.daily_research.replay(plan)
                    continue
                raise ValueError("PUBLISHED_PREDICTION_LACKS_OUTCOME_RUN")
            if outcome["plan_content"] != encode_daily_plan(plan):
                raise ValueError("PENDING_OUTCOME_FROZEN_PLAN_MISMATCH")
            row["outcome_run_id"] = outcome["run_id"]
            steps = [s for s in facts["steps"] if s["run_id"] == outcome["run_id"]]
            settled = [s for s in steps if s["step_key"].startswith("settle-")]
            completed = {s["step_key"] for s in steps if s["state"] == "SUCCEEDED"}
            row["outcome_completed_count"] = sum(s["state"] == "SUCCEEDED" for s in settled)
            row["outcome_expected_count"] = len(settled)
            row["evaluation_completed"] = "evaluate" in completed
            row["report_completed"] = "evaluation-report" in completed
            for label, keys in (
                ("outcome_completed_at", {s["step_key"] for s in settled}),
                ("evaluation_completed_at", {"evaluate"}),
                ("report_completed_at", {"evaluation-report"}),
            ):
                ids = {s["step_id"] for s in steps if s["step_key"] in keys}
                row[label] = max(
                    (a["finished_at"] for a in facts["attempts"] if a["step_id"] in ids and a["state"] == "SUCCEEDED"), default=None
                )

            if outcome["state"] == "FAILED":
                row.update(state="FAILED_TERMINAL", reason_code=outcome["terminal_reason_code"])
            elif outcome["state"] == "WAITING":
                row.update(state="WAITING_UNKNOWN_EFFECT", reason_code=outcome["terminal_reason_code"])
            elif outcome["state"] == "SUCCEEDED":
                row.update(state="COMPLETED", evaluation_id=uuid5(plan.prediction_id, "evaluation"))
                row["evaluation"] = reads.evaluation_projection(row["evaluation_id"])
            elif now < target["close_at"]:
                row["state"] = "PENDING_MATURITY"
            elif settled and all(s["state"] == "SUCCEEDED" for s in settled):
                row["state"] = "REPORT_PENDING" if row["evaluation_completed"] else "EVALUATION_PENDING"
            else:
                # Availability is read only for unfinished mature settlements.
                # Completed settlements never re-read Market inputs during health.
                members = reads.target_price_members(plan)
                available = all(
                    m.state in {DailyInputState.AVAILABLE, DailyInputState.SUSPENDED, DailyInputState.EXCLUDED} for m in members
                )
                row["state"] = "READY_FOR_SETTLEMENT" if available else "READY_FOR_OUTCOME_COLLECTION"
                if not available:
                    row["reason_code"] = "OUTCOME_DATA_UNOBSERVED"
            if replay:
                row["replay"] = (
                    app.daily_research.replay_completed_cycle(plan) if row["state"] == "COMPLETED" else app.daily_research.replay(plan)
                )
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            row.update(state="INTEGRITY_BLOCKED", reason_code=str(exc))
    scopes = {
        "ALL_HISTORY": ledger,
        "POST_CURRENT_CUTOVER": [r for r in ledger if cutover_at is not None and r["requested_at"] >= cutover_at],
        "LAST_N_TRADING_SESSIONS": [r for r in ledger if r.get("target_session_id") in recent_ids],
    }
    summaries = {name: _summary(rows) for name, rows in scopes.items()}
    for name, rows in scopes.items():
        scope_runs = {r["run_id"] for r in rows} | {r["outcome_run_id"] for r in rows if "outcome_run_id" in r}
        step_ids = {s["step_id"] for s in facts["steps"] if s["run_id"] in scope_runs}
        attempts = [a for a in facts["attempts"] if a["step_id"] in step_ids]
        summaries[name]["attempts"] = {
            "active": sum(a["state"] in {"CLAIMED", "RUNNING"} and a["lease_until"] > now for a in attempts),
            "expired": sum(a["state"] in {"CLAIMED", "RUNNING"} and a["lease_until"] <= now for a in attempts),
            "unknown": sum(a["state"] == "RECONCILIATION_REQUIRED" for a in attempts),
            "failed": sum(a["state"] == "FAILED_TERMINAL" for a in attempts),
        }
    if cutover_at is None:
        summaries["POST_CURRENT_CUTOVER"] = {"state": "NOT_ESTIMABLE", "reason_code": "CUTOVER_BOUNDARY_NOT_SUPPLIED"}
    if facts.get("history_truncated"):
        for name in summaries:
            if name == "POST_CURRENT_CUTOVER" and cutover_at is None:
                continue
            summaries[name].update(state="PARTIAL_DETAIL", complete=False,
                reason_code="RECENT_128_PUBLICATIONS_AND_CHILDREN; USE_BACKLOG_CURSOR_OR_COMPLETE_OBSERVATIONS")
    return {
        "authority": "READ_ONLY_OPERATIONAL_PROJECTION",
        "observed_at": now,
        "cutover_at": cutover_at,
        "cutover_membership": "ORIGINAL_PREDICTION_REQUESTED_AT; PENDING_WORK_IN_ALL_HISTORY",
        "recent_sessions": recent,
        "requested_recent_sessions": recent_sessions,
        "ledger": ledger,
        "complete_runtime_counts": facts.get("complete_runtime_counts"),
        "history_truncated": facts.get("history_truncated", False),
        "scopes": summaries,
        "capture_freshness": facts["freshness"],
        "artifact_verification": facts["artifact_verification"],
        "service_continuity": "REQUIRES_OWNED_SUPERVISOR_LOG_OBSERVATION",
        "business_writes": 0,
        "research_evidence": "DESCRIPTIVE / NOT_ALPHA_EVIDENCE",
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    published = [r for r in rows if "published_at" in r]
    denominator = len(rows)
    numerator = len(published)
    return {
        "state": "AVAILABLE",
        "prediction_requests": denominator,
        "published": numerator,
        "timely_publications": sum(r["timely_publication"] for r in published),
        "states": dict(Counter(r["state"] for r in rows)),
        "latest_publication_at": max((r["published_at"] for r in published), default=None),
        "outcomes_completed": sum(r.get("outcome_completed_count", 0) for r in rows),
        "evaluations_completed": sum(r.get("evaluation_completed", False) for r in rows),
        "latest_outcome_at": max((r["outcome_completed_at"] for r in rows if r.get("outcome_completed_at") is not None), default=None),
        "latest_evaluation_at": max(
            (r["evaluation_completed_at"] for r in rows if r.get("evaluation_completed_at") is not None), default=None
        ),
        "reports_completed": sum(r.get("report_completed", False) for r in rows),
        "replay_mismatches": sum(r["replay"].get("mismatch_count", 0) for r in rows),
        "replay_checked": sum("matched" in r["replay"] for r in rows),
        "publication_rate": {
            "numerator": numerator,
            "denominator": denominator,
            "denominator_kind": "DECLARED_PREDICTION_OR_ABSTENTION_REQUESTS",
            "state": "ESTIMABLE" if denominator else "NOT_ESTIMABLE",
            "reason_code": None if denominator else "NO_DECLARED_REQUESTS",
        },
    }
