"""Narrow exact trading-session roster for archive normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from market_regime_alpha.shared.identity import TradingSessionId


@dataclass(frozen=True, slots=True)
class ArchiveTradingSession:
    session_id: TradingSessionId
    exchange: str
    session_date: date
    open_at: datetime
    break_start_at: datetime
    break_end_at: datetime
    close_at: datetime


class ArchiveTradingSessionReadPort(Protocol):
    def exact(
        self,
        *,
        exchange: str,
        session_id: TradingSessionId,
    ) -> ArchiveTradingSession: ...

    def sessions(
        self,
        *,
        exchange: str,
        start_date: date,
        end_date: date,
    ) -> tuple[ArchiveTradingSession, ...]: ...

    def following(
        self,
        *,
        exchange: str,
        after_session_id: TradingSessionId,
        count: int,
    ) -> tuple[ArchiveTradingSession, ...]: ...


__all__ = ["ArchiveTradingSession", "ArchiveTradingSessionReadPort"]
