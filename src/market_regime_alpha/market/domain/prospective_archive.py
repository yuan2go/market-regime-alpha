"""Target-aligned, trading-session authoritative prospective archive contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


class ProspectiveArchiveScheduleSlot(StrEnum):
    PRE_DECISION = "PRE_DECISION"
    DECISION_NEAR = "DECISION_NEAR"
    POST_CLOSE = "POST_CLOSE"
    EVENING_REVISION = "EVENING_REVISION"
    OUTCOME_PRE_OPEN = "OUTCOME_PRE_OPEN"
    OUTCOME_PATH = "OUTCOME_PATH"
    OUTCOME_10_30 = "OUTCOME_10_30"
    OUTCOME_POST_CLOSE = "OUTCOME_POST_CLOSE"
    REVISION_VERIFICATION = "REVISION_VERIFICATION"


class ProspectiveArchiveTerminalState(StrEnum):
    CAPTURED_ON_TIME = "CAPTURED_ON_TIME"
    CAPTURED_LATE = "CAPTURED_LATE"
    MISSED = "MISSED"
    PROVIDER_GAP = "PROVIDER_GAP"
    RESOURCE_STOP = "RESOURCE_STOP"
    FAILED = "FAILED"


class ProspectiveArchiveDueState(StrEnum):
    NOT_DUE = "NOT_DUE"
    DUE = "DUE"
    OVERDUE = "OVERDUE"

    @classmethod
    def at(
        cls,
        *,
        now: datetime,
        window_start: datetime,
        window_end: datetime,
    ) -> ProspectiveArchiveDueState:
        now = require_utc(now, field="now")
        window_start = require_utc(window_start, field="window_start")
        window_end = require_utc(window_end, field="window_end")
        if window_end < window_start:
            raise ValueError("prospective capture window is invalid")
        if now < window_start:
            return cls.NOT_DUE
        if now <= window_end:
            return cls.DUE
        return cls.OVERDUE


_PLANNING_GAP_REASONS = frozenset(
    {
        "GENERATION_NOT_PREDECLARED",
        "RUNTIME_OUTAGE",
        "CALENDAR_INCOMPLETE",
        "TARGET_CONTRACT_UNAVAILABLE",
    }
)


@dataclass(frozen=True, slots=True)
class ProspectiveArchivePlanningGap:
    prospective_archive_planning_gap_id: UUID
    series_code: str
    expected_generation: int
    predecessor_market_archive_id: UUID | None
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    expected_decision_session_id: UUID
    detected_at: datetime
    reason_code: str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not self.series_code or len(self.series_code) > 100:
            raise ValueError("prospective planning gap series_code is invalid")
        if isinstance(self.expected_generation, bool) or self.expected_generation < 1:
            raise ValueError("prospective planning gap generation is invalid")
        if (self.expected_generation == 1) != (
            self.predecessor_market_archive_id is None
        ):
            raise ValueError("prospective planning gap predecessor is invalid")
        if self.target_version < 1:
            raise ValueError("prospective planning gap Target version is invalid")
        target_hash = ContentHash(str(self.target_definition_sha256))
        detected_at = require_utc(self.detected_at, field="planning gap detected_at")
        if self.reason_code not in _PLANNING_GAP_REASONS:
            raise ValueError("prospective planning gap reason is invalid")
        object.__setattr__(self, "target_definition_sha256", target_hash)
        object.__setattr__(self, "detected_at", detected_at)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "detected_at": detected_at,
                        "expected_decision_session_id": (
                            self.expected_decision_session_id
                        ),
                        "expected_generation": self.expected_generation,
                        "predecessor_market_archive_id": (
                            self.predecessor_market_archive_id
                        ),
                        "prospective_archive_planning_gap_id": (
                            self.prospective_archive_planning_gap_id
                        ),
                        "reason_code": self.reason_code,
                        "series_code": self.series_code,
                        "target_definition_id": self.target_definition_id,
                        "target_definition_sha256": str(target_hash),
                        "target_version": self.target_version,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ProspectiveArchiveSession:
    session_id: UUID
    exchange: str
    session_date: date
    open_at: datetime
    close_at: datetime

    def __post_init__(self) -> None:
        opened = require_utc(self.open_at, field="session open_at")
        closed = require_utc(self.close_at, field="session close_at")
        if not self.exchange or closed <= opened:
            raise ValueError("prospective archive Session is invalid")
        object.__setattr__(self, "open_at", opened)
        object.__setattr__(self, "close_at", closed)


@dataclass(frozen=True, slots=True)
class TargetArchiveCheckpoint:
    target_checkpoint_id: UUID
    ordinal: int
    checkpoint_role: str
    session_offset: int
    local_time: time
    timezone_name: str

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Target checkpoint ordinal must be positive")
        if self.checkpoint_role not in {
            "DECISION_REFERENCE",
            "OUTCOME_OBSERVATION",
        }:
            raise ValueError("Target checkpoint role is invalid")
        if isinstance(self.session_offset, bool) or self.session_offset < 0:
            raise ValueError("Target checkpoint session offset is invalid")
        if self.local_time.tzinfo is not None:
            raise ValueError("Target checkpoint local_time must be timezone-naive")
        try:
            ZoneInfo(self.timezone_name)
        except Exception as exc:  # pragma: no cover - platform zone database error
            raise ValueError("Target checkpoint timezone is invalid") from exc


@dataclass(frozen=True, slots=True)
class TargetArchiveSessions:
    decision: ProspectiveArchiveSession
    outcome: ProspectiveArchiveSession
    later_verification: ProspectiveArchiveSession
    reference_checkpoint: TargetArchiveCheckpoint
    outcome_checkpoint: TargetArchiveCheckpoint
    reference_at: datetime
    outcome_at: datetime


@dataclass(frozen=True, slots=True)
class TargetAlignedCaptureWindow:
    slot: ProspectiveArchiveScheduleSlot
    session_id: UUID
    target_checkpoint_id: UUID
    window_start: datetime
    window_end: datetime
    comparison_ordinal: int

    def __post_init__(self) -> None:
        start = require_utc(self.window_start, field="capture window_start")
        end = require_utc(self.window_end, field="capture window_end")
        if end <= start:
            raise ValueError("Target-aligned capture window is invalid")
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "window_end", end)


@dataclass(frozen=True, slots=True)
class ProspectiveArchiveMemberPlan:
    instrument_id: UUID
    instrument_identifier_id: UUID
    ordinal: int
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("prospective member ordinal must be positive")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "instrument_id": self.instrument_id,
                        "instrument_identifier_id": self.instrument_identifier_id,
                        "ordinal": self.ordinal,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ProspectiveArchiveSliceSchedulePlan:
    market_archive_slice_id: UUID
    instrument_id: UUID
    ordinal: int
    slot: ProspectiveArchiveScheduleSlot
    trading_session_id: UUID
    target_checkpoint_id: UUID
    comparison_ordinal: int
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("prospective schedule ordinal must be positive")
        if isinstance(self.comparison_ordinal, bool) or self.comparison_ordinal < 1:
            raise ValueError("prospective comparison ordinal must be positive")
        if not isinstance(self.slot, ProspectiveArchiveScheduleSlot):
            raise TypeError("prospective schedule slot must be typed")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "instrument_id": self.instrument_id,
                        "market_archive_slice_id": self.market_archive_slice_id,
                        "ordinal": self.ordinal,
                        "slot": self.slot,
                        "target_checkpoint_id": self.target_checkpoint_id,
                        "trading_session_id": self.trading_session_id,
                        "comparison_ordinal": self.comparison_ordinal,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ProspectiveArchiveGenerationPlan:
    market_archive_id: UUID
    series_code: str
    generation: int
    predecessor_market_archive_id: UUID | None
    exchange: str
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    reference_checkpoint_id: UUID
    outcome_checkpoint_id: UUID
    decision_session_id: UUID
    outcome_session_id: UUID
    later_verification_session_id: UUID
    members: tuple[ProspectiveArchiveMemberPlan, ...]
    schedules: tuple[ProspectiveArchiveSliceSchedulePlan, ...]
    provenance_sha256: ContentHash | str
    member_roster_sha256: ContentHash = field(init=False)
    schedule_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not self.series_code or len(self.series_code) > 100:
            raise ValueError("prospective archive series_code is invalid")
        if isinstance(self.generation, bool) or self.generation < 1:
            raise ValueError("prospective archive generation must be positive")
        if (self.generation == 1) != (self.predecessor_market_archive_id is None):
            raise ValueError("prospective archive predecessor chain is invalid")
        if self.target_version < 1:
            raise ValueError("prospective archive Target version must be positive")
        if not self.members or tuple(item.ordinal for item in self.members) != tuple(
            range(1, len(self.members) + 1)
        ):
            raise ValueError("prospective archive member roster must be contiguous")
        if len({item.instrument_id for item in self.members}) != len(self.members):
            raise ValueError("prospective archive member roster contains duplicates")
        if tuple(item.ordinal for item in self.schedules) != tuple(
            range(1, len(self.schedules) + 1)
        ):
            raise ValueError("prospective archive schedule roster must be contiguous")
        member_ids = {item.instrument_id for item in self.members}
        if any(item.instrument_id not in member_ids for item in self.schedules):
            raise ValueError("prospective archive schedule has a foreign member")
        expected_slots = set(ProspectiveArchiveScheduleSlot)
        for member_id in member_ids:
            actual = {
                item.slot for item in self.schedules if item.instrument_id == member_id
            }
            if actual != expected_slots:
                raise ValueError("prospective archive member schedule is incomplete")
        target_hash = ContentHash(str(self.target_definition_sha256))
        provenance_hash = ContentHash(str(self.provenance_sha256))
        member_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item.content_sha256),
                        "ordinal": item.ordinal,
                    }
                    for item in self.members
                )
            )
        )
        schedule_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item.content_sha256),
                        "ordinal": item.ordinal,
                    }
                    for item in self.schedules
                )
            )
        )
        object.__setattr__(self, "target_definition_sha256", target_hash)
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(self, "member_roster_sha256", member_hash)
        object.__setattr__(self, "schedule_roster_sha256", schedule_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "decision_session_id": self.decision_session_id,
                        "exchange": self.exchange,
                        "generation": self.generation,
                        "later_verification_session_id": self.later_verification_session_id,
                        "market_archive_id": self.market_archive_id,
                        "member_roster_sha256": str(member_hash),
                        "outcome_checkpoint_id": self.outcome_checkpoint_id,
                        "outcome_session_id": self.outcome_session_id,
                        "predecessor_market_archive_id": self.predecessor_market_archive_id,
                        "provenance_sha256": str(provenance_hash),
                        "reference_checkpoint_id": self.reference_checkpoint_id,
                        "schedule_roster_sha256": str(schedule_hash),
                        "series_code": self.series_code,
                        "target_definition_id": self.target_definition_id,
                        "target_definition_sha256": str(target_hash),
                        "target_version": self.target_version,
                    }
                )
            ),
        )


def _checkpoint_at(
    session: ProspectiveArchiveSession,
    checkpoint: TargetArchiveCheckpoint,
) -> datetime:
    instant = datetime.combine(
        session.session_date,
        checkpoint.local_time,
        tzinfo=ZoneInfo(checkpoint.timezone_name),
    ).astimezone(session.open_at.tzinfo)
    if not session.open_at <= instant <= session.close_at:
        raise ValueError("Target checkpoint lies outside its authoritative Session")
    return instant


def derive_target_archive_sessions(
    *,
    exchange: str,
    decision_session_id: UUID,
    sessions: tuple[ProspectiveArchiveSession, ...],
    checkpoints: tuple[TargetArchiveCheckpoint, ...],
    later_verification_session_offset: int,
) -> TargetArchiveSessions:
    """Resolve Target offsets only against an exact ordered TradingSession roster."""

    if not sessions or any(item.exchange != exchange for item in sessions):
        raise ValueError("prospective archive session exchange is inconsistent")
    if tuple(item.session_date for item in sessions) != tuple(
        sorted(item.session_date for item in sessions)
    ) or len({item.session_id for item in sessions}) != len(sessions):
        raise ValueError("prospective archive session roster is ambiguous")
    try:
        decision_index = next(
            index
            for index, session in enumerate(sessions)
            if session.session_id == decision_session_id
        )
    except StopIteration as exc:
        raise ValueError("decision Session is absent from authoritative calendar") from exc
    references = tuple(
        item for item in checkpoints if item.checkpoint_role == "DECISION_REFERENCE"
    )
    outcomes = tuple(
        item for item in checkpoints if item.checkpoint_role == "OUTCOME_OBSERVATION"
    )
    if len(references) != 1 or len(outcomes) != 1:
        raise ValueError("Target requires exactly one reference and one archive outcome checkpoint")
    reference = references[0]
    outcome = outcomes[0]
    if reference.session_offset != 0 or outcome.session_offset < 1:
        raise ValueError("Target archive checkpoint offsets are invalid")
    if later_verification_session_offset <= outcome.session_offset:
        raise ValueError("later verification must follow the Target outcome Session")
    required = decision_index + later_verification_session_offset
    if required >= len(sessions):
        raise ValueError("complete authoritative session roster is required")
    decision = sessions[decision_index]
    outcome_session = sessions[decision_index + outcome.session_offset]
    later = sessions[required]
    return TargetArchiveSessions(
        decision=decision,
        outcome=outcome_session,
        later_verification=later,
        reference_checkpoint=reference,
        outcome_checkpoint=outcome,
        reference_at=_checkpoint_at(decision, reference),
        outcome_at=_checkpoint_at(outcome_session, outcome),
    )


def target_aligned_capture_windows(
    resolved: TargetArchiveSessions,
) -> tuple[TargetAlignedCaptureWindow, ...]:
    """Freeze execution windows from exact Target and Session instants only."""

    reference_at = resolved.reference_at
    outcome_at = resolved.outcome_at
    decision_close = resolved.decision.close_at
    outcome_close = resolved.outcome.close_at
    later_close = resolved.later_verification.close_at
    rows = (
        (ProspectiveArchiveScheduleSlot.PRE_DECISION, resolved.decision.session_id,
         resolved.reference_checkpoint.target_checkpoint_id,
         reference_at - timedelta(minutes=15), reference_at - timedelta(minutes=7), 1),
        (ProspectiveArchiveScheduleSlot.DECISION_NEAR, resolved.decision.session_id,
         resolved.reference_checkpoint.target_checkpoint_id,
         reference_at, reference_at + timedelta(minutes=1), 2),
        (ProspectiveArchiveScheduleSlot.POST_CLOSE, resolved.decision.session_id,
         resolved.reference_checkpoint.target_checkpoint_id,
         decision_close + timedelta(minutes=25), decision_close + timedelta(minutes=35), 3),
        (ProspectiveArchiveScheduleSlot.EVENING_REVISION, resolved.decision.session_id,
         resolved.reference_checkpoint.target_checkpoint_id,
         decision_close + timedelta(hours=4, minutes=55),
         decision_close + timedelta(hours=5, minutes=5), 4),
        (ProspectiveArchiveScheduleSlot.OUTCOME_PRE_OPEN, resolved.outcome.session_id,
         resolved.outcome_checkpoint.target_checkpoint_id,
         resolved.outcome.open_at - timedelta(minutes=35),
         resolved.outcome.open_at - timedelta(minutes=25), 1),
        (ProspectiveArchiveScheduleSlot.OUTCOME_PATH, resolved.outcome.session_id,
         resolved.outcome_checkpoint.target_checkpoint_id,
         resolved.outcome.open_at, outcome_at, 2),
        (ProspectiveArchiveScheduleSlot.OUTCOME_10_30, resolved.outcome.session_id,
         resolved.outcome_checkpoint.target_checkpoint_id,
         outcome_at, outcome_at + timedelta(minutes=1), 3),
        (ProspectiveArchiveScheduleSlot.OUTCOME_POST_CLOSE, resolved.outcome.session_id,
         resolved.outcome_checkpoint.target_checkpoint_id,
         outcome_close + timedelta(minutes=25), outcome_close + timedelta(minutes=35), 4),
        (ProspectiveArchiveScheduleSlot.REVISION_VERIFICATION,
         resolved.later_verification.session_id,
         resolved.outcome_checkpoint.target_checkpoint_id,
         later_close + timedelta(minutes=25), later_close + timedelta(minutes=35), 5),
    )
    return tuple(
        TargetAlignedCaptureWindow(
            slot=slot,
            session_id=session_id,
            target_checkpoint_id=checkpoint_id,
            window_start=start,
            window_end=end,
            comparison_ordinal=comparison_ordinal,
        )
        for slot, session_id, checkpoint_id, start, end, comparison_ordinal in rows
    )


__all__ = [
    "ProspectiveArchiveDueState",
    "ProspectiveArchiveScheduleSlot",
    "ProspectiveArchiveGenerationPlan",
    "ProspectiveArchiveMemberPlan",
    "ProspectiveArchivePlanningGap",
    "ProspectiveArchiveSession",
    "ProspectiveArchiveSliceSchedulePlan",
    "ProspectiveArchiveTerminalState",
    "TargetArchiveCheckpoint",
    "TargetAlignedCaptureWindow",
    "TargetArchiveSessions",
    "derive_target_archive_sessions",
    "target_aligned_capture_windows",
]
