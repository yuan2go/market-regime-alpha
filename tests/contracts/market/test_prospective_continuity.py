from dataclasses import replace
from datetime import UTC, date, datetime, time
from uuid import UUID

from market_regime_alpha.market.application.prospective_continuity import plan_continuation
from market_regime_alpha.market.domain import ProspectiveArchiveSession
from tests.contracts.market.test_prospective_archive_planner import _contract, _manifest


def _calendar():
    # Explicit exchange sessions include a weekend and a calendar gap. No weekday
    # inference is permitted in the continuation planner.
    return tuple(ProspectiveArchiveSession(
        UUID(f"18000000-0000-0000-0000-{i:012d}"), "XSHG", day,
        datetime.combine(day, time(1, 30), tzinfo=UTC),
        datetime.combine(day, time(7), tzinfo=UTC),
    ) for i, day in enumerate((date(2026, 9, 4), date(2026, 9, 7),
                              date(2026, 9, 8), date(2026, 9, 10),
                              date(2026, 9, 11)), 1))


def test_downtime_records_each_missing_generation_window_before_next_future_session():
    manifest = _manifest(planned_not_before=datetime(2026, 9, 3, tzinfo=UTC))
    result = plan_continuation(manifest, contract=_contract(), sessions=_calendar(),
                               observed_at=datetime(2026, 9, 7, 8, tzinfo=UTC))
    assert result.missed_decision_session_ids == (_calendar()[1].session_id,)
    assert result.next_sessions.decision.session_id == _calendar()[2].session_id
    assert result.next_sessions.outcome.session_date == date(2026, 9, 10)
    assert result.blocked_reason is None


def test_future_head_does_not_create_unbounded_future_generations():
    manifest = _manifest(planned_not_before=datetime(2026, 9, 3, tzinfo=UTC))
    result = plan_continuation(manifest, contract=_contract(), sessions=_calendar(),
                               observed_at=datetime(2026, 9, 3, tzinfo=UTC))
    assert result.next_sessions is None and not result.missed_decision_session_ids
    assert result.blocked_reason is None


def test_incomplete_calendar_is_typed_and_does_not_guess_next_dates():
    manifest = _manifest(planned_not_before=datetime(2026, 9, 3, tzinfo=UTC))
    result = plan_continuation(manifest, contract=_contract(), sessions=_calendar()[:2],
                               observed_at=datetime(2026, 9, 4, 8, tzinfo=UTC))
    assert result.next_sessions is None
    assert result.blocked_reason == "CALENDAR_INCOMPLETE"
    assert result.blocked_decision_session_id == _calendar()[1].session_id


def test_changed_target_contract_fails_closed():
    import pytest
    manifest = _manifest(planned_not_before=datetime(2026, 9, 3, tzinfo=UTC))
    with pytest.raises(ValueError, match="Target"):
        plan_continuation(manifest, contract=replace(_contract(), version=2),
                          sessions=_calendar(), observed_at=datetime(2026, 9, 4, 8, tzinfo=UTC))
