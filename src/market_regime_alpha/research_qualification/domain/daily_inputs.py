"""Fixed post-close Feature semantics and complete actual-time input accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


_FEATURE_CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)
_FEATURE_QUANTUM = Decimal("0.000000000001")


def session_open_close_move(open_value: Decimal, close_value: Decimal) -> Decimal:
    """Unitless raw same-session price change; no fitted preprocessing."""
    if any(not isinstance(value, Decimal) or not value.is_finite() or value <= 0 for value in (open_value, close_value)):
        raise ValueError("session prices must be positive finite Decimals")
    with localcontext(_FEATURE_CONTEXT):
        return (close_value / open_value - Decimal("1")).quantize(_FEATURE_QUANTUM)


class DailyInputState(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    SUSPENDED = "SUSPENDED"
    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class DailyInputMember:
    instrument_id: UUID
    state: DailyInputState
    reason_code: str
    bar_revision_id: UUID | None = None
    capture_id: UUID | None = None
    source_sha256: str | None = None
    known_at: datetime | None = None
    recorded_at: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    open_value: Decimal | None = None
    close_value: Decimal | None = None
    source_gap_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, DailyInputState):
            raise TypeError("state must be DailyInputState")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", self.reason_code):
            raise ValueError("daily input reason_code is invalid")
        if self.source_sha256 is not None:
            ContentHash(self.source_sha256)
        for name in ("known_at", "recorded_at", "event_start", "event_end"):
            value = getattr(self, name)
            if value is not None:
                require_utc(value, field=name)
        if self.state is DailyInputState.AVAILABLE:
            if any(
                getattr(self, name) is None
                for name in (
                    "bar_revision_id",
                    "capture_id",
                    "source_sha256",
                    "known_at",
                    "recorded_at",
                    "event_start",
                    "event_end",
                    "open_value",
                    "close_value",
                )
            ):
                raise ValueError("available daily input requires complete price lineage")
            assert self.open_value is not None and self.close_value is not None
            session_open_close_move(self.open_value, self.close_value)
            assert self.event_start is not None and self.event_end is not None
            assert self.known_at is not None and self.recorded_at is not None
            if not self.event_start < self.event_end <= self.known_at <= self.recorded_at:
                raise ValueError("daily input event/known/recorded order is invalid")
        elif self.open_value is not None or self.close_value is not None:
            raise ValueError("unavailable daily input cannot contain price substitutes")

    @property
    def requires_feature(self) -> bool:
        return self.state not in {DailyInputState.EXCLUDED, DailyInputState.SUSPENDED}


@dataclass(frozen=True, slots=True)
class DailyDataReady:
    input_session_id: UUID
    target_session_id: UUID
    input_event_end: datetime
    input_cutoff: datetime
    decision_time: datetime
    target_window_start: datetime
    target_window_end: datetime
    expected_instruments: tuple[UUID, ...]
    members: tuple[DailyInputMember, ...]
    state: str
    sampled_count: int
    expected_active_count: int
    feature_ready_count: int
    feature_values: tuple[tuple[UUID, Decimal], ...]
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256({key: getattr(self, key) for key in self.__dataclass_fields__ if key != "content_sha256"}),
        )


def freeze_data_ready(
    *,
    input_session_id: UUID,
    target_session_id: UUID,
    input_event_end: datetime,
    input_cutoff: datetime,
    decision_time: datetime,
    target_window_start: datetime,
    target_window_end: datetime,
    expected_instruments: tuple[UUID, ...],
    members: tuple[DailyInputMember, ...],
) -> DailyDataReady:
    for name, value in (
        ("input_event_end", input_event_end),
        ("input_cutoff", input_cutoff),
        ("decision_time", decision_time),
        ("target_window_start", target_window_start),
        ("target_window_end", target_window_end),
    ):
        require_utc(value, field=name)
    if not input_event_end <= input_cutoff <= decision_time:
        raise ValueError("input cutoff must follow data events and precede DecisionTime")
    if input_session_id == target_session_id or not input_event_end < target_window_start < target_window_end:
        raise ValueError("target must be a strictly later exact trading session")
    if (
        not expected_instruments
        or len(set(expected_instruments)) != len(expected_instruments)
        or tuple(member.instrument_id for member in members) != expected_instruments
    ):
        raise ValueError("daily input roster differs from the full expected population")
    for member in members:
        if member.state is DailyInputState.AVAILABLE and member.event_end != input_event_end:
            raise ValueError("daily input cannot silently replace the exact session")
        if any(value is not None and value > input_cutoff for value in (member.known_at, member.recorded_at)):
            raise ValueError("daily input revision was not visible at input cutoff")
    features = tuple(
        (member.instrument_id, session_open_close_move(member.open_value, member.close_value))
        for member in members
        if member.state is DailyInputState.AVAILABLE and member.open_value is not None and member.close_value is not None
    )
    expected_active = sum(member.requires_feature for member in members)
    state = (
        "MISSED_CUTOFF"
        if decision_time >= target_window_start
        else "NOT_READY"
        if not features
        else "READY"
        if len(features) == expected_active
        else "PARTIAL"
    )
    return DailyDataReady(
        input_session_id=input_session_id,
        target_session_id=target_session_id,
        input_event_end=input_event_end,
        input_cutoff=input_cutoff,
        decision_time=decision_time,
        target_window_start=target_window_start,
        target_window_end=target_window_end,
        expected_instruments=expected_instruments,
        members=members,
        state=state,
        sampled_count=len(members),
        expected_active_count=expected_active,
        feature_ready_count=len(features),
        feature_values=features,
    )


__all__ = ["DailyDataReady", "DailyInputMember", "DailyInputState", "freeze_data_ready", "session_open_close_move"]
