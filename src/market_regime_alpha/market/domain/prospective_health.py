"""Deterministic operational counts, separate from research or Provider maturity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any
from uuid import UUID

from market_regime_alpha.market.domain.prospective_archive import ProspectiveArchiveDueState, ProspectiveArchiveTerminalState
from market_regime_alpha.shared.time import require_utc


@dataclass(frozen=True, slots=True)
class ProspectiveHealthSlice:
    market_archive_id: UUID
    market_archive_slice_id: UUID
    window_start: datetime
    window_end: datetime
    terminal_state: str | None
    observation_count: int = 0
    first_observed_at: datetime | None = None
    latest_observed_at: datetime | None = None
    latest_known_at: datetime | None = None
    latest_revision_observed_at: datetime | None = None
    latest_attempt_state: str | None = None
    latest_attempt_error_code: str | None = None
    latest_attempt_lease_until: datetime | None = None
    runtime_state: str | None = None

    def __post_init__(self) -> None:
        for name in ("window_start", "window_end", "first_observed_at", "latest_observed_at", "latest_known_at", "latest_revision_observed_at", "latest_attempt_lease_until"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_utc(value, field=name))
        if self.window_end < self.window_start:
            raise ValueError("health window is reversed")
        if self.terminal_state is not None:
            ProspectiveArchiveTerminalState(self.terminal_state)
        if type(self.observation_count) is not int or self.observation_count < 0:
            raise ValueError("health observation_count is invalid")


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    if not 0 <= numerator <= denominator:
        raise ValueError("health numerator exceeds opened expected windows")
    value = None
    if denominator:
        with localcontext() as context:
            context.prec = 38
            context.rounding = ROUND_HALF_EVEN
            value = str((Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000000000001")))
    return {
        "numerator": numerator, "denominator": denominator,
        "denominator_kind": "OPENED_EXPECTED_WINDOWS", "unit": "FRACTION",
        "state": "ESTIMABLE" if denominator else "NOT_ESTIMABLE", "value": value,
        "reason_code": None if denominator else "NO_OPENED_EXPECTED_WINDOWS",
    }


def project_prospective_health(
    *, observed_at: datetime, slices: tuple[ProspectiveHealthSlice, ...], planning_gap_count: int,
) -> dict[str, Any]:
    now = require_utc(observed_at, field="health observed_at")
    if len({item.market_archive_slice_id for item in slices}) != len(slices):
        raise ValueError("health roster contains a duplicate slice")
    if type(planning_gap_count) is not int or planning_gap_count < 0:
        raise ValueError("health planning_gap_count is invalid")
    counts = {state.value: 0 for state in ProspectiveArchiveTerminalState}
    counts.update(expected=len(slices), opened_expected=0, future=0, due_backlog=0,
                  overdue_unterminalized=0, successful_capture=0, terminal=0,
                  unknown_external_effect=0, expired_active_lease=0, runtime_failure=0,
                  observations=0, planning_gaps=planning_gap_count)
    known_times = []
    for item in slices:
        due = ProspectiveArchiveDueState.at(now=now, window_start=item.window_start, window_end=item.window_end)
        if due is ProspectiveArchiveDueState.NOT_DUE:
            if item.terminal_state is not None or item.observation_count:
                raise ValueError("future expected window already has an observed terminal effect")
            counts["future"] += 1
        else:
            counts["opened_expected"] += 1
            if item.terminal_state is None:
                counts["due_backlog" if due is ProspectiveArchiveDueState.DUE else "overdue_unterminalized"] += 1
        if item.terminal_state is not None:
            counts[item.terminal_state] += 1
            counts["terminal"] += 1
        if item.terminal_state in {"CAPTURED_ON_TIME", "CAPTURED_LATE"}:
            counts["successful_capture"] += 1
        if item.latest_attempt_error_code in {"EXTERNAL_EFFECT_UNKNOWN", "RECONCILIATION_REQUIRED"} or item.runtime_state == "RECONCILIATION_REQUIRED" or item.latest_attempt_state == "RECONCILIATION_REQUIRED":
            counts["unknown_external_effect"] += 1
        if item.latest_attempt_state in {"CLAIMED", "RUNNING"} and item.latest_attempt_lease_until is not None and item.latest_attempt_lease_until <= now:
            counts["expired_active_lease"] += 1
        if item.runtime_state in {"FAILED", "FAILED_TERMINAL"} or item.latest_attempt_state in {"FAILED", "FAILED_TERMINAL"}:
            counts["runtime_failure"] += 1
        counts["observations"] += item.observation_count
        if item.latest_known_at is not None:
            if item.latest_known_at > now:
                raise ValueError("health known-time exceeds PostgreSQL observation time")
            known_times.append(item.latest_known_at)
    alerts = tuple(
        {"reason_code": code, "severity": severity, "count": counts[key]}
        for key, code, severity in (
            ("due_backlog", "DUE_WORK_AVAILABLE", "INFO"),
            ("overdue_unterminalized", "OVERDUE_UNTERMINALIZED", "ERROR"),
            ("unknown_external_effect", "UNKNOWN_EXTERNAL_EFFECT", "ERROR"),
            ("expired_active_lease", "LEASE_RECOVERY_REQUIRED", "ERROR"),
            ("runtime_failure", "RUNTIME_FAILURE", "ERROR"),
            ("PROVIDER_GAP", "PROVIDER_GAPS", "WARNING"),
            ("RESOURCE_STOP", "RESOURCE_STOP", "ERROR"),
            ("FAILED", "CAPTURE_FAILURES", "ERROR"),
            ("MISSED", "MISSED_WINDOWS", "WARNING"),
            ("CAPTURED_LATE", "LATE_CAPTURES", "WARNING"),
            ("planning_gaps", "PLANNING_GAPS", "WARNING"),
        ) if counts[key]
    )
    last_known = max(known_times) if known_times else None
    age = None
    if last_known is not None:
        elapsed = now-last_known
        with localcontext() as context:
            context.prec = 38
            age = str(Decimal(elapsed.days*86400+elapsed.seconds) + Decimal(elapsed.microseconds)/Decimal(1_000_000))
    return {
        "counts": counts,
        "rates": {
            "capture_success": _rate(counts["successful_capture"], counts["opened_expected"]),
            "on_time_capture": _rate(counts["CAPTURED_ON_TIME"], counts["opened_expected"]),
            "terminal_coverage": _rate(counts["terminal"], counts["opened_expected"]),
        },
        "alerts": alerts,
        "operational_state": "ATTENTION_REQUIRED" if alerts else "NOT_DUE" if counts["future"] == counts["expected"] else "NO_OPEN_BACKLOG",
        "freshness": {
            "basis": "LATEST_CAPTURE_KNOWN_TIME", "latest_known_at": last_known,
            "age_seconds": age, "state": "ESTIMABLE" if age is not None else "NOT_ESTIMABLE",
            "reason_code": None if age is not None else "NO_CAPTURE_OBSERVATION",
            "market_event_freshness": "NOT_ESTIMABLE", "market_event_reason_code": "ACTUAL_EVENT_TIME_NOT_IN_HEALTH_INPUT",
        },
    }
