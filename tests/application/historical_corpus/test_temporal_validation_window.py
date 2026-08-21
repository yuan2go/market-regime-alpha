from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.historical_corpus.temporal_validation_window import (
    FrozenTemporalValidationWindow,
    TEMPORAL_VALIDATION_V1,
    freeze_temporal_validation_window,
)
from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
START = date(2025, 7, 15)


def test_window_freezes_126_calendar_sessions_and_final_target() -> None:
    calendar = _calendar(130)

    window = freeze_temporal_validation_window(
        calendar=calendar,
        start_decision_session=START,
        session_count=126,
    )

    assert window.protocol_id == TEMPORAL_VALIDATION_V1
    assert window.decision_sessions == calendar.trading_dates[:126]
    assert window.final_target_session == calendar.trading_dates[126]
    assert window.calendar_reference.artifact_id == calendar.artifact_id
    assert window.calendar_reference.content_hash == calendar.content_hash
    assert window.start_decision_session == START
    assert window.session_count == 126
    assert window.last_decision_session == calendar.trading_dates[125]
    assert window.reference.content_hash == window.window_hash
    assert (
        FrozenTemporalValidationWindow.from_canonical_dict(
            window.to_canonical_dict()
        )
        == window
    )


def test_window_rejects_missing_start_and_insufficient_target_coverage() -> None:
    with pytest.raises(ValueError, match="explicit session"):
        freeze_temporal_validation_window(
            calendar=_calendar(130, first=START + timedelta(days=1)),
            start_decision_session=START,
            session_count=126,
        )

    with pytest.raises(ValueError, match=r"final T\+1 Target"):
        freeze_temporal_validation_window(
            calendar=_calendar(126),
            start_decision_session=START,
            session_count=126,
        )


def test_window_identity_changes_with_calendar_owner_even_for_same_dates() -> None:
    first = freeze_temporal_validation_window(
        calendar=_calendar(130, source="calendar-a"),
        start_decision_session=START,
        session_count=126,
    )
    second = freeze_temporal_validation_window(
        calendar=_calendar(130, source="calendar-b"),
        start_decision_session=START,
        session_count=126,
    )

    assert first.decision_sessions == second.decision_sessions
    assert first.calendar_reference != second.calendar_reference
    assert first.reference != second.reference


def _calendar(
    count: int,
    *,
    first: date = START,
    source: str = "calendar-source",
):
    dates = tuple(first + timedelta(days=index) for index in range(count))
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId(source),
        market="A_SHARE",
        calendar_version="temporal-validation-test/v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                item,
                datetime.combine(item, time(15), SHANGHAI),
            )
            for item in dates
        ),
    )
