"""Pure Target-session resolution for generic Backtest Outcome actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from market_regime_alpha.shared.time import require_utc


@dataclass(frozen=True, slots=True)
class BacktestOutcomeCheckpoint:
    session_offset: int
    local_time: time
    timezone_name: str

    def __post_init__(self) -> None:
        if isinstance(self.session_offset, bool) or self.session_offset < 0:
            raise ValueError("Outcome checkpoint session_offset must be non-negative")
        if not self.timezone_name:
            raise ValueError("Outcome checkpoint timezone is required")


@dataclass(frozen=True, slots=True)
class BacktestSessionWindow:
    session_id: UUID
    session_date: date
    open_at: datetime
    close_at: datetime

    def __post_init__(self) -> None:
        opened = require_utc(self.open_at, field="Backtest Session open_at")
        closed = require_utc(self.close_at, field="Backtest Session close_at")
        if opened >= closed:
            raise ValueError("Backtest Session window must be ordered")
        object.__setattr__(self, "open_at", opened)
        object.__setattr__(self, "close_at", closed)


def resolve_backtest_outcome_cutoff(
    *,
    reference_session_id: UUID,
    fold_session_bindings: tuple[tuple[UUID, date], ...],
    checkpoints: tuple[BacktestOutcomeCheckpoint, ...],
    session_windows: tuple[BacktestSessionWindow, ...],
) -> datetime:
    """Resolve a Target horizon over distinct frozen trading-session identity.

    Rolling and expanding folds may repeat the same TradingSession.  Repeated
    membership is removed by identity only after proving its date is stable.
    """

    if not fold_session_bindings:
        raise ValueError("Backtest fold Session roster is empty")
    if not checkpoints:
        raise ValueError("Backtest Target has no Outcome checkpoint")
    dates_by_id: dict[UUID, date] = {}
    for session_id, session_date in fold_session_bindings:
        prior = dates_by_id.setdefault(session_id, session_date)
        if prior != session_date:
            raise ValueError("Backtest trading Session identity has conflicting dates")
    ordered = tuple(sorted(dates_by_id.items(), key=lambda item: (item[1], str(item[0]))))
    index_by_id = {session_id: index for index, (session_id, _) in enumerate(ordered)}
    if reference_session_id not in index_by_id:
        raise ValueError("Backtest reference Session is not frozen")

    windows_by_id: dict[UUID, BacktestSessionWindow] = {}
    for window in session_windows:
        if window.session_id in windows_by_id:
            raise ValueError("Backtest Session window roster contains duplicates")
        windows_by_id[window.session_id] = window
    if set(windows_by_id) != set(dates_by_id):
        raise ValueError("Backtest Session window roster differs from frozen Sessions")
    if any(
        windows_by_id[session_id].session_date != session_date
        for session_id, session_date in ordered
    ):
        raise ValueError("Backtest Session window date differs from frozen membership")

    reference_index = index_by_id[reference_session_id]
    cutoffs: list[datetime] = []
    for checkpoint in checkpoints:
        target_index = reference_index + checkpoint.session_offset
        if target_index >= len(ordered):
            raise ValueError("Backtest Session roster does not cover the Target horizon")
        session_id, session_date = ordered[target_index]
        window = windows_by_id[session_id]
        cutoff = datetime.combine(
            session_date,
            checkpoint.local_time,
            ZoneInfo(checkpoint.timezone_name),
        ).astimezone(UTC)
        if not window.open_at < cutoff <= window.close_at:
            raise ValueError("Outcome checkpoint is outside its frozen TradingSession")
        cutoffs.append(cutoff)
    return max(cutoffs)


__all__ = [
    "BacktestOutcomeCheckpoint",
    "BacktestSessionWindow",
    "resolve_backtest_outcome_cutoff",
]
