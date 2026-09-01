"""PostgreSQL error classification for Research-owned transaction adapters."""

from __future__ import annotations

from typing import Any

import psycopg

from market_regime_alpha.research_qualification.errors import (
    ResearchRetryableTransactionError,
    ResearchUnknownCommitResultError,
)
from market_regime_alpha.runtime.errors import RuntimeStateConflictError


_TRANSIENT_SQLSTATES = {"40001", "40P01", "55P03"}
_TRANSIENT_CONNECTION_SQLSTATES = {"57P01", "57P02", "57P03"}


def commit_research_transaction(connection: psycopg.Connection[Any]) -> None:
    """Commit, translating transient/unknown PostgreSQL outcomes to a typed seam."""

    try:
        connection.commit()
    except psycopg.Error as exc:
        sqlstate = exc.sqlstate or ""
        if sqlstate in _TRANSIENT_SQLSTATES:
            raise ResearchRetryableTransactionError(sqlstate or "08000") from exc
        if sqlstate in _TRANSIENT_CONNECTION_SQLSTATES or sqlstate.startswith("08") or (
            not sqlstate and isinstance(exc, psycopg.OperationalError)
        ):
            raise ResearchUnknownCommitResultError(sqlstate or "08000") from exc
        raise


def classify_research_postgres_error(
    exception: BaseException | None,
    *,
    owner: str,
) -> BaseException | None:
    """Return the owner-level error that an active PostgreSQL UoW must expose."""

    if not isinstance(exception, psycopg.Error):
        return None
    sqlstate = exception.sqlstate or ""
    if (
        sqlstate in _TRANSIENT_SQLSTATES
        or sqlstate in _TRANSIENT_CONNECTION_SQLSTATES
        or sqlstate.startswith("08")
        or (not sqlstate and isinstance(exception, psycopg.OperationalError))
    ):
        return ResearchRetryableTransactionError(sqlstate or "08000")
    if sqlstate.startswith(("22", "23")) or sqlstate == "55000":
        return RuntimeStateConflictError(
            f"PostgreSQL rejected {owner} invariants"
        )
    return None


__all__ = [
    "classify_research_postgres_error",
    "commit_research_transaction",
]
