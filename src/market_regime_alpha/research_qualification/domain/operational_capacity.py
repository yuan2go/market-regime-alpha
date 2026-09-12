"""Operational scenario over immutable cohort capacity, never future evidence."""

from datetime import datetime
from decimal import Decimal
from math import isfinite
from typing import Any

from market_regime_alpha.research_qualification.domain.validity_protocol import instant


def operational_capacity(capacity: dict[str, Any], calendar: list[dict[str, Any]], *,
                         observed_at: datetime, collection_seconds: float | None = None,
                         backup_seconds: float | None = None, publication_seconds: float | None = None,
                         outcome_grace_seconds: float = 28800) -> dict[str, Any]:
    budgets = {"collection_seconds": collection_seconds, "backup_seconds": backup_seconds,
               "publication_seconds": publication_seconds}
    for name, value in {**budgets, "outcome_grace_seconds": outcome_grace_seconds}.items():
        if value is not None and (type(value) not in {int, float} or not isfinite(value) or value <= 0):
            raise ValueError(name + " must be a positive finite measured scenario budget")
    missing = [name for name, value in budgets.items() if value is None]
    rows = sorted(calendar, key=lambda row: instant(row["open_at"]))
    if len({str(row["session_id"]) for row in rows}) != len(rows):
        raise ValueError("OPERATIONAL_CAPACITY_DUPLICATE_CALENDAR")
    reasons = list(capacity.get("reason_codes", ()))
    valid_from = capacity.get("model_use_lifecycle", {}).get("valid_from")
    if valid_from is None:
        missing.append("model_use_valid_from")
    windows = []
    budget_capacity = None
    for index, row in enumerate(rows):
        if row["session_date"] not in capacity.get("remaining_attainable", {}).get("future_session_roster", ()):
            continue
        if index == 0:
            reasons.append("PRECEDING_CAPTURED_SESSION_UNAVAILABLE")
            continue
        if valid_from is None:
            continue
        start = max(instant(rows[index - 1]["close_at"]), instant(observed_at), instant(valid_from))
        available = (instant(row["open_at"]) - start).total_seconds()
        windows.append({"target_session": row["session_date"], "publication_window_seconds": available,
                        "matures_at": row["close_at"], "automatic_outcome_grace_seconds": outcome_grace_seconds})
    state = "NOT_ESTIMABLE"
    if capacity.get("state") == "FAIL":
        state = "EXPECTED_INSUFFICIENT"
    if missing:
        reasons += ["UNMEASURED_" + name.upper() for name in missing]
    elif windows:
        assert collection_seconds is not None and backup_seconds is not None and publication_seconds is not None
        for window in windows:
            reason = ("COLLECTION_BACKUP_PUBLICATION_EXCEED_CAPTURED_WINDOW"
                if collection_seconds + backup_seconds + publication_seconds >= window["publication_window_seconds"] else
                "COLLECTION_BACKUP_EXCEED_AUTOMATIC_OUTCOME_GRACE"
                if collection_seconds + backup_seconds >= outcome_grace_seconds else None)
            window.update(state="EXPECTED_INSUFFICIENT" if reason else "READY", reason_code=reason)
        remaining = capacity.get("remaining_attainable", {})
        observed = capacity.get("observed_lower_bound", {})
        members = capacity.get("expected_members_per_session")
        if members is not None and "sessions" in observed and "observations" in observed:
            slots = sorted([members] * sum(window["state"] == "READY" for window in windows)
                + list(remaining.get("pending_exact_observation_counts", {}).values()))
            policy = capacity.get("robust", {}).get("policy")
            kept = slots[:max(0, len(slots) - policy["downtime_buffer_sessions"])] if policy else slots
            fraction = Decimal(policy["missing_observation_buffer_fraction"]) if policy else Decimal(0)
            sessions = observed["sessions"] + len(kept)
            observations = observed["observations"] + int(sum(kept) * (1 - fraction))
            budget_capacity = {"sessions": sessions, "observations": observations,
                "excluded_windows": sum(window["state"] != "READY" for window in windows),
                "buffer_policy": policy}
            if sessions < capacity["minimum_sessions"] or observations < capacity["minimum_observations"]:
                state = "EXPECTED_INSUFFICIENT"
                reasons.append("BUDGET_FEASIBLE_WINDOWS_BELOW_COHORT_FLOOR")
            elif capacity.get("state") == "PASS" and capacity.get("calendar", {}).get("use_lifetime_coverage_complete"):
                state = "READY"
        else:
            reasons.append("EXACT_SAMPLE_DENOMINATORS_UNAVAILABLE")
    if not windows and state != "EXPECTED_INSUFFICIENT":
        reasons.append("NO_CAPTURED_FUTURE_WINDOW")
    return {"state": state, "reason_codes": sorted(set(reasons)), "scenario_budgets": budgets,
            "budget_capacity": budget_capacity,
            "windows": windows, "cohort_capacity": capacity,
            "authority": "OPERATIONAL_SCENARIO_ONLY", "future_observations_guaranteed": False,
            "budget_evidence": "OPERATOR_SUPPLIED_MEASUREMENTS; NOT_PROVIDER_OR_RESEARCH_AUTHORITY",
            "successor_policy": "EXPLICIT_FUTURE_OWNER_REGISTRATION_AND_NEW_PROTOCOL_REQUIRED; NO_AUTOMATIC_EXTENSION"}
