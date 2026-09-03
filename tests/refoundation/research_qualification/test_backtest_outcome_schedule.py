from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.backtest_outcome import (
    BacktestOutcomeCheckpoint,
    BacktestSessionWindow,
    resolve_backtest_outcome_cutoff,
)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _at(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 1, day, hour, minute, tzinfo=UTC)


def test_outcome_cutoff_deduplicates_overlapping_fold_membership() -> None:
    bindings = (
        (_id(1), date(2026, 1, 5)),
        (_id(2), date(2026, 1, 6)),
        (_id(1), date(2026, 1, 5)),
        (_id(3), date(2026, 1, 7)),
    )
    windows = tuple(
        BacktestSessionWindow(
            session_id=_id(index),
            session_date=date(2026, 1, day),
            open_at=_at(day, 1, 30),
            close_at=_at(day, 7, 0),
        )
        for index, day in ((1, 5), (2, 6), (3, 7))
    )

    cutoff = resolve_backtest_outcome_cutoff(
        reference_session_id=_id(1),
        fold_session_bindings=bindings,
        checkpoints=(
            BacktestOutcomeCheckpoint(1, time(6, 30), "UTC"),
        ),
        session_windows=windows,
    )

    assert cutoff == _at(6, 6, 30)


def test_outcome_cutoff_fails_closed_on_conflicting_or_short_roster() -> None:
    windows = (
        BacktestSessionWindow(
            _id(1), date(2026, 1, 5), _at(5, 1, 30), _at(5, 7, 0)
        ),
    )

    with pytest.raises(ValueError, match="conflicting dates"):
        resolve_backtest_outcome_cutoff(
            reference_session_id=_id(1),
            fold_session_bindings=(
                (_id(1), date(2026, 1, 5)),
                (_id(1), date(2026, 1, 6)),
            ),
            checkpoints=(BacktestOutcomeCheckpoint(1, time(6, 30), "UTC"),),
            session_windows=windows,
        )

    with pytest.raises(ValueError, match="does not cover"):
        resolve_backtest_outcome_cutoff(
            reference_session_id=_id(1),
            fold_session_bindings=((_id(1), date(2026, 1, 5)),),
            checkpoints=(BacktestOutcomeCheckpoint(1, time(6, 30), "UTC"),),
            session_windows=windows,
        )
