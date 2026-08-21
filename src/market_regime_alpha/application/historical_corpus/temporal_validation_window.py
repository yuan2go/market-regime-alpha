"""Calendar-owned frozen temporal validation window."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


TEMPORAL_VALIDATION_V1: Final[str] = "TEMPORAL_VALIDATION_V1"


@dataclass(frozen=True, slots=True)
class FrozenTemporalValidationWindow:
    window_id: ArtifactId
    window_hash: str
    protocol_id: str
    start_decision_session: date
    session_count: int
    decision_sessions: tuple[date, ...]
    final_target_session: date
    calendar_reference: ValidationArtifactReference
    decision_session_hash: str
    schema_version: str = "frozen-temporal-validation-window/v1"

    def __post_init__(self) -> None:
        require_sha256("window_hash", self.window_hash)
        require_sha256("decision_session_hash", self.decision_session_hash)
        if self.protocol_id != TEMPORAL_VALIDATION_V1:
            raise ValueError("unsupported Temporal Validation protocol")
        if self.calendar_reference.artifact_kind != "TRADING_CALENDAR":
            raise ValueError("Temporal Validation requires Trading Calendar owner")
        if self.session_count != 126 or len(self.decision_sessions) != self.session_count:
            raise ValueError("TEMPORAL_VALIDATION_V1 requires exactly 126 sessions")
        if (
            not self.decision_sessions
            or self.decision_sessions[0] != self.start_decision_session
            or self.decision_sessions != tuple(sorted(set(self.decision_sessions)))
        ):
            raise ValueError("Temporal Validation Decision sessions are invalid")
        if self.final_target_session <= self.decision_sessions[-1]:
            raise ValueError("final Target session must follow the final Decision session")
        expected_session_hash = canonical_hash(
            {"decision_sessions": [item.isoformat() for item in self.decision_sessions]}
        )
        if expected_session_hash != self.decision_session_hash:
            raise ValueError("Temporal Validation session identity hash mismatch")
        digest = canonical_hash(self.identity_payload())
        if digest != self.window_hash or self.window_id != ArtifactId(
            f"frozen-temporal-validation-window:{digest[7:]}"
        ):
            raise ValueError("Temporal Validation window identity mismatch")

    @property
    def last_decision_session(self) -> date:
        return self.decision_sessions[-1]

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "FROZEN_TEMPORAL_VALIDATION_WINDOW",
            self.window_id,
            self.window_hash,
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "start_decision_session": self.start_decision_session.isoformat(),
            "session_count": self.session_count,
            "decision_sessions": [item.isoformat() for item in self.decision_sessions],
            "final_target_session": self.final_target_session.isoformat(),
            "calendar_reference": self.calendar_reference.to_canonical_dict(),
            "decision_session_hash": self.decision_session_hash,
        }

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "window_id": str(self.window_id),
            "window_hash": self.window_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> FrozenTemporalValidationWindow:
        expected = {
            "window_id",
            "window_hash",
            "schema_version",
            "protocol_id",
            "start_decision_session",
            "session_count",
            "decision_sessions",
            "final_target_session",
            "calendar_reference",
            "decision_session_hash",
        }
        if set(payload) != expected:
            raise ValueError("Frozen Temporal Validation window fields mismatch")
        raw_sessions = payload["decision_sessions"]
        raw_calendar = payload["calendar_reference"]
        if not isinstance(raw_sessions, list) or not isinstance(raw_calendar, Mapping):
            raise ValueError("Frozen Temporal Validation owner payload is malformed")
        return cls(
            window_id=ArtifactId(str(payload["window_id"])),
            window_hash=str(payload["window_hash"]),
            protocol_id=str(payload["protocol_id"]),
            start_decision_session=date.fromisoformat(
                str(payload["start_decision_session"])
            ),
            session_count=int(payload["session_count"]),
            decision_sessions=tuple(
                date.fromisoformat(str(item)) for item in raw_sessions
            ),
            final_target_session=date.fromisoformat(
                str(payload["final_target_session"])
            ),
            calendar_reference=ValidationArtifactReference(
                artifact_kind=str(raw_calendar["artifact_kind"]),
                artifact_id=ArtifactId(str(raw_calendar["artifact_id"])),
                content_hash=str(raw_calendar["content_hash"]),
            ),
            decision_session_hash=str(payload["decision_session_hash"]),
            schema_version=str(payload["schema_version"]),
        )


def freeze_temporal_validation_window(
    *,
    calendar: TradingCalendarArtifact,
    start_decision_session: date,
    session_count: int,
) -> FrozenTemporalValidationWindow:
    """Slice explicit owner sessions; never infer or accept an ending date."""

    if calendar.market not in {"A_SHARE", "CN_A_SHARE"}:
        raise ValueError("Temporal Validation requires canonical A-share Calendar")
    if calendar.timezone_name != "Asia/Shanghai":
        raise ValueError("Temporal Validation Calendar timezone is not canonical")
    if session_count != 126:
        raise ValueError("TEMPORAL_VALIDATION_V1 session_count is frozen at 126")
    try:
        start_index = calendar.trading_dates.index(start_decision_session)
    except ValueError as exc:
        raise ValueError(
            "start Decision session is not an explicit session in the Calendar owner"
        ) from exc
    target_index = start_index + session_count
    if target_index >= len(calendar.sessions):
        raise ValueError(
            "Calendar owner cannot resolve the final T+1 Target session"
        )
    decision_sessions = calendar.trading_dates[start_index:target_index]
    final_target_session = calendar.trading_dates[target_index]
    session_hash = canonical_hash(
        {"decision_sessions": [item.isoformat() for item in decision_sessions]}
    )
    calendar_reference = ValidationArtifactReference(
        "TRADING_CALENDAR",
        calendar.artifact_id,
        calendar.content_hash,
    )
    values: dict[str, object] = {
        "schema_version": "frozen-temporal-validation-window/v1",
        "protocol_id": TEMPORAL_VALIDATION_V1,
        "start_decision_session": start_decision_session.isoformat(),
        "session_count": session_count,
        "decision_sessions": [item.isoformat() for item in decision_sessions],
        "final_target_session": final_target_session.isoformat(),
        "calendar_reference": calendar_reference.to_canonical_dict(),
        "decision_session_hash": session_hash,
    }
    digest = canonical_hash(values)
    return FrozenTemporalValidationWindow(
        window_id=ArtifactId(f"frozen-temporal-validation-window:{digest[7:]}"),
        window_hash=digest,
        protocol_id=TEMPORAL_VALIDATION_V1,
        start_decision_session=start_decision_session,
        session_count=session_count,
        decision_sessions=decision_sessions,
        final_target_session=final_target_session,
        calendar_reference=calendar_reference,
        decision_session_hash=session_hash,
    )


__all__ = [
    "FrozenTemporalValidationWindow",
    "TEMPORAL_VALIDATION_V1",
    "freeze_temporal_validation_window",
]
