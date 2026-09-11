"""Capacity uses exact supplied calendar facts, never inferred trading days."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import localcontext
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.application.validity import validity_report
from market_regime_alpha.research_qualification.domain.validity_protocol import (
    cohort_capacity, load_validity_protocol, validate_protocol_revision,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


NOW = datetime(2026, 9, 11, 1, tzinfo=timezone.utc)


def _calendar(days):
    return [{"session_date": day, "session_id": UUID(int=index),
             "open_at": datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=1, minutes=30),
             "close_at": datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=7)}
            for index, day in enumerate(days, 1)]


def _use(protocol, *, expires=None):
    return {"experimental_model_use_id": UUID(protocol["identities"]["experimental_model_use"]["id"]),
            "content_sha256": protocol["identities"]["experimental_model_use"]["content_sha256"],
            "model_version_id": UUID(protocol["identities"]["model_version"]["id"]),
            "valid_from": NOW - timedelta(days=1), "registered_at": NOW - timedelta(days=1),
            "expires_at": expires or datetime(2026, 12, 31, 8, tzinfo=timezone.utc), "revoked_at": None}


def _witness(calendar):
    return {"state": "VERIFIED", "coverage_from": date(2026, 9, 14), "coverage_through": date(2026, 12, 31),
            "capture_id": UUID(int=999), "known_at": NOW - timedelta(minutes=1),
            "session_ids": [row["session_id"] for row in calendar]}


def _revision():
    previous = load_validity_protocol(2)
    protocol = deepcopy(previous)
    protocol.update(protocol_version=3, protocol_id="synthetic-capacity-revision", predecessor=previous["protocol_sha256"],
                    declared_at="2026-09-11T00:50:00+08:00", first_eligible_future_session="2026-09-15",
                    first_eligible_target_start="2026-09-15T09:30:00+08:00", first_eligible_target_session_id=str(UUID(int=1234)),
                    capacity_policy={"downtime_buffer_sessions": 10, "missing_observation_buffer_fraction": "0.20",
                                     "expected_members_per_session": 32})
    protocol["identities"]["experimental_model_use"] = {"id": str(UUID(int=5678)), "content_sha256": "9" * 64}
    protocol["frozen_population_semantics"]["experimental_model_use_id"] = str(UUID(int=5678))
    return protocol


def test_short_calendar_and_short_model_lifetime_are_distinct_failures():
    protocol = load_validity_protocol(2)
    calendar = _calendar((date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16), date(2026, 9, 17)))
    use = _use(protocol, expires=datetime(2026, 9, 18, 8, tzinfo=timezone.utc))
    short = cohort_capacity(protocol, calendar, use, observed_at=NOW)
    assert short["COHORT_CAPACITY_FEASIBILITY"] == "FAIL"
    assert short["reason_codes"] == ["CALENDAR_COVERAGE_INSUFFICIENT"]
    assert short["initial_theoretical_capacity"]["known_sessions"] == 4
    assert short["remaining_attainable"]["maximum_sessions"] is None
    assert short["robust"]["reason_codes"] == ["CAPACITY_BUFFER_NOT_PREDECLARED"]
    # A separately captured complete horizon includes a session beyond expiry.
    expanded = _calendar((*tuple(row["session_date"] for row in calendar), date(2026, 12, 31)))
    lifetime = cohort_capacity(protocol, expanded, use, observed_at=NOW, calendar_coverage_witness=_witness(expanded))
    assert lifetime["reason_codes"] == ["MODEL_USE_LIFETIME_INSUFFICIENT"]
    assert lifetime["calendar"]["use_lifetime_coverage_complete"] is True
    assert lifetime["initial_theoretical_capacity"]["known_sessions"] == 4
    assert lifetime["remaining_attainable"]["maximum_observations"] == 128


def test_capacity_does_not_fill_sparse_calendar_gaps_with_weekdays():
    protocol = load_validity_protocol(2)
    days = (date(2026, 9, 14), date(2026, 9, 24), date(2026, 10, 29), date(2026, 12, 31))
    calendar = _calendar(days)
    result = cohort_capacity(protocol, calendar, _use(protocol), observed_at=NOW, calendar_coverage_witness=_witness(calendar))
    assert result["initial_theoretical_capacity"]["session_roster"] == list(days)
    assert result["initial_theoretical_capacity"]["known_sessions"] == 4
    assert result["remaining_attainable"]["known_observation_upper_bound"] == 128


def test_frozen_buffer_requires_thirty_known_sessions_not_twenty():
    protocol = _revision()
    validate_protocol_revision(protocol, load_validity_protocol(2))
    # These explicit synthetic fixture sessions are not an operational calendar.
    calendar = _calendar(tuple(date(2026, 9, 15) + timedelta(days=index) for index in range(30)))
    twenty = cohort_capacity(protocol, calendar[:20], _use(protocol), observed_at=NOW)
    assert twenty["possible"]["state"] == "PASS"
    assert twenty["robust"]["state"] == "FAIL"
    assert twenty["robust"]["scenario_sessions"] == 10
    assert twenty["robust"]["scenario_observations"] == 256
    assert twenty["state"] == "FAIL"
    thirty = cohort_capacity(protocol, calendar, _use(protocol), observed_at=NOW)
    assert thirty["possible"]["state"] == thirty["robust"]["state"] == thirty["state"] == "PASS"
    assert thirty["robust"]["scenario_sessions"] == 20
    assert thirty["robust"]["scenario_observations"] == 512
    assert thirty["robust"]["guaranteed_observations"] is False
    assert thirty["observed_lower_bound"] == {"sessions": 0, "observations": 0}
    assert thirty["remaining_attainable"]["maximum_observations"] is None


def test_elapsed_missed_sessions_cannot_inflate_remaining_attainable_capacity():
    protocol = _revision()
    calendar = _calendar(tuple(date(2026, 9, 15) + timedelta(days=index) for index in range(30)))
    now = calendar[10]["open_at"] + timedelta(minutes=1)
    result = cohort_capacity(protocol, calendar, _use(protocol), observed_at=now, calendar_coverage_witness=_witness(calendar))
    assert result["initial_theoretical_capacity"]["known_sessions"] == 30
    assert result["remaining_attainable"]["known_remaining_sessions"] == 19
    assert result["possible"]["reason_codes"] == ["REMAINING_MODEL_USE_CAPACITY_INSUFFICIENT"]


def test_observed_counts_are_retained_and_buffers_apply_only_to_remaining_unknown_work():
    protocol = _revision()
    calendar = _calendar(tuple(date(2026, 9, 15) + timedelta(days=index) for index in range(30)))
    arguments = dict(observed_at=calendar[0]["close_at"] + timedelta(minutes=1),
                     observed_sessions=(calendar[0]["session_date"],), observed_observations=31)
    result = cohort_capacity(protocol, calendar, _use(protocol), **arguments)
    assert result["observed_lower_bound"] == {"sessions": 1, "observations": 31}
    assert result["remaining_attainable"]["known_observation_upper_bound"] == 959
    assert result["robust"]["scenario_sessions"] == 20
    assert result["robust"]["scenario_observations"] == 517
    with localcontext() as context:
        context.prec = 6
        assert cohort_capacity(protocol, calendar, _use(protocol), **arguments) == result


def test_pending_published_work_is_not_lost_after_model_use_expiry():
    protocol = _revision()
    calendar = _calendar((date(2026, 9, 15), date(2026, 9, 16)))
    use = _use(protocol, expires=calendar[-1]["close_at"])
    result = cohort_capacity(protocol, calendar, use, observed_at=calendar[-1]["close_at"] + timedelta(days=1),
                             observed_sessions=(calendar[0]["session_date"],), observed_observations=31,
                             pending_sessions=(calendar[1]["session_date"],),
                             pending_observation_counts={calendar[1]["session_date"]: 30})
    assert result["model_use_lifecycle"]["state"] == "EXPIRED"
    assert result["remaining_attainable"]["known_remaining_sessions"] == 1
    assert result["remaining_attainable"]["known_observation_upper_bound"] == 61
    assert result["remaining_attainable"]["future_session_roster"] == []


def test_pending_capacity_requires_exact_roster_and_never_replaces_unavailable_work():
    protocol = _revision()
    calendar = _calendar(tuple(date(2026, 9, 15) + timedelta(days=index) for index in range(30)))
    with pytest.raises(ArtifactIntegrityError, match="PENDING_EXACT_ROSTER"):
        cohort_capacity(protocol, calendar, _use(protocol), observed_at=NOW,
                        pending_sessions=(calendar[0]["session_date"],))
    result = cohort_capacity(protocol, calendar, _use(protocol), observed_at=NOW,
                             unavailable_sessions=tuple(row["session_date"] for row in calendar[:11]))
    assert result["remaining_attainable"]["known_remaining_sessions"] == 19
    assert result["remaining_attainable"]["known_observation_upper_bound"] == 608
    assert result["state"] == "FAIL"
    assert "UNAVAILABLE_WORK_NOT_ADMITTED_TO_CAPACITY" in result["reason_codes"]
    assert result["remaining_attainable"]["maximum_sessions"] is None


def test_pending_partial_roster_cannot_pass_missing_observation_buffer():
    protocol = _revision()
    calendar = _calendar(tuple(date(2026, 9, 15) + timedelta(days=index) for index in range(30)))
    result = cohort_capacity(protocol, calendar, _use(protocol), observed_at=NOW,
                             pending_sessions=(calendar[0]["session_date"],),
                             pending_observation_counts={calendar[0]["session_date"]: 1})
    assert result["possible"]["state"] == "PASS"
    assert result["robust"]["scenario_observations"] == 487
    assert result["robust"]["state"] == result["state"] == "FAIL"


@pytest.mark.parametrize("change", ("duplicate", "witness_roster", "future_witness", "model_identity", "model_hash", "future_registered"))
def test_unqualified_calendar_or_owner_identity_fails_closed(change):
    protocol = load_validity_protocol(2)
    calendar = _calendar((date(2026, 9, 14), date(2026, 12, 31)))
    use = _use(protocol)
    witness = _witness(calendar)
    if change == "duplicate":
        calendar.append(calendar[0])
    elif change == "witness_roster":
        witness["session_ids"] = []
    elif change == "future_witness":
        witness["known_at"] = NOW + timedelta(seconds=1)
    elif change == "model_identity":
        use["model_version_id"] = UUID(int=777)
    elif change == "model_hash":
        use["content_sha256"] = "0" * 64
    else:
        use["registered_at"] = NOW + timedelta(seconds=1)
    with pytest.raises(ArtifactIntegrityError, match="CAPACITY"):
        cohort_capacity(protocol, calendar, use, observed_at=NOW, calendar_coverage_witness=witness)


def test_capacity_is_available_from_current_owner_without_any_completed_cycle():
    from tests.contracts.research_qualification.test_validity_report import canonical_fixture
    observations, protocol, calendar = canonical_fixture()
    use = observations["cycles"][0]["frozen_identities"]["experimental_model_use"]
    observations["cycles"] = []
    observations["observed_at"] = NOW
    result = validity_report(observations, protocol, calendar, model_use=use)
    assert result["model_use_lifecycle"]["state"] == "ACTIVE"
    assert result["COHORT_CAPACITY_FEASIBILITY"] == "FAIL"
    assert result["cohort_capacity"]["initial_theoretical_capacity"]["known_sessions"] == 1
    assert result["predeclared_session_count"] == 0
    assert result["MODEL_VALUE"] == "NOT_ESTIMABLE"
    assert result["business_writes"] == 0


@pytest.mark.parametrize("change", ("minimum", "formula", "population", "model", "feature", "target", "baseline", "buffer", "same_use", "same_use_id"))
def test_capacity_revision_cannot_change_research_semantics(change):
    protocol = _revision()
    previous = load_validity_protocol(2)
    if change == "minimum":
        protocol["minimum_sessions"] = 10
    elif change == "formula":
        protocol["formula_contract"]["direction"] = "different"
    elif change == "population":
        protocol["frozen_population_semantics"]["candidate_policy_id"] = str(UUID(int=555))
    elif change in {"model", "feature", "target"}:
        protocol["identities"][{"model": "model_version", "feature": "feature_definition", "target": "target_definition"}[change]]["id"] = str(UUID(int=777))
    elif change == "baseline":
        protocol["baseline_strategy_version_id"] = str(UUID(int=888))
    elif change == "buffer":
        protocol["capacity_policy"]["missing_observation_buffer_fraction"] = "0.10"
    elif change == "same_use_id":
        protocol["identities"]["experimental_model_use"]["id"] = previous["identities"]["experimental_model_use"]["id"]
    else:
        protocol["identities"]["experimental_model_use"] = deepcopy(previous["identities"]["experimental_model_use"])
    with pytest.raises(ValueError, match="CAPACITY"):
        validate_protocol_revision(protocol, previous)


def test_capacity_revision_preserves_both_published_protocol_resource_hashes():
    before = tuple(load_validity_protocol(version)["protocol_sha256"] for version in (1, 2))
    protocol = _revision()
    validate_protocol_revision(protocol, load_validity_protocol(2))
    assert tuple(load_validity_protocol(version)["protocol_sha256"] for version in (1, 2)) == before
