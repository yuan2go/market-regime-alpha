"""Content-addressed 14:55 decision-window policy with fail-closed assessment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)


DECISION_TIME_OPERATION_POLICY_SCHEMA = "decision-time-operation-policy-v1"


class DecisionWindowState(str, Enum):
    MISSING_CALENDAR = "MISSING_CALENDAR"
    CALENDAR_CONFLICT = "CALENDAR_CONFLICT"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    NON_STANDARD_SESSION = "NON_STANDARD_SESSION"
    TOO_EARLY = "TOO_EARLY"
    WAITING_FOR_STATIC_INPUTS = "WAITING_FOR_STATIC_INPUTS"
    STATIC_READY = "STATIC_READY"
    WAITING_FOR_DECISION_WINDOW = "WAITING_FOR_DECISION_WINDOW"
    DECISION_WINDOW_RUNNING = "DECISION_WINDOW_RUNNING"
    DATA_BLOCKED = "DATA_BLOCKED"
    DEADLINE_MISSED = "DEADLINE_MISSED"


@dataclass(frozen=True, slots=True)
class DecisionWindowAssessment:
    state: DecisionWindowState
    decision_date: date
    observed_at: datetime
    decision_at: datetime | None
    hard_cutoff_at: datetime | None
    accepts_signal_evidence: bool
    late_run: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DecisionTimeOperationPolicy:
    schema_version: str
    policy_id: ArtifactId
    content_hash: str
    policy_version: str
    timezone_name: str
    decision_time: time
    static_ready_deadline: time
    minute_fetch_start: time
    hard_cutoff: time
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != DECISION_TIME_OPERATION_POLICY_SCHEMA:
            raise ValueError("unsupported DecisionTime operation policy schema")
        require_sha256("content_hash", self.content_hash)
        require_text("policy_version", self.policy_version)
        ZoneInfo(self.timezone_name)
        for label, value in (
            ("decision_time", self.decision_time),
            ("static_ready_deadline", self.static_ready_deadline),
            ("minute_fetch_start", self.minute_fetch_start),
            ("hard_cutoff", self.hard_cutoff),
        ):
            if not isinstance(value, time) or value.tzinfo is not None or value.microsecond:
                raise ValueError(f"{label} must be a naive whole-second wall time")
        if not (
            self.static_ready_deadline
            <= self.minute_fetch_start
            <= self.decision_time
            < self.hard_cutoff
        ):
            raise ValueError("DecisionTime operation deadlines are not monotonic")
        require_unique_text("policy limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("policy limitations must be sorted")
        for required in (
            "FORMAL_PIT_NOT_ESTABLISHED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ):
            if required not in self.limitations:
                raise ValueError("DecisionTime policy authority ceiling is incomplete")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        timezone_name: str,
        decision_time: time,
        static_ready_deadline: time,
        minute_fetch_start: time,
        hard_cutoff: time,
        limitations: tuple[str, ...],
    ) -> DecisionTimeOperationPolicy:
        limitations = tuple(sorted(limitations))
        semantic = _policy_payload(
            policy_version=policy_version,
            timezone_name=timezone_name,
            decision_time=decision_time,
            static_ready_deadline=static_ready_deadline,
            minute_fetch_start=minute_fetch_start,
            hard_cutoff=hard_cutoff,
            limitations=limitations,
        )
        digest = canonical_hash(semantic)
        result = cls(
            schema_version=DECISION_TIME_OPERATION_POLICY_SCHEMA,
            policy_id=ArtifactId(f"decision-time-policy-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            policy_version=policy_version,
            timezone_name=timezone_name,
            decision_time=decision_time,
            static_ready_deadline=static_ready_deadline,
            minute_fetch_start=minute_fetch_start,
            hard_cutoff=hard_cutoff,
            limitations=limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _policy_payload(
            policy_version=self.policy_version,
            timezone_name=self.timezone_name,
            decision_time=self.decision_time,
            static_ready_deadline=self.static_ready_deadline,
            minute_fetch_start=self.minute_fetch_start,
            hard_cutoff=self.hard_cutoff,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("DecisionTime operation policy hash mismatch")
        if str(self.policy_id) != f"decision-time-policy-{digest.split(':', 1)[1][:24]}":
            raise ValueError("DecisionTime operation policy identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> DecisionTimeOperationPolicy:
        expected = {
            "schema_version",
            "policy_id",
            "content_hash",
            "policy_version",
            "timezone_name",
            "decision_time",
            "static_ready_deadline",
            "minute_fetch_start",
            "hard_cutoff",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("DecisionTime operation policy fields mismatch")
        raw_limitations = payload["limitations"]
        if not isinstance(raw_limitations, list) or any(
            not isinstance(item, str) for item in raw_limitations
        ):
            raise ValueError("DecisionTime operation limitations must be strings")
        result = cls(
            schema_version=str(payload["schema_version"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            content_hash=str(payload["content_hash"]),
            policy_version=str(payload["policy_version"]),
            timezone_name=str(payload["timezone_name"]),
            decision_time=time.fromisoformat(str(payload["decision_time"])),
            static_ready_deadline=time.fromisoformat(
                str(payload["static_ready_deadline"])
            ),
            minute_fetch_start=time.fromisoformat(str(payload["minute_fetch_start"])),
            hard_cutoff=time.fromisoformat(str(payload["hard_cutoff"])),
            limitations=tuple(raw_limitations),
        )
        result.verify_identity()
        return result

    def assess(
        self,
        *,
        observed_at: datetime,
        decision_date: date,
        calendar: TradingCalendarArtifact | None,
        expected_calendar_hash: str | None,
        static_inputs_ready: bool,
    ) -> DecisionWindowAssessment:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if expected_calendar_hash is not None:
            require_sha256("expected_calendar_hash", expected_calendar_hash)
        if calendar is None:
            return self._assessment(
                DecisionWindowState.MISSING_CALENDAR,
                decision_date,
                observed_at,
                ("TRADING_CALENDAR_MISSING",),
            )
        if expected_calendar_hash is not None and calendar.content_hash != expected_calendar_hash:
            return self._assessment(
                DecisionWindowState.CALENDAR_CONFLICT,
                decision_date,
                observed_at,
                ("TRADING_CALENDAR_HASH_CONFLICT",),
            )
        if not calendar.contains(decision_date):
            return self._assessment(
                DecisionWindowState.NON_TRADING_DAY,
                decision_date,
                observed_at,
                ("DECISION_DATE_NOT_IN_EXPLICIT_TRADING_CALENDAR",),
            )
        zone = ZoneInfo(self.timezone_name)
        session = next(item for item in calendar.sessions if item.trade_date == decision_date)
        if session.session_close.astimezone(zone).time().replace(tzinfo=None) < self.hard_cutoff:
            return self._assessment(
                DecisionWindowState.NON_STANDARD_SESSION,
                decision_date,
                observed_at,
                ("EARLY_CLOSE_POLICY_NOT_DECLARED",),
            )
        local = observed_at.astimezone(zone)
        local_time = local.time().replace(tzinfo=None)
        if local.date() != decision_date:
            return self._assessment(
                DecisionWindowState.DEADLINE_MISSED,
                decision_date,
                observed_at,
                ("OBSERVATION_OUTSIDE_DECISION_DATE",),
            )
        if not static_inputs_ready:
            state = (
                DecisionWindowState.WAITING_FOR_STATIC_INPUTS
                if local_time < self.static_ready_deadline
                else DecisionWindowState.DATA_BLOCKED
            )
            reason = (
                "STATIC_INPUTS_NOT_READY"
                if state is DecisionWindowState.WAITING_FOR_STATIC_INPUTS
                else "STATIC_READY_DEADLINE_MISSED"
            )
            return self._assessment(state, decision_date, observed_at, (reason,))
        if local_time < self.minute_fetch_start:
            state = (
                DecisionWindowState.TOO_EARLY
                if local_time < self.static_ready_deadline
                else DecisionWindowState.WAITING_FOR_DECISION_WINDOW
            )
            return self._assessment(
                state,
                decision_date,
                observed_at,
                ("DECISION_WINDOW_NOT_OPEN",),
            )
        if local_time > self.hard_cutoff:
            return self._assessment(
                DecisionWindowState.DEADLINE_MISSED,
                decision_date,
                observed_at,
                ("HARD_CUTOFF_EXCEEDED",),
            )
        return self._assessment(
            DecisionWindowState.DECISION_WINDOW_RUNNING,
            decision_date,
            observed_at,
            ("CONTROLLED_DECISION_WINDOW_OPEN",),
        )

    def accepts_evidence(
        self, *, decision_date: date, available_at: datetime
    ) -> bool:
        if available_at.tzinfo is None or available_at.utcoffset() is None:
            raise ValueError("available_at must be timezone-aware")
        return available_at <= self._instant(decision_date, self.decision_time)

    def _assessment(
        self,
        state: DecisionWindowState,
        decision_date: date,
        observed_at: datetime,
        reasons: tuple[str, ...],
    ) -> DecisionWindowAssessment:
        decision_at = self._instant(decision_date, self.decision_time)
        cutoff = self._instant(decision_date, self.hard_cutoff)
        return DecisionWindowAssessment(
            state=state,
            decision_date=decision_date,
            observed_at=observed_at,
            decision_at=decision_at,
            hard_cutoff_at=cutoff,
            accepts_signal_evidence=(
                state is DecisionWindowState.DECISION_WINDOW_RUNNING
                and observed_at <= decision_at
            ),
            late_run=observed_at > decision_at,
            reason_codes=reasons,
        )

    def _instant(self, decision_date: date, value: time) -> datetime:
        return datetime.combine(
            decision_date,
            value,
            tzinfo=ZoneInfo(self.timezone_name),
        )


def default_decision_time_operation_policy() -> DecisionTimeOperationPolicy:
    return DecisionTimeOperationPolicy.create(
        policy_version="controlled-a-share-1455-v1",
        timezone_name="Asia/Shanghai",
        decision_time=time(14, 55),
        static_ready_deadline=time(14, 50),
        minute_fetch_start=time(14, 54),
        hard_cutoff=time(14, 56),
        limitations=(
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_EARLY_CLOSE_INFERENCE",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
    )


def _policy_payload(
    *,
    policy_version: str,
    timezone_name: str,
    decision_time: time,
    static_ready_deadline: time,
    minute_fetch_start: time,
    hard_cutoff: time,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": DECISION_TIME_OPERATION_POLICY_SCHEMA,
        "policy_version": policy_version,
        "timezone_name": timezone_name,
        "decision_time": decision_time.isoformat(),
        "static_ready_deadline": static_ready_deadline.isoformat(),
        "minute_fetch_start": minute_fetch_start.isoformat(),
        "hard_cutoff": hard_cutoff.isoformat(),
        "limitations": list(limitations),
    }


__all__ = [
    "DECISION_TIME_OPERATION_POLICY_SCHEMA",
    "DecisionTimeOperationPolicy",
    "DecisionWindowAssessment",
    "DecisionWindowState",
    "default_decision_time_operation_policy",
]
