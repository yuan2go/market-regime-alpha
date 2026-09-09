"""Historical schedule values and immutable identities consumed by the journal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousDecisionWindowPolicy,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
)


class ContinuousScheduleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class TradingDayAssessment:
    trading_calendar_id: ArtifactId
    trading_calendar_hash: str
    trading_date: date
    is_trading_day: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date):
            raise TypeError("trading_date must be a date")
        require_sha256("trading_calendar_hash", self.trading_calendar_hash)
        if not isinstance(self.is_trading_day, bool):
            raise TypeError("is_trading_day must be bool")
        if not self.reason_codes or self.reason_codes != tuple(
            sorted(set(self.reason_codes))
        ):
            raise ValueError("Trading Day reasons must be non-empty, unique, and sorted")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "trading_calendar_id": str(self.trading_calendar_id),
            "trading_calendar_hash": self.trading_calendar_hash,
            "trading_date": self.trading_date.isoformat(),
            "is_trading_day": self.is_trading_day,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TradingDayAssessment:
        expected = {
            "trading_calendar_id",
            "trading_calendar_hash",
            "trading_date",
            "is_trading_day",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("Trading Day assessment fields mismatch")
        reasons = payload["reason_codes"]
        if not isinstance(reasons, list) or any(
            not isinstance(item, str) for item in reasons
        ):
            raise ValueError("Trading Day reasons must be a string array")
        is_trading_day = payload["is_trading_day"]
        if not isinstance(is_trading_day, bool):
            raise ValueError("is_trading_day must be bool")
        return cls(
            trading_calendar_id=ArtifactId(str(payload["trading_calendar_id"])),
            trading_calendar_hash=str(payload["trading_calendar_hash"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            is_trading_day=is_trading_day,
            reason_codes=tuple(reasons),
        )


@dataclass(frozen=True, slots=True)
class ContinuousScheduleSnapshot:
    schedule_id: ArtifactId
    schedule_hash: str
    run_id: ArtifactId
    status: ContinuousScheduleStatus
    next_tick_at: datetime | None
    last_reserved_tick_id: ArtifactId | None
    last_reserved_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": str(self.schedule_id),
            "schedule_hash": self.schedule_hash,
            "run_id": str(self.run_id),
            "status": self.status.value,
            "next_tick_at": (
                None if self.next_tick_at is None else self.next_tick_at.isoformat()
            ),
            "last_reserved_tick_id": (
                None
                if self.last_reserved_tick_id is None
                else str(self.last_reserved_tick_id)
            ),
            "last_reserved_at": (
                None
                if self.last_reserved_at is None
                else self.last_reserved_at.isoformat()
            ),
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "closed_at": None if self.closed_at is None else self.closed_at.isoformat(),
        }




def schedule_identity(
    *,
    run_command: ContinuousResearchCommand,
    policy: ContinuousDecisionWindowPolicy,
    trading_day: TradingDayAssessment,
) -> tuple[ArtifactId, str]:
    digest = canonical_hash(
        {
            "schema_version": "continuous-runtime-schedule-v1",
            "run_id": str(run_command.run_id),
            "command_hash": run_command.command_hash,
            "policy_id": str(policy.policy_id),
            "policy_hash": policy.content_hash,
            "trading_calendar_id": str(trading_day.trading_calendar_id),
            "trading_calendar_hash": trading_day.trading_calendar_hash,
            "trading_date": run_command.trading_date.isoformat(),
            "is_trading_day": trading_day.is_trading_day,
        }
    )
    return (
        ArtifactId(f"continuous-schedule-{digest.split(':', 1)[1][:24]}"),
        digest,
    )




__all__ = [
    "ContinuousScheduleSnapshot",
    "ContinuousScheduleStatus",
    "TradingDayAssessment",
    "schedule_identity",
]
