"""Canonical historical trading-calendar artifact and next-session resolver.

The resolver consumes explicit identified sessions. It never infers trading days from weekdays
and never manufactures sessions for weekends, holidays, suspensions, or missing source data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.core.time import DecisionTime


@dataclass(frozen=True, slots=True)
class TradingSession:
    """One explicitly identified market trading session."""

    trade_date: date
    session_close: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.trade_date, date):
            raise TypeError("trade_date must be a date")
        if not isinstance(self.session_close, datetime):
            raise TypeError("session_close must be a datetime")
        if self.session_close.tzinfo is None or self.session_close.utcoffset() is None:
            raise ValueError("session_close must be timezone-aware")
        if self.session_close.date() != self.trade_date:
            raise ValueError("session_close date must match trade_date")


@dataclass(frozen=True, slots=True)
class TradingCalendarArtifact:
    """Immutable identified historical trading-session calendar."""

    artifact_id: ArtifactId
    source_dataset_id: DatasetId
    market: str
    calendar_version: str
    timezone_name: str
    sessions: tuple[TradingSession, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("market", self.market),
            ("calendar_version", self.calendar_version),
            ("timezone_name", self.timezone_name),
        ):
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        if not self.sessions:
            raise ValueError("trading calendar must contain at least one session")
        dates = tuple(session.trade_date for session in self.sessions)
        if len(dates) != len(set(dates)):
            raise ValueError("trading calendar trade dates must be unique")
        if tuple(sorted(dates)) != dates:
            raise ValueError("trading calendar sessions must be chronological")
        expected_zone = ZoneInfo(self.timezone_name)
        for session in self.sessions:
            if session.session_close.astimezone(expected_zone).date() != session.trade_date:
                raise ValueError("session_close is inconsistent with calendar timezone")

    @property
    def trading_dates(self) -> tuple[date, ...]:
        return tuple(session.trade_date for session in self.sessions)

    def resolve_next_session_date(self, decision_time: DecisionTime) -> date:
        """Return the first explicit trading session strictly after the local decision date."""

        return self.resolve_following_session_dates(decision_time, 1)[0]

    def resolve_following_session_dates(
        self,
        decision_time: DecisionTime,
        count: int,
    ) -> tuple[date, ...]:
        """Return the next exact count of identified exchange trading sessions."""

        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("count must be an integer")
        if count <= 0:
            raise ValueError("count must be positive")
        local_date = decision_time.value.astimezone(ZoneInfo(self.timezone_name)).date()
        following = tuple(
            session.trade_date
            for session in self.sessions
            if session.trade_date > local_date
        )
        if len(following) < count:
            if count == 1:
                raise LookupError(
                    "no later trading session exists in the identified calendar artifact"
                )
            raise LookupError(
                "insufficient later trading sessions in identified calendar artifact"
            )
        return following[:count]

    def contains(self, trade_date: date) -> bool:
        return trade_date in self.trading_dates


def build_trading_calendar_artifact(
    *,
    source_dataset_id: DatasetId,
    market: str,
    calendar_version: str,
    timezone_name: str,
    sessions: tuple[TradingSession, ...],
) -> TradingCalendarArtifact:
    """Build a deterministic calendar artifact from explicit sessions."""

    ordered = tuple(sorted(sessions, key=lambda session: session.trade_date))
    payload = {
        "schema_version": "trading-calendar-artifact-v1",
        "source_dataset_id": str(source_dataset_id),
        "market": market,
        "calendar_version": calendar_version,
        "timezone_name": timezone_name,
        "sessions": [
            {
                "trade_date": session.trade_date.isoformat(),
                "session_close": session.session_close.isoformat(),
            }
            for session in ordered
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return TradingCalendarArtifact(
        artifact_id=ArtifactId(f"trading-calendar-{digest[:24]}"),
        source_dataset_id=source_dataset_id,
        market=market,
        calendar_version=calendar_version,
        timezone_name=timezone_name,
        sessions=ordered,
    )
