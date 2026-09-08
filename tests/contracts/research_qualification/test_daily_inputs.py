"""Input-time and denominator examples independent of production calculations."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Context, Decimal, ROUND_UP, localcontext
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.daily_inputs import (
    DailyInputMember,
    DailyInputState,
    freeze_data_ready,
    session_open_close_move,
)


def test_shared_session_feature_is_independent_of_callers_decimal_context():
    with localcontext(Context(prec=3, rounding=ROUND_UP)):
        result = session_open_close_move(Decimal("3"), Decimal("4"))
    assert result == Decimal("0.333333333333")
    with pytest.raises(ValueError, match="positive finite"):
        session_open_close_move(Decimal("0"), Decimal("4"))


def test_ready_snapshot_preserves_full_roster_and_rejects_future_revision():
    close = datetime(2026, 9, 7, 7, tzinfo=UTC)
    cutoff = close + timedelta(hours=3)
    members = (
        DailyInputMember(
            instrument_id=UUID(int=1),
            state=DailyInputState.AVAILABLE,
            reason_code="EXACT_DAILY_BAR",
            bar_revision_id=UUID(int=11),
            capture_id=UUID(int=21),
            source_sha256="a" * 64,
            known_at=close + timedelta(minutes=10),
            recorded_at=close + timedelta(minutes=11),
            event_start=close - timedelta(hours=5, minutes=30),
            event_end=close,
            open_value=Decimal("100"),
            close_value=Decimal("105"),
        ),
        DailyInputMember(instrument_id=UUID(int=2), state=DailyInputState.SUSPENDED, reason_code="SECURITY_SUSPENDED"),
        DailyInputMember(instrument_id=UUID(int=3), state=DailyInputState.MISSING, reason_code="DAILY_BAR_ABSENT"),
    )
    arguments = dict(
        input_session_id=UUID(int=101),
        target_session_id=UUID(int=102),
        input_event_end=close,
        input_cutoff=cutoff,
        decision_time=cutoff,
        target_window_start=close + timedelta(hours=18, minutes=30),
        target_window_end=close + timedelta(days=1),
        expected_instruments=(UUID(int=1), UUID(int=2), UUID(int=3)),
        members=members,
    )
    ready = freeze_data_ready(**arguments)
    assert ready.state == "PARTIAL"
    assert ready.sampled_count == 3
    assert ready.expected_active_count == 2
    assert ready.feature_ready_count == 1
    assert ready.feature_values == ((UUID(int=1), Decimal("0.050000000000")),)
    assert len(ready.members) == 3
    assert freeze_data_ready(**arguments).content_sha256 == ready.content_sha256
    with pytest.raises(ValueError, match="visible"):
        freeze_data_ready(
            **(
                arguments
                | {
                    "members": (
                        replace(members[0], known_at=cutoff + timedelta(seconds=1), recorded_at=cutoff + timedelta(seconds=2)),
                        *members[1:],
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="roster"):
        freeze_data_ready(**(arguments | {"members": members[:2]}))
    late = freeze_data_ready(**(arguments | {"decision_time": arguments["target_window_start"]}))
    assert late.state == "MISSED_CUTOFF"
    assert late.feature_ready_count == 1
