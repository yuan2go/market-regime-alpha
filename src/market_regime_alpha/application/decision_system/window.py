"""Asia/Shanghai Daily Decision Window rules without a single-point scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from market_regime_alpha.application.decision_system.contracts import (
    DecisionWindowState,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


class DecisionWindowBlocked(ValueError):
    """Typed fail-closed window or late-evidence rejection."""


@dataclass(frozen=True, slots=True)
class DailyDecisionWindowPolicy:
    open_time: time = time(14, 30)
    cutoff_time: time = time(14, 55)

    def bounds(self, trading_date: date) -> tuple[datetime, datetime]:
        return (
            datetime.combine(trading_date, self.open_time, tzinfo=SHANGHAI),
            datetime.combine(trading_date, self.cutoff_time, tzinfo=SHANGHAI),
        )

    def state_at(self, *, trading_date: date, observed_at: datetime) -> DecisionWindowState:
        local = _aware(observed_at).astimezone(SHANGHAI)
        opened, cutoff = self.bounds(trading_date)
        if local < opened:
            return DecisionWindowState.WINDOW_NOT_OPEN
        if local <= cutoff:
            return DecisionWindowState.PREVIEW_AVAILABLE
        return DecisionWindowState.WAITING_FOR_REQUIRED_EVIDENCE

    def require_preview(self, *, trading_date: date, as_of_time: datetime) -> None:
        local = _aware(as_of_time).astimezone(SHANGHAI)
        opened, cutoff = self.bounds(trading_date)
        if not opened <= local <= cutoff:
            raise DecisionWindowBlocked("PREVIEW_OUTSIDE_DECISION_WINDOW")

    def require_finalize(
        self,
        *,
        trading_date: date,
        as_of_time: datetime,
        latest_available_at: datetime,
        uses_complete_close_bar: bool = False,
    ) -> None:
        local_as_of = _aware(as_of_time).astimezone(SHANGHAI)
        local_available = _aware(latest_available_at).astimezone(SHANGHAI)
        opened, cutoff = self.bounds(trading_date)
        if local_as_of < opened:
            raise DecisionWindowBlocked("WINDOW_NOT_OPEN")
        if local_as_of > cutoff or local_available > cutoff:
            raise DecisionWindowBlocked("EVIDENCE_AFTER_DECISION_CUTOFF")
        if local_available > local_as_of:
            raise DecisionWindowBlocked("AVAILABLE_AT_EXCEEDS_AS_OF")
        if uses_complete_close_bar:
            raise DecisionWindowBlocked("COMPLETE_CLOSE_BAR_PROHIBITED")


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Decision Window timestamp must be timezone-aware")
    return value


__all__ = [
    "DailyDecisionWindowPolicy",
    "DecisionWindowBlocked",
    "SHANGHAI",
]
