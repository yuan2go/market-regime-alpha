"""Process lifecycle only; each wakeup delegates to canonical continuation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import signal
from threading import Event
from time import monotonic
from typing import Any


@dataclass(slots=True)
class OperationStopRequest:
    requested: bool = False


class OperationStopped(RuntimeError):
    """No new owner action started; inspect canonical facts already completed."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class OperationAlertChanges:
    """In-process notification deduplication; the next health read owns status."""

    def __init__(self) -> None:
        self._previous: dict[str, dict[str, Any]] = {}

    def observe(self, alerts: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
        current = {str(item["reason_code"]): item for item in alerts}
        changes = tuple(
            {**item, "change": "UPDATED" if code in self._previous else "OPENED"}
            for code, item in current.items() if self._previous.get(code) != item
        ) + tuple(
            {"reason_code": code, "change": "RESOLVED"}
            for code in self._previous if code not in current
        )
        self._previous = current
        return changes


def serve_prospective(
    tick: Callable[[], object], *, emit: Callable[[object], None],
    wakeup_seconds: float, maximum_wakeups: int | None = None,
    maximum_tick_seconds: float | None = None,
    stop: Event | None = None,
    stop_request: OperationStopRequest | None = None,
) -> dict[str, object]:
    """Wake serially, drain the current tick on shutdown, and never retry errors.

    The interval is only a process wakeup interval. This layer owns no business
    clock, generation, due decision, claim, result or recovery policy. Restart
    re-enters the same owner reconciliation as an ordinary continuation call.
    """
    if not math.isfinite(wakeup_seconds) or wakeup_seconds <= 0:
        raise ValueError("wakeup-seconds must be finite and positive")
    if maximum_wakeups is not None and maximum_wakeups < 1:
        raise ValueError("maximum-wakeups must be positive")
    if maximum_tick_seconds is not None and (
        not math.isfinite(maximum_tick_seconds) or maximum_tick_seconds <= 0
    ):
        raise ValueError("maximum-tick-seconds must be finite and positive")
    stopping = Event() if stop is None else stop
    signal_request = OperationStopRequest() if stop_request is None else stop_request
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}

    def request_stop(signum: int, frame: object) -> None:
        # A Python signal can interrupt Event.wait while its non-reentrant
        # condition lock is held. Never acquire that lock in this handler.
        signal_request.requested = True

    completed = 0
    try:
        for number in previous:
            signal.signal(number, request_stop)
        while not signal_request.requested and not stopping.is_set():
            started = monotonic() if maximum_tick_seconds is not None else None
            emit(tick())
            completed += 1
            if started is not None:
                elapsed = monotonic() - started
                assert maximum_tick_seconds is not None
                if elapsed > maximum_tick_seconds:
                    return {"stop_reason": "TICK_BUDGET_EXCEEDED",
                            "completed_wakeups": completed, "tick_elapsed_seconds": elapsed}
            if maximum_wakeups is not None and completed >= maximum_wakeups:
                return {"stop_reason": "WAKEUP_LIMIT", "completed_wakeups": completed}
            deadline = monotonic() + wakeup_seconds
            while not signal_request.requested and not stopping.is_set():
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                stopping.wait(min(remaining, 0.1))
        return {"stop_reason": "STOP_REQUESTED", "completed_wakeups": completed}
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


__all__ = ["serve_prospective"]
