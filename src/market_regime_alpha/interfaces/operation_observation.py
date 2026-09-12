"""Read-only observations and sticky safety rejection within one service tick."""

from collections.abc import Callable
from typing import Any

import psycopg


class ActionGuard:
    """Remember an actual rejection, never a successful authorization decision."""

    def __init__(self, check: Callable[[], None]) -> None:
        self._check = check
        self._failure: BaseException | None = None

    def __call__(self) -> None:
        self.raise_if_failed()
        try:
            self._check()
        except BaseException as exc:
            self._failure = exc
            raise

    def raise_if_failed(self) -> None:
        if self._failure is not None:
            raise self._failure


def observe_health(read: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """A failed observation cannot erase a previously committed owner result."""
    try:
        return read()
    except (psycopg.Error, RuntimeError, ValueError, AttributeError) as exc:
        sqlstate = getattr(exc, "sqlstate", None)
        return {"state": "HEALTH_QUERY_FAILED", "error_type": type(exc).__name__,
                "failure_class": "RESOURCE_EXHAUSTED" if sqlstate and sqlstate.startswith("53") else "OBSERVATION_FAILED",
                "sqlstate": getattr(exc, "sqlstate", None),
                "cause_type": None if exc.__cause__ is None else type(exc.__cause__).__name__,
                "business_result": "UNCHANGED", "retry": "NEXT_READ_ONLY_OBSERVATION"}
