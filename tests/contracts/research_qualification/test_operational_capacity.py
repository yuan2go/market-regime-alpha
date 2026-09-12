from datetime import date, datetime, timezone

import pytest

from market_regime_alpha.research_qualification.domain.operational_capacity import operational_capacity
from tests.contracts.research_qualification.test_validity_capacity import _calendar


def test_reachability_keeps_budget_unknown_and_never_guarantees_future_samples():
    calendar = _calendar((date(2026, 9, 11), date(2026, 9, 14)))
    capacity = {"state": "PASS", "reason_codes": [], "calendar": {"use_lifetime_coverage_complete": True},
        "model_use_lifecycle": {"valid_from": datetime(2026, 9, 1, tzinfo=timezone.utc)},
        "minimum_sessions": 1, "minimum_observations": 32, "expected_members_per_session": 32,
        "observed_lower_bound": {"sessions": 0, "observations": 0},
        "remaining_attainable": {"future_session_roster": [date(2026, 9, 14)]}}
    args = dict(observed_at=datetime(2026, 9, 11, 8, tzinfo=timezone.utc))
    assert operational_capacity(capacity, calendar, **args)["state"] == "NOT_ESTIMABLE"
    result = operational_capacity(capacity, calendar, **args, collection_seconds=60, backup_seconds=180, publication_seconds=60)
    assert result["state"] == "READY" and result["future_observations_guaranteed"] is False
    # Independent arithmetic: Friday 08:00 UTC -> Monday 01:30 UTC = 235800 seconds.
    assert result["windows"][0]["publication_window_seconds"] == 235800
    assert operational_capacity(capacity, calendar, **args, collection_seconds=235600,
        backup_seconds=180, publication_seconds=60)["state"] == "EXPECTED_INSUFFICIENT"
    assert operational_capacity(capacity, calendar, **args, collection_seconds=28000,
        backup_seconds=900, publication_seconds=60)["state"] == "EXPECTED_INSUFFICIENT"


def test_one_missed_window_does_not_erase_later_sufficient_capacity():
    calendar = _calendar((date(2026, 9, 11), date(2026, 9, 14), date(2026, 9, 15)))
    capacity = {"state": "PASS", "reason_codes": [], "calendar": {"use_lifetime_coverage_complete": True},
        "model_use_lifecycle": {"valid_from": datetime(2026, 9, 1, tzinfo=timezone.utc)},
        "minimum_sessions": 1, "minimum_observations": 32, "expected_members_per_session": 32,
        "observed_lower_bound": {"sessions": 0, "observations": 0},
        "remaining_attainable": {"future_session_roster": [date(2026, 9, 14), date(2026, 9, 15)]}}
    result = operational_capacity(capacity, calendar,
        observed_at=datetime(2026, 9, 14, 1, 29, 55, tzinfo=timezone.utc),
        collection_seconds=60, backup_seconds=180, publication_seconds=60)
    assert result["state"] == "READY"
    assert result["budget_capacity"]["sessions"] == 1
    assert result["budget_capacity"]["excluded_windows"] == 1
    assert result["windows"][0]["state"] == "EXPECTED_INSUFFICIENT"


@pytest.mark.parametrize("minute,expected,seconds", [(30, "EXPECTED_INSUFFICIENT", 0),
    (28, "EXPECTED_INSUFFICIENT", 120), (24, "READY", 360), (None, "NOT_ESTIMABLE", None)])
def test_publication_budget_begins_only_when_frozen_model_use_is_effective(minute, expected, seconds):
    calendar = _calendar((date(2026, 9, 11), date(2026, 9, 14)))
    capacity = {"state": "PASS", "reason_codes": [], "calendar": {"use_lifetime_coverage_complete": True},
        "model_use_lifecycle": {"valid_from": None if minute is None else datetime(2026, 9, 14, 1, minute, tzinfo=timezone.utc)},
        "minimum_sessions": 1, "minimum_observations": 32, "expected_members_per_session": 32,
        "observed_lower_bound": {"sessions": 0, "observations": 0},
        "remaining_attainable": {"future_session_roster": [date(2026, 9, 14)]}}
    result = operational_capacity(capacity, calendar, observed_at=datetime(2026, 9, 11, 8, tzinfo=timezone.utc),
        collection_seconds=60, backup_seconds=180, publication_seconds=60)
    assert result["state"] == expected
    if seconds is None:
        assert "UNMEASURED_MODEL_USE_VALID_FROM" in result["reason_codes"]
    else:
        assert result["windows"][0]["publication_window_seconds"] == seconds


@pytest.mark.parametrize("bad", [0, -1, True, float("nan"), float("inf")])
def test_invalid_operational_budget_is_not_a_fallback(bad):
    with pytest.raises(ValueError, match="positive finite"):
        operational_capacity({}, [], observed_at=datetime.now(timezone.utc), collection_seconds=bad)
