"""Process lifecycle only; each wakeup delegates to canonical continuation."""

from __future__ import annotations

from collections.abc import Callable
import math
import signal
from threading import Event
from time import monotonic


def serve_prospective(
    tick: Callable[[], object], *, emit: Callable[[object], None],
    wakeup_seconds: float, maximum_wakeups: int | None = None,
    stop: Event | None = None,
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
    stopping = Event() if stop is None else stop
    signal_requested = False
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}

    def request_stop(signum: int, frame: object) -> None:
        nonlocal signal_requested
        # A Python signal can interrupt Event.wait while its non-reentrant
        # condition lock is held. Never acquire that lock in this handler.
        signal_requested = True

    completed = 0
    try:
        for number in previous:
            signal.signal(number, request_stop)
        while not signal_requested and not stopping.is_set():
            emit(tick())
            completed += 1
            if maximum_wakeups is not None and completed >= maximum_wakeups:
                return {"stop_reason": "WAKEUP_LIMIT", "completed_wakeups": completed}
            deadline = monotonic() + wakeup_seconds
            while not signal_requested and not stopping.is_set():
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                stopping.wait(min(remaining, 0.1))
        return {"stop_reason": "STOP_REQUESTED", "completed_wakeups": completed}
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


__all__ = ["serve_prospective"]
