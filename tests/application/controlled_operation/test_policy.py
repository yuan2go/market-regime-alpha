from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.controlled_operation import (
    DecisionTimeOperationPolicy,
    DecisionWindowState,
    default_decision_time_operation_policy,
)
from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = date(2026, 8, 5)


def _calendar(*, close: time = time(15), include_date: bool = True):
    session_date = TRADE_DATE if include_date else date(2026, 8, 4)
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("calendar-source"),
        market="A_SHARE",
        calendar_version="explicit-controlled-calendar-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            TradingSession(
                trade_date=session_date,
                session_close=datetime.combine(session_date, close, tzinfo=SHANGHAI),
            ),
        ),
    )


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 5, hour, minute, second, tzinfo=SHANGHAI)


@pytest.mark.parametrize(
    ("observed", "static_ready", "expected"),
    (
        (_at(14, 40), True, DecisionWindowState.TOO_EARLY),
        (_at(14, 49), False, DecisionWindowState.WAITING_FOR_STATIC_INPUTS),
        (_at(14, 51), False, DecisionWindowState.DATA_BLOCKED),
        (_at(14, 53), True, DecisionWindowState.WAITING_FOR_DECISION_WINDOW),
        (_at(14, 54), True, DecisionWindowState.DECISION_WINDOW_RUNNING),
        (_at(14, 55), True, DecisionWindowState.DECISION_WINDOW_RUNNING),
        (_at(14, 55, 1), True, DecisionWindowState.DEADLINE_MISSED),
        (_at(14, 56, 1), True, DecisionWindowState.DEADLINE_MISSED),
    ),
)
def test_decision_window_policy_states(
    observed: datetime,
    static_ready: bool,
    expected: DecisionWindowState,
) -> None:
    policy = default_decision_time_operation_policy()
    calendar = _calendar()
    result = policy.assess(
        observed_at=observed,
        decision_date=TRADE_DATE,
        calendar=calendar,
        expected_calendar_hash=calendar.content_hash,
        static_inputs_ready_at=(
            (_at(14, 39) if observed == _at(14, 40) else _at(14, 49))
            if static_ready
            else None
        ),
    )

    assert result.state is expected
    if observed > _at(14, 55):
        assert result.accepts_signal_evidence is False
        assert result.late_run is True


def test_policy_rejects_post_decision_evidence_even_before_hard_cutoff() -> None:
    policy = default_decision_time_operation_policy()

    assert policy.accepts_evidence(decision_date=TRADE_DATE, available_at=_at(14, 55))
    assert not policy.accepts_evidence(
        decision_date=TRADE_DATE,
        available_at=_at(14, 55, 1),
    )


def test_calendar_missing_conflict_holiday_and_early_close_fail_closed() -> None:
    policy = default_decision_time_operation_policy()
    calendar = _calendar()
    common = {
        "observed_at": _at(14, 55),
        "decision_date": TRADE_DATE,
        "static_inputs_ready_at": _at(14, 49),
    }

    assert policy.assess(
        **common, calendar=None, expected_calendar_hash=None
    ).state is DecisionWindowState.MISSING_CALENDAR
    assert policy.assess(
        **common,
        calendar=calendar,
        expected_calendar_hash="sha256:" + "9" * 64,
    ).state is DecisionWindowState.CALENDAR_CONFLICT
    assert policy.assess(
        **common,
        calendar=_calendar(include_date=False),
        expected_calendar_hash=None,
    ).state is DecisionWindowState.NON_TRADING_DAY
    assert policy.assess(
        **common,
        calendar=_calendar(close=time(11, 30)),
        expected_calendar_hash=None,
    ).state is DecisionWindowState.NON_STANDARD_SESSION


def test_weekend_or_long_holiday_is_not_inferred_from_weekday() -> None:
    policy = default_decision_time_operation_policy()
    calendar = _calendar(include_date=False)
    weekend = date(2026, 8, 8)

    result = policy.assess(
        observed_at=datetime(2026, 8, 8, 14, 55, tzinfo=SHANGHAI),
        decision_date=weekend,
        calendar=calendar,
        expected_calendar_hash=calendar.content_hash,
        static_inputs_ready_at=datetime(2026, 8, 8, 14, 49, tzinfo=SHANGHAI),
    )

    assert result.state is DecisionWindowState.NON_TRADING_DAY


def test_policy_identity_is_stable_and_configuration_changes_hash() -> None:
    first = default_decision_time_operation_policy()
    second = DecisionTimeOperationPolicy.from_canonical_dict(first.to_canonical_dict())
    changed = DecisionTimeOperationPolicy.create(
        policy_version="controlled-a-share-1455-v1",
        timezone_name="Asia/Shanghai",
        decision_time=time(14, 55),
        static_ready_deadline=time(14, 49),
        minute_fetch_start=time(14, 54),
        hard_cutoff=time(14, 56),
        limitations=first.limitations,
    )

    assert second == first
    assert changed.content_hash != first.content_hash


def test_policy_rejects_naive_observed_time() -> None:
    policy = default_decision_time_operation_policy()
    with pytest.raises(ValueError, match="timezone-aware"):
        policy.assess(
            observed_at=datetime(2026, 8, 5, 14, 55),
            decision_date=TRADE_DATE,
            calendar=_calendar(),
            expected_calendar_hash=None,
            static_inputs_ready_at=_at(14, 49),
        )


def test_policy_rejects_late_or_future_static_receipt() -> None:
    policy = default_decision_time_operation_policy()
    calendar = _calendar()

    late = policy.assess(
        observed_at=_at(14, 54),
        decision_date=TRADE_DATE,
        calendar=calendar,
        expected_calendar_hash=calendar.content_hash,
        static_inputs_ready_at=_at(14, 50, 1),
    )
    future = policy.assess(
        observed_at=_at(14, 49),
        decision_date=TRADE_DATE,
        calendar=calendar,
        expected_calendar_hash=calendar.content_hash,
        static_inputs_ready_at=_at(14, 49, 1),
    )

    assert late.state is DecisionWindowState.DATA_BLOCKED
    assert late.reason_codes == ("STATIC_READY_DEADLINE_MISSED",)
    assert future.state is DecisionWindowState.DATA_BLOCKED
    assert future.reason_codes == ("STATIC_RECEIPT_AFTER_OBSERVATION",)
