from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import localcontext
from uuid import UUID

import pytest

from market_regime_alpha.market.domain.prospective_health import ProspectiveHealthSlice, project_prospective_health


NOW = datetime(2026, 9, 7, 8, tzinfo=UTC)


def _slice(index, **changes):
    return replace(ProspectiveHealthSlice(
        market_archive_id=UUID(int=1), market_archive_slice_id=UUID(int=index),
        window_start=NOW-timedelta(hours=2), window_end=NOW-timedelta(hours=1),
        terminal_state=None,
    ), **changes)


def test_health_distinguishes_success_timeliness_terminal_coverage_and_expected_denominator():
    states = ("CAPTURED_ON_TIME", "CAPTURED_LATE", "PROVIDER_GAP", "RESOURCE_STOP", "FAILED", "MISSED")
    slices = tuple(_slice(i+1, terminal_state=s) for i, s in enumerate(states)) + (
        _slice(7, window_end=NOW+timedelta(seconds=1)),
        _slice(8),
        _slice(9, window_start=NOW+timedelta(seconds=1), window_end=NOW+timedelta(minutes=1)),
    )
    with localcontext() as context:
        context.prec = 2
        result = project_prospective_health(observed_at=NOW, slices=slices, planning_gap_count=0)
    assert result["counts"]["expected"] == 9
    assert result["counts"]["opened_expected"] == 8
    assert result["counts"]["future"] == 1
    assert result["counts"]["due_backlog"] == 1
    assert result["counts"]["overdue_unterminalized"] == 1
    assert result["rates"]["capture_success"]["value"] == "0.250000000000"
    assert result["rates"]["on_time_capture"]["value"] == "0.125000000000"
    assert result["rates"]["terminal_coverage"]["value"] == "0.750000000000"
    assert all(r["denominator"] == 8 for r in result["rates"].values())
    assert result["rates"]["terminal_coverage"]["numerator"] == 6
    assert result["counts"]["successful_capture"] == 2


def test_not_due_is_normal_and_rates_are_not_estimable():
    result = project_prospective_health(observed_at=NOW, slices=(
        _slice(1, window_start=NOW+timedelta(seconds=1), window_end=NOW+timedelta(minutes=1)),
    ), planning_gap_count=0)
    assert result["operational_state"] == "NOT_DUE"
    assert result["alerts"] == ()
    assert all(r["state"] == "NOT_ESTIMABLE" and r["value"] is None and r["reason_code"] == "NO_OPENED_EXPECTED_WINDOWS" for r in result["rates"].values())


def test_exact_end_is_due_then_overdue_and_duplicate_slice_is_rejected():
    item = _slice(1, window_end=NOW)
    at_end = project_prospective_health(observed_at=NOW, slices=(item,), planning_gap_count=0)
    after_end = project_prospective_health(observed_at=NOW+timedelta(microseconds=1), slices=(item,), planning_gap_count=0)
    assert at_end["counts"]["due_backlog"] == 1
    assert after_end["counts"]["overdue_unterminalized"] == 1
    with pytest.raises(ValueError, match="duplicate"):
        project_prospective_health(observed_at=NOW, slices=(item, item), planning_gap_count=0)


def test_health_reports_unknown_effect_expired_lease_and_gap_without_success_promotion():
    item = _slice(1, latest_attempt_state="RUNNING", latest_attempt_error_code="EXTERNAL_EFFECT_UNKNOWN",
                  latest_attempt_lease_until=NOW, runtime_state="RECONCILIATION_REQUIRED")
    result = project_prospective_health(observed_at=NOW, slices=(item,), planning_gap_count=2)
    assert result["counts"]["unknown_external_effect"] == 1
    assert result["counts"]["expired_active_lease"] == 1
    assert result["counts"]["successful_capture"] == 0
    assert result["rates"]["capture_success"]["value"] == "0E-12"
    assert {a["reason_code"] for a in result["alerts"]} == {
        "OVERDUE_UNTERMINALIZED", "UNKNOWN_EXTERNAL_EFFECT", "LEASE_RECOVERY_REQUIRED", "PLANNING_GAPS",
    }


def test_health_keeps_first_observation_latest_revision_and_known_time_distinct():
    item = _slice(1, terminal_state="CAPTURED_ON_TIME", observation_count=2,
                  first_observed_at=NOW-timedelta(minutes=90), latest_observed_at=NOW-timedelta(seconds=3),
                  latest_known_at=NOW-timedelta(seconds=5, microseconds=125), latest_revision_observed_at=NOW-timedelta(seconds=2))
    result = project_prospective_health(observed_at=NOW, slices=(item,), planning_gap_count=0)
    assert result["counts"]["observations"] == 2
    assert result["counts"]["successful_capture"] == 1
    assert result["freshness"]["age_seconds"] == "5.000125"
    assert result["freshness"]["latest_known_at"] == item.latest_known_at
    assert result["freshness"]["market_event_freshness"] == "NOT_ESTIMABLE"


def test_runtime_reconciliation_state_is_visible_independently_of_error_spelling():
    result = project_prospective_health(observed_at=NOW, slices=(
        _slice(1, latest_attempt_state="RECONCILIATION_REQUIRED", latest_attempt_error_code="LEASE_EXPIRED_WITH_UNKNOWN_EFFECT", runtime_state="RUNNING"),
    ), planning_gap_count=0)
    assert result["counts"]["unknown_external_effect"] == 1
