from dataclasses import replace
from datetime import UTC, date, datetime, time
from uuid import uuid4

from market_regime_alpha.infrastructure.postgres.queries.decision_inputs import _reference_window
from tests.contracts.decision_support.test_decision_domain import _target_snapshot


def test_complete_daily_reference_crosses_lunch_and_remains_the_previous_session_after_midnight():
    target = replace(_target_snapshot(), timeframe="DAILY", reference_rule="EXACT_COMPLETED_SESSION_DAILY_BAR")
    row = (
        uuid4(),
        uuid4(),
        "XSHG",
        "EQUITY",
        uuid4(),
        date(2026, 9, 7),
        datetime(2026, 9, 7, 1, 30, tzinfo=UTC),
        datetime(2026, 9, 7, 3, 30, tzinfo=UTC),
        datetime(2026, 9, 7, 5, tzinfo=UTC),
        datetime(2026, 9, 7, 7, tzinfo=UTC),
        "Asia/Shanghai",
    )
    window = _reference_window(
        row, target=target, local_time=time(15), timezone_name="Asia/Shanghai", decision_time=datetime(2026, 9, 7, 16, 30, tzinfo=UTC)
    )
    assert window.event_start == row[6]
    assert window.event_end == row[9]
    assert window.session_id == row[4]
